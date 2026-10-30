from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import JSON


class Base(DeclarativeBase):
    pass


json_type = JSON().with_variant(JSONB, "postgresql")


class Account(Base):
    __tablename__ = "accounts"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class AuthRateBucket(Base):
    __tablename__ = "auth_rate_buckets"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    count: Mapped[int] = mapped_column(Integer)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class UserProfile(Base):
    __tablename__ = "user_profiles"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    goal: Mapped[str] = mapped_column(String(32), default="balanced")
    daily_calorie_goal: Mapped[int] = mapped_column(Integer, default=2200)
    protein_goal_g: Mapped[int] = mapped_column(Integer, default=120)
    carb_goal_g: Mapped[int] = mapped_column(Integer, default=250)
    fat_goal_g: Mapped[int] = mapped_column(Integer, default=70)
    fiber_goal_g: Mapped[int] = mapped_column(Integer, default=30)
    sodium_limit_mg: Mapped[int] = mapped_column(Integer, default=2300)
    meals_per_day: Mapped[int] = mapped_column(Integer, default=3)
    allergies: Mapped[list[str]] = mapped_column(json_type, default=list)
    dietary_preferences: Mapped[list[str]] = mapped_column(json_type, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MealLog(Base):
    __tablename__ = "meal_logs"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    consumed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    hall_slug: Mapped[str] = mapped_column(String(80))
    hall_name: Mapped[str] = mapped_column(String(120))
    meal: Mapped[str] = mapped_column(String(32))
    items: Mapped[list[dict]] = mapped_column(json_type)
    calories: Mapped[float] = mapped_column(Float)
    voided: Mapped[bool] = mapped_column(Boolean, default=False)


class PlannerSettings(Base):
    """Separate table keeps upgrades additive for existing installations."""
    __tablename__ = "planner_settings"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    settings: Mapped[dict] = mapped_column(json_type, default=dict)


class FoodPreference(Base):
    __tablename__ = "food_preferences"
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), primary_key=True)
    food_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    rating: Mapped[int] = mapped_column(Integer)
