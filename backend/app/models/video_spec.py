from pydantic import BaseModel
from typing import List, Optional, Any, Dict

class Scene(BaseModel):
    scene_number: int
    description: str
    characters: List[str] = []
    location: str
    camera_movement: Optional[str] = None
    lighting: Optional[str] = None

class VideoSpecification(BaseModel):
    project_id: str
    story: Optional[str] = None
    characters: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []
    products: List[Dict[str, Any]] = []
    actions: List[Dict[str, Any]] = []
    camera: List[Dict[str, Any]] = []
    lighting: List[Dict[str, Any]] = []
    visual_style: Optional[str] = None
    audio: Optional[str] = None
    timing: Optional[str] = None
    aspect_ratio: str = "16:9"
    continuity: Dict[str, Any] = {}
    reference_assets: List[str] = []
    special_requirements: List[str] = []
    scenes: List[Scene] = []
