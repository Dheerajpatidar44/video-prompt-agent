"""Tool-specific prompt-writing rules (the single place where video model behaviour is described).

How the Veo rules were written:
- Facts about Google Veo 3.1 (clip lengths, resolutions, native audio, input ceiling, reference-asset constraints)
  come from Google's official Veo 3.1 documentation (Gemini API / Vertex AI).
- The prompt formula, camera/audio vocabulary, and continuous motion choreography follow Google Cloud's
  "Ultimate prompting guide for Veo 3.1".
- Rules marked "SYSTEM RULE" come from this project's own pipeline and validators, not from Google.
- Fixed word counts are intentionally avoided; the only hard text limit is the input ceiling in Section 13.
"""

TOOL_RULES = {
    "Veo": """<veo_tool_rules>
Model Coverage: Google Veo 3.1 (veo-3.1-generate-001, veo-3.1-fast-generate-001, veo-3.1-lite-generate-001).
Execution Model: Every planned shot becomes ONE independent Veo clip generated from ONE prompt_text (optionally anchored by an opening T=0.0s storyboard keyframe image), generating picture and synchronized native audio together.

1. DURATION, RESOLUTION & ASPECT RATIO RULES (CRITICAL)
- Valid Clip Durations: Veo 3.1 generates clips of exactly 4, 6 or 8 seconds (24 FPS). Every shot MUST have duration_seconds of 4, 6 or 8. Never output 1, 2, 3, 5, 7, or >8 seconds.
- Supported Aspect Ratios & Resolutions (Veo 3.1 GA): 16:9 or 9:16 at 720p, 1080p, or 4K.
  * Mode Note: Standard Text-to-Video and Image-to-Video / First-Last-Frame support 4s, 6s, and 8s. Reference-image-to-video ("ingredients") mode requires 8s clips.
- Reachable Totals (SYSTEM RULE): Every EVEN total from 4s upward can be built from 4s, 6s, and 8s clips. Round an ODD target UP to the next even number (5 -> 6, 7 -> 8, 9 -> 10, 15 -> 16) and never exceed that rounded ceiling.
- Explicit Script Shot-Split Priority (CRITICAL): Whenever the raw script or user Q&A explicitly specifies per-shot clip counts or durations in valid `4s`/`6s`/`8s` increments (e.g., `10s = 6+4`, or Shot 4 split into 2 clips), honor those exact shot divisions and counts rather than merging them into fewer clips. If a scripted shot uses an odd/unachievable number (e.g., `7s`, `15s`, or `17s in 2 clips`), follow any user clarification or adjust minimally by `±1s` (`4s`/`6s`/`8s`) so the combined total still matches the exact target runtime.
- Reference Splits (fallback ONLY when the script omits per-shot splits; prefer fewer clips and align to natural scene/beat changes):
  4s=4 | 6s=6 | 8s=8 (or 4+4) | 10s=6+4 | 12s=6+6 (or 4+4+4) | 14s=8+6 (or 6+4+4)
  16s=8+8 | 18s=8+6+4 | 20s=8+8+4 | 24s=8+8+8 | 30s=8+8+8+6
- Hard Ceiling on Shot Count: Never exceed the reference split cap when the script omits splits; however, explicitly scripted multi-clip sub-splits (`4s`/`6s`/`8s`) within the total duration MUST be respected across short and long (`30s`–`120s+`) runtimes. Merge tiny sub-4s beats into one continuous clip.
- Beat Allocation Procedure:
  a) List every beat, action, and spoken line in chronological order.
  b) Never cross a scene/location change inside one clip; hard cuts are clip boundaries.
  c) Merge consecutive short same-scene beats into one continuous clip (two 2s beats -> one 4s clip; two 3s beats -> one 6s clip).
  d) Never split one beat across clips unless it exceeds 8 seconds.
  e) Prefer 6s or 8s for dialogue or slow reveals; prefer 4s for one crisp action.
  f) Use every beat exactly once: nothing skipped, nothing repeated.
- Dialogue Fit: Usable speech window = duration_seconds - 1s at ~2.5 words/sec (~7 words in 4s, ~12 in 6s, ~17 in 8s). If a line is longer, use a longer clip or split cleanly at a sentence/phrase boundary across consecutive clips. NEVER paraphrase, shorten, or invent dialogue.

2. VEO PROMPT FORMULA (OFFICIAL VEO 3.1)
Build every prompt_text in this exact order as flowing natural sentences (never labeled prefixes like "Scene:" or "Subject:" and never tag lists):
[Cinematography] + [Subject] + [Action] + [Context] + [Style & Ambiance] + [Audio]
- CINEMATOGRAPHY: Shot size, camera angle, ONE primary camera movement (or "the camera stays locked off and does not move"), speed, and qualitative focus.
- SUBJECT: Who or what is in frame using the full verbatim Continuity Bible anchor (Section 4).
- ACTION: SINGLE CONTINUOUS MOTION BEAT with start state, motion (speed/direction), and closing end state (Section 5).
- CONTEXT: Location, foreground/midground/background layers, time of day, props, and atmosphere.
- STYLE & AMBIANCE: Observable light source/direction/quality, color palette, mood, surface texture, and consistent footage look.
- AUDIO: Verbatim dialogue/VO, concrete foley, room ambience, and explicit "no music" when absent from spec (Section 7).

3. CINEMATIC CAMERA VOCABULARY & QUALITATIVE OPTICS
- Shot Size: extreme close-up, close-up, medium close-up, medium shot, medium wide shot, wide / establishing shot, extreme wide shot.
- Angle: eye-level, low-angle, high-angle, overhead / top-down, over-the-shoulder, point-of-view, tilted (Dutch) angle.
- Movement (ONE primary movement per clip with speed and start/end): locked-off static, slow push-in (dolly-in), pull-back (dolly-out), tracking / following, lateral slide, pan left/right, tilt up/down, crane up/down, orbit / arc, handheld (only when scripted for UGC/documentary), aerial / drone, whip pan, rack focus.
- Qualitative Optics: shallow depth of field, deep focus, soft out-of-focus background, macro detail, wide-angle expansive framing, compressed telephoto look, gentle optical falloff.
- Unseen Observer: Never show cameras, phones, tripods, or crew unless scripted.
- Forbidden Parameters (SYSTEM VALIDATOR): Zero numeric camera parameters (mm focal lengths, f-stops, ISO, shutter speeds, sensor sizes, 4K/8K) and zero empty buzzwords ("cinematic quality", "hyper-realistic", "masterpiece", "best quality").

4. SUBJECT & CONTINUITY ANCHORS
- Copy each character, product, and location Continuity Bible anchor WORD FOR WORD into every clip where it appears. Never swap color or fabric synonyms across clips ("beige" in one clip and "oatmeal" in the next).
- Describe people visually ("a woman in her late twenties with ...") rather than relying on proper names; never name real public figures.
- Limit to 1–2 focal characters per clip with explicit spatial placement (left/right, foreground/background) and fabric/hair motion physics.

5. ACTION & MOTION (SINGLE CONTINUOUS BEAT)
- Describe ONE coherent, fluid beat: start state -> deliberate motion (speed + direction) -> end state, plus subtle secondary motion (blink, breath, fabric sway).
- Keep hand-object interactions simple and name the grip explicitly ("both hands around the ceramic mug"). Avoid fast chaotic motion, counted/intricate finger work, crowds, and unmanaged mirror/glass reflections.
- Avoid hard cuts inside a single prompt unless explicitly scripted.

6. MULTI-BEAT CONTINUOUS CHOREOGRAPHY (SYSTEM RULE)
- Although Veo 3.1 supports bracketed timestamps, THIS PIPELINE FORBIDS BRACKETED TIMESTAMPS ([00:00-00:02]) to prevent accidental on-screen digital clock or timer rendering.
- Connect merged beats with smooth temporal prose: "The shot opens with [beat 1] ... as [camera/subject smoothly transitions] into [beat 2] ... before settling on [closing state]."
- Embed dialogue naturally at the exact moment it occurs in the chronological flow. 

7. NATIVE SYNCHRONIZED AUDIO, DIALOGUE & VOICEOVER
- Always direct audio explicitly; Veo 3.1 synthesizes sound natively.
- On-Screen Dialogue: write `<visual speaker description> says: "exact line"` followed by tone/pace/emotion and accurate lip synchronization. Keep the line verbatim in its original language.
- Off-Screen Voiceover: write `Off-screen voiceover in a <voice profile> says: "exact line"` and state that the on-screen person remains silent with mouth closed.
- Keep speaker voice descriptions identical across every clip using the specification's voice profile (do not invent a voice if none is given).
- Sound Effects & Ambience: Name concrete physical sources ("soft footsteps on polished oak", "subtle linen rustle").
- Music & Subtitles: Never add unrequested music, distinctive SFX, or dialogue. If the specification gives no music, explicitly write "no music". Never request subtitles or captions.

8. CONTINUITY ACROSS INDEPENDENT CLIPS (SYSTEM RULE)
- Clips render independently, so match each clip's opening state (STARTS:) to the previous clip's closing state (ENDS:), keeping identical anchor, location, lighting, palette, and time-of-day wording within a scene.
- Record STARTS:, ENDS:, LOCK:, VOICE: (when applicable), and POST: (when applicable) lines in continuity_requirements.
- Re-establish new locations completely in words at every scene transition.

9. SELF-CONTAINED PROMPTING & KEYFRAME FALLBACK RESILIENCE (SYSTEM RULE)
- Even when an opening storyboard keyframe image is supplied in Image-to-Video mode, EVERY prompt_text MUST remain 100% self-contained in words so visual identity holds seamlessly if the pipeline falls back to Text-to-Video (for example, during safety-filter retry recovery such as code 15236754).
- NEVER write "from the reference image", "as in Image 1", "the provided logo", "as shown", or "the attached product".
- Exact Logos & Fine Text: Describe shape, color, and placement faithfully and log "POST: exact logo / text fidelity requires a post-production overlay" in continuity_requirements.

10. CONTENT SAFETY & FILTER RESILIENCE
- Avoid real public figures, celebrity likenesses, copyrighted characters, graphic violence, sexual/explicit content, hate speech, and unsafe depictions of minors.
- Keep fashion, lifestyle, and product descriptions neutral and professional to minimize false-positive person-safety rejections.

11. NEGATIVE CONSTRAINTS FORMAT
- Output 6 to 10 shot-specific unwanted visual/audio elements as a concise comma-separated list ("extra people, subtitles, watermark, warped hands, morphing clothing, camera shake, flicker").
- NEVER use "no ...", "do not ...", or "without ..." phrasing. Never list an element the shot requires.

12. LIGHTING, ATMOSPHERE & STYLE CONSISTENCY
- Specify observable lighting (source, direction, softness, color temperature) and concrete footage texture ("photorealistic live-action footage, natural skin texture, soft analog film grain"), reusing identical style wording across every clip.

13. PROMPT SIZE & HARD INPUT CEILING (SYSTEM RULE)
- Veo accepts roughly 1,024 tokens of text input per individual clip (covering `prompt_text` and `negative_prompt` together). Scale every shot's `prompt_text` strictly by its clip duration equally from Shot 1 through the final shot—NEVER shrink Shots 2..N below these minimum word floors (slightly exceeding the target range is acceptable as long as `prompt_text` stays strictly under `~3,000 characters`):
  * `4s` Clip: `180–220+ words` (minimum `180 words`)
  * `6s` Clip: `240–280+ words` (minimum `240 words`)
  * `8s` Clip: `300–350+ words` (minimum `300 words`, under `~3,000 characters`)
- If space runs tight, prioritize in this order: action, subject anchor, camera, setting, lighting, style, extra audio detail.

14. SELF-CHECK BEFORE OUTPUTTING
- Every duration_seconds is 4, 6, or 8; shots sum to scene; scenes sum to total_duration.
- Every script beat appears once in order; merged beats use fluid temporal prose (zero bracketed timestamps).
- Continuity Bible anchors are verbatim; STARTS / ENDS / LOCK lines chain cleanly.
- One primary camera movement; zero numeric optics or buzzwords; zero image references; 6 to 10 negative_constraints without "no/do not/without".
- Dialogue is verbatim, speaker-attributed, and fits the clip; no unrequested music; prompt stays under ~3,000 characters.
</veo_tool_rules>""",
}

DEFAULT_TOOL = "Veo"


def get_tool_rules(tool: str = DEFAULT_TOOL) -> str:
    """Return the prompt-writing rules for the requested tool (falls back to Veo)."""
    return TOOL_RULES.get(tool, TOOL_RULES[DEFAULT_TOOL])