# AI Video Prompt Agent - Performance Audit & Optimization Plan

## 1. Current Execution Flow

The backend executes a strictly linear and fully synchronous pipeline for script analysis. 
The current pipeline trace:

```text
API Request (POST /analyze) -> Synchronous FastAPI worker
  → graph.invoke()
    → Node: initialize_state
    → Node: analyze_script
        → LLMService.__init__() (Synchronous health check & tags check)
        → Ollama Inference (generate_structured)
    → Node: detect_gaps
        → LLMService.__init__() (Synchronous health check & tags check)
        → Ollama Inference
    → Node: build_video_spec
        → LLMService.__init__() (Synchronous health check & tags check)
        → Ollama Inference
    → Node: scene_planner
        → LLMService.__init__() (Synchronous health check & tags check)
        → Ollama Inference
    → Node: prompt_generator
        → LOOP: For EACH shot in EACH scene (e.g., 5 scenes * 3 shots = 15 iterations)
            → LLMService.__init__() (Synchronous health check & tags check)
            → Ollama Inference (generate_structured)
  → API Response
```

## 2. Latency Breakdown

| Node / Function | LLM Calls | Avg Latency Contribution | Parallelizable? | Combinable? | Issue |
|-----------------|-----------|--------------------------|-----------------|-------------|-------|
| `analyze_script`| 1 + 2 HTTP| ~15-30% of base time     | No              | Yes         | Sequential |
| `detect_gaps`   | 1 + 2 HTTP| ~15-30% of base time     | No              | Yes         | Receives same context as analyze, can be combined. |
| `build_video_spec`| 1 + 2 HTTP| ~20% of base time      | No              | Maybe       | Synchronous execution blocks thread. |
| `scene_planner` | 1 + 2 HTTP| ~30% of base time        | No              | No          | Large structured output slows local inference. |
| `prompt_generator`| **N** (per shot)| **CRITICAL (Scales linearly)** | **YES** | **YES** (Per Scene) | Sequential iteration for every single shot. If a video has 15 shots, this takes 15x inference time. |

## 3. Bottleneck Identification

1. **CRITICAL: Sequential Iteration in `prompt_generator`**
   The application calls the LLM individually for every single shot in the scene plan. If the plan has 10 shots, the user waits for 10 sequential LLM calls. This is the primary reason the system takes so long.
2. **CRITICAL: Re-instantiating `LLMService` in every node**
   Every time `LLMService()` is called, it executes two synchronous HTTP `GET` requests (`/` and `/api/tags`) before starting the inference. In a 10-shot video, this means 20+ completely redundant synchronous HTTP calls blocking the Python thread.
3. **HIGH: Separation of Analysis and Gap Detection**
   `analyze_script` and `detect_gaps` are two separate nodes that both read the script and output structured JSON. They can easily be combined into a single Pydantic schema (`ScriptAnalysisWithGaps`), cutting the initial wait time before asking questions in half.
4. **HIGH: Synchronous FastAPI Endpoints (`def` vs `async def`)**
   The routes in `scripts.py` use `def` instead of `async def` and invoke LangGraph synchronously. This blocks the FastAPI worker thread completely. While LangGraph is running, the server cannot process other requests effectively.
5. **MEDIUM: Repeated Context Injection**
   Later nodes pass the entire `VideoSpecification`, `ContinuityBible`, and previous plans repeatedly. The prompts can be minimized.

## 4. Top 10 Optimization Opportunities

1. **Batch Prompt Generation (Per Scene instead of Per Shot):** Modify `prompt_generator` to generate a list of prompts for an entire scene in one LLM call, reducing N calls to just 1 call per scene.
2. **Combine Analyze & Gap Detection:** Merge `analyze_script` and `detect_gaps` into a single LLM call that outputs both the script entities and missing gaps.
3. **Singleton / Module-level LLMService:** Initialize the Ollama client and run health checks only once at startup, passing the client to the nodes, or caching the health check result with a TTL.
4. **Async LangGraph Execution:** Convert the API routes to use `async def` and use `graph.ainvoke()` to prevent thread blocking.
5. **Async Ollama Client:** Switch from the synchronous `ollama` library or `httpx` to `AsyncClient` to allow concurrent execution.
6. **Parallelize Scene Prompt Generation:** Once prompt generation is grouped by scene, use LangGraph's `Send` API or `asyncio.gather` to generate prompts for multiple scenes concurrently.
7. **Optimize Prompt Sizes:** Remove unnecessary nested JSON dumping when passing context to the LLM (e.g., passing only the `scene_plan` for the specific scene rather than the entire `MasterScenePlan`).
8. **Faster Parsing:** Use `orjson` for JSON serialization/deserialization where possible.
9. **Remove Redundant Status Updates:** Prevent writing to the state purely for status updates if they cause unnecessary checkpointing overhead.
10. **Implement Caching:** Add an in-memory or Redis cache for the initial `analyze` step based on a hash of the script text.

## 5. Recommended Architecture

The optimized pipeline should look like:

1. **Singleton Async LLMService** (No repeated health checks).
2. **Node 1: `analyze_and_detect_gaps`** (Combines extraction and gap detection).
3. **Node 2: `build_video_spec`**
4. **Node 3: `scene_planner`**
5. **Node 4: `prompt_generator`** (Executes using `asyncio.gather` to generate prompts for all scenes concurrently, grouped by scene).
6. **API Layer:** Fully async FastAPI endpoints using `ainvoke`.

## 6. Exact Files/Functions That Need Modification

1. `app/llm/ollama.py` (Make LLMService async, cache health checks).
2. `app/graph/nodes/analyze_script.py` & `detect_gaps.py` (Merge logic).
3. `app/graph/nodes/prompt_generator.py` (Change to batch processing by scene + async execution).
4. `app/api/routes/scripts.py` (Switch to `async def` and `ainvoke`).
5. `app/graph/graph.py` (Update node structure for the merged analysis).

## Final Recommendation
I am ready to implement these changes. I recommend we start by fixing the two most critical bottlenecks:
1. Fixing the `LLMService` to prevent redundant health checks.
2. Modifying `prompt_generator` to batch generate prompts per scene rather than per shot.

Please review this audit and provide approval to begin implementation.
