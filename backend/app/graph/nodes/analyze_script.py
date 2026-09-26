"""Combined initial analysis node.

ONE LLM call produces: script analysis + gap detection + question generation.
This replaces the old analyze_script → detect_gaps → ask_questions chain.
"""
import uuid
import logging
from app.graph.state import AgentState
from app.schemas.agent import AgentStatus, GapStatus, Importance, QuestionStatus
from app.schemas.script import InitialAnalysisResult
from app.llm.claude_client import llm_service, LLMException
from app.prompts.initial_analysis import INITIAL_ANALYSIS_PROMPT

logger = logging.getLogger(__name__)


async def analyze_script(state: AgentState) -> AgentState:
    """ONE LLM call: analysis + gaps + questions."""
    script_text = state.get("original_script", "")
    if not script_text.strip():
        return {
            **state,
            "status": AgentStatus.ERROR,
            "error": "No script provided for analysis.",
        }

    thread_id = state.get("project_id", "")
    prompt = INITIAL_ANALYSIS_PROMPT.format(script=script_text)

    try:
        result = await llm_service.generate_structured(
            prompt,
            InitialAnalysisResult,
            operation="initial_analysis",
            thread_id=thread_id,
        )
    except LLMException as e:
        return {**state, "status": AgentStatus.ERROR, "error": str(e)}

    # ---- Deterministic post-processing in Python ----

    # 1. Extract analysis dict (everything except gaps/questions)
    analysis_dict = result.model_dump(exclude={"gaps", "questions"})

    # 2. Process gaps: deduplicate, sort, assign status
    seen_gap_keys = set()
    unique_gaps = []
    for g in result.gaps:
        key = (g.category, g.title.lower().strip())
        if key not in seen_gap_keys:
            seen_gap_keys.add(key)
            if not g.status:
                g.status = GapStatus.OPEN
            unique_gaps.append(g)

    priority_map = {
        Importance.CRITICAL: 0,
        Importance.IMPORTANT: 1,
        Importance.OPTIONAL: 2,
        Importance.INFERABLE: 3,
    }
    unique_gaps.sort(key=lambda g: priority_map.get(g.importance, 99))

    # 3. Process questions: validate gap_ids, deduplicate, assign IDs
    valid_gap_ids = {g.id for g in unique_gaps}
    eligible_gaps = [
        g
        for g in unique_gaps
        if g.importance in (Importance.CRITICAL, Importance.IMPORTANT)
        and g.status == GapStatus.OPEN
    ]

    processed_questions = []
    seen_q_texts = set()

    for q in result.questions:
        # Validate gap_ids
        valid_q_gaps = [gid for gid in q.gap_ids if gid in valid_gap_ids]
        if not valid_q_gaps:
            logger.warning(f"LLM generated invalid gap_ids {q.gap_ids}. Falling back to all eligible gaps.")
            valid_q_gaps = [g.id for g in eligible_gaps]

        q.gap_ids = valid_q_gaps
        q.id = str(uuid.uuid4())
        q.status = QuestionStatus.PENDING
        q.round_number = 0

        # Upgrade low-priority questions
        if q.priority in (Importance.OPTIONAL, Importance.INFERABLE):
            q.priority = Importance.IMPORTANT

        # Deduplicate
        txt = q.question.lower().strip()
        if txt not in seen_q_texts:
            seen_q_texts.add(txt)
            processed_questions.append(q)

    # Sort questions by priority
    processed_questions.sort(key=lambda q: priority_map.get(q.priority, 99))

    # 4. Determine status
    has_questions = len(processed_questions) > 0
    has_eligible = len(eligible_gaps) > 0

    if has_questions and has_eligible:
        status = AgentStatus.WAITING_FOR_USER
    else:
        status = AgentStatus.ANALYZING

    return {
        **state,
        "analysis": analysis_dict,
        "gaps": unique_gaps,
        "questions": processed_questions,
        "status": status,
        "error": None,
    }
