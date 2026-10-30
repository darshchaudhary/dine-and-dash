import { useEffect, useState } from "react";
import { clearFoodPreference, getFoodPreferences, getPlannerOptions, savePlannerOptions } from "./api";
import type { PlannerOptions } from "./types";

export default function PlannerSettings({ disabled, onSaved, feedbackVersion }: { disabled: boolean; onSaved: () => void; feedbackVersion: number }) {
  const [options, setOptions] = useState<PlannerOptions | null>(null);
  const [favorites, setFavorites] = useState("");
  const [avoided, setAvoided] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [foods, setFoods] = useState<{ food_id: string; name: string; rating: number }[]>([]);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    let stale = false;
    setError("");
    getPlannerOptions().then(value => { if (!stale) { setOptions(value); setFavorites(value.favorite_terms.join(", ")); setAvoided(value.avoided_terms.join(", ")); } }).catch(err => { if (!stale) setError(err.message); });
    return () => { stale = true; };
  }, [version]);
  useEffect(() => {
    let stale = false;
    getFoodPreferences().then(value => { if (!stale) setFoods(value); }).catch(err => { if (!stale) setError(err.message); });
    return () => { stale = true; };
  }, [feedbackVersion, version]);
  const clear = async (foodId: string) => {
    setSaving(true); setError("");
    try { await clearFoodPreference(foodId); setFoods(values => values.filter(food => food.food_id !== foodId)); onSaved(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not clear food preference."); }
    finally { setSaving(false); }
  };
  const save = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!options || saving || disabled) return;
    setSaving(true); setError("");
    try {
      const split = (text: string) => text.split(",").map(value => value.trim()).filter(Boolean);
      const result = await savePlannerOptions({ ...options, favorite_terms: split(favorites), avoided_terms: split(avoided) });
      setOptions(result); onSaved();
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save plate preferences."); }
    finally { setSaving(false); }
  };
  return <details className="planner-settings"><summary>Personalize my plate</summary>
    {error && <p role="alert" className="journal-error">{error}</p>}
    {!options ? <button className="journal-link" onClick={() => setVersion(v => v + 1)}>Retry loading preferences</button> : <form onSubmit={save}>
      <fieldset disabled={disabled || saving}>
        <legend>Meals I usually plan to eat</legend>
        <p>Your current meal is always included. Calories are reserved for selected meals later today.</p>
        <div className="planner-choices">{(["breakfast", "lunch", "dinner"] as const).map(meal => <label key={meal}><input type="checkbox" checked={options.planned_meals.includes(meal)} onChange={() => setOptions({ ...options, planned_meals: options.planned_meals.includes(meal) ? options.planned_meals.filter(value => value !== meal) : [...options.planned_meals, meal] })} />{meal}</label>)}</div>
        <label>Prioritize<select value={options.mode} onChange={event => setOptions({ ...options, mode: event.target.value as PlannerOptions["mode"] })}><option value="balanced">Balanced nutrition</option><option value="favorites">Foods I like</option><option value="convenient">Fewer station visits</option></select></label>
        <label>Foods or ingredients I like<input value={favorites} maxLength={1600} onChange={event => setFavorites(event.target.value)} placeholder="e.g. chicken, rice, broccoli" /></label>
        <label>Foods or ingredients to avoid<input value={avoided} maxLength={1600} onChange={event => setAvoided(event.target.value)} placeholder="e.g. mushrooms, olives" /></label>
        <p>Separate foods with commas. These are taste preferences; manage allergies in your nutrition settings.</p>
        {!!foods.length && <div className="saved-food-preferences"><p>Saved food preferences</p>{foods.map(food => <div key={food.food_id}><span>{food.name} · {food.rating > 0 ? "Liked" : "Disliked"}</span><button type="button" className="journal-link" onClick={() => clear(food.food_id)}>Clear</button></div>)}</div>}
        <button className="button secondary" disabled={!options.planned_meals.length} type="submit">{saving ? "Saving…" : "Save and rebuild plate"}</button>
      </fieldset>
    </form>}
  </details>;
}
