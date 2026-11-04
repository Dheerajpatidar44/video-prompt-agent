"""Tool-specific prompt-writing rules (the single place where model behaviour is described).

How the Veo rules were written
- Facts about Veo 3.1 (clip lengths, 8 s at 1080p, native audio, prompt-size limit, no reference images on
  the variant we use) come from Google's official Veo documentation (Gemini API / Vertex AI).
- The five-part prompt formula, the camera / audio vocabulary and cinematic motion choreography follow Google Cloud's
  "Ultimate prompting guide for Veo 3.1".
- Rules marked "SYSTEM RULE" come from this project's own pipeline and validators, not from Google.

AI video tools change quickly: re-check these rules against the current official docs from time to time.
They intentionally avoid fixed word counts (length should come from what the shot needs); the only size limit
is the model's hard input ceiling in section 13.
"""

TOOL_RULES = {
    "Veo": """
==========================================================
GOOGLE VEO 3.1 - RULES FOR PLANNING SHOTS AND WRITING PROMPTS
==========================================================
Every shot you plan becomes ONE independent Veo clip generated from ONE prompt_text.
Veo remembers nothing between clips, cannot see any image, and generates sound together with the picture.

----------------------------------------------------------
1. VEO DURATION RULES (CRITICAL)
----------------------------------------------------------
- Veo 3.1 generates clips of exactly 4, 6 or 8 seconds (8 seconds is the only length at 1080p; this system renders at 720p by default, so 4, 6 and 8 are all usable).
- Every shot MUST have duration_seconds of 4, 6 or 8 (4s, 6s, or 8s). Never 1, 2, 3, 5, 7, and never above 8. Under NO circumstances output a shot shorter than 4 seconds.
- Reachable totals: every EVEN total from 4 seconds upward can be built from 4, 6 and 8 second clips. An ODD total (5, 7, 9, 11, 13, 15 ...) cannot be built exactly. Round it UP to the next even number (7 -> 8, 9 -> 10, 15 -> 16). NEVER exceed the target duration budget.
- Reference splits (prefer FEWER clips, and put clip boundaries on natural beat or scene boundaries):
    4s = 4 | 6s = 6 | 8s = 8 (or 4+4 when two distinct beats need separate clips)
    10s = 6+4 | 12s = 6+6 (or 4+4+4) | 14s = 6+4+4 or 8+6 | 16s = 8+8
    18s = 8+6+4 | 20s = 8+8+4 | 24s = 8+8+8 | 30s = 8+8+8+6
- HARD CEILING ON SHOT COUNT: Never create more clips than the reference split allows (for 8s target, MAXIMUM 2 clips: 4+4 or 1 clip: 8). If the script contains more beats than allowed clips, you MUST merge them into the allowed clips. Under no circumstances create 3 or 4 clips for an 8-second video.
- Beat allocation procedure:
    a) List every beat, action and spoken line of the script in order, with the time the script gives it (if any).
    b) A clip never crosses a scene or location change. A hard cut written in the script is a clip boundary.
    c) MERGE consecutive short beats of the SAME scene into one clip when their combined intended length fits the next allowed length (two 2s beats -> one 4s clip; two 3s beats -> one 6s clip). All merged beats must still appear, in order (see section 6).
    d) Never split one beat across two clips unless that beat is longer than 8 seconds.
    e) Prefer 6s or 8s for beats with dialogue or a slow reveal; prefer 4s for one quick action.
    f) Every beat of the script is used exactly once: nothing skipped, nothing repeated.
- Dialogue fit: usable speech time is the clip length minus about 1 second (lead-in and tail) at roughly 2.5 words per second. A 4s clip holds about 7 spoken words, a 6s clip about 12, an 8s clip about 17. If a line is longer, use a longer clip or split the line at a sentence or phrase boundary across consecutive clips. Never paraphrase, shorten or invent dialogue to make it fit.

----------------------------------------------------------
2. VEO PROMPT FORMULA
----------------------------------------------------------
Build every prompt_text from these parts, in this order, as flowing natural sentences (not a tag list):
  [Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance] + [Audio]
  (Camera Movement & Framing) + (Subject Appearance) + (Continuous Action) + (Setting & Environment) + (Lighting & Atmosphere & Style) + (Sound)
- CINEMATOGRAPHY: shot size, camera angle, the ONE camera movement (or "locked-off, no movement"), its speed, and where focus sits.
- SUBJECT: who or what is in frame, using the full continuity anchor description (section 4).
- ACTION: the single continuous action with its start state, its motion, and its end state (section 5).
- CONTEXT: location, foreground / midground / background layers, time of day, props, atmosphere (dust, haze, reflections).
- STYLE & AMBIANCE: light source, direction and quality, colour palette, mood, surface texture, overall look.
- AUDIO: dialogue, voiceover, sound effects and ambient sound for exactly this clip (section 7).
Every part that matters to the shot must be present. Extra words must add visual or audio information; never repeat the same fact twice.

----------------------------------------------------------
3. CINEMATIC CAMERA VOCABULARY & OPTICS
----------------------------------------------------------
- Shot size: extreme close-up, close-up, medium close-up, medium shot, medium wide shot, wide / establishing shot, extreme wide shot.
- Angle: eye-level, low-angle, high-angle, overhead / top-down, over-the-shoulder, point-of-view, tilted (Dutch) angle.
- Movement (ONE primary movement per clip, with speed and start/end): locked-off static, slow push-in (dolly-in), pull-back (dolly-out), tracking / following, lateral slide, pan left or right, tilt up or down, crane up or down, orbit / arc around the subject, handheld (only when the script asks for a UGC or documentary feel), aerial / drone, whip pan, rack focus.
- Focus and lens effects, described QUALITATIVELY: shallow depth of field, deep focus, soft out-of-focus background, macro detail, wide-angle expansive framing, compressed telephoto look, gentle optical falloff.
- State motion plainly: "the camera stays locked off and does not move" is a valid and often best instruction.
- Describe the camera as an unseen observer. Do not show a phone, camera, tripod or crew in frame unless the script requires it.
- DO NOT output numeric camera parameters: no focal lengths in millimetres, no f-stop values, no ISO, no shutter speeds, no sensor sizes, no "4K / 8K". An automated validator rejects such prompts. Use the qualitative phrases above instead.
- Avoid empty buzzwords such as "cinematic quality", "hyper-realistic", "masterpiece", "best quality".

----------------------------------------------------------
4. SUBJECT AND CONTINUITY ANCHORS
----------------------------------------------------------
- Veo has no memory, so identity is held only by words. Copy the continuity-bible anchor description of each character, product and location WORD FOR WORD into every prompt where it appears. Do not shorten it and do not swap synonyms ("beige" in one prompt and "oatmeal" in the next).
- A strong anchor covers: apparent age group, hair colour / length / style, skin tone, build, expression and posture, every garment item by item with colour, fabric, fit and how it moves, plus accessories and footwear. Only use attributes that are stated in the specification; do not invent new ones.
- Names do not help the model. Describe the person ("a woman in her late twenties with ...") and never use real public figures' names.
- Keep to one or two characters per clip; give each a distinct descriptor and a clear position (left / right, foreground / background).
- Describe fabric and hair physics when they move (satin skirt ripples with each step, hair sways).

----------------------------------------------------------
5. ACTION AND MOTION - SINGLE CONTINUOUS MOTION BEAT
----------------------------------------------------------
- Each 4s / 6s / 8s shot describes ONE coherent, fluid beat: start state, then the motion, then the end state. Add at most small secondary motions (a blink, a breath, fabric sway).
- Give every action a speed and a direction ("slowly", "steadily", "toward the camera", "left to right"). Slow, deliberate motion renders more reliably than fast or chaotic motion.
- Keep hand-and-object interactions simple and slow, and name the grip ("both hands around the handles"). Avoid counted or repeated actions, juggling, intricate finger work, and crowds.
- Reflections (mirrors, glass, water) are unreliable. If one is in frame, say exactly what it shows, or choose a framing that avoids it.
- Every script beat assigned to the clip must be visible in the described action, in the script's order.
- Avoid hard cuts inside a single prompt unless the script explicitly demands one; describe a continuous, uninterrupted flow instead.

----------------------------------------------------------
6. MULTI-BEAT CLIPS AND CONTINUOUS CHOREOGRAPHY
----------------------------------------------------------
- When a merged clip holds two or more consecutive narrative beats within its 4s, 6s, or 8s duration, do NOT use bracketed timestamps (such as [00:00-00:02]) or numeric timer tags. Brackets risk prompting the model to render digital timers or clocks onto the screen.
- Instead, describe the multi-beat progression as ONE continuous, fluid cinematic choreography using natural temporal phrasing:
    "The shot opens with [first action/beat] ... as [the camera transitions / subject smoothly shifts] into [second action/beat] ... before settling on [closing resolution/state]."
- Maintain seamless visual continuity: state the subject anchor and environment once at the beginning, letting the physical actions flow sequentially from one to the next without hard cuts or disjointed jumps.
- If dialogue occurs during a specific part of the shot, embed it naturally at that point in the chronological description (e.g. "As she slows beside the cafe, she turns to say: 'exact line'").
- The camera movement should evolve smoothly across beats (e.g. from an initial tracking follow into a gentle pan-tilt or slow push-in).

----------------------------------------------------------
7. AUDIO, DIALOGUE AND VOICEOVER
----------------------------------------------------------
- Veo 3.1 always generates synchronised audio, so control it explicitly instead of leaving it to chance.
- On-screen dialogue: write  <speaker described visually> says: "exact line" - then the delivery (tone, pace, emotion) and, when the mouth is visible, that the lips are accurately synchronised. Keep the line verbatim and in the script's own language.
- Voiceover (off-screen narration): write  Off-screen voiceover in a <voice description> says: "exact line"  and state that the person on screen does not speak and keeps their mouth closed.
- Keep a speaker's voice description (pitch, timbre, pace, accent) identical in every clip where they speak, using the specification's voice profile if one exists. Do not invent a voice if none is given.
- Sound effects: name the concrete source ("soft footsteps on a wooden floor", "light leather bag rustle"). Ambient sound that naturally matches the location and the visible actions (room tone, footsteps) is allowed.
- Music, distinctive effects and any dialogue that are not in the specification must NOT be added. If the script gives no music, state "no music".
- Never ask for subtitles or captions; the negative constraints exclude on-screen text.

----------------------------------------------------------
8. CONTINUITY ACROSS INDEPENDENT CLIPS (SYSTEM RULE)
----------------------------------------------------------
- Clips are generated separately, so continuity is built only with text. Use identical anchor wording, identical location and lighting wording, and the same colour palette and time of day for consecutive clips of one scene.
- Write the opening state of each clip so it matches the closing state of the previous clip (same pose, same position in the room, same objects in hand).
- Record in continuity_requirements: one "STARTS:" line (the opening state), one "ENDS:" line (the closing state), and "LOCK:" lines for wardrobe, props, lighting and time of day.
- At a scene change re-establish the new location completely in words.

----------------------------------------------------------
9. WHAT VEO CANNOT SEE (SYSTEM RULE)
----------------------------------------------------------
- No reference image is attached to the model. NEVER write "from the reference image", "as in Image 1", "the provided logo", "as shown", "the attached product". Every prompt must be self-contained: translate what you know about an image into explicit words.
- Legible text, logos, labels and screens are unreliable. Describe their shape, colour and placement instead of depending on exact lettering. If the script requires an exact logo or text, describe it as faithfully as you can and add to continuity_requirements: "exact logo / text fidelity requires a post-production overlay".

----------------------------------------------------------
10. CONTENT SAFETY
----------------------------------------------------------
- A blocked clip wastes time. Avoid names of real public figures, copyrighted characters, graphic violence, sexual or explicit content, hateful content, and minors in unsafe or sensitive situations. Keep fashion, lifestyle and product language neutral and professional.

----------------------------------------------------------
11. NEGATIVE CONSTRAINTS FOR VEO
----------------------------------------------------------
- Write negative_constraints as a short comma-separated list of the unwanted visual or audio elements themselves ("extra people, subtitles, watermark, text overlays, warped hands, morphing clothing, camera shake, flicker").
- Do NOT use instruction wording such as "no ...", "do not ...", "without ...". Name the thing to avoid.
- Make the list specific to this shot (at most about 12 items), never a generic block copied between shots, and never list something the script requires (no "dialogue" when the shot has dialogue).

----------------------------------------------------------
12. LIGHTING & ATMOSPHERE AND STYLE LANGUAGE
----------------------------------------------------------
- Specify observable lighting: its source, direction, softness and colour in words (soft diffused morning window light from camera left, golden-hour rim light, high-contrast chiaroscuro, volumetric haze).
- Name texture and look concretely: photorealistic live-action footage, natural skin texture, soft analog film grain, glossy satin highlights. Use the same style words in every clip of the video so the look stays consistent.

----------------------------------------------------------
13. PROMPT SIZE (SYSTEM RULE)
----------------------------------------------------------
- Veo accepts roughly 1,024 tokens of text input. Keep every prompt_text, including its audio lines, under about 3,000 characters.
- Detail is measured by coverage of the parts in section 2, not by length. If space runs short, keep in this order: action, subject anchor, camera, setting, lighting, style, extra audio detail.

----------------------------------------------------------
14. SELF-CHECK BEFORE YOU ANSWER
----------------------------------------------------------
- Each duration_seconds is 4, 6 or 8; the shots add up to the scene, and the scenes add up to total_duration.
- Every script beat appears exactly once and in order; merged beats use fluid chronological transitions (no bracketed timestamps).
- Anchor descriptions are copied word for word; STARTS / ENDS / LOCK lines are present.
- One primary camera movement; no numeric camera parameters; no references to images; no "no / do not" wording in negative_constraints.
- Dialogue is verbatim, attributed to its speaker, and fits the clip; no unrequested music.
- The prompt stays under the size ceiling.
""",
}


DEFAULT_TOOL = "Veo"


def get_tool_rules(tool: str = DEFAULT_TOOL) -> str:
    """Return the prompt-writing rules for the requested tool (falls back to Veo)."""
    return TOOL_RULES.get(tool, TOOL_RULES[DEFAULT_TOOL])