import json, os, asyncio
from fastapi import FastAPI, HTTPException
from database import SessionLocal, engine
from models import Base, Project, CommitSync, ScrapeLog, RepoDetail
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import base64
import httpx

app = FastAPI()

# Create database tables
Base.metadata.create_all(bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic model for the request body
class ProjectCreate(BaseModel):
    name: str


class CommitSyncCreate(BaseModel):
    project_name: str
    total_commits: int


class CommitSyncResponse(BaseModel):
    id: int
    project_name: str
    total_commits: int
    synced_at: datetime

    class Config:
        from_attributes = True


@app.post("/projects/")
def create_project(project: ProjectCreate):
    print("NAME IN PROJECT", project)
    db = SessionLocal()
    db_project = Project(name=project.name)
    db.add(db_project)
    db.commit()
    db.refresh(db_project)
    return db_project

@app.get("/projects/{project_id}")
def read_project(project_id: int):
    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.post("/commits/")
def upsert_commit(commit: CommitSyncCreate):
    db = SessionLocal()
    existing = db.query(CommitSync).filter(CommitSync.project_name == commit.project_name).first()
    if existing:
        existing.total_commits = commit.total_commits
        existing.synced_at = datetime.utcnow()
    else:
        existing = CommitSync(project_name=commit.project_name, total_commits=commit.total_commits)
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return existing


@app.post("/commits/batch")
def upsert_commits(commits: List[CommitSyncCreate]):
    db = SessionLocal()
    results = []
    for commit in commits:
        existing = db.query(CommitSync).filter(CommitSync.project_name == commit.project_name).first()
        if existing:
            existing.total_commits = commit.total_commits
            existing.synced_at = datetime.utcnow()
        else:
            existing = CommitSync(project_name=commit.project_name, total_commits=commit.total_commits)
            db.add(existing)
        results.append(existing)
    db.commit()
    for r in results:
        db.refresh(r)
    return results


@app.get("/commits/", response_model=List[CommitSyncResponse])
def list_commits():
    db = SessionLocal()
    return db.query(CommitSync).all()


@app.get("/scrape/logs")
def get_scrape_logs():
    db = SessionLocal()
    logs = db.query(ScrapeLog).order_by(ScrapeLog.id.desc()).limit(20).all()
    return [
        {
            "id": log.id,
            "scraped_at": log.scraped_at.isoformat() if log.scraped_at else "",
            "total_repos": log.total_repos,
            "projects_updated": log.projects_updated,
            "projects_added": log.projects_added,
            "details": log.details,
        }
        for log in logs
    ]


@app.get("/commits/{project_name}", response_model=CommitSyncResponse)
def get_commit(project_name: str):
    db = SessionLocal()
    commit = db.query(CommitSync).filter(CommitSync.project_name == project_name).first()
    if commit is None:
        raise HTTPException(status_code=404, detail="Commit data not found")
    return commit


GITHUB_USER = "kapit4n"
GITHUB_API = "https://api.github.com"
SCRAPE_LIMIT = 20
ARCHITECTURE_PATHS = ["ARCHITECTURE.md", "docs/ARCHITECTURE.md", "docs/architecture.md", "ARCHITECTURE", "docs/architecture"]
DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "l-projects", "public", "data", "projects-all.json"))


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
IMAGE_DIRS = ["screenshots", "mockups", "assets", "images", "img", "screens", "previews"]
IMAGE_NAMES = ["main", "dashboard", "home", "screenshot", "preview", "app", "ui", "interface"]

BACKEND_KEYWORDS = {"api", "cli", "backend", "server", "service", "graphql", "rest", "microservice"}
BACKEND_LANGUAGES = {"python", "go", "java", "ruby", "php", "rust", "c#", "csharp", "c++", "cpp", "swift", "kotlin"}
UI_LANGUAGES = {"typescript", "javascript", "dart", "html", "css", "scss", "sass"}


async def discover_repo_image(client, project_name, headers):
    branches_to_try = ["main", "master"]

    for branch in branches_to_try:
        try:
            root_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}/git/trees/{branch}?recursive=1",
                headers=headers,
            )
            if root_resp.status_code != 200:
                continue

            tree = root_resp.json().get("tree", [])
            candidates = []

            for entry in tree:
                if entry["type"] != "blob":
                    continue
                path = entry["path"]
                name_lower = entry["path"].split("/")[-1].rsplit(".", 1)[0].lower()
                ext = "." + entry["path"].rsplit(".", 1)[-1].lower() if "." in entry["path"] else ""

                if ext not in IMAGE_EXTENSIONS:
                    continue

                if name_lower in IMAGE_NAMES:
                    candidates.append((0, path))
                elif any(d in path.lower() for d in IMAGE_DIRS):
                    candidates.append((1, path))
                else:
                    candidates.append((2, path))

            if candidates:
                candidates.sort(key=lambda x: (x[0], len(x[1])))
                best = candidates[0][1]
                return f"https://raw.githubusercontent.com/{GITHUB_USER}/{project_name}/{branch}/{best}"
        except Exception:
            continue

    return ""


async def fetch_repo_details_from_github(project_name: str):
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "l-projects"}
    result = {"top_commits": "", "readme": "", "architecture": "", "img": "", "is_backend": True}

    async with httpx.AsyncClient() as client:
        try:
            commits_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}/commits?per_page=5",
                headers=headers,
            )
            if commits_resp.status_code == 200:
                result["top_commits"] = json.dumps(commits_resp.json())
        except Exception:
            pass

        try:
            repo_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}",
                headers=headers,
            )
            if repo_resp.status_code == 200:
                repo_data = repo_resp.json()
                topics = repo_data.get("topics", [])
                language = (repo_data.get("language") or "").lower()
                description = (repo_data.get("description") or "").lower()

                topic_set = {t.lower() for t in topics}
                has_backend_keyword = bool(topic_set & BACKEND_KEYWORDS or language in BACKEND_LANGUAGES)
                has_ui_keyword = bool(topic_set & {"angular", "react", "vue", "mobile", "ios", "android", "ui", "frontend", "flutter"} or language in UI_LANGUAGES)
                result["is_backend"] = has_backend_keyword or not has_ui_keyword

                result["img"] = await discover_repo_image(client, project_name, headers)
        except Exception:
            pass

        try:
            readme_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}/readme",
                headers=headers,
            )
            if readme_resp.status_code == 200:
                data = readme_resp.json()
                if data.get("content"):
                    result["readme"] = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
        except Exception:
            pass

        for path in ARCHITECTURE_PATHS:
            try:
                arch_resp = await client.get(
                    f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}/contents/{path}",
                    headers=headers,
                )
                if arch_resp.status_code == 200:
                    data = arch_resp.json()
                    if data.get("content"):
                        result["architecture"] = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
                        break
            except Exception:
                pass

        if not result["architecture"] and result["readme"]:
            import re
            match = re.search(r"##?\s*(Architecture|System Design|Technical Architecture|Architecture Overview)", result["readme"])
            if match:
                result["architecture"] = result["readme"]

    return result


@app.get("/repo-details/{project_name}")
def get_repo_details(project_name: str):
    db = SessionLocal()
    detail = db.query(RepoDetail).filter(RepoDetail.project_name == project_name).first()
    if detail is None:
        raise HTTPException(status_code=404, detail="Repo details not found. POST to /repo-details/{project_name}/fetch to fetch them.")
    return {
        "project_name": detail.project_name,
        "top_commits": detail.top_commits,
        "readme": detail.readme,
        "architecture": detail.architecture,
        "img": detail.img,
        "is_backend": detail.is_backend,
        "fetched_at": detail.fetched_at.isoformat() if detail.fetched_at else "",
    }


@app.post("/repo-details/{project_name}/fetch")
async def fetch_repo_details(project_name: str):
    data = await fetch_repo_details_from_github(project_name)
    db = SessionLocal()
    existing = db.query(RepoDetail).filter(RepoDetail.project_name == project_name).first()
    if existing:
        existing.top_commits = data["top_commits"]
        existing.readme = data["readme"]
        existing.architecture = data["architecture"]
        existing.img = data["img"]
        existing.is_backend = data["is_backend"]
        existing.fetched_at = datetime.utcnow()
    else:
        existing = RepoDetail(
            project_name=project_name,
            top_commits=data["top_commits"],
            readme=data["readme"],
            architecture=data["architecture"],
            img=data["img"],
            is_backend=data["is_backend"],
            fetched_at=datetime.utcnow(),
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)
    return {
        "project_name": existing.project_name,
        "top_commits": existing.top_commits,
        "readme": existing.readme,
        "architecture": existing.architecture,
        "img": existing.img,
        "is_backend": existing.is_backend,
        "fetched_at": existing.fetched_at.isoformat() if existing.fetched_at else "",
    }


@app.get("/scrape")
async def scrape_github():
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "l-projects"}

    async with httpx.AsyncClient() as client:
        repos_resp = await client.get(
            f"{GITHUB_API}/users/{GITHUB_USER}/repos?per_page=100&sort=updated&direction=desc",
            headers=headers,
        )
        repos_resp.raise_for_status()
        repos = repos_resp.json()
        top20 = repos[:SCRAPE_LIMIT]

        entries = []
        for repo in top20:
            name = repo["name"]
            print(f"  Processing {name}...")

            lang_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{name}/languages", headers=headers
            )
            languages = lang_resp.json() if lang_resp.status_code == 200 else {}

            contrib_resp = await client.get(
                f"{GITHUB_API}/repos/{GITHUB_USER}/{name}/contributors", headers=headers
            )
            contributions = 0
            if contrib_resp.status_code == 200:
                contrib_data = contrib_resp.json()
                if isinstance(contrib_data, list) and len(contrib_data) > 0:
                    contributions = contrib_data[0].get("contributions", 0)

            language_keys = list(languages.keys())
            topics = repo.get("topics", [])

            entries.append({
                "id": repo["id"],
                "startDate": repo.get("created_at", ""),
                "updatedDate": repo.get("pushed_at") or repo.get("updated_at", ""),
                "name": name,
                "dir": repo.get("html_url", ""),
                "img": repo.get("homepage") or "",
                "features": [],
                "categories": [topics[0]] if topics else [],
                "skills": topics,
                "contributions": contributions,
                "description": repo.get("description") or "",
                "languageKeys": language_keys,
                "language": language_keys[0] if language_keys else (repo.get("language") or ""),
                "size": repo.get("size", 0),
                "openIssues": repo.get("open_issues_count", 0),
                "languages": languages,
            })

    entries.sort(key=lambda e: e["updatedDate"], reverse=True)

    existing = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE) as f:
            existing = json.load(f)

    existing_map = {}
    for p in existing:
        key = p["name"]
        if key not in existing_map or p["id"] < existing_map[key]["id"]:
            existing_map[key] = p

    projects_updated = 0
    projects_added = 0
    details = []

    merged = []
    for entry in entries:
        if entry["name"] in existing_map:
            old = existing_map[entry["name"]]
            old.update(entry)
            merged.append(old)
            del existing_map[entry["name"]]
            projects_updated += 1
            details.append(f"Updated: {entry['name']}")
        else:
            max_id = max((p["id"] for p in merged), default=0)
            entry["id"] = max_id + 1
            merged.append(entry)
            projects_added += 1
            details.append(f"Added: {entry['name']}")

    for p in existing_map.values():
        merged.append(p)

    with open(DATA_FILE, "w") as f:
        json.dump(merged, f, indent=2)

    db = SessionLocal()
    log = ScrapeLog(
        total_repos=len(entries),
        projects_updated=projects_updated,
        projects_added=projects_added,
        details="\n".join(details),
    )
    db.add(log)
    db.commit()

    return {
        "message": f"Scraped {len(entries)} projects from {GITHUB_USER}",
        "count": len(entries),
        "total": len(merged),
        "updated": projects_updated,
        "added": projects_added,
        "details": details,
    }
