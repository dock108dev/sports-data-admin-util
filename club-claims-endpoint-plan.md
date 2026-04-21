# Plan: `POST /api/onboarding/club-claims` (sports-data-admin)

## Context

The frontend (`masters-pool-web`) just gained an onboarding subdomain with a **"Claim your club"** form (`OnboardHomePage.tsx`). The frontend's `HttpApiClient.submitClubClaim()` posts to `/api/onboarding/club-claims`, but that endpoint does not exist yet — the method is a TODO. Today the form only works against the mock client.

We need the backend to:

1. Accept the claim payload, persist it (so we can review and respond), and return `{ claim_id, received_at }`.
2. Notify us when a claim comes in (email).
3. Be **publicly reachable** — no `X-API-Key` — because this is a prospect-facing form submitted by people who don't have credentials yet. Must be rate-limited to avoid abuse.

Repo layout: FastAPI + SQLAlchemy (async) + Alembic. Pattern established by `pools.py`, email via `app/services/email.py`, public routes registered without `auth_dependency` (like `auth.router` and `preferences.router`).

## Approach

### 1. ORM model

**New:** `api/app/db/onboarding.py`

```python
class ClubClaim(Base):
    __tablename__ = "club_claims"
    id: Mapped[int] = mapped_column(primary_key=True)
    claim_id: Mapped[str] = mapped_column(String(32), unique=True, index=True)  # short public id
    club_name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(320), index=True)
    expected_entries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | contacted | closed
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    source_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
```

`claim_id` is a short public identifier (e.g. `claim_<base32 6 chars>`) — do **not** expose the internal `id`. Generate with `secrets.token_urlsafe(6)` prefixed.

Export `ClubClaim` from `api/app/db/__init__.py` so Alembic autogenerate sees it.

### 2. Alembic migration

**New:** `api/alembic/versions/20260421_000057_add_club_claims_table.py`

- Revises: `20260420_000056` (the current head).
- Creates `club_claims` table with columns above.
- Indexes: `ix_club_claims_claim_id` (unique), `ix_club_claims_contact_email`, `ix_club_claims_received_at`.
- Downgrade drops the table.

Generate locally with `alembic revision --autogenerate -m "add club claims table"`, then eyeball the output — autogenerate is good but not perfect with server defaults.

### 3. Pydantic schemas + handler

**New:** `api/app/routers/onboarding.py`

```python
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])

class ClubClaimRequest(BaseModel):
    club_name: str = Field(min_length=1, max_length=200)
    contact_email: EmailStr
    expected_entries: int | None = Field(default=None, ge=1, le=100_000)
    notes: str = Field(default="", max_length=2000)

class ClubClaimResponse(BaseModel):
    claim_id: str
    received_at: datetime

@router.post("/club-claims", response_model=ClubClaimResponse, status_code=201)
async def submit_club_claim(
    req: ClubClaimRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> ClubClaimResponse:
    claim = ClubClaim(
        claim_id=f"claim_{secrets.token_urlsafe(6)}",
        club_name=req.club_name.strip(),
        contact_email=req.contact_email.lower(),
        expected_entries=req.expected_entries,
        notes=req.notes.strip(),
        source_ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] or None,
    )
    db.add(claim)
    await db.flush()
    await db.commit()

    # Fire-and-forget notification — never fail the request on email error.
    try:
        await _notify_claim(claim)
    except Exception:
        logger.exception("club_claim_notification_failed", extra={"claim_id": claim.claim_id})

    return ClubClaimResponse(claim_id=claim.claim_id, received_at=claim.received_at)
```

`_notify_claim` wraps `app.services.email.send_email` — `to=settings.onboarding_notification_email`, subject `"[Club Claim] {club_name}"`, HTML body with the four form fields + source IP. If `settings.onboarding_notification_email` is unset, skip email and just rely on the structured log line (the existing `send_email` already logs when no provider is configured; the explicit skip avoids a bogus log about missing providers).

### 4. Config

**Modify:** `api/app/config.py`

Add one setting:

```python
onboarding_notification_email: str | None = None  # where to send new club claim alerts
```

No new provider credentials — reuse whatever `RESEND_API_KEY` / SMTP config already exists.

### 5. Router registration + rate limit

**Modify:** `api/main.py` (around line 210, next to `auth.router` and `preferences.router`).

```python
from app.routers import onboarding
...
app.include_router(onboarding.router)  # PUBLIC — no auth_dependency
```

Rate limit: the existing rate-limiting middleware is per-IP. Add a per-route limit for this endpoint (e.g. **5 requests / hour / IP**) so a bot can't flood `club_claims`. If the middleware doesn't support per-route config, use `slowapi`'s `@limiter.limit("5/hour")` decorator on the handler (already a dependency — check `api/app/middleware/` for the existing limiter instance).

### 6. Tests

**New:** `api/tests/test_onboarding_api.py`

Cover:

- **Happy path:** POST with valid payload → 201, response has `claim_id` matching `^claim_[\w-]{8}$`, row persisted in DB with all fields.
- **Trims + lowercases:** whitespace in `club_name`, uppercase email → stored trimmed/lowercased.
- **Validation:** missing `club_name` → 422; invalid email → 422; negative `expected_entries` → 422; `notes` over 2000 chars → 422.
- **No API key required:** POST without `X-API-Key` header → 201 (not 401). This is the key regression we're guarding against.
- **Email failure is non-fatal:** mock `send_email` to raise → request still returns 201 and the DB row is written.
- **IP + UA captured:** set `X-Forwarded-For` / `User-Agent` → stored on the row.
- **Rate limit:** 6th request from same IP within an hour → 429.

Use `AsyncMock` for `send_email`; follow pattern in existing `test_golf_pools_api.py`. Coverage threshold is 80% so make sure every branch of the new handler is hit.

### 7. Deploy checklist

- **Migration runs automatically** on deploy via `docker compose --profile prod run --rm migrate` (CI line ~440). No manual step needed.
- **Env var to set** on the host before shipping: `ONBOARDING_NOTIFICATION_EMAIL=mike@…` (otherwise email is silently skipped).
- **Frontend switch-over**: once the endpoint is live, the frontend's `HttpApiClient.submitClubClaim` TODO comment can be removed. No endpoint-path change — the frontend already points at `/api/onboarding/club-claims`.

## Critical files

**New**
- `api/app/db/onboarding.py`
- `api/app/routers/onboarding.py`
- `api/alembic/versions/20260421_000057_add_club_claims_table.py`
- `api/tests/test_onboarding_api.py`

**Modify**
- `api/main.py` — include `onboarding.router` publicly (alongside `auth.router`, `preferences.router`)
- `api/app/config.py` — add `onboarding_notification_email`
- `api/app/db/__init__.py` — export `ClubClaim` so Alembic sees it

## Reused utilities

- `send_email` at `api/app/services/email.py:58` — no new email plumbing.
- `verify_api_key` pattern in `api/app/dependencies/auth.py` — we deliberately **don't** use it here; the omission mirrors `auth.router` at `main.py:210`.
- Handler/schema pattern mirrors `api/app/routers/golf/pools.py` `POST /pools/{pool_id}/entries` (pools.py:311–365).
- Alembic naming mirrors `20260420_000056_game_phase_server_default.py`.

## Verification

1. **Local**: `alembic upgrade head` → schema present; `pytest tests/test_onboarding_api.py -v --cov=app.routers.onboarding` → 100% branch coverage on the new router; full suite still ≥ 80%.
2. **Curl against local API:**
   ```bash
   curl -i -X POST http://localhost:8000/api/onboarding/club-claims \
     -H 'Content-Type: application/json' \
     -d '{"club_name":"Pine Valley GC","contact_email":"pro@pv.example","expected_entries":40,"notes":"for Masters 2027"}'
   ```
   Expect `201` + `{"claim_id":"claim_...","received_at":"..."}`. No `X-API-Key` header.
3. **End-to-end with frontend**: run the frontend against the real backend (`VITE_API_BASE_URL` → local API), submit the onboard claim form at `onboard.localhost:5173`, confirm the row lands in `club_claims` and the notification email arrives (or appears in logs if no email provider is configured).
4. **Negative**: same curl with a malformed email → `422` with Pydantic detail. 6th curl from same IP within an hour → `429`.
5. **Prod smoke test after deploy**: hit `https://sda.dock108.dev/api/onboarding/club-claims` once with a real payload, verify it reaches the notification inbox, mark the row as `status='closed'` in SQL.
