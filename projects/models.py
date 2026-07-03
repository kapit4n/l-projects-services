from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
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


class ScrapeLog(Base):
    __tablename__ = "scrape_logs"
    id = Column(Integer, primary_key=True, index=True)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    total_repos = Column(Integer, default=0)
    projects_updated = Column(Integer, default=0)
    projects_added = Column(Integer, default=0)
    details = Column(Text, default="")


class RepoDetail(Base):
    __tablename__ = "repo_details"
    id = Column(Integer, primary_key=True, index=True)
    project_name = Column(String, index=True, unique=True)
    top_commits = Column(Text, default="")
    readme = Column(Text, default="")
    architecture = Column(Text, default="")
    img = Column(String, default="")
    is_backend = Column(Boolean, default=True)
    fetched_at = Column(DateTime, default=datetime.utcnow)
