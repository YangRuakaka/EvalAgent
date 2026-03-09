# Value Agent Backend — Quick Start

## 1) Basic Project Structure
```
backend/
├── app/
│   ├── main.py              # FastAPI app entry
│   ├── api/                 # Routes & dependencies
│   ├── core/                # Config
│   ├── schemas/             # Pydantic models
│   └── services/            # Business/LLM logic
├── pyproject.toml           # Dependencies
└── README.md
```

## 2) Open Swagger (API Docs)
Open after the server starts: `http://localhost:8000/docs`

## 3) Environment Configuration
Create a `.env` file in `backend/` and set the keys for any providers you plan to use:
```
OPENAI_API_KEY=your-openai-api-key
DEEPSEEK_API_KEY=your-deepseek-api-key
ANTHROPIC_API_KEY=your-anthropic-api-key
GEMINI_API_KEY=your-gemini-api-key
ENABLE_OLLAMA=false
```

Optional overrides for custom gateways:
```
OPENAI_BASE_URL=https://your-openai-compatible-endpoint
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
ANTHROPIC_BASE_URL=https://api.anthropic.com
GEMINI_BASE_URL=https://generativelanguage.googleapis.com
```

Browser-agent performance related overrides:
```
BROWSER_AGENT_MAX_STEPS=30
BROWSER_AGENT_MAX_CONCURRENT=4
BROWSER_AGENT_MAX_CONCURRENT_CAP=4
BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED=true
BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES=2
BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN=1
BROWSER_AGENT_MAX_PARALLEL_RUNS=1
BROWSER_AGENT_RUN_TIMEOUT=0
BROWSER_AGENT_BROWSER_START_TIMEOUT=180
BROWSER_AGENT_BROWSER_LAUNCH_RETRIES=3
BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS=2
BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS=true
BROWSER_AGENT_ENABLE_SCREENSHOTS=true
BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING=false
BROWSER_AGENT_MAX_SCREENSHOTS=3
BROWSER_AGENT_INCLUDE_SCREENSHOTS_IN_RUN_RESPONSE=false
BROWSER_AGENT_INCLUDE_SCREENSHOT_BASE64_IN_HISTORY_PAYLOAD=false
```

Notes:
- `BROWSER_AGENT_RUN_TIMEOUT`: seconds for each submitted run batch; set `0` (or any `<=0`) to disable timeout.
- `BROWSER_AGENT_MAX_CONCURRENT`: max browser agents running concurrently *inside one run_id*.
- `BROWSER_AGENT_MAX_CONCURRENT_CAP`: hard safety cap for per-run browser concurrency.
- `BROWSER_AGENT_CONCURRENCY_FALLBACK_ENABLED`: automatically roll back to lower concurrency when browser startup/resource pressure errors are detected.
- `BROWSER_AGENT_CONCURRENCY_FALLBACK_MAX_RETRIES`: number of fallback stages to try (default supports `4 -> 2 -> 1`).
- `BROWSER_AGENT_CONCURRENCY_FALLBACK_MIN`: minimum per-run concurrency floor used by rollback.
- `BROWSER_AGENT_MAX_PARALLEL_RUNS`: max run_id jobs processed concurrently by the API worker pool.
- `BROWSER_AGENT_FORCE_THREADED_RUN_ON_WINDOWS`: runs each browser-use execution in a dedicated Proactor loop thread on Windows for better stability under concurrency.


## 4) Run the Server
From the `backend/` folder, run:
```
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

## 5) Browser Agent Endpoint
- **Path:** `POST /api/v1/browser-agent/run`
- **Payload (example):**
	```json
	{
		"task": {
			"name": "Check pricing",
			"url": "https://example.com/pricing"
		},
		"persona": "You are a diligent market analyst who verifies every number twice.",
		"model": "deepseek-chat",
		"run_times": 1
	}
	```
- Only the fields shown above are accepted; any additional keys will be rejected.
- Outputs are stored under `history_logs/` (JSON summaries + screenshots). Override with `BROWSER_AGENT_OUTPUT_DIR` in `.env` if needed.

## 6) History Logs API
- **Path:** `GET /api/v1/history-logs`
- **Description:** Streams every JSON payload cached under `history_logs/`.
- **Query params:**
	- `data_source` / `dataset`: `data1 | data2 | data3`
	- `screenshot_mode`: `inline | proxy | none`
		- `inline` (default): inline screenshot as data URI (`base64`)
		- `proxy`: return screenshot URL (`/api/v1/history-logs/screenshot?...`) for direct frontend loading
		- `none`: skip screenshot payload conversion
- **Response snapshot:**
	```json
	[
	  {
	    "filename": "Buy_milk_20251012_101507_run01.json",
	    "metadata": { "task": {"name": "Buy milk", "url": "http://localhost:3000/riverbuy"}, "run_index": 1, "persona": "You value health" },
	    "summary": { "is_done": true, "total_duration_seconds": 152.058 },
	    "details": {
	      "screenshots": ["iVBORw0KGgoAAA..."],
	      "screenshot_paths": ["history_logs/s...,"],
	      "missing_screenshots": []
	    }
	  }
	]
	```
- Screenshots that are no longer present on disk are returned as `null` entries in `details.screenshots`, and their original paths are listed under `details.missing_screenshots` for troubleshooting.

- **Path:** `GET /api/v1/history-logs/screenshot`
- **Description:** Serve a screenshot file directly by `path` (optionally with `dataset` / `data_source`), suitable for `<img src="...">`.

## 7) Offline Screenshot Hash Backfill
If older cached logs are missing `details.screenshot_hashes`, you can precompute them once offline so the online `proxy` flow stays fast and trajectory image merging remains stable.

From the `backend/` folder:
```bash
python precompute_screenshot_hashes.py
```

This default mode is a dry run. To write the hashes back into the JSON files:
```bash
python precompute_screenshot_hashes.py --write
```

Useful options:
- `--datasets data1 data2`
- `--overwrite-existing`
- `--skip-legacy-data1`
- `--cache-dir /custom/history_logs_dir`

If the backend is already deployed on Cloud Run and you want to trigger the same backfill remotely, call:

```bash
curl -X POST "$BACKEND_URL/api/v1/maintenance/backfill-screenshot-hashes" \
	-H "Content-Type: application/json" \
	-d '{
		"write": true,
		"datasets": ["data1", "data2", "data3"],
		"verbose": true
	}'
```

This uses the same backfill logic as `precompute_screenshot_hashes.py`, but runs on the deployed backend service.
