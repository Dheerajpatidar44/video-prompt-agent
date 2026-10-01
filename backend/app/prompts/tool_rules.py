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
- Write in full, natural, cinematic sentences rather than keyword lists.
- Organize the prompt so these elements are identifiable, in roughly this order:
  subject, action, setting/context, camera behavior, visual style and mood, and
  audio (only if the specification includes dialogue, ambience, or sound).
- Camera and editing language is welcome and effective here (e.g. dolly, pan,
  tracking, crane, match cut) — use it when it serves the shot, not as decoration.
- Be concrete and observable rather than abstract: describe what the viewer would
  literally see, instead of vague qualities like "beautiful" or "epic."
- If the specification includes spoken dialogue, attribute it clearly to the
  speaker and describe how it's delivered (tone, pace), rather than just quoting
  the line in isolation.
- Each prompt should stay focused on a single continuous moment or beat rather
  than cramming in multiple unrelated actions.
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