import type { Account, CurrentMenu, Hall, MealHistory, MealRecord, MenuMealInput, PastMealContext, PastMealInput, Profile, Recommendation } from "./types";
import { authHeaders, clearSession, native, storeSession } from "./auth";

function resolveApiUrl() {
  if (import.meta.env.VITE_API_URL) return import.meta.env.VITE_API_URL.replace(/\/$/, "");

  // A bundled Capacitor app is served from capacitor://localhost. The iOS
  // Simulator can reach services on the Mac over loopback. Physical-device
  // builds inject the Mac's Wi-Fi address through the ios:device script.
  if (window.location.protocol === "capacitor:") return "http://127.0.0.1:8000";

  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

const API_URL = resolveApiUrl();

export class ApiError extends Error {
  constructor(message: string, public status: number) { super(message); }
}

async function request(path: string, options: RequestInit = {}, authAction = false) {
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...options, credentials: native ? "omit" : "include",
      signal: AbortSignal.timeout(25000),
      headers: { "Content-Type": "application/json", ...authHeaders(), ...options.headers },
    });
  } catch {
    throw new Error("Couldn’t reach Dine&Dash. Check your connection and try again.");
  }
  if (!response.ok) {
    if (response.status === 401 && !authAction) {
      await clearSession();
      window.dispatchEvent(new Event("dinedash:signed-out"));
    }
    const body = await response.json().catch(() => ({}));
    const message = typeof body.detail === "string" ? body.detail : body.detail?.[0]?.msg || "Something went wrong. Please try again.";
    throw new ApiError(message, response.status);
  }
  return response.status === 204 ? null : response.json();
}

export async function authenticate(mode: "login" | "register", email: string, password: string): Promise<Account> {
  const result = await request(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify({ email: email.trim(), password }) }, true);
  await storeSession(result.access_token);
  return result.user;
}
export async function getAccount(): Promise<Account | null> {
  try { return await request("/api/auth/me", {}, true); }
  catch (error) {
    if (error instanceof ApiError && error.status === 401) { await clearSession(); return null; }
    throw error;
  }
}
export async function logout() {
  await request("/api/auth/logout", { method: "POST" }, true);
  await clearSession();
}

const easternNow = new Date(new Date().toLocaleString("en-US", { timeZone: "America/New_York" }));
const easternDay = easternNow.getDay();
const easternHour = easternNow.getHours() + easternNow.getMinutes() / 60;
const weekend = easternDay === 0 || easternDay === 6;

export const HALLS: Hall[] = [
  { id: 40536, slug: "brittain", name: "Brittain Dining Hall", short_name: "Brittain", hours: "Mon–Fri · 11 AM–10 PM", open_now: !weekend && easternHour >= 11 && easternHour < 22, available_meals: ["lunch", "dinner"] },
  { id: 40132, slug: "north-ave-dining-hall", name: "North Ave Dining Hall", short_name: "North Ave", hours: "Weekdays 7 AM–10 PM", open_now: easternHour >= (weekend ? 9 : 7) && easternHour < (weekend ? 21 : 22), available_meals: ["breakfast", "lunch", "dinner", "overnight"] },
  { id: 40126, slug: "west-village", name: "West Village", short_name: "West Village", hours: "Weekdays 7 AM–10 PM", open_now: easternHour >= (weekend ? 9 : 7) && easternHour < (weekend ? 21 : 22), available_meals: ["breakfast", "lunch", "dinner"] },
];

export async function getProfile(userId: string): Promise<Profile | null> {
  try {
    return await request(`/api/profiles/${encodeURIComponent(userId)}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

export async function saveProfile(userId: string, profile: Profile): Promise<Profile> {
  return request(`/api/profiles/${encodeURIComponent(userId)}`, { method: "PUT", body: JSON.stringify(profile) });
}

export async function fetchHalls(): Promise<Hall[]> {
  try {
    const response = await fetch(`${API_URL}/api/dining-halls`);
    if (!response.ok) throw new Error();
    return response.json();
  } catch {
    throw new Error("Could not verify dining hall hours. Check your connection and refresh.");
  }
}

export async function getRecommendation(userId: string, hallSlug: string, profile: Profile, alternatives?: { excluded_item_ids: string[]; meal: string; at: string; meal_calorie_target: number }): Promise<Recommendation> {
  try {
    return await request("/api/recommendations", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ user_id: userId, hall_slug: hallSlug, ...alternatives }),
    });
  } catch (error) {
    // Never bypass closing hours or today's calorie budget with a sample plate.
    throw error;
  }
}

export async function logMeal(payload: Omit<MealRecord, "hall_name" | "calories" | "voided">): Promise<MealRecord> {
  return request("/api/meals", { method: "POST", body: JSON.stringify(payload) });
}
export async function getMealHistory(start: string): Promise<MealHistory> {
  return request(`/api/meals?start=${encodeURIComponent(start)}`);
}
export async function removeMeal(id: string): Promise<void> {
  await request(`/api/meals/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function searchCurrentMenu(hallSlug: string, query: string): Promise<CurrentMenu> {
  return request(`/api/meals/menu?hall_slug=${encodeURIComponent(hallSlug)}&q=${encodeURIComponent(query)}`);
}
export async function logMenuFoods(payload: MenuMealInput): Promise<MealRecord> {
  return request("/api/meals/from-menu", { method: "POST", body: JSON.stringify(payload) });
}

export async function searchPastMenu(hallSlug: string, context: PastMealContext, query: string): Promise<CurrentMenu> {
  const params = new URLSearchParams({ hall_slug: hallSlug, ...context, q: query });
  return request(`/api/meals/past-menu?${params}`);
}

export async function logPastMenuFoods(payload: PastMealInput): Promise<MealRecord> {
  return request("/api/meals/from-past-menu", { method: "POST", body: JSON.stringify(payload) });
}

function demoRecommendation(hallSlug: string, profile: Profile): Recommendation {
  const hall = HALLS.find((item) => item.slug === hallSlug) || HALLS[1];
  const target = Math.round(profile.daily_calorie_goal * 0.35);
  const allergySet = new Set(profile.allergies);
  const options = [
    { id: "chicken", name: "Herb Grilled Chicken", station: "Mindful Kitchen", category: "protein", serving_amount: 1, serving_unit: "breast", servings: 1.5, nutrition: n(230, 38, 2, 7, 0, 390), allergens: [], dietary_tags: ["gluten-friendly"], why: "Anchors the plate with protein" },
    { id: "tofu", name: "Ginger Sesame Tofu", station: "Plant Forward", category: "protein", serving_amount: 4, serving_unit: "oz", servings: 1.5, nutrition: n(190, 18, 10, 9, 3, 360), allergens: ["soy", "sesame"], dietary_tags: ["vegan"], why: "A plant-forward protein anchor" },
    { id: "quinoa", name: "Lemon Herb Quinoa", station: "Harvest Table", category: "grain", serving_amount: 0.5, serving_unit: "cup", servings: 1, nutrition: n(145, 5, 26, 3, 3, 135), allergens: [], dietary_tags: ["vegan", "gluten-friendly"], why: "Provides steady meal energy" },
    { id: "broccoli", name: "Roasted Broccoli", station: "Harvest Table", category: "vegetable", serving_amount: 0.5, serving_unit: "cup", servings: 2, nutrition: n(65, 4, 9, 2, 4, 115), allergens: [], dietary_tags: ["vegan", "gluten-friendly"], why: "Adds fiber and micronutrient variety" },
    { id: "potato", name: "Roasted Sweet Potato", station: "Harvest Table", category: "vegetable", serving_amount: 0.5, serving_unit: "cup", servings: 1, nutrition: n(120, 2, 27, 1, 4, 170), allergens: [], dietary_tags: ["vegan", "gluten-friendly"], why: "Rounds out your energy target" },
  ];
  let filtered = options.filter((item) => !item.allergens.some((allergen) => allergySet.has(allergen)));
  if (profile.dietary_preferences.includes("vegan")) filtered = filtered.filter((item) => item.dietary_tags.includes("vegan"));
  if (profile.dietary_preferences.includes("vegetarian")) filtered = filtered.filter((item) => item.id !== "chicken");
  const plate = filtered.slice(0, 4).map((item) => ({
    ...item,
    portion_label: formatPortion(item.serving_amount * item.servings, item.serving_unit),
    line_nutrition: scale(item.nutrition, item.servings),
  }));
  const total = plate.reduce((sum, item) => add(sum, item.line_nutrition), n(0, 0, 0, 0, 0, 0));
  const ratio = target / profile.daily_calorie_goal;
  return {
    hall, date: easternDate(), meal: mealNow(), target_calories: target, plate,
    progress: {
      target: n(target, profile.protein_goal_g * ratio, profile.carb_goal_g * ratio, profile.fat_goal_g * ratio, profile.fiber_goal_g * ratio, profile.sodium_limit_mg * ratio),
      total,
      calorie_match_percent: Math.max(0, Math.round(100 - Math.abs(total.calories - target) / target * 100)),
    },
    excluded_for_allergies: options.length - filtered.length,
    excluded_for_diet: 0,
    data_source: "demo",
    generated_at: new Date().toISOString(),
    safety_message: "Items matching your saved allergens were excluded. Recipes and cross-contact can change—confirm labels and ask dining staff before eating.",
    note: "We couldn’t retrieve a live plate. This is sample data, not today’s menu. Check your connection and saved profile, then refresh.",
  };
}

function n(calories: number, protein_g: number, carbs_g: number, fat_g: number, fiber_g: number, sodium_mg: number) {
  return { calories, protein_g, carbs_g, fat_g, fiber_g, sodium_mg };
}

function scale(value: ReturnType<typeof n>, factor: number) {
  return Object.fromEntries(Object.entries(value).map(([key, amount]) => [key, amount * factor])) as ReturnType<typeof n>;
}

function add(a: ReturnType<typeof n>, b: ReturnType<typeof n>) {
  return Object.fromEntries(Object.keys(a).map((key) => [key, a[key as keyof typeof a] + b[key as keyof typeof b]])) as ReturnType<typeof n>;
}

function mealNow() {
  const hour = easternNow.getHours();
  return hour < 11 ? "breakfast" : hour < 17 ? "lunch" : "dinner";
}

function easternDate() {
  const year = easternNow.getFullYear();
  const month = String(easternNow.getMonth() + 1).padStart(2, "0");
  const day = String(easternNow.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatPortion(amount: number, unit: string) {
  const suffix = amount > 1 && ["cup", "piece", "slice", "serving"].includes(unit) ? "s" : "";
  return `${Number.isInteger(amount) ? amount : amount.toFixed(1)} ${unit}${suffix}`;
}
