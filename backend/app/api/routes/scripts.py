from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
import asyncio
import os
import tempfile
import logging

from app.services.script_service import ScriptService
from app.graph.graph import build_graph
from app.schemas.agent import AgentStatus, Question, Answer, QuestionStatus
from app.schemas.script import ScriptDocument

logger = logging.getLogger(__name__)

router = APIRouter()
graph = build_graph()




class AnalyzeResponse(BaseModel):
    thread_id: str
    status: str
    script: Dict[str, Any]
    analysis: Optional[Dict[str, Any]] = None
    gaps: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class SubmitAnswersRequest(BaseModel):
    answers: list[Answer]


# ----------------------------------------------------------------------
# Shared helpers — used by every state-reading endpoint below
# ----------------------------------------------------------------------

async def _get_state_values(thread_id: str) -> dict:
    import aiosqlite
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from app.graph.graph import build_graph, serde

    config = {"configurable": {"thread_id": thread_id}}
    async with aiosqlite.connect("data/memory.sqlite") as conn:
        memory = AsyncSqliteSaver(conn, serde=serde)
        await memory.setup()
        graph = build_graph(memory)
        snapshot = await graph.aget_state(config)
        
        if not snapshot or not snapshot.values:
            raise HTTPException(status_code=404, detail="Analysis thread not found.")
        return snapshot.values


def _gaps_summary(gaps_list: list) -> dict:
    return {
        "total": len(gaps_list),
        "critical": len([g for g in gaps_list if g.importance.value == "CRITICAL"]),
        "important": len([g for g in gaps_list if g.importance.value == "IMPORTANT"]),
        "optional": len([g for g in gaps_list if g.importance.value == "OPTIONAL"]),
        "items": [g.model_dump() for g in gaps_list],
    }


def _status_str(state: dict) -> str:
    status = state.get("status")
    return status.value if hasattr(status, "value") else str(status or "completed")


async def _run_graph(payload, config: dict) -> dict:
    """Dynamically construct AsyncSqliteSaver and compile graph per run."""
    import aiosqlite
    import os
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from app.graph.graph import build_graph, serde

    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect("data/memory.sqlite") as conn:
        memory = AsyncSqliteSaver(conn, serde=serde)
        await memory.setup()
        graph = build_graph(memory)
        return await graph.ainvoke(payload, config)


async def _ingest_file_async(tmp_path: str, source_type: str, filename: str, content: bytes) -> ScriptDocument:
    """Runs the full pipeline (write temp file, parse, cleanup)."""
    with open(tmp_path, "wb") as f:
        f.write(content)
    try:
        return await ScriptService.ingest_file(tmp_path, source_type, filename)
    finally:
        os.remove(tmp_path)


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_script_endpoint(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
    tool: Optional[str] = Form("Veo"),
    character_images: List[UploadFile] = File(default=[]),
    product_images: List[UploadFile] = File(default=[]),
    brand_images: List[UploadFile] = File(default=[]),
):
    if not text and not file:
        raise HTTPException(status_code=400, detail="Must provide either 'text' or 'file'.")

    script_doc = None

    try:
        if file:
            ext = os.path.splitext(file.filename)[1].lower()
            if ext not in [".txt", ".pdf"]:
                raise HTTPException(status_code=400, detail="Only .txt and .pdf files are supported.")

            source_type = "pdf" if ext == ".pdf" else "txt"
            content = await file.read()  # async, doesn't block
            if len(content) == 0:
                raise HTTPException(status_code=400, detail="Uploaded file is empty.")

            # tempfile.mkstemp is a cheap syscall;
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)

            script_doc = await _ingest_file_async(tmp_path, source_type, file.filename, content)

        elif text:
            if not text.strip():
                raise HTTPException(status_code=400, detail="Provided text is empty.")
            script_doc = ScriptService.ingest_text(text)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error during ingestion: {str(e)}")

    # Upload reference images to Cloudinary
    from app.services.cloudinary_service import upload_image
    
    ref_urls = {"character": [], "product": [], "brand": []}
    
    # helper for async upload
    async def process_images(files, category):
        for img in files:
            if img and img.filename:
                content = await img.read()
                url = await run_in_threadpool(upload_image, content, img.filename, category)
                ref_urls[category].append(url)
                
    await process_images(character_images, "character")
    await process_images(product_images, "product")
    await process_images(brand_images, "brand")

    logger.info(f"Starting graph execution. thread_id={script_doc.document_id}")
    initial_state = {
        "project_id": script_doc.document_id,
        "original_script": script_doc.normalized_text,
        "script_source": script_doc.source_type,
        "reference_images": ref_urls,
        "selected_tool": tool,
    }
    config = {"configurable": {"thread_id": script_doc.document_id}}

    try:
        from app.db.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        title = script_doc.normalized_text[:40] + "..." if len(script_doc.normalized_text) > 40 else script_doc.normalized_text
        thumb = ref_urls["character"][0] if ref_urls["character"] else (ref_urls["product"][0] if ref_urls["product"] else None)
        cursor.execute("""
            INSERT OR IGNORE INTO projects (id, title, thread_id, tool, thumbnail_url, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (script_doc.document_id, title, script_doc.document_id, tool, thumb, "ANALYZING"))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to create project in DB: {e}")

    try:
        final_state = await _run_graph(initial_state, config)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Graph execution failed")
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")

    try:
        from app.db.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (_status_str(final_state), script_doc.document_id))
        conn.commit()
        conn.close()
    except Exception as e:
        logger.error(f"Failed to update project status in DB: {e}")

    if final_state.get("error"):
        return AnalyzeResponse(
            thread_id=script_doc.document_id,
            status="error",
            script=script_doc.model_dump(),
            error=final_state["error"],
        )

    return AnalyzeResponse(
        thread_id=script_doc.document_id,
        status=_status_str(final_state),
        script=script_doc.model_dump(),
        analysis=final_state.get("analysis", {}),
        gaps=_gaps_summary(final_state.get("gaps", [])),
    )


@router.get("/{thread_id}/questions")
async def get_questions(thread_id: str):
    state = await _get_state_values(thread_id)
    questions = state.get("questions", [])
    pending = [q.model_dump() for q in questions if q.status == QuestionStatus.PENDING]
    return {"thread_id": thread_id, "questions": pending, "status": state.get("status")}


async def _update_state(config: dict, state_update: dict):
    """Dynamically construct AsyncSqliteSaver and update state."""
    import aiosqlite
    import os
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    from app.graph.graph import build_graph, serde

    os.makedirs("data", exist_ok=True)
    async with aiosqlite.connect("data/memory.sqlite") as conn:
        memory = AsyncSqliteSaver(conn, serde=serde)
        await memory.setup()
        local_graph = build_graph(memory)
        # aupdate_state is the async version of update_state
        await local_graph.aupdate_state(config, state_update)

@router.post("/{thread_id}/answers")
async def submit_answers(thread_id: str, request: SubmitAnswersRequest):
    config = {"configurable": {"thread_id": thread_id}}
    state = await _get_state_values(thread_id)

    if state.get("status") != AgentStatus.WAITING_FOR_USER:
        raise HTTPException(status_code=400, detail="Graph is not currently waiting for user answers.")

    await _update_state(config, {"new_answers": request.answers})

    try:
        final_state = await _run_graph(None, config)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph resumption failed: {str(e)}")

    try:
        from app.db.database import get_db
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE projects SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (_status_str(final_state), thread_id))
        conn.commit()
        conn.close()
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to update project status in DB: {e}")

    return {
        "status": final_state.get("status"),
        "gaps": _gaps_summary(final_state.get("gaps", [])),
    }


@router.get("/{thread_id}/video-specification")
async def get_video_specification(thread_id: str):
    state = await _get_state_values(thread_id)
    spec = state.get("video_specification")
    if not spec:
        raise HTTPException(status_code=404, detail="Video specification not yet generated.")
    return {
        "thread_id": thread_id,
        "video_specification": spec.model_dump() if hasattr(spec, "model_dump") else spec,
        "status": state.get("status"),
    }


@router.get("/{thread_id}/scene-plan")
async def get_scene_plan(thread_id: str):
    state = await _get_state_values(thread_id)
    plan = state.get("scene_plan")
    if not plan:
        raise HTTPException(status_code=404, detail="Scene plan not yet generated.")
    return {
        "thread_id": thread_id,
        "scene_plan": plan.model_dump() if hasattr(plan, "model_dump") else plan,
        "status": state.get("status"),
    }


@router.get("/{thread_id}/prompts")
async def get_prompts(thread_id: str):
    state = await _get_state_values(thread_id)
    prompt_set = state.get("prompt_set")
    if not prompt_set:
        raise HTTPException(status_code=404, detail="Prompts not yet generated.")
    return {
        "thread_id": thread_id,
        "prompt_set": prompt_set.model_dump() if hasattr(prompt_set, "model_dump") else prompt_set,
        "status": state.get("status"),
    }