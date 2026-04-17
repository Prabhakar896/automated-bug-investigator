# Automated Bug Investigation Pipeline

> Multi-agent AI system for end-to-end bug investigation — from triage to fix planning.  
> Built for Purple Merit Technologies AI/ML Engineer Assessment 2.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                    main.py  (CLI Entry Point)                       │
│         --bug-report inputs/bug_report.md --logs inputs/logs/       │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 orchestrator.py  (DAG Coordinator)                   │
│                                                                     │
│  Stage 1    Stage 2       Stage 3        Stage 4                    │
│ ┌────────┐ ┌───────────┐ ┌─────────────┐ ┌──────────────┐         │
│ │ Triage │→│Log Analyst│→│Repo Navigator│→│ Reproduction │         │
│ │ Agent  │ │  Agent    │ │   Agent      │ │    Agent     │         │
│ └────────┘ └───────────┘ └─────────────┘ └──────────────┘         │
│  Gmail↗      GitHub↗       GitHub↗          subprocess↗            │
│  Drive↗                                                            │
│                                                                     │
│  Stage 5        Stage 6       Stage 7                               │
│ ┌────────────┐ ┌──────────┐ ┌───────────────┐                     │
│ │Fix Planner │→│ Reviewer │→│ Communication │                     │
│ │   Agent    │ │  Agent   │ │    Agent      │                     │
│ └────────────┘ └──────────┘ └───────────────┘                     │
│  GitHub↗         (pure       Calendar↗                             │
│  Drive↗          reasoning)  Gmail↗                                │
│                              Talent↗                               │
└─────────────────────────────┬───────────────────────────────────────┘
                              │
                              ▼
                ┌──────────────────────────┐
                │    Output Artifacts       │
                │  • investigation_report   │
                │  • repro/repro_test.py    │
                │  • agent_trace.log        │
                └──────────────────────────┘
```

### Framework Choice: Custom DAG Orchestrator

We chose a **clean custom orchestrator** over LangGraph/CrewAI/AutoGen because:

- **Full control** over agent sequencing, timeout handling, and retry logic
- **No heavy dependencies** — the system uses only Pydantic + google-genai
- **Production-ready** error handling with graceful degradation
- **Clear code** — each agent is a single Python class with typed I/O

## Quick Start

### 1. Prerequisites

- Python 3.11+
- pip

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Environment

```bash
cp .env.example .env
# Edit .env — add your GOOGLE_API_KEY for LLM-powered analysis
# Or leave blank for deterministic demo mode
```

### 4. Run the Pipeline

You have two ways to run the pipeline: **Interactive Web Dashboard** or **CLI**.

#### Option A: Interactive Web Dashboard (Recommended)

Start the live UI server to visualize agents in real-time, see their thought logs, and view interactive MCP reports.

```bash
python dashboard.py
```
Then navigate to **http://localhost:8050** in your web browser.

#### Option B: Headless CLI

```bash
python main.py --bug-report inputs/bug_report.md --logs inputs/logs/app.log
```

**Options:**
| Flag | Default | Description |
|------|---------|-------------|
| `--bug-report` | (required) | Path to bug report Markdown file |
| `--logs` | (required) | Path to application log file |
| `--output-dir` | `./output` | Where to write investigation results |
| `--timeout` | `60` | Agent timeout in seconds |
| `--log-level` | `INFO` | Logging level (DEBUG/INFO/WARNING/ERROR) |
| `--demo-mode` | `false` | Force demo mode for MCP tools |

### 5. Verify the Repro Test Fails

```bash
pytest repro/repro_test.py -v
```

Expected: **4 FAILED** — the tests assert correct behavior that the buggy code violates.

## Technologies Used

*   **Backend & Orchestration**: Python 3.11+, Pydantic (data contracts), Custom DAG Orchestrator
*   **Web Dashboard**: FastAPI & Uvicorn (SSE for live agent streaming), Vanilla HTML/CSS/JS (Zero-dependency UI)
*   **AI / LLM Integration**: Google GenAI SDK (`google-genai`), Native support for `gemma-4-31b-it` and `gemini-2.0-flash`
*   **Testing**: Pytest (for auto-generated bug reproduction test files)
*   **Deep Code Analysis**: Built-in Python `ast` syntax tree parser for deterministic fallbacks

## Project Structure

```
├── main.py                      # CLI entry point
├── config.py                    # Environment config
├── orchestrator.py              # DAG pipeline coordinator
├── requirements.txt             # Dependencies
│
├── agents/                      # Agent implementations
│   ├── base_agent.py            #   Abstract base with timeout/retry/tracing
│   ├── triage_agent.py          #   Bug report → ranked hypotheses
│   ├── log_analyst_agent.py     #   Logs → stack traces, error patterns
│   ├── repo_navigator_agent.py  #   Source → module map, call chains
│   ├── reproduction_agent.py    #   Evidence → minimal failing test
│   ├── fix_planner_agent.py     #   Evidence → root cause + patch plan
│   ├── reviewer_agent.py        #   All outputs → critical review
│   └── communication_agent.py   #   Results → team notifications
│
├── models/                      # Pydantic data contracts
│   ├── bug_report.py            #   Bug report schema + MD parser
│   ├── agent_outputs.py         #   All inter-agent typed outputs
│   └── investigation_report.py  #   Final report schema
│
├── mcp/                         # MCP tool clients
│   ├── base_mcp.py              #   Abstract MCP client with demo mode
│   ├── github_mcp.py            #   GitHub: code search, commits, issues
│   ├── gmail_mcp.py             #   Gmail: email search, send
│   ├── drive_mcp.py             #   Drive: file search, upload
│   ├── calendar_mcp.py          #   Calendar: events, scheduling
│   └── talent_mcp.py            #   Indeed/Dice: candidate search
│
├── utils/                       # Utilities
│   ├── logger.py                #   Dual logging (console + JSON file)
│   └── llm_client.py            #   Gemini API wrapper + mock fallback
│
├── src/                         # Sample app with intentional bug
│   ├── app.py                   #   FastAPI REST API
│   ├── models.py                #   Data models
│   ├── services/
│   │   ├── payment_service.py   #   ⚠ BUGGY: discount calculation
│   │   └── user_service.py      #   Clean (acts as noise)
│   └── utils.py                 #   Utility functions
│
├── tests/                       # Existing test suite (partial)
│   ├── test_user_service.py     #   All passing
│   └── test_payment_service.py  #   Missing the critical bug case
│
├── inputs/                      # Investigation inputs
│   ├── bug_report.md            #   Bug report with symptoms
│   └── logs/app.log             #   Logs with stack traces + noise
│
├── repro/                       # Generated by Reproduction Agent
│   └── repro_test.py            #   Minimal failing test
│
├── output/                      # Generated by pipeline
│   ├── investigation_report.json
│   └── investigation_summary.md
│
└── logs/                        # Runtime logs
    └── agent_trace.log          #   Full JSON trace of every step
```

## The Intentional Bug

The sample app is a **payment processing REST API**. The bug:

**`calculate_order_total()`** applies percentage discounts to the **gross amount** (subtotal + tax) instead of just the subtotal. For a 100% discount:

```
BUGGY:   discount = (subtotal + tax) × 100% = gross → discount includes tax
         total = gross - discount = can be $0 or negative

CORRECT: discount = subtotal × 100% = subtotal → discount covers only merchandise
         taxable = subtotal - discount = $0
         tax = $0 × 8% = $0
         total = $0.00
```

## Reading Agent Traces

The agent trace log is at **`logs/agent_trace.log`**. Each line is a JSON object:

```json
{
  "timestamp": "2024-01-15T14:35:00.000Z",
  "level": "INFO",
  "logger": "pipeline.triage_agent",
  "message": "✓ triage_agent completed in 1234ms",
  "agent_name": "triage_agent",
  "action": "complete",
  "duration_ms": 1234,
  "status": "success"
}
```

**Key fields:**
- `agent_name` — which agent produced the entry
- `action` — `start`, `complete`, `tool_call`, `mcp_call`, `error`, `timeout`
- `duration_ms` — execution time in milliseconds
- `status` — `success`, `failed`, `timeout`

## MCP Integrations

| MCP Server | Tools Used | Agent(s) | Purpose |
|-----------|-----------|----------|---------|
| **GitHub** | `search_code`, `list_commits`, `get_commit`, `create_issue` | Log Analyst, Repo Navigator, Fix Planner | Code search, deploy correlation, issue creation |
| **Gmail** | `search_emails`, `send_email` | Triage, Communication | Prior report search, team notification |
| **Google Drive** | `search_files`, `upload_file` | Triage, Fix Planner | Runbook lookup, report storage |
| **Google Calendar** | `list_events`, `create_event` | Communication | Release window check, post-mortem scheduling |
| **Indeed/Dice** | `search_candidates`, `draft_contractor_spec` | Communication | Creative: auto-draft contractor spec if skills needed |

> **Demo Mode:** By default, MCP clients return simulated responses. Set `MCP_DEMO_MODE=false` and provide tokens to use real services.

## Sample Output (Truncated)

```json
{
  "bug_summary": {
    "title": "Negative payment amount on 100% promo discount",
    "symptoms": [
      "HTTP 500 errors on POST /orders with discount",
      "ValueError: Payment amount must be positive"
    ],
    "severity": "HIGH"
  },
  "root_cause": {
    "hypothesis": "calculate_order_total() applies discount to gross (subtotal + tax) instead of subtotal...",
    "confidence_pct": 92.0,
    "supporting_evidence": ["..."]
  },
  "repro": {
    "artifact_path": "repro/repro_test.py",
    "run_command": "pytest repro/repro_test.py -v"
  },
  "patch_plan": {
    "files_impacted": ["src/services/payment_service.py"],
    "approach": "Change discount base from gross to subtotal, add floor clamp..."
  },
  "mcp_actions_taken": {
    "github_issue_url": "https://github.com/antigravity/payment-service/issues/142",
    "drive_report_url": "https://drive.google.com/file/d/report_001/view",
    "calendar_event_id": "evt_postmortem_003",
    "email_sent_to": "eng-lead@antigravity.dev"
  },
  "confidence_score": 92.0
}
```

## Known Limitations

1. **LLM Dependency:** Without a `GOOGLE_API_KEY`, the system uses deterministic fallback responses — still functional but not demonstrating full LLM reasoning
2. **MCP Demo Mode:** Real MCP server connections are simulated; the interfaces are correct but actual API calls require live tokens
3. **Single-file log input:** The log analyst currently processes one file; a production system would ingest multiple log sources
4. **No actual code patching:** The Fix Planner proposes changes but doesn't write code — a production system would generate and test patches
5. **Sequential execution:** Agents run sequentially; stages 1-3 could potentially run in parallel for better performance
6. **Static repro test:** The deterministic repro test is hand-crafted; with an LLM, it would be dynamically generated from evidence

## License

Internal — Antigravity Software © 2024
