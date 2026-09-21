from app.graph.state import AgentState
from app.schemas.agent import AgentStatus
from app.schemas.script import ScriptAnalysis
from app.llm.ollama import LLMService

def analyze_script(state: AgentState) -> AgentState:
    """Analyze the current script context."""
    script_text = state.get("original_script", "")
    if not script_text.strip():
        return {
            **state,
            "status": AgentStatus.ERROR,
            "error": "No script provided for analysis."
        }

    llm = LLMService()
    
    prompt = f"""
    Analyze the following video script and extract EXPLICITLY STATED information only.
    Do NOT invent or infer details like age, hair color, lighting, or camera angles unless explicitly mentioned in the text.
    If something is not present in the script, represent it as unknown / missing / null or an empty list.

    Script:
    {script_text}
    """
    
    try:
        analysis_result = llm.generate_structured(prompt, ScriptAnalysis)
        return {
            **state,
            "analysis": analysis_result.model_dump(),
            "status": AgentStatus.ANALYZING,
            "error": None
        }
    except Exception as e:
        return {
            **state,
            "status": AgentStatus.ERROR,
            "error": str(e)
        }
