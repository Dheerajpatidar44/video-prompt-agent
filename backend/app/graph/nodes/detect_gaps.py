import json
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, Gap, GapDetectionResult, Importance
from app.llm.ollama import LLMService
from app.prompts.gap_detector import GAP_DETECTOR_PROMPT

def sort_gaps(gaps: list[Gap]) -> list[Gap]:
    # Priority order mapping
    priority = {
        Importance.CRITICAL: 1,
        Importance.IMPORTANT: 2,
        Importance.OPTIONAL: 3,
        Importance.INFERABLE: 4,
    }
    return sorted(gaps, key=lambda g: priority.get(g.importance, 5))

def deduplicate_gaps(gaps: list[Gap]) -> list[Gap]:
    unique_gaps = []
    seen = set()
    for gap in gaps:
        # Simple deduplication by category and title (lowercase)
        key = (gap.category, gap.title.lower().strip())
        if key not in seen:
            seen.add(key)
            unique_gaps.append(gap)
    return unique_gaps

def detect_gaps(state: AgentState) -> AgentState:
    """Determine what information is missing or ambiguous using local LLM."""
    script_text = state.get("original_script", "")
    analysis_dict = state.get("analysis", {})
    
    if not script_text.strip():
        # Nothing to analyze
        return state

    llm = LLMService()
    
    prompt = GAP_DETECTOR_PROMPT.format(
        script=script_text,
        analysis=json.dumps(analysis_dict, indent=2)
    )
    
    try:
        detection_result = llm.generate_structured(prompt, GapDetectionResult)
        
        raw_gaps = detection_result.gaps
        
        # Deduplicate and sort
        unique_gaps = deduplicate_gaps(raw_gaps)
        prioritized_gaps = sort_gaps(unique_gaps)
        
        # Merge with existing gaps if any
        existing_gaps = state.get("gaps", [])
        all_gaps = deduplicate_gaps(existing_gaps + prioritized_gaps)
        all_gaps = sort_gaps(all_gaps)
        
        return {
            **state,
            "gaps": all_gaps,
            "status": AgentStatus.ANALYZING,
            "error": None
        }
    except Exception as e:
        return {
            **state,
            "status": AgentStatus.ERROR,
            "error": f"Gap detection failed: {str(e)}"
        }
