import json, os, asyncio, re
from fastapi import FastAPI, HTTPException
from database import SessionLocal, engine
from models import Base, Project, CommitSync, ScrapeLog, RepoDetail
from pydantic import BaseModel
from typing import List, Optional, Any
from datetime import datetime
import base64
import httpx
from sqlalchemy import inspect, text

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

def github_headers():
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "l-projects"}
    if GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    return headers

app = FastAPI()

# Migrate old projects table if needed (add missing columns)
inspector = inspect(engine)
columns = [c["name"] for c in inspector.get_columns("projects")] if "projects" in inspector.get_table_names() else []
if "startDate" not in columns or "archived" not in columns:
    Project.__table__.drop(engine, checkfirst=True)
Base.metadata.create_all(bind=engine)

# Migrate repo_details table if needed (add features_data column)
rd_cols = {c["name"] for c in inspector.get_columns("repo_details")} if "repo_details" in inspector.get_table_names() else set()
if "features_data" not in rd_cols:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE repo_details ADD COLUMN features_data TEXT DEFAULT '[]'"))
        conn.commit()
if "documents" not in rd_cols:
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE repo_details ADD COLUMN documents TEXT DEFAULT '[]'"))
        conn.commit()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models
class ProjectCreate(BaseModel):
    name: str


class ProjectData(BaseModel):
    id: int = 0
    name: str = ""
    startDate: str = ""
    updatedDate: str = ""
    dir: str = ""
    img: str = ""
    features: Any = []
    categories: Any = []
    skills: Any = []
    contributions: int = 0
    description: str = ""
    languageKeys: Any = []
    language: str = ""
    size: int = 0
    openIssues: int = 0
    languages: Any = {}


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


def project_to_dict(p):
    return {
        "id": p.id,
        "name": p.name,
        "archived": p.archived or False,
        "startDate": p.startDate or "",
        "updatedDate": p.updatedDate or "",
        "dir": p.dir or "",
        "img": p.img or "",
        "features": json.loads(p.features) if isinstance(p.features, str) else (p.features or []),
        "categories": json.loads(p.categories) if isinstance(p.categories, str) else (p.categories or []),
        "skills": json.loads(p.skills) if isinstance(p.skills, str) else (p.skills or []),
        "contributions": p.contributions or 0,
        "description": p.description or "",
        "languageKeys": json.loads(p.languageKeys) if isinstance(p.languageKeys, str) else (p.languageKeys or []),
        "language": p.language or "",
        "size": p.size or 0,
        "openIssues": p.openIssues or 0,
        "languages": json.loads(p.languages) if isinstance(p.languages, str) else (p.languages or {}),
    }


def upsert_project(db, data: ProjectData):
    existing = db.query(Project).filter(Project.name == data.name).first()
    if existing:
        existing.startDate = data.startDate
        existing.updatedDate = data.updatedDate
        existing.dir = data.dir
        if data.img:
            existing.img = data.img
        existing.features = json.dumps(data.features)
        existing.categories = json.dumps(data.categories)
        existing.skills = json.dumps(data.skills)
        existing.contributions = data.contributions
        existing.description = data.description
        existing.languageKeys = json.dumps(data.languageKeys)
        existing.language = data.language
        existing.size = data.size
        existing.openIssues = data.openIssues
        existing.languages = json.dumps(data.languages)
        db.commit()
        db.refresh(existing)
        return existing, "updated"
    else:
        p = Project(
            name=data.name,
            startDate=data.startDate,
            updatedDate=data.updatedDate,
            dir=data.dir,
            img=data.img,
            features=json.dumps(data.features),
            categories=json.dumps(data.categories),
            skills=json.dumps(data.skills),
            contributions=data.contributions,
            description=data.description,
            languageKeys=json.dumps(data.languageKeys),
            language=data.language,
            size=data.size,
            openIssues=data.openIssues,
            languages=json.dumps(data.languages),
        )
        db.add(p)
        db.commit()
        db.refresh(p)
        return p, "created"


@app.post("/projects/")
def create_or_update_project(project: ProjectData):
    db = SessionLocal()
    p, action = upsert_project(db, project)
    return {"action": action, "project": project_to_dict(p)}


@app.post("/projects/batch")
def upsert_projects(projects: List[ProjectData]):
    db = SessionLocal()
    results = []
    for data in projects:
        p, action = upsert_project(db, data)
        results.append({"action": action, "project": project_to_dict(p)})
    return results


@app.get("/projects/")
def list_projects():
    db = SessionLocal()
    projects = db.query(Project).all()
    details_map = {d.project_name: d.img for d in db.query(RepoDetail).all() if d.img}
    result = []
    for p in projects:
        d = project_to_dict(p)
        if not d["img"] and p.name in details_map:
            d["img"] = details_map[p.name]
        result.append(d)
    return result


@app.get("/projects/{project_id}")
def read_project(project_id: int):
    db = SessionLocal()
    project = db.query(Project).filter(Project.id == project_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    return project_to_dict(project)


@app.put("/projects/{project_name}/archive")
def archive_project(project_name: str):
    db = SessionLocal()
    project = db.query(Project).filter(Project.name == project_name).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.archived = True
    db.commit()
    return {"action": "archived", "project": project_to_dict(project)}


@app.put("/projects/{project_name}/unarchive")
def unarchive_project(project_name: str):
    db = SessionLocal()
    project = db.query(Project).filter(Project.name == project_name).first()
    if project is None:
        raise HTTPException(status_code=404, detail="Project not found")
    project.archived = False
    db.commit()
    return {"action": "unarchived", "project": project_to_dict(project)}


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


@app.get("/repo-details/{project_name}/docs")
def get_project_docs(project_name: str):
    db = SessionLocal()
    detail = db.query(RepoDetail).filter(RepoDetail.project_name == project_name).first()
    if detail is None:
        raise HTTPException(status_code=404, detail="Repo details not found.")
    docs = json.loads(detail.documents) if isinstance(detail.documents, str) else (detail.documents or [])
    return {"project_name": project_name, "documents": docs}


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


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
IMAGE_DIRS = ["screenshots", "mockups", "mockup", "assets", "images", "img", "screens", "previews", "features"]
IMAGE_NAMES = ["main", "dashboard", "home", "screenshot", "preview", "app", "ui", "interface",
               "dashboard-main", "home-page", "main-page", "overview", "landing"]
PRIORITY_NAMES = {"dashboard", "main", "home", "dashboard-main", "home-page", "main-page", "overview", "landing"}

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

                in_img_dir = any(d in path.lower() for d in IMAGE_DIRS)
                is_named = name_lower in IMAGE_NAMES
                is_priority_name = name_lower in PRIORITY_NAMES

                if is_priority_name and in_img_dir:
                    candidates.append((0, path))
                elif is_priority_name:
                    candidates.append((1, path))
                elif is_named and in_img_dir:
                    candidates.append((2, path))
                elif in_img_dir:
                    candidates.append((3, path))
                elif is_named:
                    candidates.append((4, path))
                else:
                    candidates.append((5, path))

            if candidates:
                candidates.sort(key=lambda x: (x[0], len(x[1])))
                best = candidates[0][1]
                return f"https://raw.githubusercontent.com/{GITHUB_USER}/{project_name}/{branch}/{best}"
        except Exception:
            continue

    return ""


FEATURES_DIRS = ["mockups/features", "mockup/features"]
FEATURE_IMAGE_EXTS = ("png", "jpg", "jpeg", "gif", "webp", "svg")


def _strip_numeric_suffix(name):
    return re.sub(r'-\d+$', '', name)


async def discover_features(client, project_name, headers):
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
            images = {}
            descriptions = {}

            for entry in tree:
                if entry["type"] != "blob":
                    continue
                path = entry["path"]
                parts = path.rsplit("/", 1)
                if len(parts) != 2:
                    continue
                parent_dir, filename = parts

                parent_lower = parent_dir.lower()
                matched_dir = None
                for d in FEATURES_DIRS:
                    if parent_lower == d:
                        matched_dir = d
                        group_name = ""
                        break
                    if parent_lower.startswith(d + "/"):
                        matched_dir = d
                        group_name = parent_dir[len(d) + 1:]
                        break
                if matched_dir is None:
                    continue

                name_parts = filename.rsplit(".", 1)
                if len(name_parts) != 2:
                    continue
                base_name, ext = name_parts[0].lower(), name_parts[1].lower()

                key = (group_name, base_name)
                if ext in FEATURE_IMAGE_EXTS:
                    images.setdefault(key, []).append(path)
                elif ext == "md":
                    descriptions[key] = path

            grouped = {}
            used_images = set()

            def add_feature(group_name, img_path, desc_path, name):
                img_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{project_name}/{branch}/{img_path}"
                desc_url = f"https://raw.githubusercontent.com/{GITHUB_USER}/{project_name}/{branch}/{desc_path}"
                grouped.setdefault(group_name, []).append({
                    "img": img_url, "desc": desc_url, "name": name
                })

            for (group_name, base_name), desc_path in descriptions.items():
                desc_key = (group_name, base_name)
                img_list = images.get(desc_key, [])
                for img_path in img_list:
                    add_feature(group_name, img_path, desc_path, base_name)
                    used_images.add((desc_key, img_path))
                if img_list:
                    continue

                for (img_group, img_base), img_paths in images.items():
                    if img_group != group_name:
                        continue
                    if _strip_numeric_suffix(img_base) == base_name:
                        for img_path in img_paths:
                            if (img_group, img_base, img_path) not in used_images:
                                add_feature(group_name, img_path, desc_path, base_name)
                                used_images.add((img_group, img_base, img_path))

            result = []
            for gname in sorted(grouped.keys()):
                result.append({
                    "group": gname,
                    "features": grouped[gname]
                })

            if result:
                return result
        except Exception:
            continue

    return []


DOC_EXTENSIONS = (".md", ".mdx", ".rst", ".txt")
DOC_EXCLUDE = {"readme.md", "readme.rst", "architecture.md", "architecture.rst",
               "license", "license.md", "license.rst", "contributing.md",
               "changelog.md", "code_of_conduct.md", "security.md"}


async def discover_documents(client, project_name, headers):
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
            doc_candidates = []

            for entry in tree:
                if entry["type"] != "blob":
                    continue
                path = entry["path"]
                ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
                if ext not in DOC_EXTENSIONS:
                    continue

                filename = path.rsplit("/", 1)[-1].lower()
                if filename in DOC_EXCLUDE:
                    continue

                # Skip files already fetched elsewhere
                if filename == "readme.md" and "/" not in path:
                    continue

                doc_candidates.append(path)

            if not doc_candidates:
                return []

            # Fetch content for each doc
            docs = []
            for doc_path in doc_candidates:
                try:
                    resp = await client.get(
                        f"{GITHUB_API}/repos/{GITHUB_USER}/{project_name}/contents/{doc_path}",
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("content"):
                            content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8", errors="replace")
                            docs.append({
                                "path": doc_path,
                                "name": doc_path.rsplit("/", 1)[-1],
                                "content": content,
                            })
                except Exception:
                    continue

            return docs
        except Exception:
            continue

    return []


async def fetch_repo_details_from_github(project_name: str):
    headers = github_headers()
    result = {"top_commits": "", "readme": "", "architecture": "", "img": "", "is_backend": True, "updated_date": "", "features_data": [], "documents": []}

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

                result["updated_date"] = repo_data.get("pushed_at") or ""
                result["img"] = await discover_repo_image(client, project_name, headers)
                result["features_data"] = await discover_features(client, project_name, headers)
                result["documents"] = await discover_documents(client, project_name, headers)
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
        "features_data": json.loads(detail.features_data) if isinstance(detail.features_data, str) else (detail.features_data or []),
        "documents": json.loads(detail.documents) if isinstance(detail.documents, str) else (detail.documents or []),
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
        existing.features_data = json.dumps(data["features_data"])
        existing.documents = json.dumps(data["documents"])
        existing.fetched_at = datetime.utcnow()
    else:
        existing = RepoDetail(
            project_name=project_name,
            top_commits=data["top_commits"],
            readme=data["readme"],
            architecture=data["architecture"],
            img=data["img"],
            is_backend=data["is_backend"],
            features_data=json.dumps(data["features_data"]),
            documents=json.dumps(data["documents"]),
            fetched_at=datetime.utcnow(),
        )
        db.add(existing)
    db.commit()
    db.refresh(existing)

    if data.get("img") or data.get("updated_date"):
        db_project = db.query(Project).filter(Project.name == project_name).first()
        if db_project:
            if data.get("img"):
                db_project.img = data["img"]
            if data.get("updated_date"):
                db_project.updatedDate = data["updated_date"]
            db.commit()

    return {
        "project_name": existing.project_name,
        "top_commits": existing.top_commits,
        "readme": existing.readme,
        "architecture": existing.architecture,
        "img": existing.img,
        "is_backend": existing.is_backend,
        "features_data": json.loads(existing.features_data) if isinstance(existing.features_data, str) else (existing.features_data or []),
        "documents": json.loads(existing.documents) if isinstance(existing.documents, str) else (existing.documents or []),
        "fetched_at": existing.fetched_at.isoformat() if existing.fetched_at else "",
    }


@app.get("/scrape")
async def scrape_github(query: Optional[str] = None, limit: Optional[int] = None):
    headers = github_headers()
    scrape_limit = limit or SCRAPE_LIMIT

    async with httpx.AsyncClient() as client:
        if query:
            search_q = f"user:{GITHUB_USER}+{query}+in:name"
            search_url = f"{GITHUB_API}/search/repositories?q={search_q}&sort=updated&order=desc&per_page={scrape_limit}"
            repos_resp = await client.get(search_url, headers=headers)
            repos_resp.raise_for_status()
            search_data = repos_resp.json()
            repos = search_data.get("items", [])
        else:
            repos_resp = await client.get(
                f"{GITHUB_API}/users/{GITHUB_USER}/repos?per_page=100&sort=updated&direction=desc",
                headers=headers,
            )
            repos_resp.raise_for_status()
            repos = repos_resp.json()
            repos = repos[:scrape_limit]

        entries = []
        for repo in repos:
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

    db = SessionLocal()
    projects_updated = 0
    projects_added = 0
    details = []

    for entry in entries:
        existing = db.query(Project).filter(Project.name == entry["name"]).first()
        if existing:
            existing.archived = False
            existing.startDate = entry.get("startDate", "")
            existing.updatedDate = entry.get("updatedDate", "")
            existing.dir = entry.get("dir", "")
            if entry.get("img"):
                existing.img = entry.get("img", "")
            existing.features = json.dumps(entry.get("features", []))
            existing.categories = json.dumps(entry.get("categories", []))
            existing.skills = json.dumps(entry.get("skills", []))
            existing.contributions = entry.get("contributions", 0)
            existing.description = entry.get("description", "")
            existing.languageKeys = json.dumps(entry.get("languageKeys", []))
            existing.language = entry.get("language", "")
            existing.size = entry.get("size", 0)
            existing.openIssues = entry.get("openIssues", 0)
            existing.languages = json.dumps(entry.get("languages", {}))
            projects_updated += 1
            details.append(f"Updated: {entry['name']}")
        else:
            p = Project(
                name=entry["name"],
                startDate=entry.get("startDate", ""),
                updatedDate=entry.get("updatedDate", ""),
                dir=entry.get("dir", ""),
                img=entry.get("img", ""),
                features=json.dumps(entry.get("features", [])),
                categories=json.dumps(entry.get("categories", [])),
                skills=json.dumps(entry.get("skills", [])),
                contributions=entry.get("contributions", 0),
                description=entry.get("description", ""),
                languageKeys=json.dumps(entry.get("languageKeys", [])),
                language=entry.get("language", ""),
                size=entry.get("size", 0),
                openIssues=entry.get("openIssues", 0),
                languages=json.dumps(entry.get("languages", {})),
            )
            db.add(p)
            projects_added += 1
            details.append(f"Added: {entry['name']}")

    db.commit()

    log = ScrapeLog(
        total_repos=len(entries),
        projects_updated=projects_updated,
        projects_added=projects_added,
        details="\n".join(details),
    )
    db.add(log)
    db.commit()

    all_projects = db.query(Project).all()

    q_label = f" matching '{query}'" if query else ""
    return {
        "message": f"Scraped {len(entries)} projects{q_label} from {GITHUB_USER}",
        "count": len(entries),
        "total": len(all_projects),
        "updated": projects_updated,
        "added": projects_added,
        "details": details,
    }
