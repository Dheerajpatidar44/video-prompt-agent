# Video Prompt Agent

## Real video generation (Veo 3.1 Lite via Gemini API)

To run the system with real video generation instead of the mock:

1. **Get a Gemini API Key**:
   - Create an API key in Google AI Studio (https://aistudio.google.com/).
   - Ensure billing / paid tier is enabled on your Google Cloud project (Veo requires a paid account).
   - Check that Veo is available in your region.
2. **Configure `.env`**:
   - Paste the key into `GEMINI_API_KEY=""` in `backend/.env`.
   - Ensure `VIDEO_PROVIDER=veo`.
   - Model code is set via `VEO_MODEL="veo-3.1-lite-generate-preview"` (Veo 3.1 Lite is a Preview model).
   - Configure resolution: `VEO_RESOLUTION=720p` (or `1080p`).
   - Configure timeouts: `VEO_REQUEST_TIMEOUT_SECONDS=30`, `VEO_DOWNLOAD_TIMEOUT_SECONDS=120`.
3. **Enable API**:
   - Flip `USE_MOCK_VIDEO_API=false` in `backend/.env`.
4. **Recommended first-run values**:
   - `VIDEO_GENERATION_CONCURRENCY_LIMIT=1`
   - `VIDEO_MAX_RETRIES=0`
   - `VEO_RESOLUTION=720p`
5. **Veo 3.1 Lite Constraints & Specifications**:
   - **Durations**: Fixed tiers: 4, 6, or 8 seconds only. Shots planned shorter than 4s are lengthened to 4s. Shots planned longer than 8s are capped at 8s. (1080p supports 8s only).
   - **Aspect Ratios**: `16:9` and `9:16` supported.
   - **Audio**: Native audio is always generated.
   - **Prompt Limit**: 1,024 token maximum (estimated guard enforced).
   - **Features**: Negative prompts and reference images are not supported on Veo 3.1 Lite.
   - **Retention**: Video URIs expire at Google after 2 days; the agent automatically downloads and stores them in Cloudinary immediately.
6. **Cost & Pricing Table**:
   - Pricing (per second): 720p = $0.05/s, 1080p = $0.08/s.
   - 720p costs: 4s = **$0.20**, 6s = **$0.30**, 8s = **$0.40**.
   - 1080p cost: 8s = **$0.64**.
   - Smallest clip cost is $0.20.
7. **Cost Safety Guards**:
   - `VIDEO_MAX_ESTIMATED_COST_USD` (e.g. $2.00) caps total project spend.
   - `VIDEO_MAX_SHOTS_PER_PROJECT` and `VIDEO_MAX_TOTAL_SECONDS_PER_PROJECT` guard project bounds.
8. **FFmpeg**:
   - Ensure `ffmpeg` is installed on your PATH (`ffmpeg -version`) for video stitching.

### Running the Smoke Test
Before running the full pipeline, verify your API key and setup with the manual CLI smoke test (~$0.20):
```bash
# Dry-run estimate (spends $0.00):
python -m scripts.smoke_test_veo

# Execute live generation, poll, and download:
python -m scripts.smoke_test_veo --confirm
```
