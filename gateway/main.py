from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:3001"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PROJECTS_SERVICE_URL = "http://localhost:8001"
FEATURES_SERVICE_URL = "http://localhost:8002"
COMMENTARIES_SERVICE_URL = "http://localhost:8003"

@app.post("/projects/")
async def create_project(project: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/projects/", json=project)
        return response.json()

@app.get("/projects/")
async def list_projects():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/projects/")
        return response.json()

@app.post("/projects/batch")
async def upsert_projects(projects: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/projects/batch", json=projects)
        return response.json()

@app.get("/projects/{project_id}")
async def read_project(project_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/projects/{project_id}")
        return response.json()

@app.put("/projects/{project_name}/archive")
async def archive_project(project_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.put(f"{PROJECTS_SERVICE_URL}/projects/{project_name}/archive")
        return response.json()

@app.put("/projects/{project_name}/unarchive")
async def unarchive_project(project_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.put(f"{PROJECTS_SERVICE_URL}/projects/{project_name}/unarchive")
        return response.json()

@app.post("/features/")
async def create_feature(name: str, project_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{FEATURES_SERVICE_URL}/features/", json={"name": name, "project_id": project_id})
        return response.json()

@app.get("/features/{feature_id}")
async def read_feature(feature_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{FEATURES_SERVICE_URL}/features/{feature_id}")
        return response.json()

@app.post("/commentaries/")
async def create_commentary(text: str, feature_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{COMMENTARIES_SERVICE_URL}/commentaries/", json={"text": text, "feature_id": feature_id})
        return response.json()

@app.get("/commentaries/{commentary_id}")
async def read_commentary(commentary_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{COMMENTARIES_SERVICE_URL}/commentaries/{commentary_id}")
        return response.json()


@app.post("/commits/")
async def upsert_commit(project_name: str, total_commits: int):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/commits/", json={"project_name": project_name, "total_commits": total_commits})
        return response.json()

@app.post("/commits/batch")
async def upsert_commits(commits: list):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/commits/batch", json=commits)
        return response.json()

@app.get("/commits/")
async def list_commits():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/commits/")
        return response.json()

@app.get("/commits/{project_name}")
async def get_commit(project_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/commits/{project_name}")
        if response.status_code == 404:
            return {"total_commits": 0}
        return response.json()


@app.get("/scrape")
async def scrape_github(request: Request):
    params = dict(request.query_params)
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/scrape", params=params)
        return response.json()

@app.get("/scrape/logs")
async def get_scrape_logs():
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/scrape/logs")
        return response.json()


@app.get("/repo-details/{project_name}")
async def get_repo_details(project_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/repo-details/{project_name}")
        if response.status_code == 404:
            return None
        return response.json()


@app.get("/repo-details/{project_name}/docs")
async def get_project_docs(project_name: str):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/repo-details/{project_name}/docs")
        return response.json()


@app.post("/repo-details/{project_name}/fetch")
async def fetch_repo_details(project_name: str):
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/repo-details/{project_name}/fetch")
        return response.json()