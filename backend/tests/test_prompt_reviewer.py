"""Tests for the deterministic Prompt Reviewer Agent.

Validates that the reviewer correctly identifies structural, content quality,
and continuity issues, that auto-fix resolves fixable problems, and that
ReviewReport.status is ALWAYS one of the three allowed passing values.
"""
import pytest
from unittest.mock import MagicMock
from math import isclose

from app.schemas.generated_prompt import GeneratedPrompt, PromptSet, PromptStatus
from app.schemas.scene_plan import (
    MasterScenePlan, ScenePlan, ShotPlan, PlanStatus, NarrativeRole, TransitionType,
)
from app.schemas.specification import (
    VideoSpecification, OutputRequirements, CharacterSpec, LocationSpec, ProductSpec,
    ContinuityBible,
)
from app.schemas.review_report import ReviewStatus, IssueSeverity, IssueCategory
from app.validators.prompt_reviewer import PromptReviewer


# ---------------------------------------------------------------------------
# Helpers to build minimal valid test data
# ---------------------------------------------------------------------------

def _make_spec(
    characters=None, locations=None, products=None
) -> VideoSpecification:
    return VideoSpecification(
        project_id="test-proj",
        characters=characters or [
            CharacterSpec(id="char_hero", name="Hero"),
        ],
        locations=locations or [
            LocationSpec(id="loc_studio", name="Studio"),
        ],
        products=products or [
            ProductSpec(id="prod_watch", name="Luxury Watch"),
        ],
        output_requirements=OutputRequirements(duration_seconds=10),
    )


def _make_scene_plan(scenes=None) -> MasterScenePlan:
    if scenes is None:
        scenes = [
            ScenePlan(
                scene_id="scene_01",
                scene_number=1,
                title="Opening",
                purpose="Intro",
                narrative_role=NarrativeRole.ESTABLISHING,
                start_time=0.0,
                end_time=5.0,
                duration_seconds=5.0,
                location_id="loc_studio",
                character_ids=["char_hero"],
                product_ids=["prod_watch"],
                shots=[
                    ShotPlan(
                        shot_id="shot_01", shot_number=1, scene_id="scene_01",
                        start_time=0.0, end_time=2.5, duration_seconds=2.5,
                        purpose="Establish", subject="Hero", action="walks in",
                    ),
                    ShotPlan(
                        shot_id="shot_02", shot_number=2, scene_id="scene_01",
                        start_time=2.5, end_time=5.0, duration_seconds=2.5,
                        purpose="Reveal", subject="Watch", action="close-up",
                    ),
                ],
            ),
            ScenePlan(
                scene_id="scene_02",
                scene_number=2,
                title="Close",
                purpose="End",
                narrative_role=NarrativeRole.ENDING,
                start_time=5.0,
                end_time=10.0,
                duration_seconds=5.0,
                location_id="loc_studio",
                character_ids=["char_hero"],
                product_ids=[],
                shots=[
                    ShotPlan(
                        shot_id="shot_03", shot_number=3, scene_id="scene_02",
                        start_time=5.0, end_time=10.0, duration_seconds=5.0,
                        purpose="Finale", subject="Hero", action="smiles",
                    ),
                ],
            ),
        ]
    return MasterScenePlan(
        scenes=scenes,
        total_duration=10.0,
        status=PlanStatus.READY,
    )


def _make_prompt_set(prompts=None) -> PromptSet:
    if prompts is None:
        prompts = [
            GeneratedPrompt(
                prompt_id="p1", scene_id="scene_01", shot_id="shot_01",
                sequence_number=1, duration_seconds=2.5,
                prompt_text="A tall man in a dark suit walks through a dimly lit studio with polished concrete floors and soft amber overhead lighting.",
                negative_constraints="morphing, extra limbs, text overlays, watermarks",
                continuity_requirements=["dark suit on hero"],
            ),
            GeneratedPrompt(
                prompt_id="p2", scene_id="scene_01", shot_id="shot_02",
                sequence_number=2, duration_seconds=2.5,
                prompt_text="Close-up of a luxury watch on the man's wrist, the dial catching warm amber light, shallow depth of field with soft bokeh in the background.",
                negative_constraints="blurry watch face, extra fingers, morphing",
            ),
            GeneratedPrompt(
                prompt_id="p3", scene_id="scene_02", shot_id="shot_03",
                sequence_number=3, duration_seconds=5.0,
                prompt_text="The hero stands in the center of the studio, warm lighting casting a golden glow across his face as he smiles confidently toward the camera.",
                negative_constraints="morphing, bad anatomy, flickering",
            ),
        ]
    return PromptSet(prompts=prompts, total_duration=10.0)


# ---------------------------------------------------------------------------
# Test: Structurally valid set → PASSED
# ---------------------------------------------------------------------------
class TestPassingReview:
    def test_valid_prompt_set_passes(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()

        reviewer = PromptReviewer(spec, plan, pset, "A man walks in.")
        report = reviewer.run_all_checks()

        assert report.status == ReviewStatus.PASSED
        assert len(report.issues) == 0
        assert report.stats["total_prompts"] == 3


# ---------------------------------------------------------------------------
# Test: Duration mismatch → BLOCKER STRUCTURAL
# ---------------------------------------------------------------------------
class TestStructuralChecks:
    def test_scene_duration_mismatch(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        # Corrupt scene duration so shots don't sum to it
        plan.scenes[0].duration_seconds = 99.0

        pset = _make_prompt_set()
        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        structural_blockers = [
            i for i in report.issues
            if i.category == IssueCategory.STRUCTURAL and i.severity == IssueSeverity.BLOCKER
        ]
        assert len(structural_blockers) > 0
        assert any("duration" in i.message.lower() for i in structural_blockers)

    def test_unknown_entity_id(self):
        spec = _make_spec(characters=[CharacterSpec(id="char_hero", name="Hero")])
        plan = _make_scene_plan()
        # Add an unknown character to scene
        plan.scenes[0].character_ids.append("char_unknown")

        pset = _make_prompt_set()
        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        entity_issues = [
            i for i in report.issues
            if "unknown character_id" in i.message.lower()
        ]
        assert len(entity_issues) > 0

    def test_duplicate_prompt_id(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()
        # Make two prompts share the same prompt_id
        pset.prompts[1].prompt_id = pset.prompts[0].prompt_id

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        dup_issues = [i for i in report.issues if "duplicate prompt_id" in i.message.lower()]
        assert len(dup_issues) > 0


# ---------------------------------------------------------------------------
# Test: Internal ID leakage → BLOCKER CONTENT_QUALITY, auto_fixable
# ---------------------------------------------------------------------------
class TestContentQuality:
    def test_internal_id_leakage_detected(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()
        # Inject an internal ID into prompt_text
        pset.prompts[0].prompt_text = "The hero from shot_02 walks through the studio."

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        leak_issues = [
            i for i in report.issues
            if i.category == IssueCategory.CONTENT_QUALITY
            and "internal id" in i.message.lower()
        ]
        assert len(leak_issues) > 0
        assert leak_issues[0].auto_fixable is True

    def test_placeholder_detected(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()
        pset.prompts[0].prompt_text = "TODO: write a better prompt for this shot."

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        placeholder_issues = [
            i for i in report.issues
            if "placeholder" in i.message.lower() or "incomplete" in i.message.lower()
        ]
        assert len(placeholder_issues) > 0

    def test_short_prompt_flagged(self):
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()
        pset.prompts[0].prompt_text = "A man walks in."

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        short_issues = [i for i in report.issues if "short" in i.message.lower()]
        assert len(short_issues) > 0
        assert short_issues[0].severity == IssueSeverity.WARNING


# ---------------------------------------------------------------------------
# Test: Continuity drift (Pure Python + rapidfuzz)
# ---------------------------------------------------------------------------
class TestContinuityDrift:
    def test_divergent_descriptors_flagged(self):
        """Two shots with same character but wildly different descriptors."""

        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()

        # Shot 1: blonde, blue, elegant
        pset.prompts[0].prompt_text = (
            "A tall blonde woman in an elegant blue gown stands in a luxurious marble "
            "ballroom under crystal chandeliers with warm golden light."
        )
        # Shot 3 (same char): brunette, red, casual — clearly divergent
        pset.prompts[2].prompt_text = (
            "A short brunette teenager in a casual red hoodie sits on a concrete "
            "sidewalk under harsh fluorescent streetlights eating pizza."
        )

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        drift_issues = [
            i for i in report.issues
            if i.category == IssueCategory.CONTINUITY_DRIFT
        ]
        assert len(drift_issues) > 0
        assert any("conflicting core attributes" in i.message for i in drift_issues)

    def test_similar_descriptors_not_flagged(self):
        """Two shots with same character and consistent descriptors should pass."""
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()

        # Shot 1
        pset.prompts[0].prompt_text = (
            "A tall blonde woman in an elegant blue gown stands in a luxurious marble "
            "ballroom under crystal chandeliers."
        )
        # Shot 3 (same char): slightly different phrasing but consistent core attributes
        pset.prompts[2].prompt_text = (
            "The tall blonde woman wearing her blue gown walks across the marble floor."
        )

        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()

        drift_issues = [
            i for i in report.issues
            if i.category == IssueCategory.CONTINUITY_DRIFT
        ]
        assert len(drift_issues) == 0


# ---------------------------------------------------------------------------
# Test: ReviewReport.status is ALWAYS one of the three allowed values
# ---------------------------------------------------------------------------
class TestReportStatusInvariant:
    def test_status_always_valid(self):
        """No matter what issues exist, status must be one of the three passing values."""
        allowed = {ReviewStatus.PASSED, ReviewStatus.PASSED_WITH_FIXES, ReviewStatus.PASSED_WITH_WARNINGS}

        # Test with valid data
        spec = _make_spec()
        plan = _make_scene_plan()
        pset = _make_prompt_set()
        reviewer = PromptReviewer(spec, plan, pset, "")
        report = reviewer.run_all_checks()
        assert report.status in allowed

        # Test with broken data
        plan2 = _make_scene_plan()
        plan2.scenes[0].duration_seconds = 99.0
        pset2 = _make_prompt_set()
        pset2.prompts[0].prompt_text = "shot_02 leaked ID and TODO placeholder"
        reviewer2 = PromptReviewer(spec, plan2, pset2, "")
        report2 = reviewer2.run_all_checks()
        assert report2.status in allowed
