# Phase 1 — Multi-Tenancy & Authentication

**Goal:** Convert the single-tenant MVP into a multi-tenant SaaS where every piece of data belongs to an organization, and access is gated by authenticated users with roles.

**Status:** In progress
**Depends on:** none (foundational — dictates all later schema)

---

## 1. Design Decisions (locked)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Tenant isolation | **Shared DB + `organization_id` column** on every tenant-owned table | Simplest migrations, standard for SaaS MVP. App-layer enforcement now; Postgres RLS can be layered later. |
| Team model | **Multi-user orgs with roles** (`owner`, `admin`, `agent`) | Shared-inbox is table-stakes; avoids a second migration later. |
| Auth | **JWT only** — short-lived access token + refresh token | Stateless, fits the Next.js SPA + future API. API keys deferred to a later phase. |
| Password hashing | bcrypt via `passlib` | Battle-tested default. |
| Per-tenant channel config | WhatsApp + AI credentials stored **per organization** | A tenant's messages must use *their* WhatsApp number; webhooks route to a tenant by `phone_number_id`. |

---

## 2. Data Model

### New tables

**`organizations`** — the tenant.
- `id` UUID PK
- `name` Text, not null
- `slug` Text, unique, not null (URL-safe identifier)
- WhatsApp config: `whatsapp_phone_number_id` Text null (unique), `whatsapp_api_token` Text null, `whatsapp_business_account_id` Text null
- AI config: `ai_provider` Text default `'anthropic'`, `anthropic_api_key` Text null, `gemini_api_key` Text null, `system_prompt` Text null
- `created_at` timestamptz default now()
- *Note:* secret columns are plaintext in Phase 1; encryption-at-rest is a tracked follow-up (out of scope here).

**`users`** — a person who can log in. Global identity (one email = one user, can belong to many orgs).
- `id` UUID PK
- `email` Text, unique (citext-like, stored lowercased), not null
- `password_hash` Text, not null
- `full_name` Text null
- `is_active` Boolean default true
- `created_at` timestamptz default now()

**`memberships`** — user ↔ organization with a role.
- `id` UUID PK
- `user_id` UUID FK → users.id (cascade)
- `organization_id` UUID FK → organizations.id (cascade)
- `role` Enum(`owner`, `admin`, `agent`), not null
- `created_at` timestamptz default now()
- Unique (`user_id`, `organization_id`)

### Existing tables — add tenancy

Add `organization_id` UUID FK → organizations.id (cascade, not null) to: `contacts`, `campaigns`, `conversations`, `messages`.

Constraint changes:
- `contacts`: drop global unique on `phone`; add **unique (`organization_id`, `phone`)** (natural key).
- `conversations`: drop global unique on `contact_phone`; add **unique (`organization_id`, `contact_phone`)**; change FK to composite **(`organization_id`, `contact_phone`) → contacts(`organization_id`, `phone`)**.
- `messages`: change FK to composite **(`organization_id`, `contact_phone`) → contacts(`organization_id`, `phone`)**.
- Index `organization_id` on all four tables.

---

## 3. Roles & Permissions

| Capability | owner | admin | agent |
|------------|:-----:|:-----:|:-----:|
| Read contacts/conversations/campaigns | ✅ | ✅ | ✅ |
| Send/reply messages, toggle AI | ✅ | ✅ | ✅ |
| Create/edit/delete contacts & campaigns | ✅ | ✅ | ❌ |
| Manage org settings (WhatsApp/AI creds) | ✅ | ✅ | ❌ |
| Invite/remove members, change roles | ✅ | ❌ | ❌ |
| Delete organization | ✅ | ❌ | ❌ |

Enforced via a `require_role(*roles)` dependency. Phase-1 enforcement is pragmatic: read endpoints require any member; write endpoints require `admin`/`owner`; member management requires `owner`.

---

## 4. API Contract

All existing endpoints become **org-scoped** and require a valid access token. The org is derived from the token (the token carries `user_id` + active `organization_id`).

### Auth (`/auth`)
- `POST /auth/register` — body `{ email, password, full_name, organization_name }`. Creates a user + organization + `owner` membership atomically. Returns access + refresh tokens. 409 if email exists.
- `POST /auth/login` — body `{ email, password }`. Returns access + refresh tokens + the user's orgs. 401 on bad credentials.
- `POST /auth/refresh` — body `{ refresh_token }`. Returns a new access token. 401 if invalid/expired.
- `GET /auth/me` — returns the current user + memberships. Requires access token.

### Org & members (`/org`)
- `GET /org` — current org details (settings; secrets masked).
- `PATCH /org` — update org settings (name, WhatsApp/AI config). Requires admin/owner.
- `GET /org/members` — list members. Any member.
- `POST /org/members` — add a member by email with a role (creates the user with a temp password if new, or links existing). Requires owner. *(Phase-1: simple add, not an email-invite flow.)*
- `PATCH /org/members/{user_id}` — change role. Requires owner.
- `DELETE /org/members/{user_id}` — remove member. Requires owner.

### Existing routers — now scoped
- `/contacts`, `/campaigns`, `/conversations` — every query filtered by `organization_id`; every create stamps `organization_id`; cross-org access returns 404 (not 403, to avoid leaking existence).

### Webhook (`/webhook`)
- Unauthenticated (Meta calls it), but **tenant-resolved**: read `value.metadata.phone_number_id` from the payload and look up the owning organization. If no org matches, drop the event (log + 200). The Celery task receives `organization_id`.

---

## 5. Behavioural Requirements

- **Tokens:** access token TTL ~30 min, refresh TTL ~14 days. Signed with `JWT_SECRET` (new env var) using HS256. Access token claims: `sub` (user_id), `org` (organization_id), `role`, `type=access`, `exp`. Refresh: `sub`, `type=refresh`, `exp`.
- **Active org:** access token is bound to one org. A user in multiple orgs gets a token per org (org chosen at login; default = first/owner org). Switching orgs = re-issue token (out of scope to build a switcher UI; the claim supports it).
- **Isolation:** it must be impossible to read or mutate another org's contacts/campaigns/conversations/messages. Verified by tests.
- **Outbound sends** use the **org's** WhatsApp credentials (fall back to global env only when `MOCK_WHATSAPP=true` for dev). Celery tasks load the org and build a per-org WhatsApp client.
- **Webhook routing:** inbound messages are attributed to the org that owns the receiving `phone_number_id`.
- **Password:** min 8 chars (validated in schema). Never returned in any response. `password_hash` never serialized.

---

## 6. Acceptance Criteria

1. A new user can register → receives tokens → an organization + owner membership exist.
2. Login with correct/incorrect credentials returns 200/401 respectively.
3. All `/contacts`, `/campaigns`, `/conversations` endpoints return 401 without a token.
4. Two orgs with contacts sharing the same phone number coexist; neither can see the other's rows (list, get, patch, delete all scoped).
5. An `agent` cannot create/delete contacts or campaigns (403); an `owner`/`admin` can.
6. Only an `owner` can add/remove members or change roles.
7. A webhook payload with org A's `phone_number_id` creates the inbound message under org A; an unknown `phone_number_id` is dropped without error.
8. A campaign send only targets contacts within the campaign's own org.
9. Alembic migration upgrades and downgrades cleanly.
10. `pytest` passes (existing suites updated for tenancy + new auth/isolation tests green).

---

## 7. Out of Scope (Phase 1)

- API keys for programmatic access (later phase).
- Email-based invite flow / email verification / password reset.
- Encryption-at-rest for stored secrets (tracked follow-up).
- Postgres row-level security (app-layer enforcement is sufficient for now).
- Org-switcher UI; SSO/OAuth.
- Per-seat billing.

---

## 8. Test Plan

- `tests/phase1_auth/test_auth.py` — register, login (good/bad), refresh, `/auth/me`, password not leaked, weak password rejected.
- `tests/phase1_auth/test_tenancy_isolation.py` — two orgs, duplicate phone allowed across orgs, cross-org read/patch/delete → 404, list scoping.
- `tests/phase1_auth/test_rbac.py` — agent blocked from writes; owner-only member management.
- `tests/phase1_auth/test_webhook_routing.py` — payload routed to correct org by `phone_number_id`; unknown id dropped.
- Update `conftest.py`: add `default_org`, `auth_headers`, and make `client` authenticated by default so existing phase 5/6/7 suites keep working; existing direct-model inserts get an `organization_id`.

---

## 9. Implementation Checklist

- [x] Add deps: `passlib[bcrypt]`, `pyjwt`.
- [x] Config: `JWT_SECRET`, `ACCESS_TOKEN_TTL_MIN`, `REFRESH_TOKEN_TTL_DAYS`.
- [x] Models: `Organization`, `User`, `Membership`; add `organization_id` to 4 existing models; constraint changes.
- [x] Security module: password hash/verify, JWT encode/decode.
- [x] Auth dependencies: `get_current_context` (user+org+role), `require_role`.
- [x] Routers: `auth`, `org`; scope `contacts`/`campaigns`/`conversations`.
- [x] WhatsApp client: per-org factory.
- [x] Webhook: tenant resolution by `phone_number_id` (resolved in the Celery task).
- [x] Celery tasks: org-aware inbound + campaign + beat tasks.
- [x] Alembic migration (upgrades + downgrades cleanly).
- [x] Frontend: login/register page, token storage, `Authorization` header in `lib/api.ts`, route guard.
- [x] Tests + conftest updates (88 backend tests passing).
- [x] Code review pass → `REVIEW.md` (0 critical · 3 high · 7 minor; highs fixed).

**Status: complete** — verdict ship-with-fixes; the three High findings (frontend auth, two 500/validation gaps) were fixed. Deferred minors tracked in `REVIEW.md`.
