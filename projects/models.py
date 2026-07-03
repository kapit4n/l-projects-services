from sqlalchemy import Column, Integer, String, DateTime
from database import Base
from datetime import datetime

class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)


class CommitSync(Base):
    __tablename__ = "commit_sync"
    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True, unique=True)
    total_commits = Column(Integer, default=0)
    synced_at = Column(DateTime, default=datetime.utcnow)
