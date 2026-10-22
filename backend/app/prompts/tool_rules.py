"""Tool-specific prompt-writing rules.

These describe HOW each model prefers information to be structured and phrased.
They intentionally avoid fixed word counts — a prompt's length should come from
what the shot actually needs, not from an arbitrary number. They also avoid
narrow, single-use-case language so the same rules apply whether the script is
a product ad, a narrative scene, a fashion piece, or anything else.

Note: AI video tool behavior changes frequently. Revisit these against each
tool's current official prompting guide periodically.
"""

TOOL_RULES = {
    "Veo": """
- VEO DURATION RULES (CRITICAL):
  * Google Veo 3.1 Lite generates clips strictly in fixed durations: 4, 6, or 8 seconds (at 720p; 8 seconds only at 1080p).
  * Arbitrary durations (1s, 2s, 3s, 5s, 7s) are NOT natively supported by Veo.
  * Every shot MUST strictly have a duration of 4s, 6s, or 8s. Under NO circumstances output a shot < 4s.
  * Plan shot combinations so they sum to the scene and total video duration:
    - 4s video: exactly 1 shot of 4s. If the script describes multiple fast actions or rapid scenes within 4s (e.g., two 2s beats), MERGE them into 1 continuous 4s prompt where Action 1 flows seamlessly into Action 2.
    - 6s video: 1 shot of 6s
    - 8s video: 1 shot of 8s (or 2 shots of 4s)
    - 10s video: 2 shots (e.g., Shot 1 = 6s, Shot 2 = 4s)
    - 12s video: 3 shots of 4s (or 2 shots of 6s)
    - 14s video: 3 shots (e.g., Shot 1 = 6s, Shot 2 = 4s, Shot 3 = 4s)
    - 16s video: 2 shots of 8s (or 4 shots of 4s)
    - For any non-standard target, build strictly from 4s/6s/8s blocks and merge short beats so no individual prompt is ever under 4 seconds.
- VEO PROMPT FORMULA:
  Structure each prompt following Veo's optimal prompt formula:
  [Camera Movement & Framing] + [Subject Appearance & Continuous Action] + [Setting & Environment] + [Lighting & Atmosphere] + [Cinematic Style & Mood]
- SINGLE CONTINUOUS MOTION BEAT:
  Each 4s/6s/8s shot must describe ONE coherent, fluid action beat. If multiple short actions occur within a 4s/6s/8s shot, describe them as one seamless, uninterrupted camera movement transition. Avoid disjointed hard cuts within a single shot prompt.
- CINEMATIC CAMERA VOCABULARY:
  Use concrete camera movement terms Veo excels at: slow push-in, dolly tracking, sweeping pan, crane up/down, static locked-off shot, low-angle dynamic tracking. Avoid abstract buzzwords like "cinematic quality" or "hyper-realistic".
- LIGHTING & ATMOSPHERE:
  Explicitly specify observable lighting and texture: golden hour rim lighting, soft diffused morning daylight, high-contrast chiaroscuro, volumetric haze, photorealistic 35mm film grain.
- Write in full, natural, flowing cinematic sentences rather than comma-separated tag lists.
- If the specification includes spoken dialogue, attribute it clearly to the speaker and describe how it is delivered (tone, pacing, expression).
""",

    "Runway": """
- Lead with motion: describe what changes or moves during the shot before
  describing what things look like.
- If the shot will be generated from a reference image, do not re-describe
  static visual details the image already shows (appearance, outfit, static
  composition) — focus the prompt entirely on the movement and change over time.
  If there is no reference image, briefly establish the essential visual context
  first, then describe the motion.
- Use plain, direct, descriptive sentences rather than commands or conversational
  phrasing.
- Prefer positive descriptions of what should happen over negative instructions
  of what should not happen.
- Introduce one clear motion idea at a time (subject motion, camera motion,
  scene motion) rather than layering many competing movements into one prompt.
- Camera direction is supported and useful (e.g. zoom, pan, tilt, tracking) when
  the specification calls for a specific camera behavior.
""",

    "Kling": """
- Structure the prompt around: subject, the subject's movement/action, the scene
  it takes place in, and then camera language, lighting, and atmosphere.
- Replace vague or subjective descriptors ("nice lighting," "professional look")
  with concrete, specific alternatives (e.g. "soft warm backlight with gentle
  shadows" instead of "nice lighting").
- State camera movement explicitly and specifically (e.g. "slow dolly-in,"
  "static wide shot") rather than general terms like "cinematic movement,"
  which tend to produce inconsistent results.
- If the shot spans a distinct sequence of beats, it can help to lay them out
  in order within the prompt rather than describing the whole shot as one blend.
- If the specification includes dialogue, attribute it to the specific
  character and specify tone/pace/delivery alongside the line.
""",
}


DEFAULT_TOOL = "Veo"


def get_tool_rules(tool: str) -> str:
    """Return the prompt-writing rules for a given tool, falling back to the
    default tool if the requested one isn't recognized."""
    return TOOL_RULES.get(tool, TOOL_RULES[DEFAULT_TOOL])