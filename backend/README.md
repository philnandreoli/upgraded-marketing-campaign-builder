# Backend — Marketing Campaign Builder

The backend is a **FastAPI** application that orchestrates a pipeline of AI agents to build marketing campaigns end-to-end. It exposes a REST API and a WebSocket endpoint for real-time progress updates.

## Running the Backend

```bash
# From the project root
pip install -r requirements.txt
uvicorn backend.main:app --reload --port 8000
```

- **API docs:** http://localhost:8000/docs
- **Health check:** http://localhost:8000/health

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `AZURE_AI_PROJECT_ENDPOINT` | Your Azure AI Foundry project endpoint |
| `AZURE_AI_MODEL_DEPLOYMENT_NAME` | Model deployment name (default: `gpt-4`) |

See the root [README](../README.md) for the full list of optional environment variables.

## Agent Pipeline

When a new campaign is created, the **Coordinator Agent** orchestrates the following pipeline:

```
Strategy ➜ Content Creator ➜ Channel Planner ➜ Analytics ➜ Review/QA
                  ▲                                          │
                  └──────── Content Revision ◄───────────────┘
```

Each agent is a Python class that inherits from `BaseAgent` and communicates with Azure AI Foundry via the `LLMService`.

### Agent Descriptions

| Agent | File | Responsibility |
|-------|------|----------------|
| **Base Agent** | `agents/base_agent.py` | Abstract base class providing the `run()` method, LLM integration, and prompt structure that all agents inherit. |
| **Coordinator** | `agents/coordinator_agent.py` | Orchestrates the entire pipeline. Dispatches tasks to each agent in sequence, manages state transitions, handles the content-revision loop, and pauses for human approval when needed. Does **not** call the LLM itself. |
| **Strategy** | `agents/strategy_agent.py` | Analyses the campaign brief and produces objectives, target audience, value proposition, positioning, and key messages. Supports a clarification flow — it can ask the user follow-up questions when the brief has gaps before generating the full strategy. |
| **Content Creator** | `agents/content_creator_agent.py` | Generates marketing copy across multiple channels and formats: headlines, CTAs, social posts, email subjects/bodies, ad copy, and taglines. Produces A/B variants and tailors tone to each channel. |
| **Channel Planner** | `agents/channel_planner_agent.py` | Recommends the optimal marketing channel mix (email, social media, paid ads, SEO, etc.), budget allocation percentages, timing/cadence, and specific tactics for each channel. |
| **Analytics** | `agents/analytics_agent.py` | Defines the measurement framework: KPIs with quantifiable targets, tracking tools, reporting cadence, attribution model, and success criteria. |
| **Review / QA** | `agents/review_qa_agent.py` | Reviews the complete campaign for quality, brand consistency, and completeness. Produces section-level scores and a brand consistency score. Flags issues and suggestions, then triggers human-in-the-loop approval. |

### How Agents Work

1. Each agent defines a **system prompt** (its role and output schema), a **user prompt builder** (assembles campaign data into the prompt), and a **response parser** (validates the LLM JSON output).
2. The `BaseAgent.run()` method sends the prompts to the LLM and returns a structured `AgentResult`.
3. The Coordinator calls each agent in order, threading the growing campaign data through the pipeline.
4. After Review/QA, the Coordinator feeds review feedback back to the Content Creator for a revision pass.
5. Revised content is presented to the user for per-piece approval. Rejected pieces trigger another revision cycle (up to 3 rounds).

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/campaigns` | Create a new campaign from a brief |
| `GET` | `/api/campaigns` | List all campaigns |
| `GET` | `/api/campaigns/{id}` | Get a campaign by ID |
| `DELETE` | `/api/campaigns/{id}` | Delete a campaign |
| `POST` | `/api/campaigns/{id}/clarify` | Submit answers to strategy clarification questions |
| `POST` | `/api/campaigns/{id}/content-approve` | Submit per-piece content approval decisions |
| `WS` | `/ws/campaigns/{id}` | WebSocket for real-time pipeline events |

> **Deprecated:** `/api/campaigns/{id}/review` and `/api/campaigns/{id}/review-clarify` return `410 Gone`. Use `/content-approve` instead.

## Project Structure

```
backend/
├── agents/               # AI agent implementations
│   ├── base_agent.py     # Abstract base class
│   ├── coordinator_agent.py
│   ├── strategy_agent.py
│   ├── content_creator_agent.py
│   ├── channel_planner_agent.py
│   ├── analytics_agent.py
│   └── review_qa_agent.py
├── api/                  # FastAPI route handlers
│   ├── campaigns.py      # REST endpoints
│   └── websocket.py      # WebSocket endpoint
├── models/               # Pydantic models
│   ├── campaign.py       # Campaign, Strategy, Content, etc.
│   └── messages.py       # Agent messages & task definitions
├── services/             # Shared services
│   ├── llm_service.py    # Azure AI Foundry LLM integration
│   ├── agent_registry.py # Foundry Agent Operations registration
│   ├── campaign_store.py # Campaign persistence
│   ├── database.py       # SQLAlchemy async engine setup
│   └── tracing.py        # OpenTelemetry configuration
├── migrations/           # Alembic database migrations
├── tests/                # pytest test suite
├── config.py             # Pydantic-settings configuration
└── main.py               # FastAPI app entry point
```

## Running Tests

```bash
# From the project root
pytest
```

Tests use `pytest-asyncio` and are located in `backend/tests/`. The test suite includes unit tests for agents, API routes, models, the campaign store, and the LLM service.

### Key Test Configuration

- `asyncio_mode = auto` — async tests run without explicit decorators
- Test paths are set to `backend/tests` in `pytest.ini`

## Foundry Agent Operations

When `FOUNDRY_AGENTS_ENABLED=true`, the backend registers each marketing agent as an **AI Foundry Agent version** on startup via `services/agent_registry.py`. This gives you:

- Server-side agent identity and versioning
- Visibility in the Azure AI Foundry portal
- Automatic reuse of existing agent versions (creates new ones only when needed)

If registration fails for any agent, it falls back to direct LLM calls transparently.

## Configuration

All settings are loaded from environment variables (or a `.env` file) using **pydantic-settings**. A complete reference is available in `.env.example`. The configuration is defined in `config.py` and organised into:

- `AzureAIProjectSettings` — AI endpoint and model deployment
- `AgentSettings` — temperature, max tokens, retries
- `TracingSettings` — OpenTelemetry exporter, OTLP endpoint, content recording
- `FoundryAgentsSettings` — enable/disable Foundry Agent Operations
- `AppSettings` — environment, port, log level
