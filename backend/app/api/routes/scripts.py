from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from typing import Optional, Dict, Any
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

def _get_state_values(thread_id: str) -> dict:
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)
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
    """ainvoke without a hard timeout, allowing slow local LLMs unlimited time to complete."""
    return await graph.ainvoke(payload, config)


def _ingest_file_blocking(tmp_path: str, source_type: str, filename: str, content: bytes) -> ScriptDocument:
    """Runs the full blocking pipeline (write temp file, parse, cleanup) —
    call this via run_in_threadpool so it never touches the event loop directly."""
    with open(tmp_path, "wb") as f:
        f.write(content)
    try:
        return ScriptService.ingest_file(tmp_path, source_type, filename)
    finally:
        os.remove(tmp_path)


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_script_endpoint(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None),
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

            # tempfile.mkstemp is a cheap syscall; the expensive part (write,
            # parse, cleanup) is what we push to the threadpool below.
            fd, tmp_path = tempfile.mkstemp(suffix=ext)
            os.close(fd)

            # Offload the blocking write + parse (PDF extraction can take
            # real time) so the event loop stays free for other requests.
            script_doc = await run_in_threadpool(
                _ingest_file_blocking, tmp_path, source_type, file.filename, content
            )

        elif text:
            if not text.strip():
                raise HTTPException(status_code=400, detail="Provided text is empty.")
            # Fast/pure-Python for typical text lengths, but offload anyway —
            # cheap insurance if someone pastes a very large script.
            script_doc = await run_in_threadpool(ScriptService.ingest_text, text)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error during ingestion: {str(e)}")

    logger.info(f"Starting graph execution. thread_id={script_doc.document_id}")
    initial_state = {
        "project_id": script_doc.document_id,
        "original_script": script_doc.normalized_text,
        "script_source": script_doc.source_type,
    }
    config = {"configurable": {"thread_id": script_doc.document_id}}

    try:
        final_state = await _run_graph(initial_state, config)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Graph execution failed")
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")

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
    state = _get_state_values(thread_id)
    questions = state.get("questions", [])
    pending = [q.model_dump() for q in questions if q.status == QuestionStatus.PENDING]
    return {"thread_id": thread_id, "questions": pending, "status": state.get("status")}


@router.post("/{thread_id}/answers")
async def submit_answers(thread_id: str, request: SubmitAnswersRequest):
    config = {"configurable": {"thread_id": thread_id}}
    state = _get_state_values(thread_id)

    if state.get("status") != AgentStatus.WAITING_FOR_USER:
        raise HTTPException(status_code=400, detail="Graph is not currently waiting for user answers.")

    graph.update_state(config, {"new_answers": request.answers})

    try:
        final_state = await _run_graph(None, config)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph resumption failed: {str(e)}")

    return {
        "status": final_state.get("status"),
        "gaps": _gaps_summary(final_state.get("gaps", [])),
    }


@router.get("/{thread_id}/video-specification")
async def get_video_specification(thread_id: str):
    state = _get_state_values(thread_id)
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
    state = _get_state_values(thread_id)
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
    state = _get_state_values(thread_id)
    prompt_set = state.get("prompt_set")
    if not prompt_set:
        raise HTTPException(status_code=404, detail="Prompts not yet generated.")
    return {
        "thread_id": thread_id,
        "prompt_set": prompt_set.model_dump() if hasattr(prompt_set, "model_dump") else prompt_set,
        "status": state.get("status"),
    }