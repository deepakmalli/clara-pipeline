# Clara AI Automation Pipeline

**Zero-cost automation pipeline**: Demo Call → Retell Agent Draft → Onboarding Updates → Agent Revision

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Clara Automation Pipeline                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  PIPELINE A: Demo Call → v1                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │ Ingest   │──→│ LLM      │──→│ Generate │──→│ Save v1 +  │  │
│  │ Transcript│   │ Extract  │   │ Agent    │   │ Create Task│  │
│  └──────────┘   │ Memo JSON│   │ Spec     │   └────────────┘  │
│                  └──────────┘   └──────────┘                    │
│                                                                 │
│  PIPELINE B: Onboarding → v2                                   │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌────────────┐  │
│  │ Ingest   │──→│ LLM      │──→│ Diff &   │──→│ Save v2 +  │  │
│  │ Onboarding│  │ Extract  │   │ Patch    │   │ Changelog  │  │
│  └──────────┘   │ Updates  │   │ v1 → v2  │   └────────────┘  │
│                  └──────────┘   └──────────┘                    │
│                                                                 │
│  LLM: Ollama (local) or Groq (free tier)                       │
│  Orchestrator: n8n (self-hosted) or CLI                         │
│  Storage: Local JSON files                                      │
│  Task Tracker: Local files or GitHub Issues                     │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Transcript ingestion** — Read `.txt` transcript from `dataset/demo/` or `dataset/onboarding/`
2. **LLM extraction** — Send transcript to Ollama/Groq with structured extraction prompt
3. **Account Memo** — Parse LLM output into standardized JSON (all required fields)
4. **Agent Spec generation** — Fill agent prompt template with extracted data (business hours flow, after hours flow, emergency handling, transfer protocols)
5. **Storage** — Save to `outputs/accounts/<account_id>/v1/` (or `v2/`)
6. **Task tracking** — Create a review task (local JSON or GitHub Issue)
7. **Onboarding update** — Extract deltas, patch v1→v2, generate changelog
8. **Diff report** — JSON + Markdown changelog with all changes

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Docker** (for n8n and Ollama, or run Ollama natively)

### Option A: Run with Ollama (Recommended)

```bash
# 1. Clone the repo
git clone https://github.com/YOUR_USERNAME/clara-pipeline.git
cd clara-pipeline

# 2. Install Python dependencies
pip install -r requirements.txt

# 3. Copy environment config
cp .env.example .env
# Edit .env if needed (defaults work for Ollama)

# 4. Install and start Ollama
# Download from https://ollama.com
ollama pull llama3
ollama serve  # keep this running in a separate terminal

# 5. Place your transcripts
# Put demo call transcripts in: dataset/demo/
# Put onboarding transcripts in: dataset/onboarding/

# 6. Run the pipeline
python run_pipeline.py batch
```

### Option B: Run with Docker (n8n + Ollama)

```bash
# 1. Start n8n + Ollama
docker-compose up -d

# 2. Pull the LLM model inside the Ollama container
docker exec clara-ollama ollama pull llama3

# 3. Access n8n at http://localhost:5678
#    Username: admin
#    Password: clara2026

# 4. Import workflows:
#    - Go to n8n → Workflows → Import from File
#    - Import workflows/clara_batch_pipeline.json

# 5. Place transcripts in dataset/ directory and run
```

### Option C: Run with Groq (Free Cloud API)

```bash
# 1. Sign up at https://console.groq.com (free, no credit card)
# 2. Get your API key
# 3. Edit .env:
#    LLM_PROVIDER=groq
#    GROQ_API_KEY=your_key_here
# 4. Run:
python run_pipeline.py batch
```

## CLI Usage

```bash
# Process a single demo call
python run_pipeline.py demo --input dataset/demo/call1.txt

# Process a single onboarding call (auto-matches account)
python run_pipeline.py onboarding --input dataset/onboarding/call1.txt

# Process onboarding with explicit account ID
python run_pipeline.py onboarding --input dataset/onboarding/call1.txt --account-id coastal-plumbing-hvac

# Batch process all files
python run_pipeline.py batch

# List all processed accounts
python run_pipeline.py list
```

## How to Plug In Dataset Files

1. Place **demo call transcripts** in `dataset/demo/`
   - Accepted formats: `.txt`, `.json`, `.md`, `.transcript`
   - Name them descriptively: `coastal_plumbing_demo.txt`

2. Place **onboarding transcripts** in `dataset/onboarding/`
   - Same formats accepted
   - The pipeline auto-matches onboarding to demo by company name

3. Run `python run_pipeline.py batch` — it processes all demo files first (Pipeline A), then all onboarding files (Pipeline B)

## Output Structure

```
outputs/
├── accounts/
│   └── coastal-plumbing-hvac/     # account_id (auto-generated)
│       ├── v1/
│       │   ├── account_memo_v1.json
│       │   ├── agent_spec_v1.json
│       │   └── metadata.json
│       └── v2/
│           ├── account_memo_v2.json
│           ├── agent_spec_v2.json
│           ├── changelog.json
│           ├── changelog.md
│           └── metadata.json
├── tasks/
│   ├── coastal-plumbing-hvac_v1.json
│   └── coastal-plumbing-hvac_v2.json
└── batch_report.json

changelog/
└── coastal-plumbing-hvac_changelog.md
```

## Output Details

### Account Memo JSON

| Field | Description |
|-------|-------------|
| `account_id` | Auto-generated slug from company name |
| `company_name` | Full company name |
| `business_hours` | Days, start time, end time, timezone |
| `office_address` | Physical address |
| `services_supported` | List of service offerings |
| `emergency_definition` | What qualifies as an emergency |
| `emergency_routing_rules` | Who to call, in what order, fallback |
| `non_emergency_routing_rules` | During hours and after hours handling |
| `call_transfer_rules` | Timeout, retries, failure message |
| `integration_constraints` | System-specific rules (e.g., ServiceTrade) |
| `after_hours_flow_summary` | Summary of after-hours call flow |
| `office_hours_flow_summary` | Summary of business hours call flow |
| `questions_or_unknowns` | Missing or unclear information |
| `notes` | Additional observations |

### Agent Spec JSON

| Field | Description |
|-------|-------------|
| `agent_name` | Company Name - Clara Agent |
| `version` | v1 or v2 |
| `voice_style` | Voice, tone, speed, language |
| `system_prompt` | Full generated prompt with both flows |
| `key_variables` | Extracted variables for runtime |
| `tool_invocation_placeholders` | Silent tool definitions |
| `call_transfer_protocol` | Transfer rules and failure handling |
| `fallback_protocol` | What to do when all else fails |

### Changelog

Generated when v2 is created. Shows:
- What changed (field-level diff)
- From → To values
- Reason for each change
- Summary of total modifications

## Retell AI Setup

### Creating a Retell Account
1. Go to [https://www.retellai.com](https://www.retellai.com)
2. Sign up for a free account

### Using the Generated Agent Spec
Since Retell's free tier may not support programmatic agent creation:

1. Open your generated `agent_spec_v2.json` (or `v1`)
2. In Retell dashboard, create a new agent
3. Copy the `system_prompt` field into the agent's prompt configuration
4. Set voice to match `voice_style` settings
5. Configure any available tool/function settings based on `tool_invocation_placeholders`
6. Set up call transfer numbers from `key_variables.emergency_routing`

If Retell provides API access on free tier:
- Set `RETELL_API_KEY` in `.env`
- The pipeline can be extended to auto-create agents via API

## n8n Workflow Setup

### Importing Workflows
1. Start n8n: `docker-compose up -d`
2. Open [http://localhost:5678](http://localhost:5678)
3. Go to **Workflows** → **Import from File**
4. Import the workflows from the `workflows/` directory:
   - `clara_batch_pipeline.json` — Full batch processing
   - `clara_single_demo.json` — Single demo call via webhook
   - `clara_single_onboarding.json` — Single onboarding call via webhook

### Environment Variables for n8n
The Docker container mounts the project directories. The Python scripts run inside the container with access to `dataset/`, `outputs/`, `scripts/`, and `templates/`.

### Webhook Endpoints (when using single-call workflows)
- **Demo**: `POST http://localhost:5678/webhook/clara/demo`
  ```json
  { "file_path": "dataset/demo/call1.txt" }
  ```
- **Onboarding**: `POST http://localhost:5678/webhook/clara/onboarding`
  ```json
  { "file_path": "dataset/onboarding/call1.txt", "account_id": "optional" }
  ```

## LLM Configuration

| Provider | Model | Cost | Setup |
|----------|-------|------|-------|
| **Ollama** (default) | llama3 | $0 | Install Ollama, `ollama pull llama3` |
| **Groq** (fallback) | llama-3.3-70b-versatile | $0 | Sign up free at console.groq.com |

Switch providers by editing `LLM_PROVIDER` in `.env`.

## Known Limitations

1. **Ollama speed**: Without a GPU, processing can be slow (~2-5 min per transcript)
2. **Account matching**: Onboarding-to-demo matching relies on company name extraction; edge cases may need `--account-id` flag
3. **Retell integration**: Free tier may not support API-based agent creation; manual import steps provided
4. **n8n workflows**: The Docker-based n8n setup assumes Python is available in the container; may need a custom Docker image for full automation
5. **Transcript format**: Assumes plain text transcripts; audio files require local transcription (Whisper)

## What I Would Improve With Production Access

1. **Whisper integration** — Auto-transcribe audio recordings using OpenAI Whisper API or local model
2. **Retell API** — Programmatic agent creation and updates via Retell's API
3. **Real task management** — Full Asana integration with project boards, due dates, assignees
4. **Database storage** — Supabase or PostgreSQL for queryable account data
5. **CI/CD pipeline** — Auto-run on new transcript uploads via GitHub Actions
6. **Quality scoring** — Auto-evaluate extracted memo accuracy against transcript
7. **Agent testing** — Simulated test calls against generated agent config
8. **Dashboard** — Web UI for reviewing accounts, approving agents, viewing diffs
9. **Webhook-first architecture** — Event-driven pipeline triggered by file uploads
10. **Multi-language support** — Handle transcripts in Spanish and other languages

## Project Structure

```
clara-pipeline/
├── .env.example          # Environment config template
├── .gitignore
├── docker-compose.yml    # n8n + Ollama containers
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── run_pipeline.py       # Main CLI entry point
├── scripts/
│   ├── __init__.py
│   ├── llm_client.py     # Ollama/Groq LLM abstraction
│   ├── extract.py        # Transcript → Account Memo extraction
│   ├── generate_agent.py # Account Memo → Retell Agent Spec
│   ├── diff_patch.py     # v1 vs v2 diff and changelog
│   ├── task_tracker.py   # Task tracking (local/GitHub Issues)
│   └── utils.py          # Shared utilities
├── templates/
│   ├── extraction_prompt.txt           # LLM prompt for demo extraction
│   └── onboarding_extraction_prompt.txt # LLM prompt for onboarding updates
├── workflows/
│   ├── clara_batch_pipeline.json       # n8n batch workflow
│   ├── clara_single_demo.json          # n8n single demo webhook
│   └── clara_single_onboarding.json    # n8n single onboarding webhook
├── dataset/
│   ├── demo/             # Place demo transcripts here
│   └── onboarding/       # Place onboarding transcripts here
├── outputs/
│   ├── accounts/         # Generated outputs per account
│   └── tasks/            # Task tracking files
├── changelog/            # Global changelog files
└── diff_viewer.html      # Bonus: visual diff viewer
```
