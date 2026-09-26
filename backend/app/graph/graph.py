from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.graph.state import AgentState
from app.graph.nodes.initialize_state import initialize_state
from app.graph.nodes.analyze_script import analyze_script
from app.graph.nodes.update_state import update_state
from app.graph.nodes.re_analyze import re_analyze
from app.graph.nodes.build_video_spec import build_video_spec
from app.graph.nodes.generate_scenes_and_prompts import generate_scenes_and_prompts
from app.graph.routing import route_after_gap_detection, route_after_analysis


def build_graph():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("initialize_state", initialize_state)
    workflow.add_node("analyze_script", analyze_script)           # 1 LLM call (analysis + gaps + questions)
    workflow.add_node("update_state", update_state)               # Python only
    workflow.add_node("re_analyze", re_analyze)                   # 1 LLM call (re-evaluate gaps after answers)
    workflow.add_node("build_video_spec", build_video_spec)       # 1 LLM call
    workflow.add_node("generate", generate_scenes_and_prompts)    # 1 LLM call (scenes + prompts combined)

    # Edges
    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "analyze_script")
    
    # After combined analysis: if questions exist → wait for user, else → build spec
    workflow.add_conditional_edges(
        "analyze_script",
        route_after_analysis,
        {
            "WAIT_FOR_ANSWERS": "update_state",
            "PROCEED": "build_video_spec"
        }
    )
    
    # After user answers are merged, re-evaluate gaps
    workflow.add_edge("update_state", "re_analyze")
    
    # After re-analysis, route again
    workflow.add_conditional_edges(
        "re_analyze",
        route_after_gap_detection,
        {
            "ASK_QUESTIONS": "update_state",  # loop back to wait for more answers
            "PROCEED": "build_video_spec"
        }
    )
    
    # Generation: spec → combined scene+prompt generation → END
    workflow.add_edge("build_video_spec", "generate")
    workflow.add_edge("generate", END)

    memory = MemorySaver()
    return workflow.compile(checkpointer=memory, interrupt_before=["update_state"])
