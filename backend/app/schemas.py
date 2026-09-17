from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


Goal = Literal["lose", "maintain", "gain", "balanced"]


class ProfileUpsert(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    goal: Goal = "balanced"
    daily_calorie_goal: int = Field(ge=1000, le=6000)
    protein_goal_g: int = Field(ge=20, le=400)
    carb_goal_g: int = Field(ge=40, le=800)
    fat_goal_g: int = Field(ge=20, le=250)
    fiber_goal_g: int = Field(ge=10, le=100)
    sodium_limit_mg: int = Field(ge=500, le=10000)
    meals_per_day: int = Field(ge=2, le=6)
    allergies: list[str] = []
    dietary_preferences: list[str] = []

    @field_validator("allergies", "dietary_preferences")
    @classmethod
    def normalize_list(cls, values: list[str]) -> list[str]:
        return sorted({value.strip().lower() for value in values if value.strip()})


class Profile(ProfileUpsert):
    model_config = ConfigDict(from_attributes=True)

    user_id: str
    created_at: datetime
    updated_at: datetime


class MenuNutrition(BaseModel):
    calories: float = 0
    protein_g: float = 0
    carbs_g: float = 0
    fat_g: float = 0
    fiber_g: float = 0
    sodium_mg: float = 0


class MenuFood(BaseModel):
    id: str
    name: str
    station: str
    category: str
    serving_amount: float = 1
    serving_unit: str = "serving"
    nutrition: MenuNutrition
    allergens: list[str] = []
    dietary_tags: list[str] = []
    ingredients: str = ""
    nutrition_complete: bool = True


class DiningHall(BaseModel):
    id: int
    slug: str
    name: str
    short_name: str
    hours: str
    open_now: bool
    available_meals: list[str]


class MenuResponse(BaseModel):
    hall: DiningHall
    date: date
    meal: str
    items: list[MenuFood]
    unavailable_nutrition_count: int = 0
    source: Literal["nutrislice", "demo"]
    fetched_at: datetime
    note: str | None = None


class RecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    hall_slug: str
    at: datetime | None = None
    meal: str | None = None
    meal_calorie_target: int | None = Field(default=None, ge=1, le=2500)
    excluded_item_ids: list[str] = Field(default_factory=list, max_length=100)


class PlateItem(MenuFood):
    servings: float
    portion_label: str
    line_nutrition: MenuNutrition
    why: str


class GoalProgress(BaseModel):
    target: MenuNutrition
    total: MenuNutrition
    calorie_match_percent: int


class RecommendationResponse(BaseModel):
    hall: DiningHall
    date: date
    meal: str
    target_calories: int
    plate: list[PlateItem]
    progress: GoalProgress
    excluded_for_allergies: int
    excluded_for_diet: int
    data_source: Literal["nutrislice", "demo"]
    generated_at: datetime
    safety_message: str
    note: str | None = None
    consumed_today_calories: float = 0
    remaining_today_calories: float | None = None
    planning_note: str | None = None
