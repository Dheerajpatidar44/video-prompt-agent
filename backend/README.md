# AI Video Prompt Generation Agent

## Project Purpose
This is a LOCAL AI desktop application designed to generate high-quality prompts for video-generation tools (like Veo, Runway, Kling). It analyzes scripts, asks clarifying questions, plans scenes, and generates professional video specifications and multiple prompts.
**Note**: This application does NOT generate videos, and relies entirely on local models (Ollama).

## Architecture
- **Backend**: Python 3.11+, FastAPI
- **Agent Workflow**: LangGraph
- **LLM**: Local open-source models via Ollama
- **Data Validation**: Pydantic

## Current Status
**Phase 4**: Semantic gap detection using Ollama local LLM. Identifies missing, ambiguous, or contradictory information in scripts and prioritizes gaps automatically based on deterministic severity rules. Deduplication logic is included and graph routing connects smoothly to placeholder paths.

## Future Development Phases
- Phase 5: Gap detection and Question generation
- Phase 6: Clarification question loop
- Phase 7: Scene/shot planning
- Phase 8: Master prompt generation
- Phase 9: Long-script segmentation and connected prompts
- Phase 10: Continuity validation
- Phase 11: Frontend
- Phase 12: Desktop packaging
- Phase 13: EXE distribution/testing

## Setup Instructions

### 1. Requirements
- Python 3.11+
- Ollama (installed locally)

### 2. Virtual Environment Setup
```bash
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate
# On Linux/Mac:
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Environment Configuration
Copy the `.env.example` file to `.env` and adjust the variables for your local setup if necessary:
```bash
cp .env.example .env
```
Ensure `OLLAMA_BASE_URL` points to your running Ollama instance (default: `http://localhost:11434`).

### 5. Running the Backend
Start the FastAPI server:
```bash
python run.py
```
The API will be available at `http://127.0.0.1:8000`.

### 6. Running Tests
Run the test suite using pytest:
```bash
pytest
```
