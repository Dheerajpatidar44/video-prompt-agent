# Video Prompt Agent

## Real video generation (WaveSpeed)

To run the system with real video generation instead of the mock:

1. **Get an API Key**: Obtain a WaveSpeed Wan 3.0 API key.
2. **Configure `.env`**: Paste the key into `WAVESPEED_API_KEY=""` in your `.env` file.
3. **Enable API**: Flip `USE_MOCK_VIDEO_API=false` in `.env`.
4. **Recommended first-run values**:
   - `VIDEO_GENERATION_CONCURRENCY_LIMIT=1`
   - `VIDEO_MAX_RETRIES=0`
   - `WAVESPEED_RESOLUTION=480p`
5. **Cost Safety Guards**: The `.env` includes guards like `VIDEO_MAX_ESTIMATED_COST_USD` (default $0.50). Increase this value after verifying your balance.
   - Pricing (per second): 480p = $0.05, 720p = $0.10, 1080p = $0.20
   - Billed duration rounds UP to the nearest whole second (minimum 2s).
6. **FFmpeg**: Ensure `ffmpeg` is installed on your OS (`ffmpeg -version`) for video stitching.

### Running the Smoke Test
Run the manual smoke test script before starting the full backend:
```bash
python backend/scripts/smoke_test_wavespeed.py --confirm
```
