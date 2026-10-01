from fastapi import APIRouter, HTTPException
from typing import List, Optional
from pydantic import BaseModel
import sqlite3
from app.db.database import get_db

router = APIRouter()

class Project(BaseModel):
    id: str
    title: str
    thread_id: str
    tool: str
    thumbnail_url: Optional[str] = None
    status: str
    created_at: str
    updated_at: str

@router.get("/", response_model=List[Project])
def get_projects():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM projects ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

class CreateProjectRequest(BaseModel):
    id: str
    title: str
    thread_id: str
    tool: str
    thumbnail_url: Optional[str] = None

@router.post("/", response_model=Project)
def create_project(req: CreateProjectRequest):
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO projects (id, title, thread_id, tool, thumbnail_url)
            VALUES (?, ?, ?, ?, ?)
        """, (req.id, req.title, req.thread_id, req.tool, req.thumbnail_url))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="Project with this ID or thread_id already exists")
    
    cursor.execute("SELECT * FROM projects WHERE id = ?", (req.id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row)

@router.delete("/{project_id}")
def delete_project(project_id: str):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    conn.commit()
    conn.close()
    return {"message": "Project deleted"}
