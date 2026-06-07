# WhatsApp Marketing Platform — Implementation Plan

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  Docker Compose                                                 │
│                                                                 │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌───────────┐   │
│  │ Next.js  │──▶│ FastAPI  │──▶│ Postgres │   │   Redis   │   │
│  │ :3000    │   │ :8000    │   │ :5432    │   │   :6379   │   │
│  └──────────┘   └──────────┘   └──────────┘   └───────────┘   │
│                      │                               ▲          │
│                      ▼                               │          │
│                 ┌──────────┐                         │          │
│                 │  Celery  │─────────────────────────┘          │
│                 │  Worker  │                                     │
│                 └──────────┘                                     │
└─────────────────────────────────────────────────────────────────┘
         ▲                  ▲
         │ Meta Webhook     │ Claude API
    Meta Cloud API     Anthropic API
```

---

## Repository Structure

```
whatsapp-marketing-tool/
├── backend/
│   ├── app/
│   │   ├── main.py                  # FastAPI app, router registration, CORS
│   │   ├── config.py                # pydantic-settings: all env vars
│   │   ├── database.py              # async SQLAlchemy engine + session dep
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── contact.py
│   │   │   ├── message.py
│   │   │   ├── conversation.py
│   │   │   └── campaign.py
│   │   ├── schemas/
│   │   │   ├── contact.py
│   │   │   ├── message.py
│   │   │   ├── conversation.py
│   │   │   └── campaign.py
│   │   ├── routers/
│   │   │   ├── webhook.py
│   │   │   ├── contacts.py
│   │   │   ├── campaigns.py
│   │   │   └── conversations.py
│   │   ├── whatsapp/
│   │   │   └── client.py            # Meta Cloud API wrapper + mock mode
│   │   ├── ai/
│   │   │   ├── handler.py           # Claude API integration
│   │   │   └── system_prompt.txt    # Editable business persona
│   │   └── tasks/
│   │       └── celery_app.py        # Celery instance + all tasks
│   ├── tests/
│   │   ├── conftest.py              # Shared fixtures: test DB, async client, mock WA
│   │   ├── phase1/
│   │   │   └── test_infrastructure.py
│   │   ├── phase2/
│   │   │   └── test_models.py
│   │   ├── phase3/
│   │   │   └── test_whatsapp_client.py
│   │   ├── phase4/
│   │   │   └── test_webhook.py
│   │   ├── phase5/
│   │   │   ├── test_contacts.py
│   │   │   └── test_conversations.py
│   │   ├── phase6/
│   │   │   └── test_campaigns.py
│   │   ├── phase7/
│   │   │   └── test_ai_handler.py
│   │   └── phase8/
│   │       └── test_e2e.py
│   ├── alembic/
│   │   └── versions/
│   ├── alembic.ini
│   ├── templates.json               # Pre-approved WA template definitions
│   ├── requirements.txt
│   ├── pytest.ini
│   └── Dockerfile
├── frontend/
│   ├── app/
│   │   ├── page.tsx                 # Dashboard
│   │   ├── contacts/page.tsx
│   │   ├── campaigns/page.tsx
│   │   ├── campaigns/new/page.tsx
│   │   └── inbox/page.tsx
│   ├── components/
│   │   ├── ContactsTable.tsx
│   │   ├── CampaignForm.tsx
│   │   ├── ConversationList.tsx
│   │   └── MessageThread.tsx
│   ├── lib/
│   │   └── api.ts                   # Typed fetch wrapper for backend
│   ├── __tests__/
│   │   ├── components/
│   │   │   ├── ContactsTable.test.tsx
│   │   │   ├── CampaignForm.test.tsx
│   │   │   └── MessageThread.test.tsx
│   │   └── pages/
│   │       ├── dashboard.test.tsx
│   │       └── inbox.test.tsx
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── TECHNICAL.md
└── PLAN.md
```

---

## Testing Strategy

### Backend (pytest + pytest-asyncio)

- All tests run against a **real test database** (`wa_test`) spun up in the same Docker Compose
  network — no mocking the DB layer, so migrations are always validated.
- WhatsApp API calls are mocked via a `MockWhatsAppClient` fixture (not env-var based in tests —
  injected via FastAPI dependency override so behaviour is deterministic).
- Claude API calls are mocked with `pytest-httpx` or `unittest.mock.AsyncMock` — return canned
  responses so tests don't cost API credits and don't flake on network.
- Celery tasks are called **eagerly** (`CELERY_TASK_ALWAYS_EAGER=True`) in tests, so the task
  logic runs synchronously without needing a worker.
- Run all backend tests: `cd backend && pytest`
- Run a single phase: `pytest tests/phase4/`

### Frontend (Jest + React Testing Library)

- Components are tested in isolation with mocked API responses (`msw` or `jest.fn()`).
- No end-to-end browser tests for MVP — manual verification covers the golden path.
- Run frontend tests: `cd frontend && npm test`

### `conftest.py` key fixtures

| Fixture | Scope | What it provides |
|---|---|---|
| `db_session` | function | Fresh async DB session, rolls back after each test |
| `client` | function | `httpx.AsyncClient` wired to the FastAPI test app |
| `mock_wa` | function | `MockWhatsAppClient` injected via DI override |
| `mock_claude` | function | Patched `anthropic.AsyncAnthropic` returning canned text |
| `sample_contact` | function | A pre-inserted opted-in contact row |

---

## Database Schema

### `contacts`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | TEXT | |
| phone | TEXT UNIQUE | E.164 format (+91XXXXXXXXXX) |
| opted_in | BOOL | default false |
| opted_in_at | TIMESTAMPTZ | nullable |
| tags | TEXT[] | e.g. ["purchased", "vip"] |
| created_at | TIMESTAMPTZ | server default |

### `messages`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| contact_phone | TEXT FK→contacts.phone | |
| direction | ENUM inbound/outbound | |
| body | TEXT | |
| template_name | TEXT | nullable |
| status | ENUM sent/delivered/read/failed | |
| wa_message_id | TEXT | Meta's message ID for status updates |
| created_at | TIMESTAMPTZ | |

### `conversations`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| contact_phone | TEXT FK→contacts.phone UNIQUE | one conversation per contact |
| session_expires_at | TIMESTAMPTZ | now + 24h on every inbound |
| status | ENUM active/expired | |
| ai_enabled | BOOL | default true |
| updated_at | TIMESTAMPTZ | |

### `campaigns`
| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| name | TEXT | |
| template_name | TEXT | must exist in templates.json |
| template_params | JSONB | parameter values for the template |
| audience_tags | TEXT[] | contacts with ANY of these tags |
| scheduled_at | TIMESTAMPTZ | nullable = send immediately |
| status | ENUM draft/scheduled/running/completed/failed | |
| sent_count | INT | default 0 |
| delivered_count | INT | default 0 |
| read_count | INT | default 0 |
| created_at | TIMESTAMPTZ | |

---

## Environment Variables

```
# Backend
DATABASE_URL=postgresql+asyncpg://wa:wa@postgres:5432/wa_marketing
REDIS_URL=redis://redis:6379/0
WHATSAPP_API_TOKEN=          # Meta permanent token
WHATSAPP_PHONE_NUMBER_ID=    # Meta phone number ID
WEBHOOK_VERIFY_TOKEN=        # any secret string you pick
ANTHROPIC_API_KEY=           # Claude API key
MOCK_WHATSAPP=true           # set false in production

# Frontend
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Key Implementation Details

### Webhook Flow (critical path)

```
Meta POST /webhook
    │
    ├─ Parse body: extract entry[0].changes[0].value
    │       ├─ .messages[]   → inbound message
    │       └─ .statuses[]   → delivery/read status update
    │
    ├─ Return HTTP 200 IMMEDIATELY (before any async work)
    │
    └─ Enqueue Celery task: process_inbound_message(payload)
            │
            ├─ Upsert contact (opted_in=False if new)
            ├─ Save message (direction=inbound)
            ├─ Upsert conversation (session_expires_at = now+24h)
            ├─ Handle "STOP" → set opted_in=False
            └─ If conversation.ai_enabled → ai_handler → send reply → save outbound
```

### WhatsApp Client Mock Mode

When `MOCK_WHATSAPP=true`, all send methods log to stdout and return a fake message ID
(`mock_<uuid>`). This lets the full flow run locally without Meta credentials.

### AI Handler

- Model: `claude-sonnet-4-6` (current Sonnet — the brief listed `claude-sonnet-4-20250514`
  which is an older ID format; use the current stable ID)
- Max tokens: 500
- System prompt: stored in `backend/app/ai/system_prompt.txt`, defines business persona,
  what discounts/offers are allowed, escalation triggers
- Structured actions returned via tool use or a simple JSON prefix:
  - `{ "action": "reply", "text": "..." }` — normal reply
  - `{ "action": "escalate" }` — disables ai_enabled, flags for human
  - `{ "action": "save_review", "text": "...", "rating": 5 }` — stores review text

### Celery Tasks

| Task | Trigger | What it does |
|---|---|---|
| `process_inbound_message` | Webhook POST | Runs full inbound message flow |
| `send_campaign_task` | Campaign scheduled time | Fans out one `send_template_message` per opted-in contact matching audience_tags, updates campaign counts |
| `check_session_expiry_task` | Beat: every hour | Sets conversation.status=expired where session_expires_at < now |
| `trigger_post_purchase_task` | Beat: every hour | Finds contacts tagged "purchased" in last 72h with no existing review request message, sends review template |

### Templates Format (`templates.json`)

```json
[
  {
    "name": "review_request",
    "display_name": "Post-Purchase Review Request",
    "language": "en",
    "params": [
      { "slot": "1", "label": "Customer name", "example": "Priya" },
      { "slot": "2", "label": "Product name", "example": "Gold Bangle Set" }
    ]
  }
]
```

### CORS

FastAPI must allow requests from the Next.js origin (`http://localhost:3000` in dev).
In production, lock to the actual domain.

### Local Dev Webhook Exposure

Meta requires a public HTTPS URL for webhook delivery. Use ngrok:
```
ngrok http 8000
```
Set the resulting URL + `/webhook` in Meta Developer Console. The verify token must
match `WEBHOOK_VERIFY_TOKEN` in `.env`.

---

## Build Order

### Phase 1 — Infrastructure
**Implementation**
- [ ] `docker-compose.yml` with services: `postgres`, `redis`, `backend`, `celery`, `frontend`
- [ ] `backend/Dockerfile` (Python 3.12 slim)
- [ ] `frontend/Dockerfile` (Node 20 alpine)
- [ ] `.env.example` with all variables documented

**Tests — `tests/phase1/test_infrastructure.py`**
- [ ] Assert postgres container is reachable (asyncpg connect + `SELECT 1`)
- [ ] Assert redis container is reachable (`redis.ping()`)
- [ ] Assert FastAPI app starts and `GET /health` returns 200

---

### Phase 2 — Backend Core
**Implementation**
- [ ] `backend/requirements.txt` — fastapi, uvicorn, sqlalchemy[asyncio], asyncpg, alembic,
      celery[redis], redis, httpx, anthropic, pydantic-settings, python-multipart, phonenumbers,
      pytest, pytest-asyncio, pytest-httpx, httpx
- [ ] `app/config.py` — Settings class with all env vars
- [ ] `app/database.py` — async engine, session factory, `get_db` dependency
- [ ] `app/models/` — all four SQLAlchemy models
- [ ] Alembic init + first migration → run it

**Tests — `tests/phase2/test_models.py`**
- [ ] Create a contact row, read it back, assert all fields round-trip
- [ ] Assert `contacts.phone` unique constraint rejects a duplicate
- [ ] Create message + conversation rows with FK to contact, assert relationships load
- [ ] Create a campaign row, assert default counts are 0
- [ ] Assert Alembic `current` matches `head` (migration is applied)

---

### Phase 3 — WhatsApp Client
**Implementation**
- [ ] `app/whatsapp/client.py` — `send_template_message`, `send_text_message`, `mark_as_read`
- [ ] Mock mode: when `MOCK_WHATSAPP=true`, log and return fake IDs (`mock_<uuid>`)
- [ ] Consent check: raise `OptedOutError` if contact.opted_in is False

**Tests — `tests/phase3/test_whatsapp_client.py`**
- [ ] In mock mode: `send_text_message` returns a string starting with `mock_`
- [ ] In mock mode: `send_template_message` returns a string starting with `mock_`
- [ ] `OptedOutError` is raised when `opted_in=False` contact is passed
- [ ] Real mode (using `pytest-httpx`): assert correct JSON body and auth header are sent to
      Meta's graph API endpoint

---

### Phase 4 — Webhook Endpoint
**Implementation**
- [ ] `GET /webhook` — verify token + return challenge
- [ ] `POST /webhook` — parse Meta payload, return 200, enqueue Celery task
- [ ] `process_inbound_message` Celery task — full flow: upsert contact, save message,
      upsert conversation, STOP handling, AI reply

**Tests — `tests/phase4/test_webhook.py`**
- [ ] `GET /webhook` with correct token returns 200 + challenge string
- [ ] `GET /webhook` with wrong token returns 403
- [ ] `POST /webhook` always returns 200 regardless of payload
- [ ] After `process_inbound_message` (eager): inbound message is saved to DB
- [ ] After `process_inbound_message` (eager): conversation session_expires_at is ~24h from now
- [ ] "STOP" message sets contact.opted_in = False
- [ ] Status update webhook (delivered/read) updates `messages.status` correctly
- [ ] AI-enabled conversation triggers a mock Claude call and saves outbound reply

---

### Phase 5 — Contacts & Conversations APIs
**Implementation**
- [ ] `POST /contacts` — create contact (validate E.164 via `phonenumbers`)
- [ ] `GET /contacts` — list with optional `search` query param and tag filter
- [ ] `POST /contacts/import` — CSV upload, parse, bulk upsert
- [ ] `GET /conversations` — list with latest message, session status
- [ ] `GET /conversations/{phone}` — full message history
- [ ] `PATCH /conversations/{phone}` — toggle ai_enabled

**Tests — `tests/phase5/test_contacts.py` + `test_conversations.py`**
- [ ] `POST /contacts` with valid E.164 creates and returns contact
- [ ] `POST /contacts` with invalid phone returns 422
- [ ] `POST /contacts` with duplicate phone returns 409
- [ ] `GET /contacts?search=Priya` returns only matching contacts
- [ ] `GET /contacts?tags=purchased` returns only tagged contacts
- [ ] CSV import with 3 rows creates 3 contacts; duplicate phone row is upserted not duplicated
- [ ] CSV import with missing `phone` column returns 400
- [ ] `GET /conversations` returns list with `session_status` field
- [ ] `GET /conversations/{phone}` returns ordered message history
- [ ] `PATCH /conversations/{phone}` toggles `ai_enabled`

---

### Phase 6 — Campaigns API + Celery
**Implementation**
- [ ] `POST /campaigns` — validate template exists in templates.json, create record
- [ ] `GET /campaigns` — list with stats
- [ ] `GET /campaigns/{id}` — detail
- [ ] `send_campaign_task` — fan-out with per-message error handling, update counts atomically
- [ ] `check_session_expiry_task` + `trigger_post_purchase_task` in Celery Beat schedule

**Tests — `tests/phase6/test_campaigns.py`**
- [ ] `POST /campaigns` with valid template_name creates campaign with status=draft
- [ ] `POST /campaigns` with unknown template_name returns 422
- [ ] `GET /campaigns` returns list including sent_count/delivered_count/read_count
- [ ] `send_campaign_task` (eager, mock WA): sends to all opted-in contacts with matching tag,
      skips opted-out contacts, increments sent_count correctly
- [ ] `send_campaign_task` with no matching contacts completes with sent_count=0
- [ ] `check_session_expiry_task` marks a past-expiry conversation as expired
- [ ] `trigger_post_purchase_task` sends review template to contacts tagged "purchased"
      in last 72h and does not double-send

---

### Phase 7 — AI Handler
**Implementation**
- [ ] `app/ai/handler.py` — build messages array from conversation history, call Claude
- [ ] `app/ai/system_prompt.txt` — editable business persona prompt
- [ ] Parse structured action from Claude response (`reply`, `escalate`, `save_review`)
- [ ] Handle escalation: disable ai_enabled, log for human review

**Tests — `tests/phase7/test_ai_handler.py`**
- [ ] Handler builds correct message array (system + alternating user/assistant turns)
- [ ] Claude response with `"action": "reply"` returns reply text
- [ ] Claude response with `"action": "escalate"` sets conversation.ai_enabled = False
- [ ] Claude response with `"action": "save_review"` stores review text in message metadata
- [ ] Handler gracefully handles Claude API error (logs, does not crash webhook flow)
- [ ] Max token limit is respected (assert `max_tokens=500` in API call args)

---

### Phase 8 — Frontend
**Implementation**
- [ ] Bootstrap Next.js 14 App Router + Tailwind CSS
- [ ] `lib/api.ts` — typed fetch client pointing to `NEXT_PUBLIC_API_URL`
- [ ] `/` — dashboard: contact count, active conversations, campaigns this month
- [ ] `/contacts` — table with search, add-contact modal, CSV import button
- [ ] `/campaigns` — list with status badges (draft/scheduled/running/completed)
- [ ] `/campaigns/new` — form: name, template selector, tag filter, schedule picker
- [ ] `/inbox` — conversation list + message thread, session expiry countdown, AI toggle

**Tests — `frontend/__tests__/`**
- [ ] `ContactsTable`: renders rows, search input filters displayed results
- [ ] `CampaignForm`: submit with empty name shows validation error; valid submit calls API
- [ ] `MessageThread`: renders inbound vs outbound bubbles with correct alignment
- [ ] Dashboard page: shows correct stat cards when API returns mock data
- [ ] Inbox page: selecting a conversation loads the message thread

---

### Phase 9 — End-to-End Verification
**Manual golden path** (run after all phases complete)
- [ ] Import a contact via UI CSV upload → appears in contacts table
- [ ] Create a campaign → Celery task runs → message saved in DB → UI shows sent_count
- [ ] Simulate inbound message via `curl POST /webhook` with Meta payload format
- [ ] Verify AI reply is sent (mock log) and saved in conversations/{phone}
- [ ] Send "STOP" → verify contact.opted_in = False → campaign skips that contact

**Automated E2E test — `tests/phase8/test_e2e.py`**
- [ ] Full flow test using test DB + mock WA + mock Claude:
  1. Create contact via API
  2. Create campaign via API
  3. Trigger `send_campaign_task` eagerly
  4. Assert message row exists with direction=outbound
  5. POST inbound webhook payload
  6. Assert inbound message saved, conversation updated, AI outbound reply saved
  7. POST "STOP" webhook
  8. Assert contact.opted_in = False

---

## Risks & Open Questions

| Item | Status |
|---|---|
| Meta app approval for templates | Must submit templates for review; use sandbox test templates during dev |
| ngrok public URL changes on restart | Use ngrok stable URL (paid) or re-set webhook URL each session |
| Claude API response latency (~1–3s) | Acceptable for WhatsApp — users don't expect instant bot replies |
| Celery Beat for scheduled tasks | Single Beat instance in docker-compose; fine for MVP |
| `claude-sonnet-4-6` model ID | Confirmed current stable Sonnet; update if Anthropic releases newer |
| Phone number E.164 validation | Use `phonenumbers` library on ingest to normalise and reject invalid numbers |
| CSV import encoding | Accept UTF-8 only; document this for business owner |

---

## Not In Scope (MVP)

- Multi-tenancy / per-business isolation
- Payment / billing
- Rich media (images, documents, voice)
- Facebook / Instagram channels
- Role-based access control
