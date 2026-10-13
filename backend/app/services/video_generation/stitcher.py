"""Video stitcher — merge individual shot clips into one final video.

Uses ffmpeg's concat demuxer to join clips in sequence_number order.
Requires the ``ffmpeg`` binary to be installed at the OS level.

Policy for partial failures:
  - If some shots COMPLETED and others FAILED, we stitch only the successfully
    completed shots in order and mark the project PARTIAL_FAILURE.  This gives
    the user *something* rather than nothing.
  - If zero shots completed, stitching is skipped entirely.

Merge strategy:
  1. Fast path: stream copy (``-c copy``), no re-encoding. Works when every clip
     shares the same codec, resolution, frame rate and audio layout.
  2. Fallback: if the fast path fails (mismatched clips), re-encode to a uniform
     H.264/AAC output so clips from a real provider can still be joined.
"""
import asyncio
import logging
import os
import shutil
import subprocess
import tempfile
from typing import List, Optional

import httpx

from app.db import video_jobs_repository as repo
from app.schemas.video_job import VideoJobStatus

logger = logging.getLogger(__name__)

# Upper bound for a single ffmpeg run, so a hung process cannot block the poller.
FFMPEG_TIMEOUT_SECONDS = 300


class StitchingError(Exception):
    """Raised when the ffmpeg stitching process fails."""
    pass


def _run_ffmpeg(cmd: List[str]) -> subprocess.CompletedProcess:
    """Run an ffmpeg command synchronously (call via asyncio.to_thread).

    Translates the common low-level failures into StitchingError with a clear
    message instead of leaking raw FileNotFoundError / TimeoutExpired.
    """
    try:
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=FFMPEG_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        raise StitchingError(
            "ffmpeg binary not found. Install ffmpeg at the OS level and make "
            "sure it is available on PATH (check with: ffmpeg -version)."
        )
    except subprocess.TimeoutExpired:
        raise StitchingError(
            f"ffmpeg timed out after {FFMPEG_TIMEOUT_SECONDS}s while stitching."
        )


def _get_clip_duration(file_path: str) -> Optional[float]:
    """Inspect clip duration using ffprobe. Returns None if ffprobe fails or is missing."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            file_path,
        ]
        res = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        )
        if res.returncode == 0:
            out_str = res.stdout.decode(errors="replace").strip()
            if out_str:
                return float(out_str)
    except Exception:
        pass
    return None


def _trim_clip(input_path: str, output_path: str, duration_seconds: float) -> subprocess.CompletedProcess:
    """Trim a video clip to duration_seconds using ffmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-t", f"{duration_seconds:.2f}",
        "-c:v", "libx264", "-preset", "veryfast",
        "-c:a", "aac",
        output_path,
    ]
    return _run_ffmpeg(cmd)


def _build_concat_cmd(concat_list_path: str, output_path: str, reencode: bool) -> List[str]:
    """Build the ffmpeg concat command, either stream-copy or re-encode."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", concat_list_path,
    ]
    if reencode:
        cmd += ["-c:v", "libx264", "-preset", "veryfast", "-c:a", "aac"]
    else:
        cmd += ["-c", "copy"]
    cmd += ["-movflags", "+faststart", output_path]
    return cmd


async def stitch_project_videos(project_id: str) -> str | None:
    """Fetch all COMPLETED clips for ``project_id``, merge them with ffmpeg,
    upload the result to Cloudinary, and store it as the project's final video.

    Returns the permanent URL of the final video, or None if no clips succeeded.
    """
    jobs = repo.get_jobs_for_project(project_id)
    completed = [j for j in jobs if j.status == VideoJobStatus.COMPLETED and j.video_url]
    completed.sort(key=lambda j: j.sequence_number)

    if not completed:
        logger.warning(f"No completed clips for project {project_id}; skipping stitch.")
        return None

    logger.info(
        f"Stitching {len(completed)}/{len(jobs)} clips for project {project_id}"
    )

    # Create a temp directory for all intermediate files.
    tmp_dir = tempfile.mkdtemp(prefix=f"stitch_{project_id}_")
    concat_list_path = os.path.join(tmp_dir, "concat.txt")
    output_path = os.path.join(tmp_dir, "final_output.mp4")

    try:
        # 1. Download each clip to a local file and trim to planned duration if needed.
        clip_paths: List[str] = []
        skipped_shots: List[str] = []
        has_trimmed_clips = False

        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for idx, job in enumerate(completed):
                raw_clip_path = os.path.join(tmp_dir, f"clip_{idx:04d}.mp4")
                try:
                    resp = await client.get(job.video_url)
                    resp.raise_for_status()
                    with open(raw_clip_path, "wb") as f:
                        f.write(resp.content)
                except httpx.HTTPError as exc:
                    logger.error(
                        f"Failed to download clip for shot {job.shot_id}: {exc}. "
                        f"Skipping this clip."
                    )
                    skipped_shots.append(job.shot_id)
                    continue

                # Check if clip needs trimming to match planned duration
                chosen_path = raw_clip_path
                if job.duration_seconds and job.duration_seconds > 0:
                    actual_dur = await asyncio.to_thread(_get_clip_duration, raw_clip_path)
                    needs_trim = False
                    if actual_dur is not None:
                        # If actual clip duration is longer than planned duration by more than 0.2s
                        if actual_dur > job.duration_seconds + 0.2:
                            needs_trim = True
                    else:
                        # Fallback without ffprobe: compare against Veo billing tiers
                        from app.services.video_generation.cost import billed_seconds
                        billed = billed_seconds(int(job.duration_seconds))
                        if job.duration_seconds < billed:
                            needs_trim = True

                    if needs_trim:
                        trimmed_clip_path = os.path.join(tmp_dir, f"clip_{idx:04d}_trimmed.mp4")
                        logger.info(
                            f"Trimming shot {job.shot_id} clip to planned duration {job.duration_seconds:.2f}s "
                            f"(original: {actual_dur or 'unprobed'}s)."
                        )
                        proc = await asyncio.to_thread(
                            _trim_clip, raw_clip_path, trimmed_clip_path, job.duration_seconds
                        )
                        if (
                            proc.returncode == 0
                            and os.path.exists(trimmed_clip_path)
                            and os.path.getsize(trimmed_clip_path) > 0
                        ):
                            chosen_path = trimmed_clip_path
                            has_trimmed_clips = True
                        else:
                            trim_err = proc.stderr.decode(errors="replace") if proc else "unknown error"
                            logger.warning(
                                f"Failed to trim clip for shot {job.shot_id}: {trim_err[-200:]}. Using raw clip."
                            )

                clip_paths.append(chosen_path)

        if skipped_shots:
            logger.warning(
                f"Project {project_id}: {len(skipped_shots)} clip(s) could not be "
                f"downloaded and will be missing from the final video: {skipped_shots}"
            )

        if not clip_paths:
            logger.warning(f"All clip downloads failed for project {project_id}.")
            return None

        # 2. Build ffmpeg concat list file.
        with open(concat_list_path, "w") as f:
            for path in clip_paths:
                # ffmpeg concat demuxer requires forward slashes or escaped backslashes.
                safe_path = path.replace("\\", "/")
                f.write(f"file '{safe_path}'\n")

        # 3. Run ffmpeg concat: if any clip was trimmed, start directly with re-encode;
        # otherwise try fast stream-copy first, re-encode as a fallback.
        cmd = _build_concat_cmd(concat_list_path, output_path, reencode=has_trimmed_clips)
        logger.info(f"Running ffmpeg: {' '.join(cmd)}")
        proc = await asyncio.to_thread(_run_ffmpeg, cmd)

        if proc.returncode != 0 and not has_trimmed_clips:
            fast_err = proc.stderr.decode(errors="replace")
            logger.warning(
                f"ffmpeg stream-copy failed (rc={proc.returncode}); clips may have "
                f"mismatched formats. Retrying with re-encode. Details: {fast_err[-500:]}"
            )

            cmd = _build_concat_cmd(concat_list_path, output_path, reencode=True)
            logger.info(f"Running ffmpeg (re-encode): {' '.join(cmd)}")
            proc = await asyncio.to_thread(_run_ffmpeg, cmd)

            if proc.returncode != 0:
                err_text = proc.stderr.decode(errors="replace")
                logger.error(f"ffmpeg failed (rc={proc.returncode}): {err_text}")
                raise StitchingError(
                    f"ffmpeg concat failed with return code {proc.returncode}: "
                    f"{err_text[-500:]}"
                )

        # 4. Verify output file exists and is non-empty.
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise StitchingError("ffmpeg produced an empty or missing output file.")

        logger.info(
            f"ffmpeg concat succeeded. Output: {output_path} "
            f"({os.path.getsize(output_path)} bytes)"
        )

        # 5. Upload the final video to Cloudinary and store the URL.
        # Read the file inside a context manager so the handle is closed before
        # cleanup (important on Windows), and run the blocking Cloudinary SDK call
        # in a worker thread so the event loop is not stalled.
        from app.services.cloudinary_service import upload_video

        with open(output_path, "rb") as f:
            video_bytes = f.read()

        final_url = await asyncio.to_thread(
            upload_video,
            video_bytes,
            f"final-{project_id}",
            f"video-agent/{project_id}",
        )

        repo.set_project_final_video_url(project_id, final_url)
        logger.info(f"Final video stored for project {project_id}: {final_url}")
        return final_url

    finally:
        # Clean up all temporary files.
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except Exception:
            logger.warning(f"Failed to clean up temp dir: {tmp_dir}")