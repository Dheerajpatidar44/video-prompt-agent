import pytest
from app.services.script_heuristic_service import (
    ScriptHeuristicService,
    ScriptPreCheckReport,
    SceneStructure,
    DialogueLine,
)


def test_veo_shot_slots_calculation():
    # Native single-clip durations
    assert ScriptHeuristicService.calculate_veo_shot_slots(4) == [4]
    assert ScriptHeuristicService.calculate_veo_shot_slots(5) == [6]
    assert ScriptHeuristicService.calculate_veo_shot_slots(6) == [6]
    assert ScriptHeuristicService.calculate_veo_shot_slots(8) == [8]

    # Standard multi-clip combinations
    assert ScriptHeuristicService.calculate_veo_shot_slots(10) == [6, 4]
    assert ScriptHeuristicService.calculate_veo_shot_slots(12) == [6, 6]
    assert ScriptHeuristicService.calculate_veo_shot_slots(14) == [6, 4, 4]
    assert ScriptHeuristicService.calculate_veo_shot_slots(16) == [8, 8]
    assert ScriptHeuristicService.calculate_veo_shot_slots(20) == [6, 6, 4, 4]
    assert ScriptHeuristicService.calculate_veo_shot_slots(24) == [6, 6, 6, 6]
    assert ScriptHeuristicService.calculate_veo_shot_slots(30) == [8, 8, 8, 6]

    # Longer duration fallback sums to total
    slots_40 = ScriptHeuristicService.calculate_veo_shot_slots(40)
    assert sum(slots_40) >= 40
    assert all(s in [4, 6, 8] for s in slots_40)


def test_dialogue_audit_feasible():
    script = """
    INT. OFFICE - DAY
    JOHN: Hey Sarah, did you see the new product mockup?
    SARAH: Yes, it looks incredible.
    """
    lines, total_words, est_time, feasible, warnings = ScriptHeuristicService.audit_dialogue(
        script, target_duration=10.0
    )
    assert len(lines) == 2
    assert lines[0].speaker == "John"
    assert lines[0].word_count == 9
    assert lines[1].speaker == "Sarah"
    assert lines[1].word_count == 4
    assert total_words == 13
    assert est_time == pytest.approx(5.2, rel=0.1)
    assert feasible is True
    assert len(warnings) == 0


def test_dialogue_audit_overflow_warning():
    # 40+ words in a 6 second target video
    script = """
    HOST: Welcome everyone to this fast-paced presentation where we explain every single detail of our revolutionary artificial intelligence platform which solves every workflow problem imaginable across your entire business ecosystem in seconds!
    """
    lines, total_words, est_time, feasible, warnings = ScriptHeuristicService.audit_dialogue(
        script, target_duration=6.0
    )
    assert len(lines) == 1
    assert total_words > 25
    assert est_time > 10.0
    assert feasible is False
    assert len(warnings) == 1
    assert "Dialogue overflow" in warnings[0]


def test_dialogue_audit_ignores_keywords():
    script = """
    SCENE: A modern luxury penthouse.
    CAMERA: Slow pan across the marble table.
    ACTION: The glass shatters on the floor.
    NOTE: Ensure dramatic lighting.
    LEAD: We have to move right now!
    """
    lines, total_words, est_time, feasible, warnings = ScriptHeuristicService.audit_dialogue(
        script, target_duration=10.0
    )
    # Only LEAD should be parsed as dialogue
    assert len(lines) == 1
    assert lines[0].speaker == "Lead"
    assert lines[0].text == "We have to move right now!"


def test_scene_header_extraction_structured():
    script = """
    INT. COFFEE SHOP - MORNING
    A barista pours espresso into a cup.

    EXT. PARK - SUNSET
    Children playing with a frisbee on the grass.

    INT. BEDROOM - NIGHT
    Soft moonlight enters through the window curtains.
    """
    scenes = ScriptHeuristicService.extract_scenes(script)
    assert len(scenes) == 3

    assert scenes[0].scene_number == 1
    assert scenes[0].setting_type == "INT"
    assert scenes[0].lighting_time == "DAY"  # MORNING maps to DAY

    assert scenes[1].scene_number == 2
    assert scenes[1].setting_type == "EXT"
    assert scenes[1].lighting_time == "GOLDEN_HOUR"  # SUNSET maps to GOLDEN_HOUR

    assert scenes[2].scene_number == 3
    assert scenes[2].setting_type == "INT"
    assert scenes[2].lighting_time == "NIGHT"


def test_scene_header_extraction_unstructured_fallback():
    script = "A sleek perfume bottle sits on black sand with smoke rising behind it."
    scenes = ScriptHeuristicService.extract_scenes(script)
    assert len(scenes) == 1
    assert scenes[0].scene_number == 1
    assert scenes[0].setting_type == "UNKNOWN"
    assert scenes[0].lighting_time == "UNKNOWN"


def test_detect_duration_and_aspect():
    script_vertical = "Create a 15-second vertical Reels video showing a watch review."
    dur, aspect = ScriptHeuristicService.detect_duration_and_aspect(script_vertical)
    assert dur == 15.0
    assert aspect == "9:16"

    script_horizontal = "A 10s horizontal cinematic commercial for YouTube in 16:9 widescreen."
    dur2, aspect2 = ScriptHeuristicService.detect_duration_and_aspect(script_horizontal)
    assert dur2 == 10.0
    assert aspect2 == "16:9"

    script_none = "A slow motion shot of water splashing."
    dur3, aspect3 = ScriptHeuristicService.detect_duration_and_aspect(script_none)
    assert dur3 is None
    assert aspect3 is None


def test_scan_script_full_pipeline():
    script = """
    EXT. DESERT HIGHWAY - SUNSET
    A red sports car accelerates down the empty road.
    Format: 9:16 Instagram Reels.
    Duration: 10s

    DRIVER: There is nowhere left to hide.
    """
    report = ScriptHeuristicService.scan_script(script)

    assert isinstance(report, ScriptPreCheckReport)
    assert report.detected_duration_seconds == 10.0
    assert report.aspect_ratio_hint == "9:16"
    assert report.veo_recommended_shots == [6, 4]
    assert report.scene_count == 1
    assert len(report.dialogue_lines) == 1
    assert report.dialogue_timing_feasible is True
    assert "Duration: 10.0s -> Google Veo Clip Slotting: 6s + 4s" in report.deterministic_summary_text
    assert "Aspect Ratio Detected: 9:16" in report.deterministic_summary_text
    assert "EXT/GOLDEN_HOUR" in report.deterministic_summary_text


def test_commercial_av_table_and_timestamps():
    av_script = """
    Product: Aurora Shoes
    | Timestamp | Visual | Audio (VO / Music) |
    | 0:00 - 0:05 | An adult kneeling on the floor, struggling with laces. | Ambient room tone ticking. |
    | 0:05 - 0:12 | Adult smiling, sliding on elastic shoe in one second. | Happy musical chime. |
    | 0:12 - 0:20 | Toddler running in the park with golden sunlight. | Upbeat music. VO: "Aurora Shoes. Built for speed." |
    """
    report = ScriptHeuristicService.scan_script(av_script)
    assert report.detected_duration_seconds == 20.0
    assert report.veo_recommended_shots == [6, 6, 4, 4]
    assert report.scene_count == 3
    assert report.detected_scenes[0].header == "SHOT 1 [0:00 - 0:05]"
    assert report.detected_scenes[1].header == "SHOT 2 [0:05 - 0:12]"
    assert report.detected_scenes[2].header == "SHOT 3 [0:12 - 0:20]"
    assert len(report.dialogue_lines) == 1
    assert report.dialogue_lines[0].speaker == "Vo"
    assert "Aurora Shoes. Built for speed." in report.dialogue_lines[0].text


def test_creator_second_ranges_and_ui_popup_filter():
    script = """
    Create a sharp 4K-quality 9:16 vertical video.
    0–2s: Mascot looks at phone. Clear popup: "Application Status: Not Selected"
    VO: "Resume bheja. Interview tak nahi pahuncha. Pata hai kyun?"
    3–8s: Mascot holds resume. X-ray scan highlights missing keywords.
    VO: "90% companies ab resume insaan nahi, ek software padhta hai."
    """
    report = ScriptHeuristicService.scan_script(script)
    assert report.detected_duration_seconds == 8.0
    assert report.aspect_ratio_hint == "9:16"
    assert report.scene_count == 2
    assert "SCENE 1 [0s - 2s]" in report.detected_scenes[0].header
    assert "SCENE 2 [3s - 8s]" in report.detected_scenes[1].header
    # Clear popup should NOT be counted as speaker dialogue
    speakers = [d.speaker for d in report.dialogue_lines]
    assert "Clear Popup" not in speakers
    assert all(d.speaker == "Vo" for d in report.dialogue_lines)
    assert len(report.dialogue_lines) == 2


def test_detect_two_minute_and_3digit_durations():
    cases = [
        ("Create a 2-minute 16:9 brand film.", 120.0, "16:9"),
        ("Target duration: 120s. Cinematic action.", 120.0, None),
        ("A 120-second commercial in landscape 16:9.", 120.0, "16:9"),
        ("Runtime: 2 minutes vertical video.", 120.0, "9:16"),
        ("Make a 1 minute 30 seconds documentary intro.", 90.0, None),
        ("0-120s: Full product journey.", 120.0, None),
        ("0:00 - 0:08 Intro\n1:52 - 2:00 Outro", 120.0, None),
    ]
    for script, expected_dur, expected_aspect in cases:
        dur, aspect = ScriptHeuristicService.detect_duration_and_aspect(script)
        assert dur == expected_dur, f"Expected {expected_dur}, got {dur} for: {script}"
        assert aspect == expected_aspect

    report = ScriptHeuristicService.scan_script("Create a 2-minute 16:9 commercial.")
    assert report.detected_duration_seconds == 120.0
    assert sum(report.veo_recommended_shots) == 120
    assert all(s in (4, 6, 8) for s in report.veo_recommended_shots)


