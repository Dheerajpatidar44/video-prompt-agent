"""Interactive CLI tool to test Script Heuristic & Timing Analysis without any API keys.

Usage:
    venv\\Scripts\\python test_script_cli.py "C:\\path\\to\\script.txt"
    venv\\Scripts\\python test_script_cli.py "C:\\path\\to\\script.pdf"
    venv\\Scripts\\python test_script_cli.py "C:\\path\\to\\script.txt" 10  (with 10s target duration)
"""
import os
import sys
from pathlib import Path

# Fix Windows console encoding for special characters
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.services.script_heuristic_service import ScriptHeuristicService


def load_script_content(file_path: str) -> str:
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        print(f"[*] Reading PDF file with PDFParser...")
        import asyncio
        from app.parsers.pdf_parser import PDFParser
        parser = PDFParser()
        return asyncio.run(parser.parse(file_path))
    else:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()


def main():
    print("=" * 65)
    print("      SCRIPT HEURISTIC & TIMING TESTER (ZERO API KEYS)")
    print("=" * 65)

    if len(sys.argv) < 2:
        print("\n[!] Bhai aapne koi script file provide nahi ki hai.")
        print("\nKese chalana he:")
        print('  1. Text Script file ke sath:')
        print('     venv\\Scripts\\python test_script_cli.py "my_script.txt"')
        print('\n  2. PDF Script file ke sath:')
        print('     venv\\Scripts\\python test_script_cli.py "my_script.pdf"')
        print('\n  3. Target duration enforce karne ke liye (e.g. 10s):')
        print('     venv\\Scripts\\python test_script_cli.py "my_script.txt" 10')
        print("\n" + "=" * 65)
        return

    script_path = sys.argv[1].strip("\"'")
    explicit_duration = None
    if len(sys.argv) > 2:
        try:
            explicit_duration = float(sys.argv[2])
        except ValueError:
            pass

    if not os.path.exists(script_path):
        print(f"\n[ERROR] Di gayi file nahi mili: '{script_path}'")
        return

    print(f"\nReading script: {script_path} ...")
    try:
        script_text = load_script_content(script_path)
    except Exception as exc:
        print(f"[ERROR] Script read karne me error: {exc}")
        return

    if not script_text.strip():
        print("[ERROR] Script file khali (empty) hai.")
        return

    print(f"Loaded {len(script_text)} characters. Running heuristics...")

    report = ScriptHeuristicService.scan_script(
        script_text=script_text,
        explicit_target_duration=explicit_duration
    )

    print("\n" + "=" * 65)
    print("             EXTRACTION REPORT (LOCAL PYTHON)")
    print("=" * 65)
    print(f"[*] File Name          : {Path(script_path).name}")
    print(f"[*] Target Duration    : {report.detected_duration_seconds or 'Auto/Not specified'} seconds")
    print(f"[*] Veo Shot Slots     : {' + '.join(f'{s}s' for s in report.veo_recommended_shots)} ({len(report.veo_recommended_shots)} clips)")
    print(f"[*] Aspect Ratio       : {report.aspect_ratio_hint or 'None detected (Default: 16:9)'}")
    print(f"[*] Scene Count        : {report.scene_count}")

    if report.detected_scenes:
        print("\n--- Parsed Scenes ---")
        for sc in report.detected_scenes:
            print(f"  Scene {sc.scene_number}: {sc.header}")
            print(f"    - Setting : {sc.setting_type} (Interior/Exterior)")
            print(f"    - Lighting: {sc.lighting_time}")

    print("\n--- Dialogue & Speech Audit ---")
    print(f"[*] Total Spoken Lines : {len(report.dialogue_lines)}")
    print(f"[*] Total Words        : {report.total_dialogue_words}")
    print(f"[*] Est. Speech Time   : ~{report.estimated_speech_seconds:.1f} seconds (at 2.5 words/sec)")
    print(f"[*] Timing Feasibility : {'FEASIBLE (Dialogue fits in video)' if report.dialogue_timing_feasible else 'OVERFLOW WARNING (Dialogue too long!)'}")

    if report.dialogue_lines:
        print("\n  Sample Spoken Lines:")
        for dl in report.dialogue_lines[:3]:
            print(f"    - {dl.speaker}: \"{dl.text}\" ({dl.word_count} words -> ~{dl.estimated_seconds}s)")

    if report.warnings:
        print("\n[!] WARNINGS GENERATED:")
        for w in report.warnings:
            print(f"    -> {w}")

    print("=" * 65)
    print("\n[+] Claude LLM Prompt me bheja jaane waala Final Deterministic Block:")
    print("-" * 65)
    print(report.deterministic_summary_text)
    print("-" * 65)
    print("\n[SUCCESS] Script successfully analyze ho gayi bina kisi API key ke!\n")


if __name__ == "__main__":
    main()
