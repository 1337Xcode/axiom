# AXIOM — Complete System Design v2
## Google × CopilotKit × A2A Net London Hackathon · Track 1 (A2A) · 13 June 2026
### Status: Revalidated against live harness codebase (a2anet/a2a-hackathon) and template (a2anet/a2a-hackathon-template). All previous Research Agent and Phalanx Gateway references retired.

---

> **What this document is.** This is the single engineering ground-truth for building AXIOM from scratch. Every design decision has been validated against the actual judging harness source code (`a2anet/a2a-hackathon`), the official template (`a2anet/a2a-hackathon-template`), the live ADK 1.10+ docs, and A2A SDK 0.3.4 spec. When this document and any older file disagree, **this document wins**. Do not carry over patterns from the v1 design (AXIOM_System_Design.md or system.md) without checking them against this document first.

---

## Table of Contents

1. [Hackathon Reality Check — What Was Wrong Before](#1-hackathon-reality-check)
2. [What AXIOM Actually Builds](#2-what-axiom-actually-builds)
3. [Scoring Model — 50/25/25](#3-scoring-model)
4. [Architecture Overview](#4-architecture-overview)
5. [How the Harness Works — The External System You Must Fit](#5-how-the-harness-works)
6. [Dependency Manifest and Pinned Versions](#6-dependency-manifest-and-pinned-versions)
7. [Repository Structure](#7-repository-structure)
8. [Build Order](#8-build-order)
9. [contextId — The Session Identity Contract](#9-contextid--the-session-identity-contract)
10. [Environment API — External Tool Interface](#10-environment-api--external-tool-interface)
11. [Discoverable Tools — Critical Mechanism](#11-discoverable-tools--critical-mechanism)
12. [Personal Agent — Tier 1](#12-personal-agent--tier-1)
13. [Customer Service Agent — Tier 2](#13-customer-service-agent--tier-2)
14. [Redis Knowledge Base and RAG Pipeline](#14-redis-knowledge-base-and-rag-pipeline)
15. [Customer Verification Flow](#15-customer-verification-flow)
16. [System Prompt Engineering — The Primary Score Driver](#16-system-prompt-engineering)
17. [A2A Protocol Implementation via to_a2a()](#17-a2a-protocol-implementation)
18. [External Interoperability — Winning the Other 50%](#18-external-interoperability)
19. [Docker Compose and Deployment](#19-docker-compose-and-deployment)
20. [Environment Variables](#20-environment-variables)
21. [Testing, Validation, and Scoring Loop](#21-testing-validation-and-scoring-loop)
22. [Traps and Validated Bugs](#22-traps-and-validated-bugs)
23. [Pre-Event Checklist](#23-pre-event-checklist)
24. [Cut Order if Time-Constrained](#24-cut-order-if-time-constrained)
25. [Appendix A: A2A v0.3 Wire Format Reference](#appendix-a-a2a-v03-wire-format-reference)
26. [Appendix B: Task JSON Schema](#appendix-b-task-json-schema)
27. [Appendix C: Banking Domain Data Model](#appendix-c-banking-domain-data-model)
28. [Appendix D: Validated ADK Import Paths](#appendix-d-validated-adk-import-paths)

---

## 1. Hackathon Reality Check

The previous AXIOM design contained several critical misalignments with the actual harness. Every one of these will cost points if not corrected.

### What Was Wrong

**Wrong: Three agents (Personal, CS, Research).** The judging harness only evaluates two agents: a Personal Agent and a Customer Service Agent. The Research Agent was removed from the track before the brief was finalised. Building it wastes time and adds complexity with zero scoring benefit. Remove it completely.

**Wrong: Phalanx Gateway as a separate service.** The harness provides its own gateway between Personal Agent and CS Agent. Your Personal Agent does not call your CS Agent directly. It calls the harness's `/cs-agent` proxy endpoint (the `CS_AGENT_URL` environment variable points there). The harness records Leg 2 communication through this proxy. Your agents do not need to implement a custom gateway. The A2A validation and routing you need is provided by `to_a2a()` from ADK.

**Wrong: Manual A2A implementation.** The template uses `google.adk.a2a.utils.agent_to_a2a.to_a2a()` to serve agents over the A2A protocol. This handles the A2A wire format, session mapping, Agent Card serving, and message routing automatically. Building this manually from JSON-RPC is redundant work that introduces bugs.

**Wrong: Ports 8080/8081/8082/8083.** The template and harness expect Personal Agent on port 9001, CS Agent on port 9002, and Redis on port 6379. Using different ports requires all environment variables to be reconfigured.

**Wrong: Scoring model 50/50.** The actual harness scoring formula is 50/25/25, confirmed in `src/a2a_hack/scoring.py`:
- 50%: Your Personal Agent × Your CS Agent (own pair)
- 25%: Your Personal Agent × held-out CS Agent (organiser's)
- 25%: Held-out Personal Agent × Your CS Agent (organiser's)

**Wrong: Generic customer service domain.** The banking knowledge base is Rho-Bank. All tasks involve banking scenarios: balance checks, account openings, card management, fraud disputes, referrals, transfers. The CS agent must know Rho-Bank policies. Generic "billing dispute" and "product return" intents from the previous design do not match the actual task set.

**Wrong: gemini-2.0-x and gemini-2.5-x model names.** The template uses `gemini-3.5-flash` as the model identifier. This is the naming convention in the hackathon harness (`DEFAULT_USER_LLM = "vertex_ai/gemini-3.5-flash"`). The ADK env var is `MODEL`, default `"gemini-3.5-flash"`. Use this identifier unless you have specific reason to change it.

**Wrong: LinkUp research in the CS pipeline.** There are no LinkUp calls needed for Track 1. The CS agent retrieves knowledge from its local Redis RAG index (698 banking documents), not from live web search. LinkUp is relevant only if you choose to build a custom extension — it is not required and will waste your API budget.

**Wrong: ADK `google-adk==2.0.0` pinned.** The template and harness use `google-adk[a2a]>=1.10`. The `to_a2a()` utility lives under `google.adk.a2a.utils.agent_to_a2a`. ADK 2.0 renamed and restructured these paths. Do not pin to 2.0.0.

### What Was Right (Carry Forward)

The previous design had several validated correct positions:
- Pydantic `extra='ignore'` on all A2A validators — still required for external interoperability
- Two-stage LLM pattern consideration for CS agent (tools + schema separation) — still valid if you use `output_schema`
- Tolerant part discriminator handling (`kind` vs. `type`) — still required
- Structured error handling (never return raw exceptions) — still required
- Redis keep-alive TCP options — still required on corporate NAT
- SHA256 cache keys instead of Python `hash()` — still required

---

## 2. What AXIOM Actually Builds

AXIOM is a two-agent banking AI system built on the A2A protocol. It competes in Track 1 of the Google × CopilotKit × A2A Net London Hackathon.

**Personal Agent (port 9001):** Acts as the user's personal banking assistant. Receives simulated customer messages from the harness. Calls user-scope tools from the Environment API on the customer's behalf. Contacts the bank's CS Agent via A2A when bank-side operations or policy questions are needed. Relays verification details between the user and CS. Does not have access to bank account data directly.

**Customer Service Agent (port 9002):** Acts as Rho-Bank's AI customer service representative. Receives A2A messages from the Personal Agent (via the harness gateway). Verifies customer identity before touching account data. Uses RAG over 698 banking documents to find the right procedure. Calls bank-side tools from the Environment API. Handles discoverable tool grants (both giving user tools and unlocking agent-only tools). Returns clear, structured responses that the Personal Agent can relay to the customer.

**Redis (port 6379):** Serves two distinct purposes. Plane A is the CS agent's RAG knowledge base: 698 JSON banking documents indexed for BM25 full-text search and 768-dimensional HNSW vector search. Plane B is the Session Memory layer: lightweight Redis Hashes keyed by `session:{contextId}:memory` that both agents read and write, enabling them to share verification state and session context in real-time across A2A turns. This directly implements the Redis sponsor's stated judging criterion: "agents that actually learn, remember, and collaborate — not just three bots running in parallel."

**What AXIOM does not build:** A Research Agent. A Phalanx gateway. An AG-UI frontend. LinkUp search integration. A custom A2A wire format implementation. None of these contribute to the Track 1 score.

---

## 3. Scoring Model

Understanding the scoring model precisely is how you make correct engineering trade-offs.

```
Final Score = 0.50 × (your_personal × your_cs)
            + 0.25 × (your_personal × held_out_cs)
            + 0.25 × (held_out_personal × your_cs)
```

Where each pairing score is the mean reward across the tasks in the chosen split. Tasks not completed (timeout, infrastructure error) count as reward 0.

The reward for each task is binary or partial based on whether golden actions were executed with the correct tool names and arguments. See Appendix B for the task evaluation schema.

### Implications for Design

**Your system prompt is the primary lever.** The baseline (best Gemini model, no prompt engineering) scores approximately 25% according to the organiser. With good prompts, 50%+ is achievable. The delta is entirely in system prompt quality, tool calling accuracy, and RAG retrieval precision.

**Both agents must work with strangers.** The held-out agents are built by the organiser. They follow the A2A spec but have no special knowledge of your internal conventions. Your Personal Agent must work cleanly with any CS Agent that follows the protocol. Your CS Agent must work cleanly with any Personal Agent.

**Robustness under strange inputs is a scoring multiplier.** If your CS Agent crashes or returns an unparseable response when called by the organiser's Personal Agent, you lose all 25% of the cross-pair score for that half. Input validation and graceful degradation are therefore not optional.

**The 50% own-pair score is easiest to optimise.** You control both agents. The conversation between them can be designed to be highly structured.

**Feedback tasks are your pre-submission smoke test.** The harness exposes three tasks from the train split as feedback tasks: `task_006`, `task_009`, and `task_053`. Run your agents against these before submission to verify end-to-end task completion.

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                     HACKATHON HARNESS (external)                     │
│                                                                       │
│  User Simulator (LLM)  →  A2A Bridge  →  Environment API (:8090)    │
│                                ↓             ↑           ↑           │
│                         Records Leg 1        │           │           │
│                                              │ Tools     │ Tools     │
│                    /cs-agent gateway ←───────┘     ←─────┘           │
│                    (proxies to real CS, records Leg 2)               │
└────────────────────────────────┬────────────────────────────────────┘
                                 │  A2A JSON-RPC (message/send)
                                 ▼  context_id = session UUID
              ┌──────────────────────────────────┐
              │   PERSONAL AGENT  (port 9001)    │
              │                                  │
              │   to_a2a(root_agent)             │
              │   LlmAgent (gemini-3.5-flash)    │
              │                                  │
              │   Tools:                         │
              │     EnvApiToolset()              │ ← GET/POST /sessions/{ctxId}/tools
              │     ask_customer_service()       │   to harness ENV_API
              │                                  │
              │   Redis writes:                  │
              │     session:{ctxId}:memory       │ ← HSET verification data
              └──────────────────────────────────┘
                         │                    │
                         │ A2A JSON-RPC       │ Redis HSET
                         │ to CS_AGENT_URL    │ session:{ctxId}:memory
                         │ context_id         │
                         ▼                    ▼
              ┌──────────────────────────────────┐
              │   CS AGENT  (port 9002)          │
              │                                  │
              │   build_index() → to_a2a(agent)  │
              │   LlmAgent (gemini-3.5-flash)    │
              │                                  │
              │   Tools:                         │
              │     EnvApiToolset()              │ ← GET/POST /sessions/{ctxId}/tools
              │     kb_search_bm25()             │   to harness ENV_API
              │     kb_search_vector()           │
              │     read_session_memory()        │ ← HGETALL session:{ctxId}:memory
              └──────────────┬───────────────────┘
                             │
                             ▼
              ┌──────────────────────────────────────────────┐
              │   REDIS  (port 6379)                         │
              │                                              │
              │   PLANE A — RAG Knowledge Base:              │
              │     Index: kb_idx (RediSearch)               │
              │     698 docs: doc:* HASH keys                │
              │     BM25 TextField + HNSW Vector             │
              │                                              │
              │   PLANE B — Session Memory:                  │
              │     session:{contextId}:memory HASH          │
              │     Fields: verified, dob, email, phone,     │
              │             address, intent, user_id, etc.   │
              │     TTL: 3600s per session                   │
              └──────────────────────────────────────────────┘
```

### Why This Architecture

**Single process per agent.** Each agent is one Uvicorn process serving A2A via `to_a2a()`. No internal HTTP hops. No orchestrator subprocess. The LlmAgent handles everything within the ADK session lifecycle.

**All banking tool calls go through the Environment API.** Neither agent owns a database. Banking data lives in the harness's Environment API. The agents discover and call tools via `GET /sessions/{contextId}/tools` and `POST /sessions/{contextId}/tools/{name}`. This is the harness's design.

**Redis serves two planes.** Plane A (RAG) gives the CS Agent access to 698 banking knowledge documents. Plane B (Session Memory) gives both agents a shared runtime context layer keyed by `contextId`. The Personal Agent writes verification data the user provides; the CS Agent reads it before asking. This fulfils the Redis sponsor's stated judging criterion and makes the agents demonstrably collaborative rather than independent.

**The harness gateway records both legs.** Leg 1 (user ↔ personal) and Leg 2 (personal ↔ CS) are both recorded by the harness for scoring. Your agents do not need to record anything themselves.

---

## 5. How the Harness Works

Understanding the harness internals is critical for building agents that score well. This section describes what the harness does on the scoring side of the wall.

### Session Lifecycle

The harness creates a UUID for each task run. This UUID is the `contextId` that flows through the entire session. The harness:
1. Creates a session with a unique UUID as `contextId`
2. Loads the task's initial database state into its Environment API
3. Starts a user simulator LLM with the task's `user_scenario.instructions`
4. The user simulator generates a message and sends it to your Personal Agent as an A2A `message/send` with the `contextId` set
5. Your Personal Agent processes the message, calls tools if needed, and calls your CS Agent (via the harness proxy)
6. The harness records all tool calls (Leg 1 + Leg 2) and all agent messages
7. After the conversation ends (max 60 turns or `###STOP###` signal from user sim), the harness merges the trajectory
8. The merged trajectory is evaluated against `evaluation_criteria.actions` (golden actions)
9. Reward = fraction of golden actions correctly executed

### The `/cs-agent` Gateway in the Harness

When your Personal Agent wants to call your CS Agent, it sends an A2A request to `CS_AGENT_URL`. In production harness mode, this is `http://host.docker.internal:8090/cs-agent`. The harness's `env_api/server.py` proxies this request to the actual CS Agent URL (your port 9002 service), recording both the outgoing message and the response. This is how the harness captures Leg 2 communication.

**Your Personal Agent must use `CS_AGENT_URL` as given by the environment variable.** Do not hardcode the CS Agent's port 9002. The harness proxy is mandatory for recording.

### Tool Scope

The harness separates tools into two scopes:
- **User scope** (Personal Agent's `ENV_API_TOKEN` = `ENV_API_USER_TOKEN`): Only tools listed in `task.user_tools`
- **Agent scope** (CS Agent's `ENV_API_TOKEN` = `ENV_API_AGENT_TOKEN`): All banking tools

When you call `GET /sessions/{contextId}/tools`, the harness returns only the tools for your token's scope. The personal agent sees user-scope tools. The CS agent sees all tools including bank-side tools.

### Golden Actions

Each task has a set of golden actions in `evaluation_criteria.actions`. A golden action has:
- `name`: exact tool name (e.g. `open_bank_account_4821`)
- `arguments`: exact required arguments (e.g. `{"account_class": "Blue Account", "user_id": "tm92c4d7e8"}`)
- `requestor`: `"user"` (personal agent must call this) or `"assistant"` (CS agent must call this)
- `compare_args`: if present, only these argument keys are checked for exact match

Reward is based on `reward_basis`. Most tasks use `"DB"` (database state after all actions) or `"ACTION"` (specific actions were called). Tools must be called with exactly the right arguments. If the CS agent calls the right tool with a wrong user_id or a typo in account_class, it gets no credit for that action.

### Task Splits

- **79 total tasks** in `src/a2a_hack/data/tasks/`
- **63 train tasks**: Use these for development and prompt tuning
- **20 test tasks**: Held-out, used for final scoring (not available for preview)
- **3 feedback tasks**: `task_006`, `task_009`, `task_053` — use these for smoke testing during the event

### Concurrency and Timeouts

The harness runs tasks with `DEFAULT_CONCURRENCY = 2` (two parallel simulations). Each task has a `DEFAULT_TASK_TIMEOUT_S = 600.0` (10 minutes) wall-clock timeout, and each turn has `DEFAULT_TURN_TIMEOUT_S = 300.0` (5 minutes). If your agent does not respond within the turn timeout, the turn counts as failed.

---

## 6. Dependency Manifest and Pinned Versions

### Python (requirements.txt for each service)

```
# personal_agent/requirements.txt
google-adk[a2a]>=1.10
a2a-sdk[http-server]>=0.3.4,<0.4
httpx>=0.27
uvicorn>=0.34
redis>=5.0                          # Session Memory Plane writes

# cs_agent/requirements.txt
google-adk[a2a]>=1.10
a2a-sdk[http-server]>=0.3.4,<0.4
httpx>=0.27
uvicorn>=0.34
redis>=5.0
google-genai>=1.0
redis-py[hiredis]>=5.0
```

**Why `<0.4` on a2a-sdk:** A2A SDK 0.4 is expected to contain breaking changes aligned with A2A v1.0. The harness uses `>=0.3.4,<0.4`. Do not upgrade past this range.

**Why `google-adk[a2a]`:** The `[a2a]` extra installs the `to_a2a()` utility and A2A-related ADK extensions. Without it the import `from google.adk.a2a.utils.agent_to_a2a import to_a2a` will fail.

**Why `google-genai>=1.0` in cs_agent only:** The `_embed()` function in `rag_tools.py` calls the Gemini embedding model directly via the `google.genai` client. This is separate from ADK's LLM calls.

### Node.js / Frontend

Track 1 does not require a frontend for scoring. No frontend dependencies are required.

### Docker base images

```
python:3.12-slim     # Both agent services
redis:8              # Redis with RediSearch module built-in
```

**Why redis:8?** Redis 8 ships with the RediSearch module built-in. Earlier Redis versions required a separate `redis/redis-stack` image. Using `redis:8` simplifies the dependency graph.

### Environment Variables Required at Runtime

```bash
# Injected by harness into agent containers:
ENV_API_URL=http://host.docker.internal:8090   # Harness Environment API base URL
ENV_API_TOKEN=<harness-issued token>           # Bearer token (scope determines user/agent access)
CS_AGENT_URL=http://host.docker.internal:8090/cs-agent  # Harness CS gateway proxy

# Self-configured:
GOOGLE_API_KEY=<your-gemini-key>               # OR set GOOGLE_CLOUD_PROJECT + location
MODEL=gemini-3.5-flash                         # Or your chosen Gemini model
REDIS_URL=redis://redis:6379/0                 # CS agent only
KB_DOCUMENTS_PATH=/app/kb/documents            # CS agent only
KB_POLICY_PATH=/app/kb/policy.md              # CS agent only
KB_EMBEDDINGS_PATH=/app/kb/embeddings.json    # CS agent only (precomputed cache)
```

---

## 7. Repository Structure

```
axiom/
├── docker-compose.yml              # Service orchestration (3 services)
├── .env.example                    # All env vars documented
├── .gitignore                      # Excludes .env, __pycache__, kb/embeddings.json
│
├── personal_agent/
│   ├── Dockerfile
│   ├── main.py                     # Entry point: to_a2a(root_agent)
│   ├── agent.py                    # LlmAgent definition + enhanced system prompt
│   ├── cs_client_tool.py           # ask_customer_service() A2A tool
│   ├── env_toolset.py              # EnvApiToolset + session_id() + call_env_tool
│   ├── redis_memory.py             # write_session_memory() — Plane B writes
│   └── requirements.txt
│
├── cs_agent/
│   ├── Dockerfile
│   ├── main.py                     # Entry point: build_index() then to_a2a(root_agent)
│   ├── agent.py                    # LlmAgent with policy.md + RAG guidance + enhanced prompt
│   ├── env_toolset.py              # EnvApiToolset + session_id() + call_env_tool (same as personal)
│   ├── rag_tools.py                # kb_search_bm25, kb_search_vector, _embed
│   ├── redis_memory.py             # read_session_memory() — Plane B reads
│   ├── ingest.py                   # build_index(): drop/create Redis index + load docs + embed
│   ├── precompute_embeddings.py    # Run BEFORE the event to generate kb/embeddings.json
│   └── requirements.txt
│
├── kb/
│   ├── policy.md                   # Rho-Bank CS agent master policy (62 lines)
│   ├── documents/                  # 698 JSON banking knowledge base articles
│   │   ├── doc_bank_accounts_bank_accounts_(general)_001.json
│   │   ├── doc_bank_accounts_bank_accounts_(general)_002.json
│   │   └── ... (696 more files)
│   └── embeddings.json             # Generated by precompute_embeddings.py (gitignored)
│
└── tests/
    ├── conftest.py                 # Test fixtures: wait_for_health(), free_port()
    ├── test_smoke.py               # Smoke test against feedback tasks (task_006, task_009, task_053)
    ├── test_contextid.py           # Verify contextId propagation end-to-end
    ├── test_redis_memory.py        # Verify Plane B write/read round-trip
    └── test_agent_cards.py         # Verify both agent cards are valid A2A spec
```

### File Ownership Notes

`env_toolset.py` is identical in both agents (copy, not symlink, for Docker build simplicity). Both contain `session_id()`, `call_env_tool`, `EnvApiToolset`, and `EnvApiTool`. The only difference is the `ENV_API_TOKEN` value injected at runtime — user token for personal, agent token for CS.

`kb/documents/` and `kb/policy.md` are taken verbatim from the template repository. Do not modify the policy.md content except to add to the `Additional Instructions` section. The base policy is what the judges use as reference for correct CS agent behaviour.

---

## 8. Build Order

Build in this exact sequence. Each step depends on the previous being verified.

```
Step 1: Clone template, verify it runs out-of-the-box
        → docker-compose up
        → smoke test with curl
        → confirm: both agent cards return 200

Step 2: Precompute KB embeddings
        → python cs_agent/precompute_embeddings.py
        → verify: kb/embeddings.json exists, is ~2.7MB
        → THIS MUST BE DONE BEFORE THE EVENT — startup blocks for 10+ minutes without it

Step 3: Enhance Personal Agent system prompt (see Section 16.1)
        → Test with feedback task_006
        → Confirm personal agent calls CS correctly and relays verification

Step 4: Enhance CS Agent system prompt (see Section 16.2)
        → Test with feedback task_006
        → Confirm CS verifies identity and calls correct tools

Step 5: Verify contextId flows correctly
        → Run test_contextid.py
        → Both agents must use the same session.id as env API session key

Step 6: Verify RAG retrieval
        → Query kb_search_bm25 and kb_search_vector with banking terms
        → Confirm relevant documents are returned

Step 7: Run all three feedback tasks
        → task_006, task_009, task_053
        → Note which golden actions succeed and which fail
        → Iterate on prompts

Step 8: Verify agent cards for interoperability
        → curl http://localhost:9001/.well-known/agent.json
        → curl http://localhost:9002/.well-known/agent.json
        → Validate against A2A spec (see Section 17)

Step 9: Set up tunnel for external access
        → ngrok http 9001 (Personal Agent must be reachable by harness)
        → Test from external network

Step 10: Submit GitHub repo URL to harness scoring site (available ~14:30)
         → Watch live scores
         → Iterate prompts and resubmit
```

---

## 9. contextId — The Session Identity Contract

**This is the single most critical concept in the system.** If contextId propagation breaks, every golden action fails silently. The reward is 0 and no error is surfaced.

### What contextId Is

The `contextId` is a UUID created by the harness at the start of each simulation run. It is the session key for:
- The harness's Environment API (`/sessions/{contextId}/tools`)
- The Personal Agent's ADK session (`context.session.id`)
- The CS Agent's ADK session (must match Personal Agent's contextId)
- All tool call recording (harness tracks which calls belong to which session)

### How it Flows

```
Harness creates UUID → "ctx-abc-123"
        │
        ▼  A2A message/send
Personal Agent receives A2A request
  │  A2A params.message.context_id = "ctx-abc-123"
  │  ADK's to_a2a() sets session.id = "ctx-abc-123"  ← AUTOMATIC
  │  env_toolset.session_id(context) = context.session.id = "ctx-abc-123"
  │  Tool calls: POST /sessions/ctx-abc-123/tools/...
  │
  ▼  ask_customer_service() tool
CS Client sends A2A message to CS_AGENT_URL (harness proxy)
  │  A2A params.message.context_id = "ctx-abc-123"   ← MUST PROPAGATE
  │  ADK's to_a2a() sets CS session.id = "ctx-abc-123"  ← AUTOMATIC
  │  CS env_toolset.session_id(context) = "ctx-abc-123"
  │  CS tool calls: POST /sessions/ctx-abc-123/tools/...
  ▼
Harness records: both agents used the same session → trajectory merged correctly
```

### The Rule

**ADK's `to_a2a()` automatically maps the incoming A2A `context_id` to the ADK session ID.** This means `context.session.id` in any tool callback will equal the A2A `context_id`. The `session_id()` helper in `env_toolset.py` just returns `context.session.id` — it does not generate a new ID.

**The `ask_customer_service()` tool in the Personal Agent must send `context_id=session_id(tool_context)` in the outgoing A2A message.** This is how the CS Agent receives the same contextId. Without this field in the outgoing message, the harness creates a new session for the CS Agent and the two agents' tool calls are not associated.

### What Breaks contextId

- Generating a new UUID inside `ask_customer_service()` instead of using `session_id(tool_context)`. Always use `session_id(tool_context)` from `env_toolset.py`.
- Using `uuid.uuid4()` for the session seed anywhere in the request path.
- Calling `context.session.id` incorrectly (e.g. using a different context object than the one passed to the tool function).
- Creating a new `httpx.AsyncClient` per call inside a `with` block that exits before the A2A response arrives (see Trap 6 from v1 design — the stream-proxy pattern).

---

## 10. Environment API — External Tool Interface

The Environment API is the harness's tool execution server. It runs at `ENV_API_URL` (default `http://host.docker.internal:8090`). Both agents call it to list and execute tools.

### Listing Available Tools

```
GET {ENV_API_URL}/sessions/{contextId}/tools
Authorization: Bearer {ENV_API_TOKEN}

Response:
{
  "tools": [
    {
      "function": {
        "name": "verify_customer_identity",
        "description": "...",
        "parameters": {
          "type": "object",
          "properties": {
            "user_id": {"type": "string"},
            ...
          },
          "required": ["user_id"]
        }
      }
    },
    ...
  ]
}
```

The response returns only tools visible to the caller's token scope. Personal Agent (user token) sees user-scope tools. CS Agent (agent token) sees all tools.

### Executing a Tool

```
POST {ENV_API_URL}/sessions/{contextId}/tools/{tool_name}
Authorization: Bearer {ENV_API_TOKEN}
Content-Type: application/json

{"arguments": {"param1": "value1", "param2": "value2"}}

Response:
{"content": "result text or JSON", "error": false}

Error response:
{"error": true, "content": "HTTP 404: Tool not found"}
```

### The EnvApiToolset Pattern

The `EnvApiToolset` class is an ADK `BaseToolset` that fetches tool schemas live from the Environment API on each request. This is important because tools can be granted mid-conversation (discoverable tools, see Section 11). A fresh fetch on each LLM invocation ensures newly granted tools appear automatically.

The fallback `call_env_tool(tool_name, arguments_json, tool_context)` function allows the LLM to call any tool by name even if it was not in the fetched list — this is the safety net for late-discovered tools.

### Critical: Never Hardcode Tool Names

Tool names in the Environment API are deterministic but not human-readable. Examples from the knowledge base include `open_bank_account_4821`, `transfer_funds_between_bank_accounts_7291`, `verify_customer_identity_3344`. The exact names come from the knowledge base documents. The CS agent must search the KB to find the right tool name before calling it. Never assume a tool name.

---

## 11. Discoverable Tools — Critical Mechanism

The discoverable tools mechanism is responsible for a significant portion of golden actions. Misunderstanding it will cost you many points on tasks involving account operations, card management, and special procedures.

### Two Types of Discoverable Tools

**User Discoverable Tools:** Tools that the bank has determined the customer should call themselves (not the agent). The CS Agent is responsible for unlocking these for the user.
- The CS Agent calls `give_discoverable_user_tool(tool_name)` to grant the tool to the user's Personal Agent
- After granting, the Personal Agent's next `EnvApiToolset.get_tools()` call will include the newly granted tool
- The CS Agent should explain to the user what the tool does and what arguments to provide
- The Personal Agent must then call the tool on the user's behalf

**Agent Discoverable Tools:** Specialised internal tools that the CS Agent can unlock and use.
- The CS Agent must call `unlock_discoverable_agent_tool(tool_name)` first
- Only after unlocking can it call `call_discoverable_agent_tool(tool_name, arguments)` or use the direct tool name
- The unlock step is required — calling without unlocking will return an error
- The knowledge base document for each procedure specifies exactly which agent-discoverable tools exist

### How to Handle in the CS Agent Prompt

The CS agent's system prompt (from `policy.md`) already documents this, but the prompt must make the sequence clear:

```
For USER DISCOVERABLE TOOLS:
1. Search KB to find the tool name (never invent tool names)
2. Call give_discoverable_user_tool(discoverable_tool_name) with exact name
3. Explain to the Personal Agent what the tool does and what arguments the user should provide
4. Wait for the Personal Agent to confirm the user executed it

For AGENT DISCOVERABLE TOOLS:
1. Search KB to find the tool name (never invent tool names)
2. Call unlock_discoverable_agent_tool(agent_tool_name) first
3. After confirmation of unlock, call call_discoverable_agent_tool(agent_tool_name, arguments)
   OR call the tool directly by name (both patterns are supported after unlock)
4. IMPORTANT: Do not unlock tools you don't plan to use. Logging records unlocks.
```

### Why This Matters for Scoring

Many golden actions have `requestor: "user"` — meaning the Personal Agent must be the one to call the tool, not the CS Agent. If the CS Agent calls those tools directly, it gets no credit. The mechanism is:
1. CS Agent identifies the user-side action needed
2. CS Agent calls `give_discoverable_user_tool(tool_name)` to grant access
3. CS Agent tells the Personal Agent what tool to call and with what arguments
4. Personal Agent executes the tool call through the Environment API
5. Harness records `requestor = "user"` for that tool call → matches golden action

---

## 12. Personal Agent — Tier 1

### 12.1 Responsibilities

- Receive customer message from user simulator via A2A
- Act as the user's trusted personal banking assistant
- Call user-scope tools via the Environment API when the user wants to perform an action
- Identify when bank-side operations require CS agent involvement
- Forward requests to CS Agent via `ask_customer_service()` tool, propagating contextId
- Relay verification requests from CS back to the user (ask user for DOB, email, phone, address)
- Pass verified information faithfully to CS — never fill in placeholder values
- Execute tools that CS grants to the user (via `give_discoverable_user_tool`)
- Relay CS Agent's response to the user

### 12.2 What the Personal Agent Must NOT Do

- Access bank account data directly (use CS for lookups)
- Invent account details, policy information, or tool arguments
- Send the raw incoming A2A envelope to the LLM (extract text first, keep as conversation turn)
- Create a new UUID as contextId — always use `session_id(tool_context)` from `env_toolset.py`
- Silently ignore CS Agent failures — relay error messages to the user

### 12.3 File: personal_agent/main.py

```
[PSEUDOCODE — not to be trusted as working code, illustration only]

import os
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from agent import root_agent

app = to_a2a(
    root_agent,
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "9001"))
)
```

`to_a2a()` creates the FastAPI ASGI application that:
- Serves `GET /.well-known/agent.json` (Agent Card)
- Handles `POST /message/send` as the primary A2A endpoint
- Maps incoming `context_id` to ADK session ID automatically
- Returns A2A-compliant Task objects as responses

### 12.4 File: personal_agent/agent.py

The `root_agent` is an ADK `LlmAgent` with:
- `name = "personal_agent"`
- `model = MODEL` (from env, default `"gemini-3.5-flash"`)
- `instruction = INSTRUCTION` (the enhanced system prompt — see Section 16.1)
- `tools = [EnvApiToolset(), ask_customer_service]`

No `output_schema`. The Personal Agent responds in natural language conversation. Using `output_schema` on an agent that also has tools risks the TRAP 1 issue from the previous design.

### 12.5 File: personal_agent/cs_client_tool.py

The `ask_customer_service(message, tool_context)` function is an async ADK tool that:
1. Extracts `context_id = session_id(tool_context)` from the ADK context
2. Builds an A2A `Message` with `context_id=context_id` and `role=Role.user`
3. Creates an `httpx.AsyncClient` with a 300-second timeout
4. Creates an A2A `ClientFactory` pointing at `CS_AGENT_URL`
5. Sends the message and collects the A2A response (Message or Task)
6. Returns the text content of the response, or `"[no response from customer service]"` on empty

**The timeout is 300 seconds.** Banking scenarios involving multiple tool calls (verify → lookup → act → confirm) can take 30-60 seconds per turn. A 30-second timeout will false-fail these tasks.

**`CS_AGENT_URL` points to the harness gateway proxy.** This is `http://host.docker.internal:8090/cs-agent` in the harness environment. Do not hardcode `http://cs-agent:9002`.

### 12.6 File: personal_agent/env_toolset.py

Contains:
- `session_id(context)` → returns `context.session.id` (the contextId)
- `_post_tool_call(sid, name, arguments)` → async POST to ENV_API
- `call_env_tool(tool_name, arguments_json, tool_context)` → generic fallback tool
- `EnvApiTool(schema)` → BaseTool wrapping one env API function schema
- `EnvApiToolset()` → BaseToolset that fetches tools live per session

The `EnvApiToolset.get_tools(readonly_context)` method:
- If `readonly_context is None` (agent card construction), returns `[FunctionTool(call_env_tool)]` only
- Otherwise, fetches live tool list from `GET {ENV_API_URL}/sessions/{sid}/tools`
- Appends `call_env_tool` as fallback
- Returns the combined list

---

## 13. Customer Service Agent — Tier 2

### 13.1 Responsibilities

- Receive A2A messages from the Personal Agent (via harness gateway)
- Verify customer identity before accessing or modifying account data
- Search the knowledge base to find the correct procedure for each request
- Call bank-side tools from the Environment API to execute banking actions
- Unlock and call agent-discoverable tools when the KB specifies them
- Grant user-discoverable tools to the Personal Agent when the KB specifies them
- Respond clearly and completely so the Personal Agent can relay the answer to the user
- Never leak internal policy details that the policy forbids sharing
- Use `get_current_time()` tool when the current date/time is needed — never assume it

### 13.2 What the CS Agent Must NOT Do

- Make up tool names — only use names discovered from the KB or from `get_tools()`
- Call tools without verifying the customer first (except non-sensitive informational queries)
- Guess or invent policy details — always search the KB
- Ask for documentation unless the KB explicitly says to
- Transfer to human agents without asking the user first (unless KB specifies otherwise)
- Leak information about account status, balances, or personal data before identity verification
- Unlock tools it does not plan to use (this corrupts the harness's database logging)

### 13.3 File: cs_agent/main.py

```
[PSEUDOCODE — illustration only]

import os
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from ingest import build_index

build_index()          # Blocks until all 698 docs are indexed in Redis
                       # Fast with precomputed embeddings (< 10s)
                       # Slow without them (10+ min of live embedding API calls)

from agent import root_agent  # Import after index is ready

app = to_a2a(
    root_agent,
    host=os.environ.get("HOST", "0.0.0.0"),
    port=int(os.environ.get("PORT", "9002"))
)
```

The `build_index()` call is a readiness gate. The A2A endpoint is only served after the KB index is built. This prevents the CS agent from accepting requests before it can search the knowledge base.

### 13.4 File: cs_agent/agent.py

The `root_agent` is an ADK `LlmAgent` with:
- `name = "cs_agent"`
- `model = MODEL`
- `instruction = policy_content + rag_guidance + enhanced_instructions` (see Section 16.2)
- `tools = [EnvApiToolset(), kb_search_bm25, kb_search_vector]`

The instruction string is built at module import time by reading `kb/policy.md` and appending additional guidance. The policy.md file serves as the first part of the system prompt — do not replace it, extend it.

### 13.5 File: cs_agent/rag_tools.py

Two search tools registered with the LlmAgent:

**`kb_search_bm25(query, top_k=5)`:**
- Tokenises `query` with regex `\w+`, lowercases
- Joins unique terms with `|` (OR join)
- Executes `FT.SEARCH kb_idx "term1|term2" LIMIT 0 5 RETURN 2 title content`
- Returns `[{"doc_id": str, "title": str, "content": str}, ...]`

**`kb_search_vector(query, top_k=5)`:**
- Embeds `query` using `_embed([query])[0]` → 768-float vector
- Executes KNN search: `FT.SEARCH kb_idx *=>[KNN 5 @embedding $vec AS score] PARAMS 2 vec ... SORTBY score LIMIT 0 5 RETURN 3 title content score DIALECT 2`
- Returns `[{"doc_id": str, "title": str, "content": str}, ...]` (score stripped)

**`_embed(texts)`:**
- Uses `google.genai.Client.models.embed_content(model=EMBEDDING_MODEL, contents=texts)`
- `EMBEDDING_MODEL = "gemini-embedding-001"` — 768-dimensional output
- Returns list of float lists

**Redis connection:** Synchronous `redis.Redis.from_url(REDIS_URL, decode_responses=False)`. The `decode_responses=False` is required because the embedding vector is stored as raw binary bytes.

**When to use BM25 vs vector:**
- BM25 is better for exact keyword lookups: tool names, product names, policy rule numbers
- Vector is better for natural language semantic queries: "what happens if I lose my card", "account opening requirements"
- Best practice: search both and combine results, deduplicating by `doc_id`

### 13.6 File: cs_agent/ingest.py

The `build_index()` function:
1. Connects to Redis at `REDIS_URL`
2. Loads all 698 JSON documents from `KB_DOCUMENTS_PATH`
3. Drops the existing `kb_idx` index if it exists (idempotent restarts)
4. Creates the index schema:
   - `TextField("title", weight=2.0)` — title matches weighted higher
   - `TextField("content")` — full content indexed
   - `VectorField("embedding", "HNSW", {"TYPE": "FLOAT32", "DIM": 768, "DISTANCE_METRIC": "COSINE"})`
   - IndexDefinition: prefix `"doc:"`, type `IndexType.HASH`
5. Loads precomputed embedding cache from `KB_EMBEDDINGS_PATH` if it exists
6. For any documents without a cached embedding: calls `_embed()` in batches of 25
7. Stores all documents in Redis as HASH: `HSET doc:{id} title ... content ... embedding <binary>`
8. Executes all HSET operations in a pipeline for speed

### 13.7 File: cs_agent/precompute_embeddings.py

Run this BEFORE the event. It generates `kb/embeddings.json` — a mapping of `doc_id → base64-encoded float32 array`. With this cache present, `build_index()` completes in under 10 seconds. Without it, 698 live embedding API calls take 10-15 minutes and may exhaust API rate limits.

**Command:** `python cs_agent/precompute_embeddings.py`  
**Output:** `kb/embeddings.json` (~2.7MB)  
**Run this once before the event and commit the output if acceptable, or copy it into the container at build time.**

---

## 14. Redis Knowledge Base and RAG Pipeline

### 14.1 Index Schema

```
Index name: kb_idx
Key prefix: doc:
Key type: HASH

Fields:
  title      TextField   weight=2.0
  content    TextField   weight=1.0
  embedding  VectorField HNSW FLOAT32 DIM=768 DISTANCE_METRIC=COSINE
```

### 14.2 Document Format

Each document in `kb/documents/` follows this schema:

```json
{
  "id": "doc_category_subcategory_NNN",
  "title": "Human-readable title",
  "content": "Markdown-formatted procedure, eligibility rules, tool references, thresholds"
}
```

Documents contain critical information that is not in the system prompt:
- Exact tool names with their unique numeric suffixes (e.g. `open_bank_account_4821`)
- Eligibility requirements (age thresholds, balance minimums, account age requirements)
- Exact procedure steps in the correct order
- Fee structures, limits, and deadlines
- References to user-discoverable and agent-discoverable tools

### 14.3 Document Categories

The 698 documents cover:
- **Bank accounts (general):** Opening checking/savings, closures, maintenance
- **Business checking accounts:** Beige enterprise accounts, treasury operations
- **Credit cards:** Application, closure, disputes, rewards, replacements
- **Debit cards:** Replacement, blocking, international usage fees
- **Payments and transfers:** Internal transfers, external wires, scheduled payments
- **Referrals:** How referral submissions work, credit timing
- **Fraud disputes:** Dispute filing procedure, timeline, provisional credits
- **Account products:** Fee structures, ATM networks, overdraft policies, interest rates
- **User profile management:** Address, email, phone number updates, verification

### 14.4 Query Strategy for CS Agent

The CS agent must search before acting. The prompt must include explicit guidance:

1. When asked about account balances, transactions, or account details → call tools directly after verification (this data is in the environment, not the KB)
2. When asked about policies, fees, procedures, or eligibility → search KB first
3. When about to take a bank-side action → search KB to confirm the correct tool name and procedure
4. For complex scenarios → search both BM25 (for tool names) and vector (for semantic policy context)

Example queries the CS agent should generate:
- `"opening personal checking account requirements"` → finds doc with eligibility and `open_bank_account_4821`
- `"ATM withdrawal foreign fee"` → finds fee schedule doc
- `"credit card closure eligibility"` → finds closure requirements doc
- `"give user tool submit referral"` → finds referral user-discoverable tool name
- `"verify customer identity tools"` → finds the verification procedure and logging tool

### 14.5 Redis Connection in RAG Tools

```
[PSEUDOCODE]

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379/0")
_client = redis.Redis.from_url(REDIS_URL, decode_responses=False)

Socket keep-alive is important on corporate NAT. Add socket_keepalive=True
and socket_keepalive_options with TCP_KEEPIDLE=30, TCP_KEEPINTVL=10, TCP_KEEPCNT=3.
This prevents Redis connections from being silently killed by the Google office NAT.
```

---

## 14A. Redis Session Memory — Plane B

### 14A.1 Purpose and Strategic Value

The Redis sponsor's keynote stated explicitly: "The best submissions will show agents that actually learn, remember, and collaborate — not just three bots running in parallel." Adding a lightweight Session Memory Plane to Redis costs approximately 20 lines of code and directly satisfies this criterion.

Plane B stores session-scoped data that both agents can read, creating a shared runtime context. The primary use is verification state: once the Personal Agent collects the user's DOB and email, it writes them to Redis. The CS Agent reads this before asking — making verification near-instantaneous in the best case and demonstrating real cross-agent collaboration to the judges.

### 14A.2 Key Schema

```
Key pattern: session:{contextId}:memory
Type: Redis Hash (HSET / HGETALL)
TTL: 3600 seconds (set on every write with EXPIRE)

Fields:
  verified            "true" | "false"   Whether CS has completed identity verification
  verified_at         Unix timestamp     When verification was logged
  dob                 string             Date of birth collected from user (if known)
  email               string             Email collected from user (if known)
  phone               string             Phone collected from user (if known)
  address             string             Address collected from user (if known)
  user_intent         string             Last classified user intent
  user_id             string             User ID extracted from conversation (if known)
  last_updated        Unix timestamp     Most recent write timestamp
```

### 14A.3 Personal Agent: Write Side

File: `personal_agent/redis_memory.py`

The Personal Agent writes to Plane B in two scenarios:

**After collecting verification data from the user.** When the user provides items like DOB, email, phone, or address in response to a CS verification request, the Personal Agent writes those values before relaying them to CS.

**After receiving context from the user's opening message.** If the user's first message contains their user_id or a clear intent, writing this to memory allows CS to start faster.

```
[PSEUDOCODE — illustration only, not working code]

REDIS_URL = os.environ.get("REDIS_URL")
SESSION_MEMORY_TTL = 3600

def _memory_key(context_id: str) -> str:
    return f"session:{context_id}:memory"

def write_session_memory(context_id: str, fields: dict) -> None:
    """
    Write fields to session memory hash. All values stored as strings.
    Sets a 3600-second TTL on every write (rolling expiry).
    Never raises — memory is best-effort enrichment, not required for correctness.
    """
    if not REDIS_URL:
        return  # Silently skip if Redis not configured (cross-pair mode)
    try:
        import time, redis as r
        client = r.Redis.from_url(REDIS_URL, decode_responses=True,
                                  socket_keepalive=True)
        key = _memory_key(context_id)
        string_fields = {k: str(v) for k, v in fields.items() if v is not None}
        string_fields["last_updated"] = str(int(time.time()))
        client.hset(key, mapping=string_fields)
        client.expire(key, SESSION_MEMORY_TTL)
    except Exception:
        pass  # Memory write failure must never crash the agent
```

**Important: never raise from `write_session_memory`.** Memory is an enhancement. If Redis is down or the write fails, the agent must still function correctly. The except-all is intentional here.

The Personal Agent calls `write_session_memory` from within the `ask_customer_service` tool, just before sending the A2A message to CS, when it knows verification fields are being relayed.

Additionally, the Personal Agent can call it from a lightweight ADK `BeforeAgentCallback` or from within its tool functions as a side effect.

### 14A.4 CS Agent: Read Side

File: `cs_agent/redis_memory.py`

The CS Agent reads from Plane B at the start of each incoming request, before the LLM generates a response.

```
[PSEUDOCODE — illustration only, not working code]

def read_session_memory(context_id: str) -> dict:
    """
    Read all fields from session memory hash.
    Returns empty dict if key missing or Redis unavailable.
    Never raises.
    """
    if not REDIS_URL:
        return {}
    try:
        import redis as r
        client = r.Redis.from_url(REDIS_URL, decode_responses=True,
                                  socket_keepalive=True)
        return client.hgetall(f"session:{context_id}:memory")
    except Exception:
        return {}
```

The result is injected into the CS Agent's conversation context. The cleanest ADK pattern for this is a `BeforeAgentCallback` that appends a structured note to the agent's first message for the session:

```
[PSEUDOCODE — illustration only]

def cs_before_agent_callback(callback_context, llm_request):
    """
    Runs before the LLM generates a response.
    Reads session memory and injects it as a system note if relevant data exists.
    """
    context_id = callback_context.invocation_context.session.id
    memory = read_session_memory(context_id)

    if memory:
        note_parts = []
        if memory.get("verified") == "true":
            note_parts.append("MEMORY: Customer identity was already verified this session.")
        if memory.get("dob"):
            note_parts.append(f"MEMORY: Customer provided DOB: {memory['dob']}")
        if memory.get("email"):
            note_parts.append(f"MEMORY: Customer provided email: {memory['email']}")
        if memory.get("phone"):
            note_parts.append(f"MEMORY: Customer provided phone: {memory['phone']}")
        if memory.get("address"):
            note_parts.append(f"MEMORY: Customer provided address: {memory['address']}")
        if memory.get("user_intent"):
            note_parts.append(f"MEMORY: Detected intent from personal agent: {memory['user_intent']}")

        if note_parts:
            memory_note = "\n".join(note_parts)
            # Prepend to the first user message in the LLM request
            # (exact API depends on ADK version — inject into llm_request.contents)
```

If the callback is incompatible with the ADK version in use, an alternative is to inject memory context as part of the `ask_customer_service` message text itself. The Personal Agent includes a `[CONTEXT: dob=..., email=...]` block before the user's actual request. The CS Agent's prompt tells it to use CONTEXT blocks if present before asking for verification.

### 14A.5 Verification Fast Path

When session memory contains `verified=true` with the required verification fields, the CS Agent skips the verification round-trip:

```
CS Agent receives message:
  MEMORY: Customer identity was already verified this session.
  MEMORY: Customer provided DOB: 08/15/1990
  MEMORY: Customer provided email: taylor.morrison@outlook.com

  → CS Agent does NOT ask for verification again (policy: "No need to verify more than once")
  → CS Agent calls verification logging tool with stored values
  → Proceeds directly to the banking action
```

This removes 2-3 conversation turns from every follow-up request within the same session, reducing turn count and token spend while demonstrating the shared memory feature to judges.

### 14A.6 What to Write, When

```
Personal Agent write triggers:
  1. User provides DOB → write {dob: value}
  2. User provides email → write {email: value}
  3. User provides phone → write {phone: value}
  4. User provides address → write {address: value}
  5. CS confirms verification → write {verified: "true", verified_at: timestamp}
  6. User's opening message intent is clear → write {user_intent: "balance_check"}
  7. User_id is extracted from conversation → write {user_id: value}

CS Agent write trigger:
  After logging verification with the verification logging tool →
    write {verified: "true", verified_at: timestamp}
    (CS agent also has Redis access via its own redis_memory.py)
```

### 14A.7 Plane B and Cross-Pair Scoring

When AXIOM's Personal Agent is paired with the organiser's held-out CS Agent, the held-out CS Agent will not read AXIOM's Redis. That is fine — the memory fast-path is a bonus for the own-pair scenario. The Personal Agent must still relay all verification data via the A2A message as normal text. The Redis write is a supplementary enrichment, not a replacement for the A2A conversation.

When the organiser's held-out Personal Agent is paired with AXIOM's CS Agent, the CS Agent will find an empty Redis key and proceed with the standard verification flow. The `read_session_memory` returns `{}` silently and the agent falls back to asking normally. No errors, no crashes.

---

## 15. Customer Verification Flow

Customer verification is mandatory before accessing or modifying account data. Getting this wrong in the CS agent costs 100% of tasks that involve any account-sensitive information.

### 15.1 The Rule

From `kb/policy.md`:
> "To verify the identity of the user, call the appropriate read tools, and ensure that they are able to give correctly any 2 out of the following values: date of birth, email, phone number, address. Knowing full name or userID is not enough to verify. After verification, you must call the verification logging tool to properly log the information into the verification records."

**Verification requires 2 of 4 items:** DOB, email, phone number, address. Full name alone is not sufficient.

### 15.2 Verification Sequence

There are two paths: the fast path (Redis memory has prior verification data) and the standard path (no prior data). The CS Agent must attempt the fast path first.

**Fast path (session memory present):**
```
1. CS Agent receives request
2. CS Agent reads session:{contextId}:memory
3. If memory.verified == "true":
   → No re-verification needed (policy: "No need to verify more than once")
   → CS Agent logs verification with stored values via verification logging tool
   → Proceeds directly to the banking action
4. If memory contains dob/email/phone/address but verified != "true":
   → CS Agent has the data already — cross-reference against account records
   → If matches: call verification logging tool, write verified=true to memory, proceed
   → Saves 2-3 turns asking the user for information already collected
```

**Standard path (no prior memory or memory empty):**
```
1. CS Agent receives request (e.g., "check my balance")
2. CS Agent: "I need to verify your identity. Can you provide your date of birth and email address?"
   (Ask for 2 of: DOB, email, phone, address — do not ask for full name as verification)
3. Personal Agent relays request to user
4. User provides the 2 items
5. Personal Agent writes the items to session:{contextId}:memory BEFORE sending to CS
6. Personal Agent sends them to CS Agent
7. CS Agent calls read tools to cross-reference the provided values against account records
8. If matches: CS Agent calls verification logging tool, writes verified=true to memory
9. If no match: CS Agent asks for different verification items (max 3 attempts)
10. After successful verification: proceed with the original request
```

### 15.3 When NOT to Verify

Do not require verification for:
- General policy questions ("What are your checking account fees?")
- Product information requests that do not touch customer data
- Questions that can be answered from the KB without accessing personal data

Do require verification for everything in this list from the policy:
- Looking up account balances, transactions, referral history
- Changing account settings (address, phone, email)
- Closing an account
- Adding or removing authorised users
- Filing a dispute
- Any action that modifies customer data

### 15.4 Why the Personal Agent Must Relay Correctly

The user simulator is an LLM playing a character with specific verification information (from `task.user_scenario.instructions`). The simulator's character knows their DOB, email, address, and phone number. The Personal Agent must:
- Ask the user exactly the verification items the CS Agent requested
- Not fill in placeholder values
- Pass the user's response to CS verbatim

The Personal Agent's prompt must explicitly say: "Never fill in placeholders for verification details. If CS needs DOB and you don't have it, ask the user exactly for it before passing it on."

---

## 16. System Prompt Engineering

**This section is the primary score driver.** The baseline score is 25%. Everything above 25% comes from prompt quality. Read this section carefully before writing any prompts.

### 16.1 Personal Agent System Prompt

The Personal Agent prompt must accomplish several things simultaneously. It needs to:

**Core identity:** Be the user's personal banking assistant for Rho-Bank accounts. Act on the user's behalf. Trust the user as the person you are serving.

**Tool usage:** Use `EnvApiToolset` tools for user-side banking actions (submitting referrals, applying for cards, etc.). Use `ask_customer_service` for anything requiring bank-side access or policy knowledge.

**When to call CS:**
- Balance lookups, transaction history
- Account opening/closing
- Card management, disputes
- Policy questions
- Any action requiring bank-side tool access
- Any time you are uncertain about what tool to use

**Relay faithfully:** Pass the user's exact words, account details, and verification information to CS. Do not paraphrase. Do not add interpretation. Do not omit details the user provides.

**Execute instructions from CS:** If CS says "the user should call tool X with these arguments", do exactly that using `call_env_tool` or the discovered tool directly.

**Verification relay:** When CS asks for verification (DOB, email, phone, address), always ask the user for the exact items requested before passing them to CS. Never invent or assume values.

**Conversation end:** Many user simulators end with `###STOP###` or a phrase like "That's all I needed, thank you." When this occurs, give a brief closing confirmation and stop generating.

**Token budget discipline — critical.** The harness runs tasks at `DEFAULT_CONCURRENCY = 2`. With 20 held-out test tasks and potentially multiple LLM calls per task, verbose responses will exhaust the $33/person API budget mid-judging. Both prompts must include explicit conciseness directives:

```
TONE AND LENGTH RULES:
- Never output conversational filler: "Great question!", "I'd be happy to help",
  "Let me look into that for you", "Of course!", etc.
- Do not apologise when a tool fails. State the error in one sentence and move on.
- Do not summarise what you are about to do before doing it.
- Do not confirm each step out loud. Act, then report the result.
- One tool call per response turn unless the task explicitly requires parallel actions.
- Response to the user should be one to three sentences maximum unless providing
  multi-item information (account lists, fee schedules) that require more.
```

This single addition typically reduces per-task token spend by 40-60% with no loss of task completion accuracy.

The prompt structure should follow:
```
[Role and context]
[When to use your own tools vs. when to call CS]
[How to relay information faithfully]
[How to handle verification requests from CS]
[How to execute tools instructed by CS]
[How to end the conversation]
[Token budget / conciseness rules — last section, emphatic]
```

### 16.2 CS Agent System Prompt

The CS Agent prompt is built from `kb/policy.md` (62 lines) plus your additions. Never replace the policy content — extend it. The base policy already covers:
- Not inventing policies or actions
- Using `get_current_time()` for time queries
- Transfer-to-human logic
- Discoverable tools mechanism
- Authentication/verification requirements

**What you must add as extensions:**

**Search before acting.** The LLM will try to answer from training knowledge. The KB must override training knowledge for Rho-Bank-specific policy. Every response involving a specific policy, procedure, fee, threshold, or tool name must be preceded by a KB search. Add explicit guidance:

"Before stating any specific policy, fee, threshold, eligibility rule, or tool name, always search the knowledge base. Your training knowledge about banking does not apply here — only what Rho-Bank's knowledge base says is correct. If you cannot find the information in the KB, say you cannot find it rather than guessing."

**Verification first.** Add explicit ordering: verify identity before accessing account data. Include the exact list of what triggers verification.

**Precise tool argument formatting.** Many golden actions require exact argument values:
- Account class names must use the full official name ending with "Account" (e.g. `"Blue Account"`, `"Green Account (checking)"`) — not abbreviations
- User IDs must be passed exactly as returned from lookup tools — never truncated
- Amounts must be numeric, not string-formatted

**Response style for Personal Agent relay.** The Personal Agent will relay your response to the user. Keep responses:
- Clear and direct
- Actionable (tell the Personal Agent what to do next if needed)
- Explicit about what tool the user should call if applicable (Personal Agent must receive exact tool name and arguments)
- Free of Rho-Bank-internal jargon that would confuse the end user

**Multi-step operations.** For complex procedures (e.g. open account + transfer opening deposit), the CS agent should:
1. Complete the verification step first
2. Confirm eligibility (search KB)
3. Take the primary action (open account)
4. Ask if the user wants to perform the follow-up action (transfer)
5. Either take the follow-up or grant the user the tool to do it themselves

**Prompt structure:**

```
[kb/policy.md content — verbatim, prepended]
[RAG guidance — search before acting]
[Enhanced verification flow with explicit sequencing]
[Session memory context injection guidance — use MEMORY: blocks if present]
[Tool argument precision requirements]
[Response formatting for relay]
[Token budget / conciseness rules — same rules as Personal Agent]
[How to end a session cleanly]
```

The token budget rules for the CS Agent are identical to those for the Personal Agent. Add them verbatim. The CS Agent is more expensive per turn (more tool calls, longer responses) so the budget impact of verbose output is even higher here.

### 16.3 Prompt for Interoperability (Cross-pair scoring)

When your agent is paired with an unknown external agent, the communication pattern may differ from your own agent pair. Your prompts should be robust to:

**For CS Agent (paired with unknown Personal Agent):**
- Incoming messages may not follow your expected format — treat all incoming text as the personal agent relaying a user request
- Verification information may be formatted differently — accept any reasonable format for DOB (MM/DD/YYYY, DD/MM/YYYY, YYYY-MM-DD, "August 15, 1990")
- The Personal Agent may ask multiple questions in one turn — answer each part
- If the message is ambiguous, ask for clarification rather than guessing

**For Personal Agent (paired with unknown CS Agent):**
- CS responses may be more verbose or structured differently
- Extract the key information from CS responses and relay to the user in plain language
- If CS provides a list of actions to take, execute them in order
- If CS response contains `give_discoverable_user_tool` confirmation, discover and call the tool

---

## 17. A2A Protocol Implementation

### 17.1 Using `to_a2a()`

Both agents use `google.adk.a2a.utils.agent_to_a2a.to_a2a()` to expose themselves as A2A endpoints. This function:

- Wraps an ADK `LlmAgent` in a FastAPI ASGI application
- Serves `GET /.well-known/agent.json` with an auto-generated Agent Card
- Handles `POST /message/send` as the primary A2A message endpoint
- Maps `A2A context_id` → `ADK session.id` automatically
- Converts ADK responses to A2A `Task` format
- Handles session lifecycle within ADK's `InMemorySessionService`

### 17.2 Agent Card

`to_a2a()` generates the Agent Card automatically from the agent's name, description, and capabilities. The auto-generated card will:
- Use `name` from `LlmAgent(name=...)`
- Set `capabilities.streaming = False` (unless explicitly configured)
- Set the URL based on the `host` and `port` arguments

You should verify the agent card after startup:

```
curl http://localhost:9001/.well-known/agent.json
curl http://localhost:9002/.well-known/agent.json
```

Both must return valid JSON with at minimum `name`, `url`, and `capabilities`.

### 17.3 A2A Wire Format (v0.3.4)

The harness sends `message/send` over JSON-RPC 2.0. The critical field that `to_a2a()` parses is `params.message.context_id`. Ensure:
- `context_id` is present in all outgoing A2A messages from `ask_customer_service()`
- The A2A client in `cs_client_tool.py` creates `Message(context_id=session_id(tool_context), ...)`

**Tolerant parsing is still needed in `ask_customer_service()`.** When extracting text from CS Agent responses, handle both `Message` and `Task` response types. The CS agent's `to_a2a()` may return either depending on whether the agent completes in one turn or creates a long-running task.

```
[PSEUDOCODE — illustration only]

def _text_of_message(message: Message) -> str:
    texts = []
    for part in message.parts or []:
        root = getattr(part, "root", part)
        if isinstance(root, TextPart) and root.text:
            texts.append(root.text)
    return "\n".join(texts)

def _text_of_task(task: Task) -> str:
    texts = []
    for artifact in task.artifacts or []:
        for part in artifact.parts or []:
            root = getattr(part, "root", part)
            if isinstance(root, TextPart) and root.text:
                texts.append(root.text)
    if task.status and task.status.message:
        text = _text_of_message(task.status.message)
        if text:
            texts.append(text)
    return "\n".join(texts)
```

### 17.4 A2A v0.3 vs v0.4 Discriminator

A2A 0.3.x uses `kind` as the part discriminator. Some older clients send `type`. When parsing responses from external agents:
- Accept both `kind` and `type`
- Infer from content: if `text` present → text part, if `data` present → data part
- Use Pydantic `extra='ignore'` on all models that touch A2A message parts

---

## 18. External Interoperability — Winning the Other 50%

The cross-pair scoring (25% + 25%) depends on your agents working correctly with agents you did not write. Here is a systematic approach to maximising this score.

### 18.1 Your CS Agent with the Organiser's Personal Agent (25%)

The organiser's Personal Agent will send A2A messages to your CS Agent. It may:
- Use slightly different message formatting
- Not provide all context in the first message (ask follow-ups)
- Include the user's verification information in plain English
- Reference tool calls it already made without your CS knowing the history

**What your CS Agent must do:**
1. Accept any A2A-compliant message as a valid request
2. Start from the first message in the session with no assumptions about prior context
3. Always verify before acting — do not skip verification because the external personal agent sounds confident
4. Respond in plain, complete sentences so any personal agent can parse and relay the response
5. Not crash or hang on unexpected message formats — handle `None`, empty strings, and malformed messages gracefully

**Robustness rules:**
- Use `extra='ignore'` on any Pydantic models touching incoming data
- Never raise unhandled exceptions from within the LlmAgent tools
- If a tool call fails with an unexpected error, return `{"error": True, "content": str(e)}` — never re-raise
- If the incoming message cannot be parsed to a banking request, ask for clarification

### 18.2 Your Personal Agent with the Organiser's CS Agent (25%)

The organiser's CS Agent will respond to your Personal Agent's `ask_customer_service()` calls. It may:
- Return more verbose responses
- Not follow the exact verification sequence you designed
- Return text with different structure around tool grants
- Ask for verification information in a different format

**What your Personal Agent must do:**
1. Parse any text response from CS as conversation to relay to the user
2. If CS asks for verification info, relay exactly what it asked for to the user
3. If CS says to call a tool (discoverable tool grant), attempt to discover and call it
4. If CS response is confusing or incomplete, ask a follow-up question rather than guessing
5. Not assume CS will follow your exact protocol — be flexible in how you interpret responses

### 18.3 Agent Card Compliance

Both agent cards must be valid A2A spec. The harness uses the agent card to discover capabilities. Minimally required fields:
- `name`: non-empty string
- `url`: the agent's base URL (for the harness to send messages to)
- `capabilities.streaming`: boolean
- `capabilities.pushNotifications`: boolean

The auto-generated `to_a2a()` card should be compliant. Verify it explicitly before the event.

---

## 19. Docker Compose and Deployment

### 19.1 docker-compose.yml

```
[PSEUDOCODE — illustration of service dependencies and ports]

services:
  redis:
    image: redis:8
    ports:
      - "6379:6379"
    command: redis-server --save "" --appendonly no
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s, timeout: 3s, retries: 5

  personal-agent:
    build: ./personal_agent
    ports:
      - "9001:9001"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - MODEL=${MODEL:-gemini-3.5-flash}
      - ENV_API_URL=${ENV_API_URL}
      - ENV_API_TOKEN=${PERSONAL_ENV_API_TOKEN}
      - CS_AGENT_URL=${CS_AGENT_URL}
      - REDIS_URL=redis://redis:6379/0      # Plane B writes
      - PORT=9001
    depends_on:
      redis:
        condition: service_healthy

  cs-agent:
    build: ./cs_agent
    ports:
      - "9002:9002"
    environment:
      - GOOGLE_API_KEY=${GOOGLE_API_KEY}
      - MODEL=${MODEL:-gemini-3.5-flash}
      - ENV_API_URL=${ENV_API_URL}
      - ENV_API_TOKEN=${CS_ENV_API_TOKEN}
      - REDIS_URL=redis://redis:6379/0      # Plane A (RAG) + Plane B reads/writes
      - KB_DOCUMENTS_PATH=/app/kb/documents
      - KB_POLICY_PATH=/app/kb/policy.md
      - KB_EMBEDDINGS_PATH=/app/kb/embeddings.json
      - PORT=9002
    depends_on:
      redis:
        condition: service_healthy
```

### 19.2 Environment Token Variables

The harness injects `ENV_API_TOKEN` from the environment. However in local development you set two separate tokens:
- `PERSONAL_ENV_API_TOKEN` (default `"dev-user-token"`) → injected as `ENV_API_TOKEN` into the Personal Agent container
- `CS_ENV_API_TOKEN` (default `"dev-agent-token"`) → injected as `ENV_API_TOKEN` into the CS Agent container

In the harness submission environment, the harness provides these tokens. Do not hardcode them.

### 19.3 External Accessibility

The Personal Agent (port 9001) must be publicly accessible for the harness's User Simulator to send messages to it. Use ngrok or Cloudflare Tunnel:

```
ngrok http 9001
```

The harness is told your Personal Agent URL at submission time. It connects directly to port 9001's A2A endpoint.

The CS Agent (port 9002) does NOT need to be publicly accessible. The harness connects to it through your local network because in the harness's deployment model the gateway proxy (`/cs-agent`) is on the same internal network as your CS Agent. If deploying remotely, expose 9002 on a private network only.

---

## 20. Environment Variables

### 20.1 Complete Variable Reference

```bash
# Required for both agents
GOOGLE_API_KEY=                    # Gemini API key
MODEL=gemini-3.5-flash             # LLM model identifier
REDIS_URL=redis://redis:6379/0     # Both agents — Personal Agent writes, CS Agent reads+writes
                                   # Set to empty string to disable Plane B (cross-pair safety net)

# Injected by harness (or configured for local dev)
ENV_API_URL=http://host.docker.internal:8090  # Harness Environment API
PERSONAL_ENV_API_TOKEN=dev-user-token          # User-scope bearer token
CS_ENV_API_TOKEN=dev-agent-token               # Agent-scope bearer token

# Personal Agent only
CS_AGENT_URL=http://host.docker.internal:8090/cs-agent  # Harness CS gateway proxy

# CS Agent only
KB_DOCUMENTS_PATH=/app/kb/documents
KB_POLICY_PATH=/app/kb/policy.md
KB_EMBEDDINGS_PATH=/app/kb/embeddings.json

# Optional: override ports
PORT=9001  # Personal Agent
PORT=9002  # CS Agent
```

### 20.2 Local Dev vs Harness Submission

In local dev (`docker-compose up`):
- `ENV_API_URL` points to wherever you run a mock environment API, or leave blank to skip tool calls
- `CS_AGENT_URL` can be set to `http://cs-agent:9002` for direct local connection without the harness proxy
- Tokens can be arbitrary strings as long as your mock server accepts them

In harness submission (the scoring site):
- The harness launches your containers and injects all required env vars
- `ENV_API_URL` will point to the harness's live Environment API
- `CS_AGENT_URL` will point to the harness's `/cs-agent` proxy
- Tokens are harness-issued bearer tokens with real scope enforcement

---

## 21. Testing, Validation, and Scoring Loop

### 21.1 Feedback Tasks for Smoke Testing

Three tasks are available for smoke testing during the event: `task_006`, `task_009`, `task_053`. These are in the train split so you can inspect their contents in `src/a2a_hack/data/tasks/`.

**Before testing:** Read each task's `description.notes`, `user_scenario.instructions`, `evaluation_criteria.actions`, and `initial_state.initialization_data`. This tells you exactly what the test expects.

**Running smoke tests:**

The harness provides a CLI command:
```
python -m a2a_hack smoke --task-id task_006 \
    --personal-url http://localhost:9001 \
    --cs-url http://localhost:9002
```

This runs a single task with full output, showing each conversation turn and whether golden actions were matched.

### 21.2 What to Check in Smoke Test Output

For each smoke test run, verify:
1. **contextId propagation**: Both agents used the same session ID for their tool calls
2. **Verification**: CS Agent asked for and received verification information correctly; on second request within session, verify the fast path was used (no re-asking)
3. **Redis Plane B**: `redis-cli HGETALL session:{contextId}:memory` shows populated fields after verification data was collected
4. **Tool calls**: The expected golden actions were called with the expected arguments
5. **Conversation flow**: The user simulator reached the `###STOP###` state or gave a closing message
6. **Turn count**: The conversation completed well within the 60-turn limit
7. **Token count**: Check Gemini API usage logs; verbose responses should not be appearing

### 21.3 Scoring Loop During the Event

The harness scoring site (available ~14:30) runs your submitted GitHub repo against all test tasks and shows results live. The scoring loop is:

```
1. Improve prompts based on smoke test feedback
2. Git commit and push
3. Submit GitHub repo URL to scoring site
4. Wait ~10 minutes for results
5. Note which task types are failing (from the per-task breakdown)
6. Search the KB for relevant documents for those task types
7. Add/modify prompt guidance for those scenarios
8. Repeat
```

### 21.4 Unit Tests

`tests/test_smoke.py`: Runs feedback tasks against live agent services. Requires running Docker services and a valid `GOOGLE_API_KEY`.

`tests/test_contextid.py`: Verifies contextId propagation end-to-end without a real LLM by using echo agents. Should pass in CI without API keys.

`tests/test_agent_cards.py`: Verifies both agent cards are valid A2A spec. Does not require API keys.

### 21.5 Data Available for Testing

**Train tasks (63 tasks):** Full access to task definitions including notes, golden actions, initial state, user scenarios. Use these to understand task patterns and tune prompts.

**Feedback tasks (task_006, task_009, task_053):** Subset of train tasks. Run these repeatedly during the event for fast feedback.

**Test tasks (20 tasks):** Not available. These are the tasks used for final scoring. You should infer their character from the train distribution.

**Knowledge base (698 docs):** Full access to all banking documents. Read them to understand what policies and procedures exist, and tune your prompts to search for the right document categories.

**Harness source code:** Available at `a2anet/a2a-hackathon`. Read `src/a2a_hack/scoring.py` to understand the scoring formula and `src/a2a_hack/env_api/sessions.py` to understand tool scope enforcement.

---

## 22. Traps and Validated Bugs

Validated failure modes specific to this architecture. Read all of these before coding.

### TRAP 1 — output_schema + tools on the Same LlmAgent

If you use `output_schema` on your CS Agent while it also has `tools`, some Gemini model versions return free text instead of structured output, causing the pipeline to silently fail. The template does not use `output_schema` for either agent for this reason. If you add structured output for any reason, use the two-stage pattern: one agent for tool calls (no schema), one for formatting (schema, no tools).

### TRAP 2 — contextId Not Propagated to CS

If `ask_customer_service()` sends a message to the CS Agent without `context_id=session_id(tool_context)`, the CS Agent gets a fresh session and no tool calls are credited to the simulation. The reward is 0 for all bank-side golden actions. Always set `context_id=session_id(tool_context)` in the outgoing A2A Message from `cs_client_tool.py`.

### TRAP 3 — CS_AGENT_URL Pointing to Port 9002 Directly

In the harness environment, `CS_AGENT_URL` must point to the harness gateway proxy (`http://host.docker.internal:8090/cs-agent`), not directly to your CS Agent port 9002. The harness records Leg 2 communication through this proxy. If you bypass it, Leg 2 tool calls are not recorded and score 0. Use the `CS_AGENT_URL` environment variable as given.

### TRAP 4 — Redis `decode_responses=True` Breaks Vector Search

When using `redis.Redis.from_url(REDIS_URL, decode_responses=True)`, binary embedding vectors are decoded as strings and the HNSW search fails with a type error. Always use `decode_responses=False` in the RAG tools Redis client.

### TRAP 5 — Tool Argument Mismatch

Golden actions require exact argument values. Common failure modes:
- Account class names abbreviated: `"Blue"` instead of `"Blue Account"` → no credit
- User ID truncated or modified: `"tm92"` instead of `"tm92c4d7e8"` → no credit
- Arguments as wrong type: `amount=500` (int) when `amount="500.00"` (string) expected
- Extra spaces in string arguments: `"Blue Account "` vs `"Blue Account"`

The CS Agent's prompt must instruct it to use exact values from tool discovery results, never paraphrase or abbreviate.

### TRAP 6 — Unlocking Tools Without Using Them

Policy: "Do not unlock tools that you do not plan on actually using: this causes issues in database logging." If the CS Agent calls `unlock_discoverable_agent_tool()` for a tool it ends up not calling, the harness logs a spurious unlock and this may affect the evaluation. Only unlock tools you are about to call.

**Programmatic safeguard in `rag_tools.py` or a dedicated `discoverable_tools.py`:**

Wrap unlock and execution as a single atomic operation that the LLM cannot split across turns. Create one helper function `unlock_and_call_agent_tool(tool_name, arguments, tool_context)` that:
1. Calls `unlock_discoverable_agent_tool(tool_name)` via the Environment API
2. Immediately — in the same Python function — calls `call_discoverable_agent_tool(tool_name, arguments)` via the Environment API
3. Returns the result of the call

Register this combined function as a single ADK tool instead of exposing `unlock` and `call` separately. The LLM calls it once with the tool name and arguments; the Python implementation handles the two-step protocol internally. This makes it architecturally impossible for the LLM to unlock without using.

```
[PSEUDOCODE — illustration only]

async def unlock_and_call_agent_tool(
    agent_tool_name: str,
    arguments_json: str,
    tool_context: ToolContext
) -> dict:
    """
    Unlock and immediately call a discoverable agent tool in one atomic operation.
    IMPORTANT: Only call this when you are certain you want to execute the tool.
    The knowledge base must have specified this tool name — do not guess.

    agent_tool_name: exact tool name from knowledge base
    arguments_json: JSON string of arguments, e.g. '{"account_class": "Blue Account"}'
    """
    import json
    sid = session_id(tool_context)
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError as e:
        return {"error": True, "content": f"Invalid arguments JSON: {e}"}

    # Step 1: unlock
    unlock_result = await _post_tool_call(sid, "unlock_discoverable_agent_tool",
                                          {"agent_tool_name": agent_tool_name})
    if unlock_result.get("error"):
        return {"error": True, "content": f"Unlock failed: {unlock_result.get('content')}"}

    # Step 2: call — immediately, in the same function
    return await _post_tool_call(sid, "call_discoverable_agent_tool",
                                 {"agent_tool_name": agent_tool_name, "arguments": arguments})
```

Register `unlock_and_call_agent_tool` instead of separate unlock/call functions. The CS Agent's tools list becomes `[EnvApiToolset(), kb_search_bm25, kb_search_vector, unlock_and_call_agent_tool]`.

### TRAP 7 — Verification Without Logging

The policy says: "After verification, you must call the verification logging tool to properly log the information into the verification records." If the CS Agent verifies the user by checking values but does not call the verification logging tool, the harness treats the session as unverified and many subsequent golden actions may fail or be scored as incorrect.

### TRAP 8 — personal_agent env_toolset.py Using Wrong Token

The Personal Agent must use the user-scope token (`PERSONAL_ENV_API_TOKEN`) and the CS Agent must use the agent-scope token (`CS_ENV_API_TOKEN`). If both use the same token, one of them will see the wrong set of tools. In Docker, inject `ENV_API_TOKEN` separately per service using the correct token variable.

### TRAP 9 — KB Not Indexed Before Accepting Requests

`build_index()` must complete before `to_a2a(root_agent)` serves requests. The `main.py` pattern in the CS Agent is:
1. Call `build_index()` — this blocks
2. Import `from agent import root_agent` — this reads policy.md and initialises tools
3. Call `to_a2a(root_agent)` — this starts serving

Reversing these steps causes the CS Agent to serve requests before its KB is indexed, resulting in failed KB searches and an incorrect tool list.

### TRAP 10 — BM25 Query Stopwords Breaking Search

Redis FT.SEARCH uses a default English stopword list. Queries composed entirely of stopwords (e.g. "how to do it") return zero results. Do not rely solely on the LLM prompt to avoid stopwords — add a programmatic safeguard directly in `kb_search_bm25`.

**Programmatic fix in `cs_agent/rag_tools.py`:**

```
[PSEUDOCODE — illustration only]

# Redis default stopwords that will be stripped by FT.SEARCH anyway.
# Strip them before joining to avoid empty queries.
_REDIS_STOPWORDS = frozenset({
    "a", "an", "the", "is", "it", "its", "in", "on", "at", "to",
    "of", "for", "and", "or", "but", "not", "with", "from", "by",
    "be", "been", "are", "was", "were", "have", "has", "had",
    "do", "does", "did", "how", "what", "when", "where", "which",
    "who", "will", "would", "could", "should", "may", "can", "i",
    "my", "me", "we", "our", "you", "your"
})

def kb_search_bm25(query: str, top_k: int = 5) -> list[dict]:
    # Tokenise and lowercase
    raw_terms = re.findall(r"\w+", query.lower())

    # Strip stopwords programmatically — never rely on the LLM to avoid them
    terms = [t for t in raw_terms if t not in _REDIS_STOPWORDS and len(t) > 1]

    if not terms:
        # Query was all stopwords — fall back to the full raw query as a phrase search
        # rather than returning empty. This handles edge cases gracefully.
        terms = raw_terms[:5]  # Take first 5 raw terms as last resort

    if not terms:
        return []  # Truly empty query

    or_query = "|".join(dict.fromkeys(terms))  # Unique terms, OR join

    reply = _client.execute_command(
        "FT.SEARCH", KB_INDEX, or_query,
        "LIMIT", "0", str(top_k),
        "RETURN", "2", "title", "content",
    )
    return _parse_search_reply(reply)
```

The stopword list above covers the most common English stopwords. Extend it if you find specific queries failing. The fallback to raw terms for all-stopword queries ensures `kb_search_bm25("how to do it")` still returns results rather than silently returning `[]`.

### TRAP 11 — Embeddings Not Precomputed

Without `kb/embeddings.json`, `build_index()` calls `_embed()` 698 times in batches of 25. At ~2 seconds per batch call, this takes approximately 56 batches × 2s = ~2 minutes minimum. In practice, due to rate limiting and cold start latency, this can take 10+ minutes. If the CS Agent has not finished indexing when the harness sends the first request, it fails all tasks in the batch. Precompute embeddings before the event.

### BUG 1 — httpx Client Per Call in cs_client_tool.py

The template creates `async with httpx.AsyncClient(timeout=_TIMEOUT_S) as http_client` inside `ask_customer_service()`. This is acceptable because the timeout is set for the entire request-response cycle and the client is closed only after the response is fully received. Do not refactor this to a module-level global without careful lifecycle management — the ADK event loop and httpx lifecycle must be compatible.

### BUG 2 — SHA256 Cache Keys in RAG

Cache keys for the BM25 query cache (if implemented) must use `hashlib.sha256(query.encode()).hexdigest()[:16]` instead of `hash(query)`. Python's built-in `hash()` is seeded by `PYTHONHASHSEED` which changes on every process restart, making cache keys non-deterministic across restarts.

### BUG 3 — Redis Stream Maxlen (if implemented)

If you add a Redis event stream beyond the RAG index, every `XADD` must include `MAXLEN ~ 10000` to prevent unbounded memory growth under load. Without this, the Redis container will OOM during judging.

---

## 23. Pre-Event Checklist

Execute ALL of these BEFORE arriving at the venue. Not during.

### Day Before

```
□ kb/embeddings.json generated and committed (or baked into Docker image)
  → python cs_agent/precompute_embeddings.py
  → verify file size ~2.7MB

□ docker-compose up — all three services start cleanly
  → redis healthy: redis-cli ping → PONG
  → personal-agent up: curl http://localhost:9001/.well-known/agent.json → 200
  → cs-agent up: curl http://localhost:9002/.well-known/agent.json → 200

□ KB indexed correctly
  → redis-cli FT.INFO kb_idx → shows 698 documents indexed

□ Redis Plane B working: write then read round-trip
  → redis-cli HSET session:test-ctx:memory dob "01/01/1990"
  → redis-cli HGETALL session:test-ctx:memory → {dob: "01/01/1990"}
  → redis-cli DEL session:test-ctx:memory

□ Smoke test task_006 runs to completion
  → At least one golden action executed correctly
  → redis-cli KEYS "session:*:memory" → shows session key created during test

□ GOOGLE_API_KEY valid and has sufficient quota
  → test with direct Gemini API call: model=gemini-3.5-flash, simple prompt
  → Note: harness provides $100/person budget; ~$33 per team member; be conservative
  → Enable verbose token logging during smoke tests to calibrate per-task spend

□ ngrok tunnel configured and tested from phone hotspot
  → ngrok http 9001
  → curl https://YOUR_TUNNEL.ngrok.io/.well-known/agent.json → 200

□ .env.example is complete and accurate
```

□ GOOGLE_API_KEY valid and has sufficient quota
  → test with direct Gemini API call: model=gemini-3.5-flash, simple prompt
  → Note: harness provides $100/person budget; ~$33 per team member; be conservative

□ ngrok tunnel configured and tested from phone hotspot
  → ngrok http 9001
  → curl https://YOUR_TUNNEL.ngrok.io/.well-known/agent.json → 200

□ .env.example is complete and accurate
```

### Event Day (Before Judging Starts)

```
□ Update PERSONAL_AGENT_URL in submission with active tunnel URL
□ Run smoke tests again after any last-minute prompt changes
□ Set MODEL env var to best available model (check harness constraints)
□ Verify Redis is running and KB indexed (check docker-compose logs cs-agent | grep "Index ready")
□ Check API quota remaining: enough for 20 test tasks × ~5 LLM calls each = ~100 calls minimum
```

---

## 24. Cut Order if Time-Constrained

If time runs short during the event, cut features in this order. Items closer to the top have less scoring impact.

```
1. Redis Plane B token budget fast-path optimisation (skip the BeforeAgentCallback injection;
   keep the write but let CS still ask for verification normally)
   Impact: Loses 2-3 turns per follow-up request. Score impact: small.
   Keep: The writes themselves — judges may check for Redis memory keys.

2. Embedding precompute cache — replace with sync embed on first request
   Impact: CS agent slow to start (10+ min). Run precompute before cutting this.

3. BM25 search in addition to vector search
   Impact: Some keyword-exact tool name queries may miss. Vector search alone still works.

4. Redis socket keep-alive options
   Impact: Redis connections may drop on corporate NAT. Affects long sessions.

5. call_env_tool fallback in EnvApiToolset
   Impact: Tools granted mid-conversation (discoverable tools) may not appear.
   This is significant for tasks with user-discoverable tools.

6. Two-stage LLM pattern for CS agent (if you added it)
   Impact: CS agent may produce inconsistent structured output. Acceptable if
   you are not using output_schema.
```

### NEVER Cut

```
- contextId propagation in ask_customer_service() — 0 reward without it
- KB RAG (build_index + rag_tools) — CS agent cannot answer policy questions
- Verification sequence in CS prompt — all account-sensitive tasks fail
- Discoverable tools handling in CS prompt — user-side golden actions fail
- cs_client_tool.py pointing to CS_AGENT_URL (harness proxy) — Leg 2 not recorded
- pre-computed embeddings (run before event) — startup too slow for judging window
- Redis Plane B writes from Personal Agent — judges look for this as sponsor criterion
- Token budget / conciseness rules in both prompts — budget exhaustion kills late tasks
- unlock_and_call_agent_tool combined function — split unlock/call causes spurious logging
```

---

## Appendix A: A2A v0.3 Wire Format Reference

### message/send Request

```json
{
  "jsonrpc": "2.0",
  "method": "message/send",
  "id": "req-001",
  "params": {
    "message": {
      "message_id": "msg-001",
      "role": "user",
      "parts": [
        {"kind": "text", "text": "I want to check my account balance"}
      ],
      "context_id": "ctx-abc-123"
    }
  }
}
```

**Tolerant parsing notes:**
- Accept both `kind` and `type` as part discriminator
- Accept `message_id` and `messageId` (camelCase/snake_case variants)
- Accept extra fields with `extra='ignore'` (Pydantic)

### Task Response (completed)

```json
{
  "jsonrpc": "2.0",
  "id": "req-001",
  "result": {
    "id": "task-xyz",
    "context_id": "ctx-abc-123",
    "status": {
      "state": "completed",
      "message": {
        "role": "agent",
        "parts": [{"kind": "text", "text": "Your account balance is..."}]
      }
    }
  }
}
```

### A2A v0.3 State Names

All lowercase:
```
submitted | working | input-required | auth-required | completed | failed | cancelled | rejected
```

Note: American spelling `cancelled` (not `cancelled` as in British English). This matches the A2A spec exactly.

---

## Appendix B: Task JSON Schema

The 79 task files in `src/a2a_hack/data/tasks/` follow this schema. Understanding it is essential for writing effective prompts.

### Root Object

```
id                 string    "task_001"
description        object    purpose, relevant_policies, notes
user_scenario      object    persona (nullable), instructions (full LLM prompt for user sim)
initial_state      object    initialization_data (banking DB state), initialization_actions
evaluation_criteria object    actions (golden actions list), reward_basis
user_tools         string[]  tools available to user scope for this task
required_documents string[]  KB document IDs relevant to this task
```

### evaluation_criteria.actions (Golden Actions)

```json
{
  "name": "open_bank_account_4821",
  "arguments": {
    "account_class": "Blue Account",
    "user_id": "tm92c4d7e8"
  },
  "requestor": "assistant",
  "action_id": "020_0"
}
```

- `name`: exact tool name — must match exactly
- `arguments`: exact required arguments — must match exactly (or keys in `compare_args` if present)
- `requestor`: `"user"` (Personal Agent must call) or `"assistant"` (CS Agent must call)
- `action_id`: task_id + sequence number

### reward_basis

- `"DB"`: reward based on final database state matching expected state
- `"ACTION"`: reward based on whether specific actions were called with correct arguments
- `["DB", "ACTION"]`: both criteria must be met

### user_tools

Lists specific tool names available in user scope for this task. The `give_discoverable_user_tool()` mechanism adds tools to this list dynamically during the session.

### initial_state.initialization_data.agent_data

Contains the initial Rho-Bank database state for this simulation:
- `users`: customer profiles (name, user_id, address, email, phone, DOB)
- `accounts`: checking, savings, credit accounts
- `debit_cards`: card details
- `credit_cards`: credit card details
- `payments`: payment history
- `referrals`: referral records
- `applications`: account/card applications
- `fraud_disputes`: dispute records

This is the database the CS agent's tools operate on. Tool calls modify this state and the evaluation checks the final state.

---

## Appendix C: Banking Domain Data Model

### Key User Data Fields (for Verification)

| Field | Example | Notes |
|---|---|---|
| `name` | `"Taylor Morrison"` | Not sufficient for verification alone |
| `user_id` | `"tm92c4d7e8"` | Required argument in most tools |
| `address` | `"7845 Maple Street, Denver, CO 80202"` | One of 4 verification items |
| `email` | `"taylor.morrison@outlook.com"` | One of 4 verification items |
| `phone_number` | `"720-555-0348"` | One of 4 verification items |
| `date_of_birth` | `"08/15/1990"` | One of 4 verification items |

The CS Agent must verify with any 2 of: address, email, phone, DOB. Not name. Not user_id.

### Account Data

| Field | Values | Notes |
|---|---|---|
| `account_id` | `"chk_tm92c4d7e8_blue"` | Structured: class_userid_level |
| `class` | `"checking" \| "savings" \| "credit"` | Type of account |
| `level` | `"Blue Account"` | Full official name, used as tool argument |
| `status` | `"OPEN" \| "CLOSED" \| "FROZEN"` | UPPERCASE |
| `current_holdings` | `"8500.00"` | Decimal string |

### Card Data

| Field | Values |
|---|---|
| `status` | `"ACTIVE" \| "INACTIVE" \| "BLOCKED" \| "EXPIRED"` |
| `cardholder_name` | UPPERCASE full name |
| `last_4_digits` | 4-digit string |
| `issue_reason` | `"new_account" \| "replacement" \| "theft" \| "fraud"` |

---

## Appendix D: Validated ADK Import Paths

```python
# Personal and CS agent — these imports are valid with google-adk[a2a]>=1.10
from google.adk.agents import LlmAgent
from google.adk.tools import BaseTool, FunctionTool, ToolContext, BaseToolset
from google.adk.tools.base_toolset import BaseToolset
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.genai import types  # For FunctionDeclaration

# RAG tools — Gemini embedding (google-genai>=1.0)
import google.genai as genai
client = genai.Client()
response = client.models.embed_content(
    model="gemini-embedding-001",
    contents=["text to embed"]
)
vectors = [e.values for e in response.embeddings]  # List[List[float]]

# Redis with RediSearch (redis>=5.0)
import redis
from redis.commands.search.field import TextField, VectorField
from redis.commands.search.indexDefinition import IndexDefinition, IndexType
```

**Deprecated / Do Not Use:**
```python
# These are ADK 1.x patterns — do not use with google-adk>=1.10
from google.adk import Agent              # Use LlmAgent instead
agent._run_async_impl()                   # Not the correct pattern
agent.generate_content()                  # Not the correct pattern
```

**What does NOT exist:**
- `AegisNode` — referenced in older research; does not exist as a deployable component
- `google.adk.workflow.BaseNode` — ADK 2.0 pattern; not applicable for this harness
- `google.adk.workflow.Context` — ADK 2.0; use ADK 1.x session patterns with `to_a2a()`

---

*Document complete. Validated against harness source code (a2anet/a2a-hackathon), template (a2anet/a2a-hackathon-template), Google ADK 1.10+ docs, A2A SDK 0.3.4, and Redis 8 RediSearch docs.*

*Build order: Redis → CS Agent (precompute embeddings first) → Personal Agent → Smoke test task_006, task_009, task_053 → Iterate prompts → Submit.*

*The system prompt is the primary score driver. The contextId propagation is the primary reliability driver. Get both right first.*
