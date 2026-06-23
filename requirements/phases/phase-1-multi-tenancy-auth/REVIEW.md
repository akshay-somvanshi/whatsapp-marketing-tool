# Phase 1 — Multi-Tenancy & Authentication — Adversarial Review

> **Resolution (applied after review):**
> - **H1 (frontend auth)** — FIXED. Added `lib/auth.ts` (token storage), `Authorization` header + 401→/login handling in `lib/api.ts`, `app/login/page.tsx` (login/register), and `components/AuthGuard.tsx` (route guard + logout) wired into the layout.
> - **H2 (duplicate phone_number_id → 500)** — FIXED. `PATCH /org` now catches `IntegrityError` → 409.
> - **H3 (ai_provider accepts arbitrary strings)** — FIXED. `OrgUpdate` validates `ai_provider ∈ {anthropic, gemini}` (422 otherwise).
> - **M6 (register race → 500)** — FIXED. `register` catches `IntegrityError` → 409.
> - **Deferred (tracked):** M1 (global creds fallback), M2 (member add w/o invite — by design), M3 (no `DELETE /org` endpoint), M4 (cannot null-out a secret), M5/M7 (nits), and the migration-downgrade caveat on real duplicate-phone data. These are noted for a later phase; none are isolation/auth-critical.
> - Post-fix: **88 backend tests pass**; frontend type-checks clean.

**Verdict: ship-with-fixes.** The backend tenant-isolation model is genuinely solid — verified end-to-end at both the app layer and the DB (composite FK) layer — and all 82 tests pass. No confirmed cross-tenant data leak or auth bypass. The fixes below are real but none are isolation/auth-critical except the missing frontend auth wiring (which makes the deployed UI unusable) and a couple of unhandled-500 / validation gaps.

**Findings: 0 Critical · 3 High · 7 Minor.**

---

## 🔴 Critical
None confirmed. Tenant isolation, JWT type separation, RBAC gating, and webhook routing all behave correctly under test.

---

## 🟠 High

### H1 — Frontend auth integration not delivered (checklist item incomplete)
**Files:** `frontend/lib/api.ts`, `frontend/app/` (no `login`/`register` routes).
The implementation checklist calls for "login/register page, token storage, `Authorization` header in `lib/api.ts`." None of these exist: `frontend/lib/api.ts` contains no `Authorization`/`Bearer`/token-storage code, and there are no `login`/`register` pages. Meanwhile every backend scoped endpoint now requires a bearer token (verified: empty/garbage tokens → 401).
**Why it matters:** the shipped frontend can no longer call `/contacts`, `/campaigns`, `/conversations`, or `/org` — every request will 401. The product is non-functional end-to-end despite the backend being correct.
**Fix:** add login/register pages, persist the access + refresh tokens, inject `Authorization: Bearer <access>` in the `lib/api.ts` fetch wrapper, and handle 401→refresh.

### H2 — `PATCH /org` with a duplicate `whatsapp_phone_number_id` returns HTTP 500 (unhandled IntegrityError)
**File:** `backend/app/routers/org.py:56-78` (`update_org`).
*Confirmed by probe.* `whatsapp_phone_number_id` is globally unique. Setting it to a value already owned by another org raises `asyncpg.UniqueViolationError`, which propagates as a 500 with the raw DB error in the response body (Starlette debug). An admin who guesses/knows another org's `phone_number_id` learns it is taken, and the endpoint crashes rather than returning a clean 409.
**Why it matters:** availability + minor info leak; ugly UX; the same applies to `slug` collisions in `register` (`_slugify` appends a random suffix so that's mostly safe, but the org PATCH path is not).
**Fix:** wrap the `commit()` in a try/except on `IntegrityError` and return `409 "phone_number_id already in use"`, or pre-check for an existing org with that `phone_number_id`.

### H3 — `ai_provider` accepts arbitrary strings (no validation)
**Files:** `backend/app/schemas/org.py` (`OrgUpdate.ai_provider: str | None`), `backend/app/routers/org.py:69`.
*Confirmed by probe:* `PATCH /org {"ai_provider": "not_a_real_provider"}` → 200 and persists. Only `"anthropic"` and `"gemini"` are meaningful. At reply time (`ai/handler.py:90-99`) an invalid provider silently falls through to "whichever key exists" — so AI behaviour diverges from the configured intent with no error.
**Why it matters:** silent misconfiguration; a tenant thinks they selected a provider that is being ignored.
**Fix:** validate `ai_provider` against `{"anthropic","gemini"}` in the schema (Literal/enum) and reject otherwise.

---

## 🟡 Minor / Nits

### M1 — `client_for_org` live-mode fallback can send from one org's number with the global env token
**File:** `backend/app/whatsapp/client.py:171-177`.
In live mode, if an org has `whatsapp_phone_number_id` set but `whatsapp_api_token` NULL (or vice-versa), the client falls back to `settings.WHATSAPP_API_TOKEN` / `settings.WHATSAPP_PHONE_NUMBER_ID`. This can mismatch a tenant's `phone_number_id` against the global token, or send a tenant's traffic on the global dev number. It will not leak across tenants (each call is built per-org) but will fail or misattribute at Meta.
**Fix:** in live mode, if an org lacks complete WhatsApp creds, raise/skip rather than silently using global env values; log a clear error.

### M2 — `add_member` silently links an existing user from another org without consent
**File:** `backend/app/routers/org.py:106-149`.
*Confirmed by probe:* an owner can add any existing user's email (e.g. another org's owner) as a member of their own org; returns 201. This matches the requirement ("links existing"), and it only grants that user access to the *adder's* org (no cross-org leak), so it is by-design — but it is an unexpected "add anyone by email" with no invite/accept step. Acceptable for Phase 1 (invite flow is out of scope), flagged so it is a conscious choice.

### M3 — No `DELETE /org` endpoint though the permission table lists "Delete organization (owner)"
**File:** `backend/app/routers/org.py`.
Section 3's permission matrix includes "Delete organization — owner", but the API contract (Section 4) does not list a delete endpoint and none is implemented. Inconsistency between matrix and contract; not a blocker.
**Fix:** either drop the matrix row for Phase 1 or add `DELETE /org` (owner-only).

### M4 — `update_org` cannot clear a secret/field back to empty
**File:** `backend/app/routers/org.py:73-75`.
The loop skips any field whose value `is None`, so a client can never null-out a stored token/key/system_prompt via PATCH (sending `null` is treated as "no change"). Sending `""` would store an empty string instead. Minor functional gap — there is no way to *unset* a credential.

### M5 — `_handle_inbound_message` reconstructs `+` prefix naively
**File:** `backend/app/tasks/celery_app.py:135-136`.
`phone = f"+{raw_phone}"` assumes Meta always sends a bare international number. If `from` is empty the contact phone becomes `"+"`; guarded only loosely by the later `if not phone or not body`. Edge-case robustness, not isolation.

### M6 — `register` is not atomic against a concurrent duplicate email
**File:** `backend/app/routers/auth.py:65-86`.
The `SELECT ... WHERE email` check then `INSERT` is a check-then-act race; two simultaneous registrations of the same email would have one fail on the DB unique constraint as a 500 rather than a clean 409. Low likelihood; `users.email` unique constraint prevents actual duplication. Consider catching `IntegrityError`.

### M7 — `decode_token` does not pin claim presence for refresh `org`/`role`
**File:** `backend/app/security.py:63-73`, `routers/auth.py:114-139`.
Refresh tokens correctly omit `org`/`role` (verified: payload is `{sub, type:refresh, iat, exp}`), and refresh re-derives org/role from the live earliest membership — good. No bug; noting that role/org are always re-read from DB on refresh and on every request (`dependencies.py:46-64`), so revocation/role-change take effect immediately. This is a strength, listed here only for completeness.

---

## What's solid / verified

- **DB-level tenant isolation is real.** Composite FK `(organization_id, contact_phone) → contacts(organization_id, phone)` was probed directly: an orphan message and a message referencing a contact that exists only in *another* org are both rejected with `IntegrityError`. Isolation does not rely solely on app-layer `WHERE` clauses.
- **App-layer scoping is complete.** Every read/update/delete in `contacts.py`, `campaigns.py`, `conversations.py` filters by `ctx.organization_id`; cross-org GET/PATCH/DELETE return 404 (verified). Celery tasks (`_handle_status_update`, `_handle_inbound_message`, `_send_ai_reply`, campaign fanout, post-purchase) all scope by `org.id`/`contact.organization_id`. The post-purchase "already sent" check and campaign contact query are correctly org-scoped.
- **Auth correctness.** Access vs refresh `type` is enforced in `decode_token`; an access token is rejected at `/auth/refresh` (verified test + probe). Empty `Authorization` header and garbage tokens both yield **401** (verified), malformed claims → 401, unknown-org membership → 403 (not a member). User re-loaded and `is_active`-checked on every request.
- **RBAC matches the matrix.** Agent blocked from contact/campaign writes (403); admin/owner allowed; member management is owner-only; `owner` role cannot be assigned via API (422); owner cannot be removed or have role changed; a user cannot change/remove themselves.
- **Webhook routing.** Resolution by `phone_number_id` via the unique column; missing metadata and unknown ids are dropped with a log and no error/no write (verified). `phone_number_id` uniqueness makes "multiple orgs" impossible at the DB level.
- **Migration round-trips cleanly (AC #9).** Verified live: `downgrade -1` restores the exact original auto-generated constraint names (`contacts_phone_key`, `conversations_contact_phone_key`, `conversations_contact_phone_fkey`, `messages_contact_phone_fkey`), then `upgrade head` re-applies. Backfill into a single default org is correct and non-destructive. **Caveat:** the downgrade re-creates a *global* unique on `contacts.phone`; if real multi-tenant data with duplicate phones exists, the downgrade would fail at that step (expected — downgrade is destructive of the multi-tenant invariant). Worth a one-line note in the migration.
- **Secret masking.** `/org` GET/PATCH return only `*_set` booleans via `_org_out`; raw `whatsapp_api_token`/`anthropic_api_key`/`gemini_api_key` are never serialized. `password_hash` never appears in any schema (`UserOut`, `MemberOut` verified). `/auth/me` confirmed to omit password fields.
- **Tests are mostly meaningful, not rubber-stamps.** Isolation tests use two real orgs with the same phone; RBAC tests exercise actual role tokens; the webhook tests drive the real async pipeline and assert org attribution + that unknown ids write nothing. `test_protected_endpoints_require_auth` genuinely hits the 401 path (verified the empty header is not silently dropped). 82/82 pass.

## Acceptance criteria status

| # | Criterion | Status |
|---|-----------|--------|
| 1 | Register → tokens + org + owner membership | ✅ Met |
| 2 | Login 200/401 | ✅ Met |
| 3 | Scoped endpoints 401 without token | ✅ Met (verified incl. empty header) |
| 4 | Two orgs, duplicate phone, full scoping | ✅ Met (list/get/patch/delete all scoped; DB FK reinforces) |
| 5 | Agent blocked from writes; owner/admin allowed | ✅ Met |
| 6 | Owner-only member management | ✅ Met |
| 7 | Webhook routed to owning org; unknown id dropped | ✅ Met |
| 8 | Campaign send targets only own-org contacts | ✅ Met |
| 9 | Migration up/down clean | ✅ Met (verified live round-trip) |
| 10 | pytest passes | ✅ Met (82 passed) |

Backend acceptance criteria are all met. The frontend implementation-checklist items (H1) are **not** delivered — the deployed UI cannot authenticate against the now-protected API.

## Test-coverage gaps worth adding (not blockers)
- No test asserts `PATCH /org` returns a clean error on duplicate `phone_number_id` (currently 500 — see H2).
- No test that a campaign send/inbound for one org never writes a Message under another org (DB FK covers it, but an explicit task-level isolation test would harden it).
- No test that `/org` and `/org/members` 401 without a token (only the read endpoints in `test_protected_endpoints_require_auth` cover `/org`; member-management auth is untested for the no-token case).
- No negative test for `ai_provider` validation (see H3).
