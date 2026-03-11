"""Authentication endpoints for downstream consuming applications.

POST /auth/signup — create a new user account, returns JWT
POST /auth/login  — authenticate with email/password, returns JWT
GET  /auth/me     — return current caller identity & role
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db
from app.db.users import User
from app.dependencies.roles import create_access_token, resolve_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class SignupRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., min_length=8, description="Password (min 8 characters)")


class LoginRequest(BaseModel):
    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer")
    role: str = Field(..., description="User role")


class MeResponse(BaseModel):
    id: int | None = Field(None, description="User ID (null for guests)")
    email: str | None = Field(None, description="User email (null for guests)")
    role: str = Field(..., description="Current role: guest, user, or admin")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post(
    "/signup",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new user account",
)
async def signup(
    body: SignupRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    # Check for existing email
    existing = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    user = User(
        email=body.email.lower(),
        password_hash=_pwd_ctx.hash(body.password),
        role="user",
        is_active=True,
    )
    db.add(user)
    await db.flush()  # populate user.id

    token = create_access_token(user.id, user.role)
    logger.info("user_signup", extra={"user_id": user.id, "email": user.email})

    return TokenResponse(access_token=token, role=user.role)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate and receive a JWT",
)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(
        select(User).where(User.email == body.email.lower())
    )
    user = result.scalar_one_or_none()

    if user is None or not _pwd_ctx.verify(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    token = create_access_token(user.id, user.role)
    logger.info("user_login", extra={"user_id": user.id, "email": user.email})

    return TokenResponse(access_token=token, role=user.role)


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Get current user identity",
    description=(
        "Returns the caller's identity and role. Guests (no token) "
        "receive ``{role: 'guest'}``. Authenticated callers receive "
        "their user ID, email, and role."
    ),
)
async def me(
    request: Request,
    role: str = Depends(resolve_role),
    db: AsyncSession = Depends(get_db),
) -> MeResponse:
    if role == "guest":
        return MeResponse(role="guest")

    user_id: int | None = getattr(request.state, "user_id", None)
    if user_id is None:
        return MeResponse(role=role)

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return MeResponse(role=role)

    return MeResponse(id=user.id, email=user.email, role=user.role)
