import json
from app.services.script_service import ScriptService
from app.graph.graph import build_graph
from app.llm.ollama import LLMService

def test_manual_integration():
    print("Checking Ollama availability...")
    llm = LLMService()
    if not llm.check_health():
        print("Ollama is not running. Please start Ollama to run this test.")
        return
        
    if not llm.check_model():
        print(f"Model '{llm.model_name}' is not installed in Ollama.")
        print(f"Please run: ollama pull {llm.model_name}")
        return
        
    print("Ollama is ready. Ingesting script...")
    
    script_doc = ScriptService.ingest_file("test_script.txt", "txt", "test_script.txt")
    print("Script ingested and normalized successfully.")
    
    graph = build_graph()
    initial_state = {
        "project_id": script_doc.document_id,
        "original_script": script_doc.normalized_text,
        "script_source": script_doc.source_type
    }
    
    print("Running LangGraph workflow...")
    config = {"configurable": {"thread_id": script_doc.document_id}}
    final_state = graph.invoke(initial_state, config)
    
    if final_state.get("error"):
        print(f"Workflow error: {final_state['error']}")
        return
        
    print("\n--- STRUCTURED SCRIPT ANALYSIS ---")
    analysis = final_state.get("analysis", {})
    print(json.dumps(analysis, indent=2))
    print("\n--- TEST COMPLETE ---")

if __name__ == "__main__":
    test_manual_integration()
