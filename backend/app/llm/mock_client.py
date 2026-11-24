"""Mock LLM Service for Testing, Offline development, and CI pipelines.

Subclasses BaseLLMService and produces valid mock Pydantic responses
for all production schemas without requiring external API access or credentials.
"""
import logging
from typing import TypeVar, Type, Optional, List
from pydantic import BaseModel

from app.llm.base import BaseLLMService
from app.schemas.script import InitialAnalysisResult
from app.schemas.specification import VideoSpecification, OutputRequirements, SpecStatus
from app.schemas.generation import GenerationResult, GeneratedScenePlan, GeneratedShotPlan, GeneratedPromptItem
from app.schemas.agent import ReAnalysisResult, Gap, GapCategory, Importance, GapStatus
from app.prompts.prompt_patch import PromptPatchResult

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class MockLLMService(BaseLLMService):
    """Deterministically generates mock Pydantic outputs for tests."""

    def __init__(self):
        self.call_history: List[dict] = []

    async def generate_structured(
        self,
        prompt: str,
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        self.call_history.append({
            "operation": operation,
            "thread_id": thread_id,
            "prompt": prompt,
            "system_instruction": system_instruction,
            "schema": schema.__name__,
            "with_images": False,
        })
        logger.info(f"MockLLMService: generate_structured for {operation} (schema={schema.__name__})")
        return self._create_mock_instance(schema, thread_id)

    async def generate_structured_with_images(
        self,
        prompt: str,
        image_urls: List[str],
        schema: Type[T],
        *,
        system_instruction: Optional[str] = None,
        operation: str = "unknown",
        thread_id: str = "",
        max_tokens: Optional[int] = None,
    ) -> T:
        self.call_history.append({
            "operation": operation,
            "thread_id": thread_id,
            "prompt": prompt,
            "image_urls": image_urls,
            "system_instruction": system_instruction,
            "schema": schema.__name__,
            "with_images": True,
        })
        logger.info(f"MockLLMService: generate_structured_with_images for {operation} (schema={schema.__name__})")
        return self._create_mock_instance(schema, thread_id)

    async def close(self) -> None:
        pass

    def _create_mock_instance(self, schema: Type[T], thread_id: str) -> T:
        if schema == InitialAnalysisResult:
            return InitialAnalysisResult(
                story_objective="Mock story objective",
                story_summary="Mock script summary for testing",
                gaps=[],
                questions=[],
            )

        if schema == VideoSpecification:
            return VideoSpecification(
                project_id=thread_id or "mock_project",
                story_summary="Mock video spec summary",
                output_requirements=OutputRequirements(duration_seconds=10, aspect_ratio="16:9"),
                status=SpecStatus.READY,
            )

        if schema == GenerationResult:
            return GenerationResult(
                scenes=[
                    GeneratedScenePlan(
                        scene_id="scene_1",
                        scene_number=1,
                        title="Mock Scene",
                        purpose="Establishing shot",
                        narrative_role="ACTION",
                        start_time=0.0,
                        end_time=4.0,
                        duration_seconds=4.0,
                        shots=[
                            GeneratedShotPlan(
                                shot_id="shot_1",
                                shot_number=1,
                                scene_id="scene_1",
                                start_time=0.0,
                                end_time=4.0,
                                duration_seconds=4.0,
                                purpose="Establishing shot",
                                subject="Mock subject",
                                action="Subject looks at the camera",
                            )
                        ],
                    )
                ],
                total_duration=4.0,
                prompts=[
                    GeneratedPromptItem(
                        prompt_id="prompt_1",
                        scene_id="scene_1",
                        shot_id="shot_1",
                        sequence_number=1,
                        duration_seconds=4.0,
                        prompt_text="Cinematic establishing shot of mock scene.",
                    )
                ],
            )

        if schema == ReAnalysisResult:
            return ReAnalysisResult(
                gaps=[
                    Gap(
                        id="gap_1",
                        category=GapCategory.CHARACTER,
                        importance=Importance.IMPORTANT,
                        description="Mock character gap",
                        evidence="Mock evidence",
                        status=GapStatus.RESOLVED,
                    )
                ],
                questions=[],
            )

        if schema == PromptPatchResult:
            return PromptPatchResult(
                prompt_text="Patched cinematic prompt text with correct lighting.",
                negative_constraints=None,
            )

        # Fallback for generic schemas: construct with defaults or empty dict
        try:
            return schema()
        except Exception:
            return schema.model_construct()

