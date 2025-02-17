from fastapi import FastAPI, HTTPException
from database import SessionLocal, engine
from models import Base, Feature
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
class FeatureCreate(BaseModel):
    name: str
    project_id: int

@app.post("/features/")
def create_feature(feature: FeatureCreate):
    db = SessionLocal()
    db_feature = Feature(name=feature.name, project_id=feature.project_id)
    db.add(db_feature)
    db.commit()
    db.refresh(db_feature)
    return db_feature

@app.get("/features/{feature_id}")
def read_feature(feature_id: int):
    db = SessionLocal()
    feature = db.query(Feature).filter(Feature.id == feature_id).first()
    if feature is None:
        raise HTTPException(status_code=404, detail="Feature not found")
    return feature
