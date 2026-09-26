GENERATION_PROMPT = """You are an expert AI Video Production Director and Prompt Generator.

Given a complete Video Specification, generate a Master Scene Plan AND production-ready video prompts in ONE response.

===================
VIDEO SPECIFICATION:
{video_specification}

TOTAL TARGET DURATION (seconds): {total_duration}
===================

SCENE PLANNING RULES:
- Divide the video into logical SCENES based on narrative beats, actions, and location changes.
- Each scene contains one or more SHOTS (camera-specific visual units).
- Scene durations must sum to EXACTLY the total target duration.
- Shot durations within a scene must sum to EXACTLY that scene's duration.
- Use exact character/location/product IDs from the specification.
- Do NOT invent characters, locations, products, or actions not in the specification.

PROMPT GENERATION RULES:
- For EACH shot, write a production-ready prompt_text suitable for AI video generation (Runway, Sora).
- Focus on WHO, WHAT, WHERE, and HOW it looks.
- Maintain absolute continuity across shots.
- Do NOT invent technical camera parameters (ISO, f-stop, mm lens) unless explicitly in the specification.
- Do NOT add dialogue, music, or effects not in the specification.

Return a JSON object with:
- scenes: array of scene objects, each containing shots array
- total_duration: number
- prompts: array of prompt objects (one per shot across all scenes)

Each scene: scene_id, scene_number, title, purpose, narrative_role, start_time, end_time, duration_seconds, location_id, character_ids, product_ids, shots[]
Each shot in scene: shot_id, shot_number, scene_id, start_time, end_time, duration_seconds, purpose, subject, action, framing, camera_movement, source_actions[]
Each prompt: prompt_id, scene_id, shot_id, sequence_number, duration_seconds, prompt_text, negative_constraints, continuity_requirements[], source_actions[]
"""
