export type Account = { id: string; email: string };

export type EatenItem = { id: string; name: string; portion_label: string; calories: number };
export type MealRecord = {
  id: string; consumed_at: string; hall_slug: string; hall_name: string;
  meal: string; items: EatenItem[]; calories: number; voided: boolean;
};
export type MealHistory = {
  timezone: string; start: string; total_calories: number;
  days: { date: string; calories: number }[]; meals: MealRecord[];
};
export type MenuFood = {
  id: string; name: string; station: string; serving_amount: number; serving_unit: string;
  nutrition: Nutrition; nutrition_complete: boolean; allergens: string[];
};
export type CurrentMenu = { hall: Hall; date: string; meal: string; items: MenuFood[]; match_count: number; note: string };
export type MenuMealInput = { id: string; hall_slug: string; menu_date: string; meal: string; items: { food_id: string; servings: number }[] };
export type PastMealContext = { local_time: string; meal: "breakfast" | "lunch" | "dinner" };
export type PastMealInput = MenuMealInput & { local_time: string };

export type Nutrition = {
  calories: number;
  protein_g: number;
  carbs_g: number;
  fat_g: number;
  fiber_g: number;
  sodium_mg: number;
};

export type Profile = {
  user_id?: string;
  name: string;
  goal: "lose" | "maintain" | "gain" | "balanced";
  daily_calorie_goal: number;
  protein_goal_g: number;
  carb_goal_g: number;
  fat_goal_g: number;
  fiber_goal_g: number;
  sodium_limit_mg: number;
  meals_per_day: number;
  allergies: string[];
  dietary_preferences: string[];
};

export type Hall = {
  id: number;
  slug: string;
  name: string;
  short_name: string;
  hours: string;
  open_now: boolean;
  available_meals: string[];
};

export type PlateItem = {
  id: string;
  name: string;
  station: string;
  category: string;
  serving_amount: number;
  serving_unit: string;
  servings: number;
  portion_label: string;
  nutrition: Nutrition;
  line_nutrition: Nutrition;
  allergens: string[];
  dietary_tags: string[];
  why: string;
};

export type Recommendation = {
  hall: Hall;
  date: string;
  meal: string;
  target_calories: number;
  plate: PlateItem[];
  progress: { target: Nutrition; total: Nutrition; calorie_match_percent: number };
  excluded_for_allergies: number;
  excluded_for_diet: number;
  data_source: "nutrislice" | "demo";
  generated_at: string;
  safety_message: string;
  note?: string;
  consumed_today_calories?: number;
  remaining_today_calories?: number;
  planning_note?: string;
};
