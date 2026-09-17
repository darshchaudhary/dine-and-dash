"""Opaque, revocable sessions. Only token digests are persisted in PostgreSQL."""
import asyncio
import hashlib
import secrets
import time
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator
from pwdlib import PasswordHash
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from .config import get_settings
from .database import get_session
from .models import Account, AuthRateBucket, AuthSession

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
passwords = PasswordHash.recommended()
dummy_hash = passwords.hash(secrets.token_urlsafe(32))
hash_slots = asyncio.Semaphore(2)
COOKIE = "dinedash_session"


class Credentials(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: SecretStr

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value):
        return value.lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, value):
        if not 15 <= len(value.get_secret_value()) <= 128:
            raise ValueError("Use a password between 15 and 128 characters.")
        return value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth:
        scheme, _, token = auth.partition(" ")
        return token if scheme.lower() == "bearer" and 20 <= len(token) <= 128 else None
    return request.cookies.get(COOKIE)


async def current_account(request: Request, db: AsyncSession = Depends(get_session)) -> Account:
    token = session_token(request)
    if not token or len(token) > 128:
        raise HTTPException(401, "Please sign in.")
    account = await db.scalar(select(Account).join(AuthSession).where(
        AuthSession.token_hash == digest(token), AuthSession.expires_at > datetime.now(timezone.utc)
    ))
    if not account:
        raise HTTPException(401, "Your session expired. Please sign in again.")
    return account


async def throttle(db: AsyncSession, category: str, identifier: str, limit: int, seconds: int):
    now = datetime.now(timezone.utc)
    window = int(time.time()) // seconds
    key = f"{category}:{digest(identifier)}:{window}"
    insert = pg_insert if db.bind.dialect.name == "postgresql" else sqlite_insert
    stmt = insert(AuthRateBucket).values(key=key, count=1, expires_at=now + timedelta(seconds=seconds * 2))
    stmt = stmt.on_conflict_do_update(index_elements=[AuthRateBucket.key], set_={"count": AuthRateBucket.count + 1}).returning(AuthRateBucket.count)
    count = (await db.execute(stmt)).scalar_one()
    await db.execute(delete(AuthRateBucket).where(AuthRateBucket.expires_at < now))
    await db.commit()
    if count > limit:
        raise HTTPException(429, "Too many attempts. Please try again later.", headers={"Retry-After": str(seconds)})


async def issue_session(account: Account, request: Request, response: Response, db: AsyncSession):
    now = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    expires = now + timedelta(days=get_settings().session_days)
    # A new login replaces the session presented by this client, not other devices.
    old = session_token(request)
    if old:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(old)))
    await db.execute(delete(AuthSession).where(AuthSession.expires_at <= now))
    db.add(AuthSession(token_hash=digest(token), account_id=account.id, expires_at=expires))
    await db.commit()
    result = {"user": {"id": account.id, "email": account.email}, "expires_at": expires}
    if request.headers.get("x-dinedash-client") == "native":
        result["access_token"] = token
    else:
        response.set_cookie(COOKIE, token, max_age=get_settings().session_days * 86400,
                            httponly=True, secure=get_settings().cookie_secure,
                            samesite="none" if get_settings().cookie_secure else "lax", path="/api")
    return result


@router.post("/register", status_code=201)
async def register(data: Credentials, request: Request, response: Response, db: AsyncSession = Depends(get_session)):
    await throttle(db, "register", request.client.host if request.client else "unknown", 10, 3600)
    async with hash_slots:
        hashed = await run_in_threadpool(passwords.hash, data.password.get_secret_value())
    account = Account(id=str(uuid4()), email=str(data.email), password_hash=hashed)
    db.add(account)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(400, "Unable to register this email. Try signing in instead.")
    return await issue_session(account, request, response, db)


@router.post("/login")
async def login(data: Credentials, request: Request, response: Response, db: AsyncSession = Depends(get_session)):
    await throttle(db, "login-ip", request.client.host if request.client else "unknown", 60, 900)
    await throttle(db, "login-email", str(data.email), 10, 900)
    account = await db.scalar(select(Account).where(Account.email == str(data.email)))
    async with hash_slots:
        valid = await run_in_threadpool(passwords.verify, data.password.get_secret_value(), account.password_hash if account else dummy_hash)
    if not account or not valid:
        raise HTTPException(401, "Email or password is incorrect.")
    return await issue_session(account, request, response, db)


@router.get("/me")
async def me(account: Account = Depends(current_account)):
    return {"id": account.id, "email": account.email}


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_session)):
    token = session_token(request)
    if token:
        await db.execute(delete(AuthSession).where(AuthSession.token_hash == digest(token)))
        await db.commit()
    response.delete_cookie(COOKIE, path="/api", secure=get_settings().cookie_secure,
                           httponly=True, samesite="none" if get_settings().cookie_secure else "lax")
