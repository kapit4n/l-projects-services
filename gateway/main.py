from fastapi import FastAPI, HTTPException
import httpx

app = FastAPI()

PROJECTS_SERVICE_URL = "http://localhost:8001"
FEATURES_SERVICE_URL = "http://localhost:8002"
COMMENTARIES_SERVICE_URL = "http://localhost:8003"

@app.post("/projects/")
async def create_project(name: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{PROJECTS_SERVICE_URL}/projects/", json={"name": name})
        return response.json()

@app.get("/projects/{project_id}")
async def read_project(project_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{PROJECTS_SERVICE_URL}/projects/{project_id}")
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