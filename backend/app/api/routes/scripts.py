from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel
from typing import Optional, Dict, Any
from app.services.script_service import ScriptService
from app.graph.graph import build_graph
from app.schemas.agent import AgentStatus, Question, Answer, QuestionStatus
import os
import tempfile

router = APIRouter()
graph = build_graph()

class AnalyzeResponse(BaseModel):
    thread_id: str
    status: str
    script: Dict[str, Any]
    analysis: Optional[Dict[str, Any]] = None
    gaps: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

@router.post("/analyze", response_model=AnalyzeResponse)
def analyze_script_endpoint(
    text: Optional[str] = Form(None),
    file: Optional[UploadFile] = File(None)
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
            
            with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
                content = file.file.read()
                if len(content) == 0:
                    raise HTTPException(status_code=400, detail="Uploaded file is empty.")
                tmp.write(content)
                tmp_path = tmp.name
                
            try:
                script_doc = ScriptService.ingest_file(tmp_path, source_type, file.filename)
            finally:
                os.remove(tmp_path)
                
        elif text:
            if not text.strip():
                raise HTTPException(status_code=400, detail="Provided text is empty.")
            script_doc = ScriptService.ingest_text(text)
            
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error during ingestion: {str(e)}")

    # Execute LangGraph workflow
    print(f"DIAGNOSTIC: Entering graph execution. THREAD_ID = {script_doc.document_id}")
    initial_state = {
        "project_id": script_doc.document_id,
        "original_script": script_doc.normalized_text,
        "script_source": script_doc.source_type
    }
    
    try:
        config = {"configurable": {"thread_id": script_doc.document_id}}
        print("DIAGNOSTIC: graph.invoke starting")
        final_state = graph.invoke(initial_state, config)
        print("DIAGNOSTIC: graph.invoke finished")
        
        if final_state.get("error"):
            print("DIAGNOSTIC: graph returned error state")
            return AnalyzeResponse(
                thread_id=script_doc.document_id,
                status="error",
                script=script_doc.model_dump(),
                error=final_state["error"]
            )
            
        gaps_list = final_state.get("gaps", [])
        gaps_dict = {
            "total": len(gaps_list),
            "critical": len([g for g in gaps_list if g.importance.value == "CRITICAL"]),
            "important": len([g for g in gaps_list if g.importance.value == "IMPORTANT"]),
            "optional": len([g for g in gaps_list if g.importance.value == "OPTIONAL"]),
            "items": [g.model_dump() for g in gaps_list]
        }
            
        return AnalyzeResponse(
            thread_id=script_doc.document_id,
            status="completed",
            script=script_doc.model_dump(),
            analysis=final_state.get("analysis", {}),
            gaps=gaps_dict
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph execution failed: {str(e)}")

@router.get("/{thread_id}/questions")
def get_questions(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Analysis thread not found.")
        
    state_values = state_snapshot.values
    questions = state_values.get("questions", [])
    
    # Return pending questions
    pending = [q.model_dump() for q in questions if q.status == QuestionStatus.PENDING]
    
    return {
        "thread_id": thread_id,
        "questions": pending,
        "status": state_values.get("status")
    }

class SubmitAnswersRequest(BaseModel):
    answers: list[Answer]

@router.post("/{thread_id}/answers")
def submit_answers(thread_id: str, request: SubmitAnswersRequest):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Analysis thread not found.")
        
    if state_snapshot.values.get("status") != AgentStatus.WAITING_FOR_USER:
        raise HTTPException(status_code=400, detail="Graph is not currently waiting for user answers.")
        
    # Update the graph with new_answers
    # We use graph.update_state to inject the answers, then resume
    graph.update_state(config, {"new_answers": request.answers})
    
    try:
        final_state = graph.invoke(None, config) # None as input means just resume
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Graph resumption failed: {str(e)}")
        
    gaps_list = final_state.get("gaps", [])
    gaps_dict = {
        "total": len(gaps_list),
        "critical": len([g for g in gaps_list if g.importance.value == "CRITICAL"]),
        "important": len([g for g in gaps_list if g.importance.value == "IMPORTANT"]),
        "optional": len([g for g in gaps_list if g.importance.value == "OPTIONAL"]),
        "items": [g.model_dump() for g in gaps_list]
    }
        
    return {
        "status": final_state.get("status"),
        "gaps": gaps_dict
    }

@router.get("/{thread_id}/video-specification")
def get_video_specification(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Analysis thread not found.")
        
    state_values = state_snapshot.values
    spec = state_values.get("video_specification")
    
    if not spec:
        raise HTTPException(status_code=404, detail="Video specification not yet generated.")
        
    return {
        "thread_id": thread_id,
        "video_specification": spec.model_dump() if hasattr(spec, "model_dump") else spec,
        "status": state_values.get("status")
    }

@router.get("/{thread_id}/scene-plan")
def get_scene_plan(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Analysis thread not found.")
        
    state_values = state_snapshot.values
    plan = state_values.get("scene_plan")
    
    if not plan:
        raise HTTPException(status_code=404, detail="Scene plan not yet generated.")
    
    return {
        "thread_id": thread_id,
        "scene_plan": plan.model_dump() if hasattr(plan, "model_dump") else plan,
        "status": state_values.get("status")
    }

@router.get("/{thread_id}/prompts")
def get_prompts(thread_id: str):
    config = {"configurable": {"thread_id": thread_id}}
    state_snapshot = graph.get_state(config)
    
    if not state_snapshot or not state_snapshot.values:
        raise HTTPException(status_code=404, detail="Analysis thread not found.")
        
    state_values = state_snapshot.values
    prompt_set = state_values.get("prompt_set")
    
    if not prompt_set:
        raise HTTPException(status_code=404, detail="Prompts not yet generated.")
        
    return {
        "thread_id": thread_id,
        "prompt_set": prompt_set.model_dump() if hasattr(prompt_set, "model_dump") else prompt_set,
        "status": state_values.get("status")
    }
