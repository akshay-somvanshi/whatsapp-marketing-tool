# Technical Reference

This document covers the full system architecture, data flows, API reference, and how to extend or modify each layer of the platform.

---

## Table of Contents

1. [System Architecture](#1-system-architecture)
2. [Service Configuration](#2-service-configuration)
3. [Database Schema & Relationships](#3-database-schema--relationships)
4. [Request Flows](#4-request-flows)
5. [API Reference](#5-api-reference)
6. [WhatsApp Client](#6-whatsapp-client)
7. [AI Handler](#7-ai-handler)
8. [Celery Tasks & Beat Schedule](#8-celery-tasks--beat-schedule)
9. [Frontend Architecture](#9-frontend-architecture)
10. [Testing Guide](#10-testing-guide)
11. [How To: Common Modifications](#11-how-to-common-modifications)
12. [Environment Variables Reference](#12-environment-variables-reference)
13. [Deployment Notes](#13-deployment-notes)

---

## 1. System Architecture

```
                          ┌─────────────────────────────────────────────────────────┐
                          │  Docker Compose Network                                 │
                          │                                                         │
  Browser ───────────────▶│  Next.js :3000  ──────────────────────────────────────▶│──▶ FastAPI :8000
                          │                                                         │         │
  Meta Cloud ────────────▶│  (via ngrok in dev)  GET/POST /webhook                 │         │
                          │                                                         │         ├──▶ PostgreSQL :5432
  Anthropic API ◀─────────│──────────────────────────────── Claude calls            │         │
                          │                                                         │         ├──▶ Redis :6379 ◀─── Celery Worker
                          │                                                         │         │
  Meta Graph API ◀────────│──────────────────────────── WA client send calls        │         └──▶ Celery Beat (scheduler)
                          │                                                         │
                          └─────────────────────────────────────────────────────────┘
```

### Service Responsibilities

| Service | Image | Role |
|---|---|---|
| `postgres` | postgres:16-alpine | Persistent storage for all application data |
| `redis` | redis:7-alpine | Celery broker + result backend |
| `backend` | ./backend (Python 3.12) | FastAPI HTTP server, all business logic, WhatsApp + Claude clients |
| `celery` | ./backend (same image) | Background task processor, runs `celery_app.celery_worker` |
| `frontend` | ./frontend (Node 20) | Next.js 14 App Router UI, communicates with backend over HTTP |

The `celery` and `backend` services share the same Docker image and codebase — the difference is just the startup command (`uvicorn` vs `celery worker`).

---

## 2. Service Configuration

### `docker-compose.yml` key points

- All services share a custom bridge network `wa_net`
- `postgres` data is persisted in a named volume `pg_data`
- `backend` and `celery` both mount `.env` and share the same environment
- Health checks on `postgres` and `redis` ensure dependent services wait for readiness
- Celery Beat runs as a separate command within the `celery` service (or a dedicated `celery-beat` service)

### `backend/pytest.ini`

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
env =
    DATABASE_URL=postgresql+asyncpg://wa:wa@localhost:5432/wa_test
    REDIS_URL=redis://localhost:6379/1
    MOCK_WHATSAPP=true
    CELERY_TASK_ALWAYS_EAGER=true
```

---

## 3. Database Schema & Relationships

### Entity Relationship

```
contacts (phone PK-equivalent)
    │
    ├──< messages (contact_phone FK)
    │
    └──1 conversations (contact_phone FK UNIQUE)
              │
              └─ (session_expires_at, ai_enabled tracked here)

campaigns (standalone, no FK to contacts — audience resolved at send time by tag)
```

### contacts

```sql
CREATE TABLE contacts (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name          TEXT NOT NULL,
    phone         TEXT UNIQUE NOT NULL,          -- E.164, e.g. +919876543210
    opted_in      BOOLEAN NOT NULL DEFAULT FALSE,
    opted_in_at   TIMESTAMPTZ,
    tags          TEXT[] NOT NULL DEFAULT '{}',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### messages

```sql
CREATE TYPE message_direction AS ENUM ('inbound', 'outbound');
CREATE TYPE message_status    AS ENUM ('sent', 'delivered', 'read', 'failed');

CREATE TABLE messages (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_phone  TEXT NOT NULL REFERENCES contacts(phone) ON DELETE CASCADE,
    direction      message_direction NOT NULL,
    body           TEXT NOT NULL,
    template_name  TEXT,                          -- null for free-form messages
    status         message_status NOT NULL DEFAULT 'sent',
    wa_message_id  TEXT,                          -- Meta's wamid for status tracking
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_messages_contact_phone ON messages(contact_phone);
CREATE INDEX idx_messages_wa_message_id ON messages(wa_message_id);
```

### conversations

```sql
CREATE TYPE conversation_status AS ENUM ('active', 'expired');

CREATE TABLE conversations (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    contact_phone       TEXT UNIQUE NOT NULL REFERENCES contacts(phone) ON DELETE CASCADE,
    session_expires_at  TIMESTAMPTZ NOT NULL,
    status              conversation_status NOT NULL DEFAULT 'active',
    ai_enabled          BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### campaigns

```sql
CREATE TYPE campaign_status AS ENUM ('draft', 'scheduled', 'running', 'completed', 'failed');

CREATE TABLE campaigns (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name             TEXT NOT NULL,
    template_name    TEXT NOT NULL,
    template_params  JSONB NOT NULL DEFAULT '{}',
    audience_tags    TEXT[] NOT NULL DEFAULT '{}',  -- empty = all opted-in contacts
    scheduled_at     TIMESTAMPTZ,                   -- null = send immediately on create
    status           campaign_status NOT NULL DEFAULT 'draft',
    sent_count       INTEGER NOT NULL DEFAULT 0,
    delivered_count  INTEGER NOT NULL DEFAULT 0,
    read_count       INTEGER NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

## 4. Request Flows

### 4a. Webhook Verification (GET /webhook)

Meta calls this once when you register your webhook URL.

```
Meta GET /webhook?hub.mode=subscribe&hub.verify_token=XXX&hub.challenge=YYY
    │
    └─ FastAPI checks hub.verify_token == settings.WEBHOOK_VERIFY_TOKEN
            ├─ Match → return PlainTextResponse(hub.challenge), 200
            └─ No match → return 403
```

### 4b. Incoming Message (POST /webhook)

The most critical path. Must return 200 within 5 seconds or Meta retries.

```
Meta POST /webhook  (JSON body)
    │
    ├─ FastAPI router returns HTTP 200 IMMEDIATELY
    │
    └─ Enqueues Celery task: process_inbound_message.delay(payload)
                │
                ├─ Parse: entry[0].changes[0].value
                │       ├─ .messages[]  → handle as inbound message
                │       └─ .statuses[]  → handle as status update
                │
                ─── IF inbound message ───
                │
                ├─ Upsert contact (create with opted_in=False if phone not seen before)
                ├─ Save message row (direction=inbound, status=sent)
                ├─ mark_as_read(wa_message_id) via WA client
                ├─ Upsert conversation:
                │       session_expires_at = NOW() + 24h
                │       status = active
                ├─ If body.strip().upper() == "STOP":
                │       contact.opted_in = False  →  STOP processing
                │
                └─ If conversation.ai_enabled:
                        ├─ Load last N messages for this contact (conversation history)
                        ├─ Call ai_handler(history, contact.name)
                        ├─ Parse action from response
                        │       ├─ "reply" → send_text_message(phone, text)
                        │       │            save outbound message row
                        │       ├─ "escalate" → conversation.ai_enabled = False
                        │       └─ "save_review" → log/store review text
                        └─ done

                ─── IF status update ───
                │
                └─ Find message by wa_message_id, update status field
```

### 4c. Campaign Send Flow

```
POST /campaigns  →  create campaign row (status=draft or scheduled)
    │
    ├─ If scheduled_at is null or in the past:
    │       send_campaign_task.delay(campaign_id)  →  status=running
    │
    └─ If scheduled_at is future:
            Celery Beat picks it up at scheduled_at  →  send_campaign_task.delay(campaign_id)

send_campaign_task(campaign_id):
    ├─ Load campaign
    ├─ Query contacts WHERE opted_in=True AND tags && campaign.audience_tags
    │       (if audience_tags is empty, all opted-in contacts)
    ├─ For each contact:
    │       ├─ send_template_message(phone, template_name, params)
    │       ├─ Save outbound message row
    │       ├─ campaign.sent_count += 1  (atomic SQL UPDATE)
    │       └─ On error: log with contact phone + wa_message_id, continue
    └─ campaign.status = completed
```

---

## 5. API Reference

All endpoints are prefixed with nothing (mounted at root). Frontend calls `NEXT_PUBLIC_API_URL/endpoint`.

### Health

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Returns `{"status": "ok"}` — used by Docker healthcheck |

### Webhook

| Method | Path | Description |
|---|---|---|
| GET | `/webhook` | Meta webhook verification |
| POST | `/webhook` | Incoming messages and status updates from Meta |

**POST /webhook body** (Meta format, do not alter):
```json
{
  "object": "whatsapp_business_account",
  "entry": [{
    "changes": [{
      "value": {
        "messages": [{
          "from": "919876543210",
          "id": "wamid.xxx",
          "timestamp": "1700000000",
          "text": { "body": "Hello" },
          "type": "text"
        }],
        "statuses": [{
          "id": "wamid.xxx",
          "status": "delivered",
          "timestamp": "1700000001"
        }]
      }
    }]
  }]
}
```

### Contacts

| Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/contacts` | `?search=name_or_phone&tags=tag1,tag2` | `Contact[]` |
| POST | `/contacts` | `ContactCreate` | `Contact` |
| POST | `/contacts/import` | multipart CSV file | `{ created, updated, errors }` |

**ContactCreate schema:**
```json
{ "name": "Priya Sharma", "phone": "+919876543210", "opted_in": true, "tags": ["purchased"] }
```

### Conversations

| Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/conversations` | — | `ConversationSummary[]` |
| GET | `/conversations/{phone}` | — | `ConversationDetail` (includes messages[]) |
| PATCH | `/conversations/{phone}` | `{ "ai_enabled": false }` | `Conversation` |

### Campaigns

| Method | Path | Body / Params | Response |
|---|---|---|---|
| GET | `/campaigns` | — | `Campaign[]` |
| GET | `/campaigns/{id}` | — | `Campaign` |
| POST | `/campaigns` | `CampaignCreate` | `Campaign` |

**CampaignCreate schema:**
```json
{
  "name": "Summer Sale",
  "template_name": "review_request",
  "template_params": { "1": "Priya", "2": "Gold Bangle Set" },
  "audience_tags": ["purchased"],
  "scheduled_at": "2026-06-10T10:00:00Z"
}
```

---

## 6. WhatsApp Client

File: `backend/app/whatsapp/client.py`

```python
class WhatsAppClient:
    async def send_template_message(
        self,
        phone: str,           # E.164 without leading +, e.g. "919876543210"
        template_name: str,
        language_code: str,
        components: list[dict]
    ) -> str:                 # returns wa_message_id

    async def send_text_message(
        self,
        phone: str,
        text: str
    ) -> str:                 # returns wa_message_id

    async def mark_as_read(
        self,
        wa_message_id: str
    ) -> None:
```

**Mock mode** (when `settings.MOCK_WHATSAPP=True`):
- All methods print to stdout: `[MOCK WA] send_text_message to +919876543210: Hello`
- Return `mock_<uuid4>` as the message ID
- No HTTP calls are made

**Consent enforcement**: The client does NOT check `opted_in` — callers (tasks) are responsible for filtering. The `OptedOutError` exception is only raised if you explicitly call `client.assert_opted_in(contact)` before sending.

**Meta API endpoint**: `https://graph.facebook.com/v19.0/{WHATSAPP_PHONE_NUMBER_ID}/messages`

**Auth header**: `Authorization: Bearer {WHATSAPP_API_TOKEN}`

---

## 7. AI Handler

File: `backend/app/ai/handler.py`

### How it builds the Claude request

```python
messages = []
for msg in conversation_history:          # ordered oldest → newest
    role = "user" if msg.direction == "inbound" else "assistant"
    messages.append({"role": role, "content": msg.body})

response = await anthropic_client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=500,
    system=system_prompt,                  # loaded from system_prompt.txt
    messages=messages,
)
```

### Structured Action Protocol

The system prompt instructs Claude to always respond with a JSON object as its first line:

```
{"action": "reply", "text": "Thank you for your purchase! ..."}
{"action": "escalate"}
{"action": "save_review", "text": "Great quality!", "rating": 5}
```

The handler parses this line, falls back to treating the entire response as a plain reply if JSON parsing fails.

### System Prompt Location

`backend/app/ai/system_prompt.txt` — edit this file directly. Restart the backend container for changes to take effect. The prompt is loaded once at startup via `@lru_cache`.

### Conversation History Length

The handler loads the last **20 messages** by default (configurable via `settings.AI_HISTORY_LIMIT`). This balances context quality with token cost.

---

## 8. Celery Tasks & Beat Schedule

File: `backend/app/tasks/celery_app.py`

### Task Registry

| Task name | Queue | Triggered by |
|---|---|---|
| `tasks.process_inbound_message` | `default` | Webhook POST handler |
| `tasks.send_campaign_task` | `campaigns` | `POST /campaigns` or Beat |
| `tasks.check_session_expiry_task` | `beat` | Celery Beat, every hour |
| `tasks.trigger_post_purchase_task` | `beat` | Celery Beat, every hour |

### Beat Schedule

```python
beat_schedule = {
    "check-session-expiry": {
        "task": "tasks.check_session_expiry_task",
        "schedule": crontab(minute=0),        # every hour on the hour
    },
    "post-purchase-trigger": {
        "task": "tasks.trigger_post_purchase_task",
        "schedule": crontab(minute=30),       # every hour at :30
    },
}
```

### Adding a New Task

1. Define the task function in `celery_app.py` decorated with `@celery_app.task`
2. If it should run on a schedule, add it to `beat_schedule`
3. Add a test in the relevant phase test file with `CELERY_TASK_ALWAYS_EAGER=True`

### Error Handling

- `send_campaign_task` catches exceptions per-contact: one bad send does not abort the campaign
- `process_inbound_message` catches AI handler errors: the conversation is saved even if Claude fails
- All task errors are logged with `logger.exception(...)` — check `docker compose logs celery`

---

## 9. Frontend Architecture

```
frontend/app/                  Next.js App Router
├── layout.tsx                 Root layout: nav sidebar, font, global styles
├── page.tsx                   /  → Dashboard
├── contacts/
│   └── page.tsx               /contacts → ContactsTable + modals
├── campaigns/
│   ├── page.tsx               /campaigns → list view
│   └── new/page.tsx           /campaigns/new → CampaignForm
└── inbox/
    └── page.tsx               /inbox → split-pane conversation view

frontend/components/           Shared presentational components
frontend/lib/api.ts            Typed API client — all fetch calls go through here
```

### API Client Pattern (`lib/api.ts`)

```typescript
const API = process.env.NEXT_PUBLIC_API_URL;

export async function getContacts(search?: string, tags?: string[]): Promise<Contact[]> {
  const params = new URLSearchParams();
  if (search) params.set('search', search);
  if (tags?.length) params.set('tags', tags.join(','));
  const res = await fetch(`${API}/contacts?${params}`);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```

All API functions follow this pattern: build URL, fetch, throw on non-2xx, return typed JSON.

### Real-Time Updates (Inbox)

The inbox polls `GET /conversations` every 5 seconds using `setInterval` inside a `useEffect`. There is no WebSocket for MVP. This is intentional — polling is simpler and sufficient for a single business owner checking conversations.

To upgrade to WebSockets later: replace the polling interval with a native WebSocket connection to a new backend endpoint `WS /ws/conversations`, and push new message events from the `process_inbound_message` Celery task via Redis pub/sub.

---

## 10. Testing Guide

### Running Backend Tests

```bash
# From repo root
cd backend

# All tests
pytest

# Single phase
pytest tests/phase4/ -v

# Single test
pytest tests/phase4/test_webhook.py::test_webhook_verification -v

# With coverage
pytest --cov=app --cov-report=term-missing
```

### Test Database Setup

Tests use a separate database `wa_test`. The `conftest.py` creates all tables using SQLAlchemy's `metadata.create_all()` at session start (not via Alembic — that's tested separately in phase2). Each test function gets a DB session that is rolled back after the test.

### Key Fixtures (`tests/conftest.py`)

```python
@pytest.fixture
async def db_session():
    # Creates a transaction, yields session, rolls back
    ...

@pytest.fixture
async def client(db_session):
    # FastAPI TestClient with db_session injected via DI override
    ...

@pytest.fixture
def mock_wa(client):
    # Replaces WhatsAppClient with MockWhatsAppClient via DI override
    # MockWhatsAppClient records all send calls for assertion
    ...

@pytest.fixture
def mock_claude(monkeypatch):
    # Patches anthropic.AsyncAnthropic.messages.create
    # Returns configurable canned response
    ...
```

### Running Frontend Tests

```bash
cd frontend
npm test                    # watch mode
npm test -- --watchAll=false   # CI mode (run once)
```

---

## 11. How To: Common Modifications

### Add a New Message Template

1. Get the template approved in Meta Business Manager
2. Add an entry to `backend/templates.json`:
   ```json
   {
     "name": "flash_sale",
     "display_name": "Flash Sale Announcement",
     "language": "en",
     "params": [
       { "slot": "1", "label": "Discount %", "example": "20" },
       { "slot": "2", "label": "Expiry date", "example": "June 10" }
     ]
   }
   ```
3. Restart the backend: `docker compose restart backend`
4. The template now appears in the campaign builder UI

### Modify the AI Persona

Edit `backend/app/ai/system_prompt.txt`. The prompt should:
- State the AI's name and the business it represents
- Define what it can and cannot offer
- List escalation triggers word-for-word so the AI uses `"action": "escalate"` reliably
- Include a few example conversation snippets if the AI is misunderstanding the context

Restart the backend after editing.

### Add a New API Endpoint

1. Create or edit the relevant router in `backend/app/routers/`
2. Add the Pydantic v2 request/response schemas in `backend/app/schemas/`
3. Register the router in `backend/app/main.py` with `app.include_router(...)`
4. Add a test in the appropriate phase test file
5. Add a typed function for it in `frontend/lib/api.ts`

### Add a New Database Column

1. Edit the SQLAlchemy model in `backend/app/models/`
2. Generate a new Alembic migration:
   ```bash
   docker compose exec backend alembic revision --autogenerate -m "add column x to table y"
   ```
3. Review the generated file in `backend/alembic/versions/`
4. Apply it:
   ```bash
   docker compose exec backend alembic upgrade head
   ```
5. Update the Pydantic schemas if the column should appear in API responses

### Change the Claude Model

In `backend/app/ai/handler.py`, change the `model=` argument:
```python
model="claude-opus-4-8"   # for higher quality, higher cost
model="claude-haiku-4-5-20251001"  # for lower cost, faster response
```

See the [Anthropic docs](https://docs.anthropic.com/en/docs/about-claude/models) for current model IDs and pricing.

### Add a New Celery Scheduled Task

1. Define the task in `backend/app/tasks/celery_app.py`:
   ```python
   @celery_app.task(name="tasks.my_new_task")
   def my_new_task():
       ...
   ```
2. Add it to `beat_schedule`:
   ```python
   "my-new-task": {
       "task": "tasks.my_new_task",
       "schedule": crontab(hour=9, minute=0),  # every day at 09:00
   },
   ```
3. Write a test with `CELERY_TASK_ALWAYS_EAGER=True` that calls `my_new_task.delay()` and asserts the DB side effects

---

## 12. Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Yes | — | asyncpg connection string: `postgresql+asyncpg://user:pass@host:5432/db` |
| `REDIS_URL` | Yes | — | Redis connection: `redis://host:6379/0` |
| `WHATSAPP_API_TOKEN` | Yes (prod) | — | Meta permanent system user token |
| `WHATSAPP_PHONE_NUMBER_ID` | Yes (prod) | — | Meta phone number ID from Developer Console |
| `WEBHOOK_VERIFY_TOKEN` | Yes | — | Any secret string; must match what you enter in Meta's console |
| `ANTHROPIC_API_KEY` | Yes | — | Claude API key from console.anthropic.com |
| `MOCK_WHATSAPP` | No | `false` | Set `true` to skip real WhatsApp API calls |
| `AI_HISTORY_LIMIT` | No | `20` | Number of past messages sent to Claude as context |
| `NEXT_PUBLIC_API_URL` | Yes | — | Backend URL as seen by the browser (e.g. `http://localhost:8000`) |

---

## 13. Deployment Notes

This section covers what needs to change when moving from `docker compose` local dev to a production server.

### Checklist

- [ ] Set `MOCK_WHATSAPP=false` and provide real Meta credentials
- [ ] Set `WEBHOOK_VERIFY_TOKEN` to a long random string (e.g. `openssl rand -hex 32`)
- [ ] Put the FastAPI backend behind a TLS-terminating reverse proxy (nginx or Caddy) — Meta requires HTTPS for webhooks
- [ ] Use a managed PostgreSQL service (e.g. Supabase, RDS) or ensure pg_data volume is on persistent storage
- [ ] Set `NEXT_PUBLIC_API_URL` to the production backend domain
- [ ] Configure CORS in `backend/app/main.py` to allow only the production frontend domain
- [ ] Run Alembic migrations as part of the deploy: `alembic upgrade head`
- [ ] Consider using a process supervisor (systemd, supervisord) or container orchestration (ECS, Fly.io) instead of plain Docker Compose for uptime

### Celery Beat in Production

Run Celery Beat as a dedicated service (not co-located with the worker) to avoid duplicate scheduled task fires:

```bash
celery -A app.tasks.celery_app beat --loglevel=info --scheduler django_celery_beat.schedulers:DatabaseScheduler
```

Or use a separate `celery-beat` container in your compose/orchestration config.

### Meta Webhook URL

Update to your production domain in the Meta Developer Console:
`https://yourdomain.com/webhook`

The verify token must match `WEBHOOK_VERIFY_TOKEN` in production `.env`.
