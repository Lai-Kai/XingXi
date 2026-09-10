# API Reference

This document provides a complete reference for the DeerFlow backend APIs.

## Overview

DeerFlow backend exposes two sets of APIs:

1. **LangGraph-compatible API** - Agent interactions, threads, and streaming (`/api/langgraph/*`)
2. **Gateway API** - Models, MCP, skills, uploads, and artifacts (`/api/*`)

All APIs are accessed through the Nginx reverse proxy at port 2026.

For agent conversations, clients can either pre-create a thread
(`POST /api/langgraph/threads`) or start immediately with the stateless stream
endpoint (`POST /api/langgraph/runs/stream`). The latter auto-creates a thread
and returns `thread_id` and `run_id` in the response `Content-Location` header.

## LangGraph-compatible API

Base URL: `/api/langgraph`

The public LangGraph-compatible API follows LangGraph SDK conventions. In the unified nginx deployment, Gateway owns `/api/langgraph/*` and translates those paths to its native `/api/*` run, thread, and streaming routers.

### Threads

#### Create Thread

```http
POST /api/langgraph/threads
Content-Type: application/json
```

**Request Body:**
```json
{
  "metadata": {}
}
```

**Response:**
```json
{
  "thread_id": "abc123",
  "created_at": "2024-01-15T10:30:00Z",
  "metadata": {}
}
```

#### Get Thread State

```http
GET /api/langgraph/threads/{thread_id}/state
```

**Response:**
```json
{
  "values": {
    "messages": [...],
    "sandbox": {...},
    "artifacts": [...],
    "thread_data": {...},
    "title": "Conversation Title"
  },
  "next": [],
  "config": {...}
}
```

### Runs

#### Create Run

Execute the agent with input.

```http
POST /api/langgraph/threads/{thread_id}/runs
Content-Type: application/json
```

**Request Body:**
```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "recursion_limit": 100,
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**Stream Mode Compatibility:**
- Use: `values`, `messages-tuple`, `custom`, `updates`, `events`, `debug`, `tasks`, `checkpoints`
- Do not use: `tools` (deprecated/invalid in current `langgraph-api` and will trigger schema validation errors)

**Recursion Limit:**

`config.recursion_limit` caps the number of graph steps LangGraph will execute
in a single run. The unified Gateway path defaults to `100` in
`build_run_config` (see `backend/app/gateway/services.py`), which is a safer
starting point for plan-mode or subagent-heavy runs. Clients can still set
`recursion_limit` explicitly in the request body; increase it if you run deeply
nested subagent graphs. For safety, the Gateway clamps any client-supplied value
to a configurable server ceiling (`max_recursion_limit` in `config.yaml`,
default `1000`) so a single run cannot execute unbounded graph steps (runaway
LLM cost / DoS); invalid or non-positive values fall back to the `100` default.

**Configurable Options:**
- `model_name` (string): Override the default model
- `thinking_enabled` (boolean): Enable extended thinking for supported models
- `is_plan_mode` (boolean): Enable TodoList middleware for task tracking

**Response:** Server-Sent Events (SSE) stream

```
event: values
data: {"messages": [...], "title": "..."}

event: messages
data: {"content": "Hello! I'd be happy to help.", "role": "assistant"}

event: end
data: {}
```

#### Get Run History

```http
GET /api/langgraph/threads/{thread_id}/runs
```

**Response:**
```json
{
  "runs": [
    {
      "run_id": "run123",
      "status": "success",
      "created_at": "2024-01-15T10:30:00Z"
    }
  ]
}
```

#### Stream Run

Stream responses in real-time.

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Content-Type: application/json
```

Same request body as Create Run. Returns SSE stream.

#### Stateless Stream Run

Start a conversation without creating a thread first. Gateway auto-creates a
thread when `config.configurable.thread_id` is omitted, and returns both
identifiers in the response `Content-Location` header.

```http
POST /api/langgraph/runs/stream
Content-Type: application/json
Accept: text/event-stream
```

Through Nginx, `/api/langgraph/runs/stream` is rewritten to the native Gateway
path `POST /api/runs/stream`.

**Request Body:** Same as [Create Run](#create-run). Omit `thread_id` to start a
new conversation; include it to continue an existing one:

```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "Hello, can you help me?"
      }
    ]
  },
  "config": {
    "recursion_limit": 100,
    "configurable": {
      "model_name": "gpt-4",
      "thinking_enabled": false,
      "is_plan_mode": false
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

**Response:** Server-Sent Events (SSE) stream with a `Content-Location` header:

```http
Content-Location: /api/threads/{thread_id}/runs/{run_id}
```

Clients should parse `thread_id` and `run_id` from this header (the path ends
with `/runs/{run_id}`). Persist `thread_id` and send it back on the next turn
via `config.configurable.thread_id` to keep conversation history.

**Continuing a conversation:**

```json
{
  "input": {
    "messages": [
      {
        "role": "user",
        "content": "What did I just ask?"
      }
    ]
  },
  "config": {
    "configurable": {
      "thread_id": "abc123",
      "model_name": "gpt-4"
    }
  },
  "stream_mode": ["values", "messages-tuple", "custom"]
}
```

---

## Gateway API

Base URL: `/api`

### Knowledge graph neighborhoods

`GET /api/knowledge-graph/query?entity=<name-or-id>&max_depth=2&max_nodes=200`
returns a bounded graph around a resolved entity. Authentication is required.
`entity` accepts a stable ID, canonical name, or reviewed alias. `max_depth`
accepts 1–3 (default 2); `max_nodes` accepts 1–200 (default 120). Optional repeated
`relation_types` parameters filter relation types. Optional `release_id` pins
the query to a knowledge Release; otherwise the Gateway resolves the active
Release before traversal.

The response contains `query`, `status`, `message`, `candidates`, `nodes`,
`edges`, `evidence`, and `truncated`, plus the resolved `release_id` and requested
`max_depth`/`max_nodes`. Clients should reuse the returned Release when changing
depth or exploring another node. Peripheral edges use the same directed relation
and Evidence locator contracts as direct edges. `truncated` means traversal hit
a bound; it is independent of any client display pagination. Empty or ambiguous
results retain scope metadata and must not be interpreted as proof that a
historical relationship does not exist.

### Models

#### List Models

Get all available LLM models from configuration.

```http
GET /api/models
```

**Response:**
```json
{
  "models": [
    {
      "name": "gpt-4",
      "display_name": "GPT-4",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "claude-3-opus",
      "display_name": "Claude 3 Opus",
      "supports_thinking": false,
      "supports_vision": true
    },
    {
      "name": "deepseek-v3",
      "display_name": "DeepSeek V3",
      "supports_thinking": true,
      "supports_vision": false
    }
  ]
}
```

#### Get Model Details

```http
GET /api/models/{model_name}
```

**Response:**
```json
{
  "name": "gpt-4",
  "display_name": "GPT-4",
  "model": "gpt-4",
  "max_tokens": 4096,
  "supports_thinking": false,
  "supports_vision": true
}
```

### MCP Configuration

#### Get MCP Config

Get current MCP server configurations.

```http
GET /api/mcp/config
```

Requires an authenticated admin session. Sensitive env/header/OAuth secret
values are masked in the response.

**Response:**
```json
{
  "mcp_servers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    }
  }
}
```

#### Update MCP Config

Update MCP server configurations.

```http
PUT /api/mcp/config
Content-Type: application/json
```

Requires an authenticated admin session. API-managed `stdio` MCP servers may
only use allowed executable names for `command` (default: `npx`, `uvx`). Set
`DEER_FLOW_MCP_STDIO_COMMAND_ALLOWLIST` to a comma-separated list when a
deployment needs additional trusted launchers.

**Request Body:**
```json
{
  "mcp_servers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN"
      },
      "description": "GitHub operations"
    }
  }
}
```

**Response:**
```json
{
  "mcp_servers": {
    "github": {
      "enabled": true,
      "type": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_TOKEN": "***"
      },
      "description": "GitHub operations"
    }
  }
}
```

#### Reset MCP Tools Cache

Clear cached MCP tools and persistent MCP sessions process-wide. This affects
all threads and users in the current Gateway process. Tools are loaded again
from configured MCP servers on the next agent run or tool lookup.

```http
POST /api/mcp/cache/reset
```

Requires an authenticated admin session.

**Response:**
```json
{
  "success": true,
  "message": "MCP tools cache reset. Tools will reload on next use."
}
```

### Skills

#### List Skills

Get all available skills.

```http
GET /api/skills
```

**Response:**
```json
{
  "skills": [
    {
      "name": "pdf-processing",
      "display_name": "PDF Processing",
      "description": "Handle PDF documents efficiently",
      "enabled": true,
      "license": "MIT",
      "path": "public/pdf-processing"
    },
    {
      "name": "frontend-design",
      "display_name": "Frontend Design",
      "description": "Design and build frontend interfaces",
      "enabled": false,
      "license": "MIT",
      "path": "public/frontend-design"
    }
  ]
}
```

#### Get Skill Details

```http
GET /api/skills/{skill_name}
```

**Response:**
```json
{
  "name": "pdf-processing",
  "display_name": "PDF Processing",
  "description": "Handle PDF documents efficiently",
  "enabled": true,
  "license": "MIT",
  "path": "public/pdf-processing",
  "allowed_tools": ["read_file", "write_file", "bash"],
  "content": "# PDF Processing\n\nInstructions for the agent..."
}
```

#### Enable Skill

```http
POST /api/skills/{skill_name}/enable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' enabled"
}
```

#### Disable Skill

```http
POST /api/skills/{skill_name}/disable
```

**Response:**
```json
{
  "success": true,
  "message": "Skill 'pdf-processing' disabled"
}
```

#### Install Skill

Install a skill from a `.skill` file.

```http
POST /api/skills/install
Content-Type: multipart/form-data
```

**Request Body:**
- `file`: The `.skill` file to install

**Response:**
```json
{
  "success": true,
  "message": "Skill 'my-skill' installed successfully",
  "skill": {
    "name": "my-skill",
    "display_name": "My Skill",
    "path": "custom/my-skill"
  }
}
```

#### Reload Skills

Invalidate the skill prompt caches for every user in the current Gateway
process. Subsequent runs rescan the configured public, custom, and legacy skill
directories; runs that have already started keep their existing skill snapshot.

```http
POST /api/skills/reload
```

The request has no body and requires an authenticated administrator. For a
cookie-authenticated request, send the CSRF cookie value in the matching header:

```bash
curl -X POST http://localhost:2026/api/skills/reload \
  -b cookies.txt \
  -H "X-CSRF-Token: <csrf_token-cookie-value>"
```

**Response:**

```json
{
  "success": true,
  "scope": "process",
  "message": "Skill caches invalidated; subsequent runs in this Gateway process will rescan the latest skills."
}
```

`success` confirms cache invalidation, not that every file on disk was valid:
malformed skills retain the existing parser behavior of being skipped and
logged. The endpoint returns `401` for unauthenticated callers, `403` for
non-admin users, and a generic `500` if the invalidation mechanism itself
fails or the process-local background scan does not finish within the cache
refresh timeout. A loader-level failure, such as an unavailable mounted root,
does not publish an empty catalog: the last successfully loaded process cache
remains available. A timed-out scan continues in its daemon worker and can
still populate the process cache when it finishes.

The scope is deliberately process-local. Each Uvicorn worker or Kubernetes Pod
must be called directly; repeated requests through a load-balanced Service do
not guarantee that every instance is reached. External MinIO/NFS/CSI writes
bypass the validation, SkillScan, and history used by the install/edit APIs, so
the mounted directory must be writable only by trusted operators.

### File Uploads

#### Upload Files

Upload one or more files to a thread.

```http
POST /api/threads/{thread_id}/uploads
Content-Type: multipart/form-data
```

**Request Body:**
- `files`: One or more files to upload

**Response:**
```json
{
  "success": true,
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "markdown_file": "document.md",
      "markdown_path": ".deer-flow/threads/abc123/user-data/uploads/document.md",
      "markdown_virtual_path": "/mnt/user-data/uploads/document.md",
      "markdown_artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.md"
    }
  ],
  "message": "Successfully uploaded 1 file(s)"
}
```

**Supported Document Formats** (auto-converted to Markdown):
- PDF (`.pdf`)
- PowerPoint (`.ppt`, `.pptx`)
- Excel (`.xls`, `.xlsx`)
- Word (`.doc`, `.docx`)

#### List Uploaded Files

```http
GET /api/threads/{thread_id}/uploads/list
```

**Response:**
```json
{
  "files": [
    {
      "filename": "document.pdf",
      "size": 1234567,
      "path": ".deer-flow/threads/abc123/user-data/uploads/document.pdf",
      "virtual_path": "/mnt/user-data/uploads/document.pdf",
      "artifact_url": "/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf",
      "extension": ".pdf",
      "modified": 1705997600.0
    }
  ],
  "count": 1
}
```

#### Delete File

```http
DELETE /api/threads/{thread_id}/uploads/{filename}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted document.pdf"
}
```

### Thread Cleanup

Remove DeerFlow-managed local thread files under `.deer-flow/threads/{thread_id}` after the LangGraph thread itself has been deleted.

```http
DELETE /api/threads/{thread_id}
```

**Response:**
```json
{
  "success": true,
  "message": "Deleted local thread data for abc123"
}
```

**Error behavior:**
- `422` for invalid thread IDs
- `500` returns a generic `{"detail": "Failed to delete local thread data."}` response while full exception details stay in server logs

### Artifacts

#### Get Artifact

Download or view an artifact generated by the agent.

```http
GET /api/threads/{thread_id}/artifacts/{path}
```

**Path Examples:**
- `/api/threads/abc123/artifacts/mnt/user-data/outputs/result.txt`
- `/api/threads/abc123/artifacts/mnt/user-data/uploads/document.pdf`

**Query Parameters:**
- `download` (boolean): If `true`, force download with Content-Disposition header

**Response:** File content with appropriate Content-Type

---

## Error Responses

All APIs return errors in a consistent format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

**HTTP Status Codes:**
- `400` - Bad Request: Invalid input
- `404` - Not Found: Resource not found
- `422` - Validation Error: Request validation failed
- `500` - Internal Server Error: Server-side error

---

## Authentication

DeerFlow supports four HTTP identity sources. They share the same thread/run isolation rules but differ in whether a row is created in `users` and how external identities are mapped. See [AUTH_DESIGN.md](AUTH_DESIGN.md) for the full design.

| Model | Entry | `users` table | Isolation key |
|---|---|---|---|
| Browser session | `access_token` cookie after login/register | Yes | `users.id` |
| OIDC / SSO | OAuth callback → cookie | Yes | `users.id` (see [SSO.md](SSO.md)) |
| IM channel binding | Connect code + `channel_connections` | Bound to registered user | `channel_connections.owner_user_id` |
| **Internal Auth** | `X-DeerFlow-Internal-Token` + `X-DeerFlow-Owner-User-Id` | **No** | Owner string on `threads_meta.user_id` |

**IM channel binding** and **Internal Auth** are both *platform-trust* integrations: DeerFlow trusts the channel/platform to authenticate end users. IM bindings persist the mapping in `channel_connections` / `channel_conversations` and require a DeerFlow `users` row. Internal Auth lets a platform call the Gateway API directly with a deployment-shared token and a per-request owner header—no `users` row, but thread/run/checkpoint isolation works the same way.

### Browser session (default)

DeerFlow enforces authentication for all non-public HTTP routes. Public routes are limited to health/docs metadata and these public auth endpoints:

- `POST /api/v1/auth/initialize` creates the first admin account when no admin exists.
- `POST /api/v1/auth/login/local` logs in with email/password and sets an HttpOnly `access_token` cookie.
- `POST /api/v1/auth/register` creates a regular `user` account and sets the session cookie.
- `POST /api/v1/auth/logout` clears the session cookie.
- `GET /api/v1/auth/setup-status` reports whether the first admin still needs to be created.

The authenticated auth endpoints are:

- `GET /api/v1/auth/me` returns the current user.
- `POST /api/v1/auth/change-password` changes password, optionally changes email during setup, increments `token_version`, and reissues the cookie.

Protected state-changing requests also require the CSRF double-submit token: send the `csrf_token` cookie value as the `X-CSRF-Token` header. Login/register/initialize/logout are bootstrap auth endpoints: they are exempt from the double-submit token but still reject hostile browser `Origin` headers.

User isolation is enforced from the authenticated user context:

- Thread metadata is scoped by `threads_meta.user_id`; search/read/write/delete APIs only expose the current user's threads.
- Thread files live under `{base_dir}/users/{user_id}/threads/{thread_id}/user-data/` and are exposed inside the sandbox as `/mnt/user-data/`.
- Memory and custom agents are stored under `{base_dir}/users/{user_id}/...`.

Note: MCP outbound connections can still use OAuth for configured HTTP/SSE MCP servers; that is separate from DeerFlow API authentication.

### Internal Auth (platform HTTP integration)

For server-to-server integrations (e.g. a Feishu or WeCom/Enterprise WeChat bot backend), configure:

```bash
export DEER_FLOW_INTERNAL_AUTH_TOKEN="<long-random-secret>"
```

| Header | Required | Description |
|---|---|---|
| `X-DeerFlow-Internal-Token` | Yes | Must match `DEER_FLOW_INTERNAL_AUTH_TOKEN`; missing/invalid → `401` |
| `X-DeerFlow-Owner-User-Id` | Yes for per-user isolation | Platform user id (e.g. `feishu_ou_alice`, `wecom_user_bob`); omit → `default` bucket |

Does **not** use browser cookies or CSRF tokens. Does **not** insert into `users`; sets `threads_meta.user_id` / `runs.user_id` from the owner header. DeerFlow validates only the platform token—not whether the owner id represents a real end user; user validity is entirely the platform's responsibility. See [AUTH_DESIGN.md — Internal Auth](AUTH_DESIGN.md#internal-auth-direct-http) for trust boundaries, persistence, and security notes.

Use the standard Gateway thread/run endpoints (`POST /api/threads`, `POST /api/threads/{thread_id}/runs/stream`, etc.) with the headers above on every request.

---

## Rate Limiting

No rate limiting is implemented by default. For production deployments, configure rate limiting in Nginx:

```nginx
limit_req_zone $binary_remote_addr zone=api:10m rate=10r/s;

location /api/ {
    limit_req zone=api burst=20 nodelay;
    proxy_pass http://backend;
}
```

---

## Streaming Support

Gateway's LangGraph-compatible API streams run events with Server-Sent Events (SSE).

**Thread-scoped streaming** (thread must exist):

```http
POST /api/langgraph/threads/{thread_id}/runs/stream
Accept: text/event-stream
```

**Stateless streaming** (no pre-created thread; Gateway auto-creates one):

```http
POST /api/langgraph/runs/stream
Accept: text/event-stream
```

Both endpoints return `Content-Location: /api/threads/{thread_id}/runs/{run_id}`.
The DeerFlow web UI and LangGraph SDK clients rely on this header to discover the
assigned `thread_id` and `run_id` on the first message of a new chat.

---

## SDK Usage

### Python (LangGraph SDK)

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:2026/api/langgraph")
run_meta: dict[str, str] = {}


def on_run_created(meta) -> None:
    # langgraph-sdk 0.3.x parses Content-Location only when this callback is set.
    if meta.thread_id:
        run_meta["thread_id"] = meta.thread_id
    run_meta["run_id"] = meta.run_id


# Option A: stateless stream — no thread pre-creation
# Gateway auto-creates a thread and returns thread_id/run_id in Content-Location.
async for event in client.runs.stream(
    None,
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
    on_run_created=on_run_created,
):
    print(event)

thread_id = run_meta["thread_id"]  # persist before the next turn

# Option A (continued): same thread on the next turn
async for event in client.runs.stream(
    None,
    "lead_agent",
    input={"messages": [{"role": "user", "content": "What did I just ask?"}]},
    config={"configurable": {"thread_id": thread_id, "model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
    on_run_created=on_run_created,
):
    print(event)

# Option B: thread-scoped stream — create thread first, then stream
thread = await client.threads.create()
async for event in client.runs.stream(
    thread["thread_id"],
    "lead_agent",
    input={"messages": [{"role": "user", "content": "Hello"}]},
    config={"configurable": {"model_name": "gpt-4"}},
    stream_mode=["values", "messages-tuple", "custom"],
    on_run_created=on_run_created,
):
    print(event)
```

### JavaScript/TypeScript

```typescript
// Using fetch for Gateway API
const response = await fetch('/api/models');
const data = await response.json();
console.log(data.models);

function parseRunLocation(contentLocation: string | null) {
  if (!contentLocation) return null;
  const match = /\/threads\/([^/]+)\/runs\/([^/]+)/.exec(contentLocation);
  if (!match) return null;
  return { threadId: match[1], runId: match[2] };
}

// Option A: stateless stream — no thread pre-creation
let threadId: string | undefined;
const firstResponse = await fetch("/api/langgraph/runs/stream", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  },
  body: JSON.stringify({
    input: { messages: [{ role: "user", content: "Hello" }] },
    stream_mode: ["values", "messages-tuple", "custom"],
  }),
});

const created = parseRunLocation(firstResponse.headers.get("Content-Location"));
threadId = created?.threadId;
console.log("thread_id:", created?.threadId, "run_id:", created?.runId);

// Option B: continue the same thread on the next turn
const followUpResponse = await fetch("/api/langgraph/runs/stream", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  },
  body: JSON.stringify({
    input: { messages: [{ role: "user", content: "What did I just ask?" }] },
    config: { configurable: { thread_id: threadId } },
    stream_mode: ["values", "messages-tuple", "custom"],
  }),
});

// Option C: thread-scoped stream when you already have a thread_id
const streamResponse = await fetch(`/api/langgraph/threads/${threadId}/runs/stream`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    Accept: "text/event-stream",
  },
  body: JSON.stringify({
    input: { messages: [{ role: "user", content: "Hello" }] },
    stream_mode: ["values", "messages-tuple", "custom"],
  }),
});

const reader = streamResponse.body?.getReader();
// Decode and parse SSE frames from reader in your client code.
```

### cURL Examples

```bash
# List models
curl http://localhost:2026/api/models

# Get MCP config
curl http://localhost:2026/api/mcp/config

# Upload file
curl -X POST http://localhost:2026/api/threads/abc123/uploads \
  -F "files=@document.pdf"

# Enable skill
curl -X POST http://localhost:2026/api/skills/pdf-processing/enable

# Stateless stream — no thread pre-creation
curl -s -D - -N -X POST http://localhost:2026/api/langgraph/runs/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {
      "recursion_limit": 100,
      "configurable": {"model_name": "gpt-4"}
    },
    "stream_mode": ["values", "messages-tuple", "custom"]
  }'
# Read Content-Location: /api/threads/{thread_id}/runs/{run_id} from the headers.

# Continue the same thread on the next turn
curl -s -N -X POST http://localhost:2026/api/langgraph/runs/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "What did I just ask?"}]},
    "config": {
      "configurable": {"thread_id": "abc123", "model_name": "gpt-4"}
    },
    "stream_mode": ["values", "messages-tuple", "custom"]
  }'

# Thread-scoped flow — create thread first, then stream
curl -X POST http://localhost:2026/api/langgraph/threads \
  -H "Content-Type: application/json" \
  -d '{}'

curl -X POST http://localhost:2026/api/langgraph/threads/abc123/runs/stream \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "input": {"messages": [{"role": "user", "content": "Hello"}]},
    "config": {
      "recursion_limit": 100,
      "configurable": {"model_name": "gpt-4"}
    },
    "stream_mode": ["values", "messages-tuple", "custom"]
  }'
```

> The unified Gateway path defaults `config.recursion_limit` to 100 for
> plan-mode and subagent-heavy runs. Clients may still set
> `config.recursion_limit` explicitly — see the [Create Run](#create-run)
> section for details.
# Source Document Registration

All source-document endpoints require an authenticated administrator. They register provenance metadata only; file upload and copyright authorization are separate workflows.

## Create a source document

`POST /api/source-documents`

```json
{
  "title": "木渎小志",
  "edition": "民国十二年刻本",
  "source_institution": "苏州地方文献馆",
  "source_type": "gazetteer",
  "source_level": "A",
  "holder": "星羲项目资料组"
}
```

The server returns `201`, generates an immutable `source-...` ID, sets `status` to `registered` and `copyright_status` to `unknown`, and records the administrator and timestamps. Required fields reject blank or missing values. Source level accepts only `A` through `E`.

## List and view source documents

- `GET /api/source-documents`
- `GET /api/source-documents/{document_id}`

Records with the same title are not merged. Different editions or source institutions keep distinct IDs.

## Update a source document

`PATCH /api/source-documents/{document_id}` accepts one or more of `title`, `edition`, `source_institution`, `source_type`, `source_level`, `holder`, or `status`. IDs and creation audit fields are not accepted. A successful update preserves the stable ID and creation audit while refreshing `updated_by` and `updated_at`.

Stage 08 does not accept file content or upload state. Copyright decisions are managed separately through the authorization endpoints below.

# Source Copyright and Authorization

Authorization changes and history require an authenticated administrator. New and migrated sources default to `authorization_status=unconfirmed`, `visibility_scope=internal`, and an empty `authorized_uses` list, so access is denied until an explicit decision is recorded.

## Update authorization

`PUT /api/source-documents/{document_id}/authorization`

```json
{
  "copyright_status": "authorized",
  "authorization_status": "active",
  "authorization_basis": "项目方提供的书面授权编号 AUTH-2026-001",
  "authorization_valid_from": "2026-07-20T00:00:00+08:00",
  "authorization_valid_until": "2027-07-20T00:00:00+08:00",
  "visibility_scope": "public",
  "authorized_uses": ["internal_processing", "public_quote"],
  "authorization_proof_object_key": "users/admin/authorization/proof.pdf",
  "change_reason": "录入项目方确认的授权范围"
}
```

`authorization_status` accepts `unconfirmed`, `active`, `expired`, or `revoked`. `authorized_uses` accepts `internal_processing`, `public_full_text`, and `public_quote`; `visibility_scope` accepts `internal`, `authenticated`, or `public`. Active authorization requires a nonblank basis and at least one use. Dates require timezone offsets, and the end must be later than the start. The proof key is an optional reference only; proof upload belongs to Stage 10.

Every successful update atomically appends an audit event. `change_reason` is required. View the ordered, append-only history with:

`GET /api/source-documents/{document_id}/authorization/history`

## Check public access

`GET /api/public/source-documents/{document_id}/access?use=public_quote`

This endpoint is anonymous and returns only a decision:

```json
{
  "use": "public_quote",
  "allowed": true,
  "reason": "authorized",
  "effective_status": "active"
}
```

Unconfirmed, expired, revoked, not-yet-valid, non-public, or use-mismatched sources return `allowed=false`. Expiration is evaluated at request time, so an elapsed active authorization is reported with `effective_status=expired` without waiting for a background job. This endpoint does not expose authorization basis or proof metadata and does not download source files.

# Source File Upload

All source-file endpoints require an authenticated administrator. Upload completion only records the original object and its source binding; it does not parse, OCR, index, authorize, review, or publish the document.

## Upload limits

`GET /api/source-documents/upload/limits`

```json
{
  "max_files": 10,
  "max_file_size": 52428800,
  "max_total_size": 104857600,
  "allowed_extensions": [".pdf", ".png", ".jpg", ".jpeg", ".docx", ".txt", ".md", ".markdown"]
}
```

The numeric limits come from `config.yaml -> uploads`. Both browser and server use them, but server validation is authoritative.

## Upload source originals

`POST /api/source-documents/{document_id}/files`

Send `multipart/form-data` with one or more fields named `files`. The server reads each file in chunks, rejects empty/oversized files, verifies content signatures instead of trusting the extension or request MIME, and cleans staging files on every outcome.

```bash
curl -X POST http://localhost:2026/api/source-documents/source-123/files \
  -b cookies.txt \
  -H "X-CSRF-Token: <csrf-cookie-value>" \
  -F "files=@mudu.pdf;type=application/pdf" \
  -F "files=@map.png;type=image/png"
```

The response is per-file, so one rejected file does not roll back successful siblings:

```json
{
  "success_count": 1,
  "failure_count": 1,
  "items": [
    {
      "filename": "mudu.pdf",
      "status": "uploaded",
      "file": {
        "id": "source-file-...",
        "document_id": "source-123",
        "object_key": "users/source-123/objects/original/...",
        "original_filename": "mudu.pdf",
        "mime_type": "application/pdf",
        "size": 12345,
        "uploaded_by": "admin-id",
        "uploaded_at": "2026-07-21T00:00:00Z"
      }
    },
    {
      "filename": "forged.pdf",
      "status": "failed",
      "error_code": "invalid_file_type",
      "error": "Unsupported or invalid file type"
    }
  ]
}
```

Possible per-file error codes include `empty_file`, `file_too_large`, `batch_too_large`, `too_many_files`, `invalid_file_type`, and `storage_failed`. A disconnected or cancelled request removes its staging file. Retrying sends that file again as a new request.

## List bound files

`GET /api/source-documents/{document_id}/files` returns successful persistent bindings in upload order, including Stage 11 hash and relationship fields.

# Source File Deduplication

The source upload endpoint computes SHA-256 after streaming validation and checks all registered source files. The default `duplicate_policy=report` returns a per-file conflict without writing another object or binding:

```json
{
  "filename": "renamed.pdf",
  "status": "failed",
  "error_code": "duplicate_file",
  "error": "File content already exists",
  "existing_file": {
    "id": "source-file-existing",
    "sha256": "...",
    "duplicate_of_file_id": null,
    "version_of_file_id": null
  }
}
```

To bind the canonical bytes to another registered source without storing them again:

```http
POST /api/source-documents/{document_id}/files
Content-Type: multipart/form-data

files=@renamed.pdf
duplicate_policy=reference_existing
```

The new binding returns the canonical `object_key` and sets `duplicate_of_file_id`.
`reference_existing` is valid only when the uploaded bytes match an existing SHA-256; otherwise the item returns `reference_target_not_found`.

To create an explicit version relation, send `duplicate_policy=new_version` and `version_of_file_id=<existing-source-file-id>`. Different bytes create a new object and set only `version_of_file_id`; identical bytes reuse the canonical object and set both duplicate and version relations. A missing target returns `version_target_required` or `version_target_not_found` for that file.

When the filename already exists under the selected source but the bytes differ, the default response is `same_name_different_content`; the client must explicitly choose `new_version`. A database partial unique index ensures concurrent default uploads cannot create two canonical rows for one hash.

# Digital Document Parsing

All parsing endpoints require an authenticated administrator. Parsing reads the stored original without modifying it. Supported digital formats are PDF, DOCX, TXT, and Markdown; PNG/JPEG and PDFs without a text layer are deferred to Stage 13 OCR.

## Parse a source file

`POST /api/source-documents/{document_id}/files/{file_id}/parse`

The response contains the canonical file's persisted parse. A duplicate source-file reference reuses that canonical result instead of parsing or indexing the same bytes again.

```json
{
  "reused_existing": false,
  "document": {
    "id": "parsed-source-file-123",
    "source_file_id": "source-file-123",
    "parser_name": "pdfium",
    "parser_version": "1",
    "mime_type": "application/pdf",
    "page_count": 2,
    "text": "第一页正文\n\n第二页正文",
    "metadata": {"pagination": "physical", "title": "木渎小志"},
    "parsed_at": "2026-07-21T00:00:00Z",
    "blocks": [
      {"block_type": "paragraph", "page_number": 1, "block_index": 0, "text": "第一页正文", "metadata": {}},
      {"block_type": "paragraph", "page_number": 2, "block_index": 1, "text": "第二页正文", "metadata": {}}
    ]
  }
}
```

Parser failures return HTTP 422 with a structured detail:

```json
{"detail": {"code": "no_extractable_text", "message": "PDF has no extractable text layer"}}
```

Stable codes are `invalid_pdf`, `password_protected_pdf`, `no_extractable_text`, `invalid_docx`, `text_encoding_unknown`, and `unsupported_document_type`.

## Read a parsed result

`GET /api/source-documents/{document_id}/files/{file_id}/parse`

The endpoint returns the persisted document object above, or `404` when the source, file, canonical target, or parsed result does not exist. It does not trigger parsing.

# Scanned Source OCR

All OCR endpoints require an authenticated administrator. Enable `config.yaml -> ocr` and set `model_name` to a `models[]` entry with `supports_vision: true`. OCR reuses that model's API key and OpenAI-compatible `base_url`, `openai_api_base`, or `api_base`; do not duplicate credentials under `ocr`. Set `api_mode: chat_completions` for `/v1/chat/completions`, or `api_mode: responses` when the provider requires `/v1/responses` structured output.

## Start or reuse OCR

`POST /api/source-documents/{document_id}/files/{file_id}/ocr`

PDF pages are rendered at `ocr.render_dpi`; PNG/JPEG inputs become page 1. Page images are stored as `page_image` objects before the configured vision Provider processes up to `max_concurrency` pages. One failed page returns `status=failed` without discarding successful siblings. Pages below `review_confidence_threshold` return `status=review_required`.

```json
{
  "source_file_id": "source-file-123",
  "reused_existing": false,
  "attempts": [
    {
      "id": "ocr-source-file-123-p1-a1",
      "source_file_id": "source-file-123",
      "page_number": 1,
      "attempt_number": 1,
      "status": "completed",
      "raw_text": "木渎",
      "mean_confidence": 0.95,
      "rotation_degrees": 0,
      "regions": [
        {"text": "木渎", "confidence": 0.95, "bounding_box": {"x": 0.1, "y": 0.2, "width": 0.3, "height": 0.1}}
      ]
    }
  ]
}
```

Duplicate source-file references reuse the canonical file's existing attempts. Concurrent first requests also return the canonical persisted result once one request commits.

## Read OCR results

`GET /api/source-documents/{document_id}/files/{file_id}/ocr` returns the latest attempt for every canonical page without starting Provider work. It returns `404` before OCR exists.

## Retry one failed page

`POST /api/source-documents/{document_id}/files/{file_id}/ocr/pages/{page_number}/retry`

Only a page whose latest status is `failed` can be retried. The endpoint reuses its persisted page image, increments `attempt_number`, appends a new attempt, and leaves sibling pages untouched. A completed or review-required page returns HTTP 409 with `code=ocr_page_not_failed`.

## List low-confidence pages

`GET /api/source-documents/ocr/review-queue` returns only latest attempts with `status=review_required`. A later successful retry removes the page from the queue while its earlier attempt remains available for audit in the database.

Stage 13 stores raw OCR output only. Text cleaning, raw/clean dual-track records, Chunk splitting, retrieval indexing, and publication happen in later stages.

# Raw And Clean OCR Text

All cleaning endpoints require an authenticated administrator and resolve duplicate source-file bindings to the canonical file. Raw text is read only from the latest persisted OCR page attempt; request bodies cannot supply or overwrite raw text.

## Generate a clean generation

`POST /api/source-documents/{document_id}/files/{file_id}/clean`

```json
{
  "rule_version": "xingxi-clean-v1",
  "script_conversion": "preserve",
  "variant_map": {"衞": "衛"},
  "normalize_line_endings": true,
  "join_single_line_breaks": true,
  "remove_repeated_headers": true,
  "remove_repeated_footers": true,
  "remove_page_number_footers": true
}
```

`script_conversion` is `preserve`, `simplified`, or `traditional`. OpenCC performs script conversion. `variant_map` permits only one-character to one-character entries so phrase rewriting cannot be disguised as glyph normalization. Repeated headers/footers require at least two matching pages; page-number removal recognizes explicit page-number forms. Rules run against a copy and append a generation atomically for every latest OCR page that has raw text.

```json
{
  "source_file_id": "source-file-123",
  "pages": [
    {
      "id": "cleaned-...",
      "ocr_attempt_id": "ocr-source-file-123-p1-a1",
      "page_number": 1,
      "generation_number": 1,
      "raw_text": "後臺\n史料",
      "raw_sha256": "...",
      "clean_text": "后台史料",
      "clean_sha256": "...",
      "rule_version": "xingxi-clean-v1",
      "script_conversion": "simplified",
      "policy": {"rule_version": "xingxi-clean-v1", "script_conversion": "simplified"},
      "changes": [
        {"sequence": 0, "rule_id": "join_single_line_break", "raw_start": 2, "raw_end": 3, "clean_start": 2, "clean_end": 2, "before": "\n", "after": ""}
      ]
    }
  ]
}
```

Calling POST again appends the next `generation_number`. It never updates previous clean output or `wu_ocr_page_attempts.raw_text`. If no latest OCR page contains text, the endpoint returns HTTP 409 with `code=ocr_text_unavailable`.

## Read latest clean pages

`GET /api/source-documents/{document_id}/files/{file_id}/clean` returns the latest generation for each canonical page, including raw/clean text, both hashes, policy, and changes. It returns `404` before a clean generation exists.

## Read page generation history

`GET /api/source-documents/{document_id}/files/{file_id}/clean/pages/{page_number}/generations` returns all page generations in ascending order. This is the audit and before/after comparison surface; automatic cleaning is not a human collation or approval result.

# Versioned Structure Chunks

All ChunkSet endpoints require an authenticated administrator and operate on the canonical source file's latest clean page generations. They do not generate embeddings, entities, evidence, or search indexes.

## Create or reuse a ChunkSet

`POST /api/source-documents/{document_id}/files/{file_id}/chunks`

```json
{
  "split_version": "structure-v1",
  "max_characters": 1000,
  "overlap_characters": 100
}
```

The splitter recognizes `卷一`/`第一卷` and `目一`/`第一目` headings, keeps headings outside body chunks, joins an unfinished paragraph across adjacent physical pages, and splits long paragraphs with `step = max_characters - overlap_characters`. Every non-heading paragraph produces at least one Chunk. Raw text is projected from the corresponding OCR page while clean text drives structure and windows.

```json
{
  "reused_existing": false,
  "chunk_set": {
    "id": "chunk-set-...",
    "source_file_id": "source-file-123",
    "policy": {"split_version": "structure-v1", "max_characters": 1000, "overlap_characters": 100},
    "input_sha256": "...",
    "structure": [
      {"id": "structure-...", "kind": "volume", "title": "卷一", "page_start": 1, "page_end": 2, "children": []}
    ],
    "chunks": [
      {
        "id": "chunk-...",
        "chunk_index": 0,
        "volume": "卷一",
        "item": "目一",
        "paragraph_index": 0,
        "paragraph_char_start": 0,
        "paragraph_char_end": 120,
        "raw_text": "...",
        "clean_text": "...",
        "page_start": 1,
        "page_end": 2,
        "cleaned_page_ids": ["cleaned-..."],
        "content_sha256": "..."
      }
    ]
  }
}
```

The input fingerprint covers ordered clean generation IDs and their raw/clean hashes. Repeating the same version, policy and input returns `reused_existing=true`. Reusing a version for changed policy or changed clean input returns HTTP 409 with `code=split_version_conflict`; choose a new `split_version` to rebuild and retain both versions. Missing clean input returns `clean_text_unavailable`; heading-only input returns `no_chunkable_text`.

## List and read versions

`GET /api/source-documents/{document_id}/files/{file_id}/chunks` returns all ChunkSets in creation order.

`GET /api/source-documents/{document_id}/files/{file_id}/chunks/{split_version}` returns one version or `404`. Chunk IDs are deterministic for the canonical file, full policy, hierarchy, page range, index and content.

# Persistent Ingestion Jobs

All ingestion endpoints require an authenticated administrator. A successful `POST /api/source-documents/{document_id}/files` item now contains `ingestion_job` (or `ingestion_error` when the file was stored but Job creation failed). Upload completion creates a pending Job; it does not pretend that parsing, OCR, review, indexing or publication already happened.

The canonical step order is `parse -> ocr -> clean -> chunk -> review -> index`. Only an actually executing step has Job status `running`; between steps the Job is `pending`. Completing `chunk` changes the Job to `awaiting_review` and leaves review/index pending. Stage 17 must supply the review decision before indexing can start.

## Create, list and read

`POST /api/source-documents/{document_id}/files/{file_id}/ingestion-jobs`

```json
{"idempotency_key": "operator-import-2026-07-21:file-123"}
```

The response is `{"reused_existing": false, "job": {...}}`. Reusing the same administrator/key for the same file returns the existing current snapshot; using it for another file returns `409 idempotency_conflict`.

- `GET /api/source-documents/{document_id}/files/{file_id}/ingestion-jobs` lists that file's Jobs.
- `GET .../ingestion-jobs/{job_id}` reads one current snapshot.
- `GET .../ingestion-jobs/{job_id}/events?after_sequence=N` returns append-only progress events after `N`, ordered by sequence.

## Worker transitions and leases

`POST .../ingestion-jobs/{job_id}/steps/{step_name}/start`

```json
{"worker_id": "gateway-worker-1"}
```

Start atomically checks `config.yaml -> ingestion.max_concurrent_jobs`, the Job version, expected step, and the database-wide active lease count. Success records the worker and a lease lasting `ingestion.lease_seconds`. `409 ingestion_concurrency_limit` means no slot is available or another worker won the claim.

The owner renews before expiry with `POST .../ingestion-jobs/{job_id}/lease` and the same `worker_id`. A wrong owner or expired lease returns `409 ingestion_lease_lost`. Gateway startup requeues only leases expired beyond `ingestion.recovery_grace_seconds`; it does not steal work from another live Gateway.

- `POST .../steps/{step_name}/complete` accepts `{"output_ref": "parsed-document:..."}`.
- `POST .../steps/{step_name}/fail` accepts `error_code`, `error_message`, and `retryable`.
- `POST .../steps/{step_name}/retry` resets only the current retryable failed step; completed outputs remain intact.
- `POST .../ingestion-jobs/{job_id}/cancel` is idempotent. A late worker completion is rejected by the Job version/status guard.

Illegal ordering, terminal-state writes and stale optimistic versions return `409 invalid_ingestion_transition`. Error codes are stable machine-readable identifiers; messages are operator-facing details.

# Human Text Review

All review routes are administrator-only. Reviews target one exact clean page generation or one exact Chunk; later cleaning/splitting creates new pending targets instead of inheriting approval silently.

## Review workspace queue

`GET /api/source-documents/{document_id}/files/{file_id}/review/queue?chunk_set_id={chunk_set_id}`

The response contains the selected ChunkSet's ordered Chunks and only the clean page IDs referenced by those Chunks. Page rows include raw/clean text, page/generation, current review status, OCR confidence, rotation and cleaning-change count. Chunk rows include raw/clean text, structure, page range, exact clean page IDs and current status.

## Submit decisions

`POST /api/source-documents/{document_id}/files/{file_id}/review/decisions`

```json
{
  "items": [
    {"target_type": "page", "target_id": "cleaned-page-1", "decision": "reviewed"},
    {"target_type": "chunk", "target_id": "chunk-1", "decision": "disputed", "comment": "版本异文待确认"}
  ]
}
```

Allowed decisions are `reviewed`, `rejected`, and `disputed`; `pending` is not a decision. Rejected/disputed items require a non-empty comment. A batch accepts 1–100 unique targets. Every target is validated before writing; missing/cross-file targets roll back the whole batch. Concurrent revision conflicts return `409 review_conflict` so the reviewer can reload current history.

Each success appends a `ReviewRecord` with `revision`, `previous_status`, decision, comment, batch, authenticated reviewer and time, while updating the target's materialized current status in the same transaction. Existing ReviewRecords are not updated or deleted.

## History and gates

- `GET .../review/history?target_type=page|chunk&target_id=...` returns ordered immutable revisions.
- `GET .../review/chunks/{chunk_id}/gate` returns `allowed` plus `chunk_not_reviewed` and/or `page_not_reviewed` reasons.
- `POST .../review/finalize` accepts `chunk_set_id` and `ingestion_job_id`. Every Chunk and every referenced clean page in that set must be reviewed. Success completes the Job's review step and moves it to `index` pending at 85%; it does not create a knowledge version or index rows.

## Knowledge Releases

All `/api/knowledge-releases` endpoints require an administrator. `GET /api/knowledge-releases`, `GET /state`, `GET /events`, and `GET /{release_id}` return immutable versions, the single active pointer, append-only switches, and an exact manifest.

`POST /api/knowledge-releases` accepts `chunk_set_ids`, required `release_notes`, `expected_state_version`, and `activate`. Publication rechecks every Chunk and referenced clean generation inside the write transaction. A successful active publish creates the Release, all manifest items, the pointer update, and its event atomically. Unreviewed content returns `409 release_gate_blocked`; stale pointer or duplicate manifest returns `409 release_conflict`.

`POST /api/knowledge-releases/activate` switches to an existing immutable version. `POST /api/knowledge-releases/rollback` accepts an optional older `target_release_id`; when omitted it selects the immediately preceding version. Both require `expected_state_version` and a reason. Rollback never deletes source files, review records, Releases, or manifests. New agent Runs persist server-owned `knowledge_release_id`, `knowledge_release_version`, and `knowledge_release_manifest_sha256` metadata from the active pointer.

```json
{
  "chunk_set_id": "chunk-set-1",
  "ingestion_job_id": "ingestion-job-1"
}
```

An incomplete set returns `409 review_gate_blocked` with target-specific reasons. Retrying finalize after a process interruption is safe after the Stage 16 lease recovery returns the review step to pending.

## Release-scoped Full-text Search

`POST /api/knowledge-search/fulltext` accepts `query`, optional `release_id`, `document_ids`, `source_levels`, `source_types`, `page`, and `page_size` (maximum 100). The authenticated HTTP route always forces `authorized_use=public_quote`; clients cannot request internal processing scope. If `release_id` is omitted, the current active Release is used. A missing or incomplete index returns `409` with `code=fulltext_release_not_ready`.

Use quoted text for an exact phrase, for example `"香溪沿岸"`; whitespace-separated values such as `木渎 古桥` are AND terms. Punctuation and FTS operators are treated as text, not SQL. Results include `release_id/version`, total/page metadata, deterministic lexical score, matched terms, a plain-text `【highlight】` summary, document title/edition, volume/item, page range and source level. No semantic expansion occurs.

`POST /api/knowledge-search/fulltext/releases/{release_id}/rebuild` is administrator-only and rebuilds a historical Release from its immutable manifest. Normal production publication does not require this endpoint: `POST /api/knowledge-releases` writes the full-text index and readiness state before atomically changing the active pointer. Current source authorization is checked at query time; revoked, expired, non-public, or quote-unauthorized sources are omitted even if old index rows exist.

## Release-scoped Vector Search

`POST /api/knowledge-search/vector` accepts `query`, optional `release_id`, `document_ids`, `source_levels`, `source_types`, `top_k` (maximum 100), and `min_similarity`. The route always forces `authorized_use=public_quote`. It embeds the query only when the active index has the same configured model, explicit compatibility version, and dimensions. A missing, building, failed, stale-manifest, or incompatible index returns `409` with `code=vector_index_not_ready`; an embedding-provider failure returns `502` with `code=embedding_provider_error`.

Results contain the Release and vector-index IDs, embedding model/version, cosine similarity, Chunk ID, document title/edition, volume/item, page range, source level, reviewed status, and quote. Similarity is candidate relevance only and must not be presented as factual confidence. Authorization is evaluated from the current SourceDocument on every query, so revocation or expiry takes effect without rebuilding.

`POST /api/knowledge-search/vector/rebuild` is administrator-only and accepts `release_id` plus `expected_state_version`. The persistent index enters `building` before provider calls. Texts are embedded in configured batches; partial output, duplicate/missing Chunks, dimension mismatch, or provider failure cannot move the active pointer. A complete build atomically marks the version ready and advances the per-Release pointer. `GET /api/knowledge-search/vector/releases/{release_id}/state` and `/versions` expose the pointer and build history to administrators.

Persistent indexing requires `embedding.enabled=true`, an OpenAI-compatible embedding endpoint, and explicit `embedding.dimensions`. Change `embedding.version` whenever provider behavior changes, then rebuild. SQLite uses sqlite-vec cosine KNN. PostgreSQL uses pgvector and dimension-specific partial HNSW indexes. This API does not run Stage 19 full-text search or Stage 21 fusion.

## Hybrid Full-text and Vector Search

`POST /api/knowledge-search/hybrid` accepts `query`, optional `release_id`, the same document/type/level filters, `top_k`, `candidate_k`, and `min_vector_similarity`. The server resolves one immutable Release ID first and forces `authorized_use=public_quote`, then starts full-text and vector retrieval concurrently. `candidate_k` must be at least `top_k` and is capped at 100.

The fusion algorithm is Reciprocal Rank Fusion: each channel contributes `1 / (rrf_k + rank)` and candidates are deduplicated by Chunk ID. The response exposes `algorithm`, `rrf_k`, `degraded`, per-channel status/hit count/error code, plus each hit's native full-text score, vector similarity, ranks, RRF contributions, fused score and citation. A response from another Release is rejected as `release_mismatch`.

Lexical retrieval uses the `hybrid_search.channel_timeout_seconds` deadline;
semantic retrieval uses the shorter `hybrid_search.vector_timeout_seconds`
grace period by default so a slow embedding provider does not hold back an
otherwise usable full-text answer. `ok` and `empty` are healthy statuses.
`timeout`, `error`, or `unavailable` mark the response degraded while
preserving results from the other channel. Identical release-scoped requests
share an in-flight task and a short process-local cache. If neither channel is
usable, the endpoint returns `503 hybrid_search_unavailable`; it never converts
an infrastructure failure into a false empty historical result. When Embedding
is disabled, vector status is `unavailable` and full-text remains usable.

RRF measures retrieval agreement only. Stage 21 does not add authority-level, review-status, temporal, or diversity weights; those belong to Stage 22. The Xingxi `search_sources` tool uses this hybrid service and returns the same channel observability with the Release ID frozen in Run metadata.

## Trust-aware Candidate Reranking

The hybrid endpoint and Xingxi `search_sources` apply the Stage 22 `trust_rerank` policy after RRF. The default weights are relevance `0.70`, source authority `0.15`, review status `0.10`, and verified temporal alignment `0.05`; these four values must sum to one. `document_repeat_penalty` is applied greedily after component scoring so another source can enter `top_k`. Reranking operates on `candidate_k` candidates before truncation.

Each hit includes `ranking.policy_version`, `final_score`, `temporal_match`, weighted component values, machine-readable reasons, and warnings. D/E sources add `low_authority_source`; disputed review adds `disputed_review`; a verified time conflict adds `temporal_conflict`. Candidates are retained rather than silently removed. A strongly relevant low-grade candidate can still outrank weakly relevant high-grade evidence.

The response-level `evidence_status` is `conflicting` when returned evidence includes disputed review, `inferred` when every returned source is D/E, `insufficient` for no hits, and otherwise `supported`. `message` follows that status. `confidence_notice` states that fusion/ranking scores are candidate priority, not factual confidence.

Temporal alignment is not client-controlled. Stage 22 accepts only server-owned validated signals from later structured retrieval; with no signal it records `unknown` and a neutral component. It does not infer a dynasty or date from titles, editions, or quote text. Stage 23 owns structured filters and the later domain stages own historical time data.

## Structured Search Filters and Cursor Paging

`POST /api/knowledge-search/structured` is the canonical Stage 23 search endpoint. Its `filters` object is a strict whitelist: `document_ids`, `editions`, `source_types`, `source_levels`, `dynasties`, `entity_types`, `review_statuses`, `min_spatial_confidence`, and `max_spatial_confidence`. Unknown fields, invalid enums, duplicate values, confidence outside 0–1, or an inverted confidence range return `422`. Values within one array are OR; different fields are AND. No arbitrary operator or SQL expression is accepted.

`dynasties` uses the documented enum from `pre_qin` through `prc`; `entity_types` uses the shared domain EntityType enum. Release publication snapshots known edition/source/review metadata into `wu_search_filter_metadata`. Dynasty and entity values use normalized `wu_search_filter_facets`; spatial confidence is nullable. Missing metadata does not match that filter and is never guessed from title or quote text.

Requests accept `page_size` 1–50, `candidate_k` 1–100, optional `cursor`, and `min_vector_similarity`. The opaque cursor records an offset plus the immutable Release and a SHA-256 fingerprint of query, filters, Release selection, candidate limit, and similarity threshold. Reusing it after changing conditions returns `400 invalid_search_cursor`; an active Release change also requires pagination restart. Responses include candidate/returned counts, `has_more`, `next_cursor`, channel status, evidence status, and ranked hits.

`GET /api/knowledge-search/structured/filters/schema` returns the authoritative JSON Schema. Xingxi `search_sources` accepts the same nested `filters` and optional cursor while preserving legacy `document_ids`/`source_levels`; supplying the same field both ways is rejected. The frontend `knowledge-search` client uses the corresponding typed request, and a contract test guards enum/field drift.

## Evidence-bound Alias Expansion

Structured search performs Stage 24 query-time alias expansion after resolving the immutable Release. `max_alias_expansions` defaults to 5 and is capped at 20. The response `alias_expansion` includes original and resolved queries, expanded canonical terms, candidate entity/type/alias information, applicable dynasties, Evidence IDs, eligibility reason, ambiguity, and truncation.

Automatic replacement requires all of the following: alias review status is `reviewed`, at least one persisted Evidence ID exists, requested dynasty filters overlap the alias period when both are present, and that normalized alias has exactly one eligible entity. `missing_evidence`, `alias_not_reviewed`, and `dynasty_mismatch` candidates are returned but not expanded. Multiple eligible entities produce `ambiguous_alias`, `requires_disambiguation=true`, and no resolved query; the service retains literal-query results without choosing an entity.

Alias storage is Release-scoped in `wu_alias_index`; dynasties and evidence bindings are normalized in `wu_alias_dynasties` and `wu_alias_evidence`. Evidence bindings use a database foreign key to `wu_evidence`. Migration `0022_alias_query_expansion` creates these tables. Stage 24 exposes query behavior only; alias creation, merge/split review, and stable entity CRUD remain later-stage responsibilities.
