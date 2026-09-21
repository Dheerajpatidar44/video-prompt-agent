from pydantic import BaseModel
from typing import List

class PromptBase(BaseModel):
    scene_number: int
    prompt_text: str

class Prompt(PromptBase):
    id: str
    project_id: str
