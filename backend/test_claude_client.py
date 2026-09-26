import json
import asyncio
import time
from app.services.script_service import ScriptService
from app.graph.graph import build_graph
from app.llm.claude_client import llm_service
import pytest

@pytest.mark.asyncio
async def test_manual_integration():
    print("Ingesting script...")
    script_doc = ScriptService.ingest_file("test_script.txt", "txt", "test_script.txt")
    print("Script ingested and normalized successfully.")
    
    graph = build_graph()
    initial_state = {
        "project_id": script_doc.document_id,
        "original_script": script_doc.normalized_text,
        "script_source": script_doc.source_type
    }
    
    print("Running LangGraph workflow (async)...")
    config = {"configurable": {"thread_id": script_doc.document_id}}
    
    t0 = time.perf_counter()
    final_state = await graph.ainvoke(initial_state, config)
    elapsed = time.perf_counter() - t0
    
    if final_state.get("error"):
        print(f"Workflow error: {final_state['error']}")
        return
        
    print(f"\n--- TOTAL WALL TIME: {elapsed:.2f}s ---")
    print(f"\n--- STATUS: {final_state.get('status')} ---")
    
    print("\n--- SCRIPT ANALYSIS ---")
    analysis = final_state.get("analysis", {})
    print(json.dumps(analysis, indent=2, default=str))
    
    gaps = final_state.get("gaps", [])
    print(f"\n--- GAPS: {len(gaps)} ---")
    for g in gaps:
        print(f"  [{g.importance.value}] {g.title}: {g.description}")
    
    questions = final_state.get("questions", [])
    print(f"\n--- QUESTIONS: {len(questions)} ---")
    for q in questions:
        print(f"  [{q.priority.value}] {q.question}")
    
    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    asyncio.run(test_manual_integration())
