from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from app.graph.state import AgentState
from app.graph.nodes.initialize_state import initialize_state
from app.graph.nodes.analyze_script import analyze_script
from app.graph.nodes.update_state import update_state
from app.graph.nodes.re_analyze import re_analyze
from app.graph.nodes.build_video_spec import build_video_spec
from app.graph.nodes.generate_scenes_and_prompts import generate_scenes_and_prompts
from app.graph.routing import route_after_analysis


# Every custom Enum/BaseModel class found across app/schemas/*.py
# (confirmed via: Select-String -Path "app\schemas\*.py" -Pattern "class .*BaseModel|class .*Enum")
ALLOWED_CHECKPOINT_TYPES = [
    # app/schemas/agent.py
    ("app.schemas.agent", "Importance"),
    ("app.schemas.agent", "GapStatus"),
    ("app.schemas.agent", "QuestionStatus"),
    ("app.schemas.agent", "AnswerType"),
    ("app.schemas.agent", "GapCategory"),
    ("app.schemas.agent", "Gap"),
    ("app.schemas.agent", "GapDetectionResult"),
    ("app.schemas.agent", "Question"),
    ("app.schemas.agent", "QuestionGenerationResult"),
    ("app.schemas.agent", "ReAnalysisResult"),
    ("app.schemas.agent", "Answer"),
    ("app.schemas.agent", "AgentStatus"),

    # app/schemas/generated_prompt.py
    ("app.schemas.generated_prompt", "PromptStatus"),
    ("app.schemas.generated_prompt", "GeneratedPrompt"),
    ("app.schemas.generated_prompt", "PromptSet"),

    # app/schemas/generation.py
    ("app.schemas.generation", "GeneratedShotPlan"),
    ("app.schemas.generation", "GeneratedScenePlan"),
    ("app.schemas.generation", "GeneratedPromptItem"),
    ("app.schemas.generation", "GenerationResult"),

    # app/schemas/scene_plan.py
    ("app.schemas.scene_plan", "TransitionType"),
    ("app.schemas.scene_plan", "NarrativeRole"),
    ("app.schemas.scene_plan", "PlanStatus"),
    ("app.schemas.scene_plan", "ValidationIssue"),
    ("app.schemas.scene_plan", "ShotPlan"),
    ("app.schemas.scene_plan", "ScenePlan"),
    ("app.schemas.scene_plan", "MasterScenePlan"),

    # app/schemas/script.py
    ("app.schemas.script", "ScriptDocument"),
    ("app.schemas.script", "ScriptAnalysis"),
    ("app.schemas.script", "InitialAnalysisResult"),

    # app/schemas/specification.py
    ("app.schemas.specification", "SpecSource"),
    ("app.schemas.specification", "SpecStatus"),
    ("app.schemas.specification", "ReferenceAssetType"),
    ("app.schemas.specification", "ReferenceAsset"),
    ("app.schemas.specification", "SourcedField"),
    ("app.schemas.specification", "CharacterSpec"),
    ("app.schemas.specification", "LocationSpec"),
    ("app.schemas.specification", "ProductSpec"),
    ("app.schemas.specification", "ActionSpec"),
    ("app.schemas.specification", "CameraSpec"),
    ("app.schemas.specification", "LightingSpec"),
    ("app.schemas.specification", "CompositionSpec"),
    ("app.schemas.specification", "VisualStyleSpec"),
    ("app.schemas.specification", "DialogueSpec"),
    ("app.schemas.specification", "AudioSpec"),
    ("app.schemas.specification", "OutputRequirements"),
    ("app.schemas.specification", "ContinuityBible"),
    ("app.schemas.specification", "UnresolvedItem"),
    ("app.schemas.specification", "ConstraintSpec"),
    ("app.schemas.specification", "VideoSpecification"),
]


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

    # After re-analysis, route again (same routing logic as after analyze_script)
    workflow.add_conditional_edges(
        "re_analyze",
        route_after_analysis,
        {
            "WAIT_FOR_ANSWERS": "update_state",  # loop back to wait for more answers
            "PROCEED": "build_video_spec"
        }
    )

    # Generation: spec → combined scene+prompt generation → END
    workflow.add_edge("build_video_spec", "generate")
    workflow.add_edge("generate", END)

    serde = JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_CHECKPOINT_TYPES)
    memory = MemorySaver(serde=serde)
    return workflow.compile(checkpointer=memory, interrupt_before=["update_state"])