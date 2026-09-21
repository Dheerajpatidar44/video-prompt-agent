from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.graph.state import AgentState
from app.graph.nodes.initialize_state import initialize_state
from app.graph.nodes.analyze_script import analyze_script
from app.graph.nodes.detect_gaps import detect_gaps
from app.graph.nodes.ask_questions import ask_questions
from app.graph.nodes.update_state import update_state
from app.graph.nodes.re_analyze import re_analyze
from app.graph.nodes.build_video_spec import build_video_spec
from app.graph.nodes.scene_planner import scene_planner
from app.graph.nodes.prompt_generator import prompt_generator
from app.graph.routing import route_after_gap_detection

def build_graph():
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("initialize_state", initialize_state)
    workflow.add_node("analyze_script", analyze_script)
    workflow.add_node("detect_gaps", detect_gaps)
    workflow.add_node("ask_questions", ask_questions)
    workflow.add_node("update_state", update_state)
    workflow.add_node("re_analyze", re_analyze)
    workflow.add_node("build_video_spec", build_video_spec)    
    workflow.add_node("scene_planner", scene_planner)
    workflow.add_node("prompt_generator", prompt_generator)
    # Add edges
    workflow.set_entry_point("initialize_state")
    workflow.add_edge("initialize_state", "analyze_script")
    workflow.add_edge("analyze_script", "detect_gaps")
    
    # Conditional routing after gap detection
    workflow.add_conditional_edges(
        "detect_gaps",
        route_after_gap_detection,
        {
            "ASK_QUESTIONS": "ask_questions",
            "PROCEED": "build_video_spec"
        }
    )
    
    # Human-in-the-loop will interrupt here. 
    # Once resumed, update_state processes answers.
    workflow.add_edge("ask_questions", "update_state")
    
    # After updating state, re-evaluate gaps
    workflow.add_edge("update_state", "re_analyze")
    
    # After re-analysis, route again to either ask_questions or proceed
    workflow.add_conditional_edges(
        "re_analyze",
        route_after_gap_detection,
        {
            "ASK_QUESTIONS": "ask_questions",
            "PROCEED": "build_video_spec"
        }
    )
    
    # Linear generation flow ends at prompt_generator for Phase 9
    workflow.add_edge("build_video_spec", "scene_planner")
    workflow.add_edge("scene_planner", "prompt_generator")
    workflow.add_edge("prompt_generator", END)
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory, interrupt_before=["update_state"])
