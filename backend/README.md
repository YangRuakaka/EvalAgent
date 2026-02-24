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
BROWSER_AGENT_MAX_CONCURRENT=2
BROWSER_AGENT_MAX_PARALLEL_RUNS=1
BROWSER_AGENT_RUN_TIMEOUT=0
BROWSER_AGENT_BROWSER_START_TIMEOUT=180
BROWSER_AGENT_BROWSER_LAUNCH_RETRIES=3
BROWSER_AGENT_BROWSER_RETRY_BACKOFF_SECONDS=2
BROWSER_AGENT_ENABLE_SCREENSHOTS=true
BROWSER_AGENT_ENABLE_SCREENSHOT_PROCESSING=false
BROWSER_AGENT_MAX_SCREENSHOTS=3
BROWSER_AGENT_INCLUDE_SCREENSHOTS_IN_RUN_RESPONSE=false
BROWSER_AGENT_INCLUDE_SCREENSHOT_BASE64_IN_HISTORY_PAYLOAD=false
```

Notes:
- `BROWSER_AGENT_RUN_TIMEOUT`: seconds for each submitted run batch; set `0` (or any `<=0`) to disable timeout.
- `BROWSER_AGENT_MAX_CONCURRENT`: max browser agents running concurrently *inside one run_id*.
- `BROWSER_AGENT_MAX_PARALLEL_RUNS`: max run_id jobs processed concurrently by the API worker pool.


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
- **Description:** Streams every JSON payload cached under `history_logs/` and inlines any referenced screenshots as base64 strings so the consumer can render them immediately.
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
