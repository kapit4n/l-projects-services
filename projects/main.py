import json, os, asyncio
from fastapi import FastAPI, HTTPException
from database import SessionLocal, engine
from models import Base, Project, CommitSync
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
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
DATA_FILE = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "l-projects", "public", "data", "projects-all.json"))


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

    merged = []
    for entry in entries:
        if entry["name"] in existing_map:
            old = existing_map[entry["name"]]
            old.update(entry)
            merged.append(old)
            del existing_map[entry["name"]]
        else:
            max_id = max((p["id"] for p in merged), default=0)
            entry["id"] = max_id + 1
            merged.append(entry)

    for p in existing_map.values():
        merged.append(p)

    with open(DATA_FILE, "w") as f:
        json.dump(merged, f, indent=2)

    return {
        "message": f"Scraped {len(entries)} projects from {GITHUB_USER}",
        "count": len(entries),
        "total": len(merged),
    }
