from fastapi import FastAPI, HTTPException
from database import SessionLocal, engine
from models import Base, Project
from pydantic import BaseModel

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
