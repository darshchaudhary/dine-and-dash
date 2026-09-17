from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .database import engine, get_session
from .models import Account, Base, UserProfile
from .auth import current_account, router as auth_router
from .security import BodyLimitMiddleware
from .meals import router as meals_router
from . import planning
from .nutrislice import all_halls, get_menu, meal_for_time
from .recommendations import recommend
from .schemas import (
    DiningHall,
    MenuResponse,
    Profile,
    ProfileUpsert,
    RecommendationRequest,
    RecommendationResponse,
)


settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield
    finally:
        await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Personalized Georgia Tech dining-hall plate recommendations backed by Nutrislice.",
    lifespan=lifespan,
)
allowed_origins = list({settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173", "capacitor://localhost"})


@app.middleware("http")
async def protect_requests(request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.url.path.startswith("/api/"):
        # Custom headers require a successful CORS preflight in browsers. Never
        # trust a client-supplied user ID or accept cookie mutations from any origin.
        origin = request.headers.get("origin")
        if (origin and origin not in allowed_origins) or request.headers.get("x-dinedash-client") not in {"web", "native"}:
            return JSONResponse({"detail": "Request origin not allowed."}, status_code=403)
    response = await call_next(request)
    if request.url.path.startswith(("/api/auth", "/api/profiles", "/api/recommendations", "/api/meals")):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    # FastAPI's default validation output includes submitted password values.
    return JSONResponse({"detail": [{"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()]}, status_code=422)


app.include_router(auth_router)
app.include_router(meals_router)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
async def readiness(session: AsyncSession = Depends(get_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable") from exc
    return {"status": "ok", "database": "ok"}


@app.get("/api/dining-halls", response_model=list[DiningHall])
async def dining_halls(at: datetime | None = Query(default=None)) -> list[DiningHall]:
    return all_halls(at)


@app.get("/api/profiles/{user_id}", response_model=Profile)
async def get_profile(user_id: str, account: Account = Depends(current_account), session: AsyncSession = Depends(get_session)) -> UserProfile:
    if user_id != account.id:
        raise HTTPException(403, "This profile belongs to another account.")
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Profile not found")
    return profile


@app.put("/api/profiles/{user_id}", response_model=Profile)
async def upsert_profile(
    user_id: str,
    payload: ProfileUpsert,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> UserProfile:
    if user_id != account.id:
        raise HTTPException(403, "This profile belongs to another account.")
    profile = await session.get(UserProfile, user_id)
    if profile is None:
        profile = UserProfile(user_id=user_id, **payload.model_dump())
        session.add(profile)
    else:
        for key, value in payload.model_dump().items():
            setattr(profile, key, value)
    await session.commit()
    await session.refresh(profile)
    return profile


@app.get("/api/menu", response_model=MenuResponse)
async def menu(
    hall_slug: str,
    at: datetime | None = Query(default=None),
    meal: str | None = Query(default=None),
) -> MenuResponse:
    try:
        return await get_menu(hall_slug, at, meal)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/recommendations", response_model=RecommendationResponse)
async def recommendations(
    payload: RecommendationRequest,
    account: Account = Depends(current_account),
    session: AsyncSession = Depends(get_session),
) -> RecommendationResponse:
    if payload.user_id != account.id:
        raise HTTPException(403, "This profile belongs to another account.")
    profile = await session.get(UserProfile, payload.user_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Complete setup before requesting a plate")
    at = planning.now()
    planning.open_hall(payload.hall_slug, at)
    consumed = await planning.consumed_today(session, account.id, at)
    meal = meal_for_time(at, payload.hall_slug)
    target = planning.remaining_target(profile.daily_calorie_goal, consumed, meal)
    # Never accept an old/future timestamp or target to bypass closing hours or
    # today's consumption. Alternatives are recomputed from the current service.
    payload = payload.model_copy(update={"at": at, "meal": meal, "meal_calorie_target": target})
    try:
        result = await recommend(profile, payload)
        result.consumed_today_calories = round(consumed, 2)
        result.remaining_today_calories = round(max(0, profile.daily_calorie_goal - consumed), 2)
        result.planning_note = f"{round(consumed)} kcal logged today; {round(result.remaining_today_calories)} kcal remaining toward your saved goal. The meal target reserves calories for later services."
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
