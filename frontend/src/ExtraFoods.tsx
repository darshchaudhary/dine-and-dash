import "./ExtraFoods.css";
import { useEffect, useRef, useState } from "react";
import { Plus, Search, X } from "lucide-react";
import { ApiError, logMenuFoods, logPastMenuFoods, searchCurrentMenu, searchPastMenu } from "./api";
import type { CurrentMenu, Hall, MealRecord, MenuFood, MenuMealInput, PastMealContext, Profile } from "./types";

export default function ExtraFoods({ hall, profile, onSaved, onClose, past, onLockChange }: { hall: Hall; profile: Profile; onSaved: (meal: MealRecord) => void; onClose: () => void; past?: PastMealContext; onLockChange?: (locked: boolean) => void }) {
  const [query, setQuery] = useState("");
  const [menu, setMenu] = useState<CurrentMenu | null>(null);
  const [selected, setSelected] = useState<{ food: MenuFood; servings: number }[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [searchError, setSearchError] = useState("");
  const [version, setVersion] = useState(0);
  const pending = useRef<(MenuMealInput & { local_time?: string }) | null>(null);
  const lock = useRef(false);
  const service = useRef("");
  useEffect(() => {
    let stale = false;
    setLoading(true); setSearchError("");
    const timer = setTimeout(() => {
      (past ? searchPastMenu(hall.slug, past, query) : searchCurrentMenu(hall.slug, query)).then(result => {
        if (stale) return;
        const key = `${result.date}:${result.meal}`;
        if (service.current && service.current !== key && !pending.current) {
          setSelected([]); setError("The service changed. Please select foods from the new menu.");
        }
        service.current = key; setMenu(result);
      }).catch(err => { if (!stale) { setMenu(null); setSearchError(err.message); } })
        .finally(() => { if (!stale) setLoading(false); });
    }, 250);
    return () => { stale = true; clearTimeout(timer); };
  }, [hall.slug, query, version, past]);
  const frozen = saving || !!pending.current;
  useEffect(() => { onLockChange?.(frozen); }, [frozen, onLockChange]);
  const save = async () => {
    if (lock.current || (!pending.current && (!selected.length || !menu))) return;
    pending.current ||= { id: crypto.randomUUID(), hall_slug: hall.slug, menu_date: menu!.date, meal: menu!.meal, ...(past ? { local_time: past.local_time } : {}), items: selected.map(item => ({ food_id: item.food.id, servings: item.servings })) };
    lock.current = true; setSaving(true); setError("");
    try { const payload = pending.current; const record = payload.local_time ? await logPastMenuFoods({ ...payload, local_time: payload.local_time }) : await logMenuFoods(payload); pending.current = null; onSaved(record); }
    catch (err) {
      if (err instanceof ApiError && [400, 409, 422].includes(err.status)) { pending.current = null; setSelected([]); setVersion(v => v + 1); }
      setError(err instanceof Error ? err.message : "Could not log foods. Please retry.");
    } finally { lock.current = false; setSaving(false); }
  };
  const total = selected.reduce((sum, item) => sum + item.food.nutrition.calories * item.servings, 0);
  return <section className="extra-foods" aria-label={past ? "Choose past meal foods" : "Log other foods"}>
    <div className="extra-heading"><div><h2>{past ? "What did you eat?" : "Ate something else?"}</h2><p>{hall.short_name} · {menu?.meal || past?.meal || "Current service"}{past && ` · ${past.local_time.replace("T", " ")} Eastern`}</p></div><button className="icon-button" disabled={frozen} onClick={onClose} aria-label={past ? "Change meal date or hall" : "Close other foods"}><X size={20} /></button></div>
    <label className="extra-search"><Search size={18} /><input autoFocus type="search" maxLength={100} value={query} disabled={frozen} placeholder="Search foods or stations" aria-label={past ? "Search selected historical dining hall menu" : "Search current dining hall menu"} onChange={e => setQuery(e.target.value)} /></label>
    <p className="extra-disclaimer">{past ? "Only the selected date and service’s published menu is searched. Historical menus may be unavailable, and listings cannot confirm actual station stock." : "Only this hall’s current published menu is searched—not guaranteed station stock."} This records what you ate, not a recommendation; check allergen labels.</p>
    {searchError && <div role="alert" className="journal-error">{searchError}<button onClick={() => setVersion(v => v + 1)}>Retry search</button></div>}
    {loading ? <p role="status">{past ? "Searching historical menu…" : "Searching current menu…"}</p> : menu && <div className="extra-results" aria-label="Matching menu foods"><small>{menu.match_count} matches{menu.match_count > menu.items.length ? " · showing first 40; type more to narrow results" : ""}</small>{!menu.items.length && <p>No matching foods in this service. Try a different name or station.</p>}{menu.items.map(food => <article key={food.id}><div><strong>{food.name}</strong><p>{food.station} · {food.serving_amount} {food.serving_unit} · {food.nutrition_complete ? `${Math.round(food.nutrition.calories)} kcal` : "Nutrition unavailable"}</p>{food.allergens.length > 0 && <small className={food.allergens.some(a => profile.allergies.includes(a)) ? "allergen-warning" : ""}>Contains: {food.allergens.join(", ")}</small>}</div><button className="icon-button" aria-label={`Add ${food.name}`} disabled={frozen || !food.nutrition_complete || selected.length >= 20 || selected.some(item => item.food.id === food.id)} onClick={() => setSelected(items => [...items, { food, servings: 1 }])}><Plus size={18} /></button></article>)}</div>}
    {selected.length > 0 && <div className="extra-selected"><h3>What you ate</h3>{selected.map(item => <div key={item.food.id}><strong>{item.food.name}</strong><label>Servings<select aria-label={`Servings of ${item.food.name}`} disabled={frozen} value={item.servings} onChange={e => setSelected(items => items.map(i => i.food.id === item.food.id ? { ...i, servings: Number(e.target.value) } : i))}>{[0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 5, 6].map(n => <option key={n} value={n}>{n}×</option>)}</select></label><span>{Math.round(item.food.nutrition.calories * item.servings)} kcal</span><button className="journal-link" disabled={frozen} onClick={() => setSelected(items => items.filter(i => i.food.id !== item.food.id))}>Remove</button></div>)}</div>}
    {error && <p role="alert" className="journal-error">{error}</p>}
    <p className="extra-disclaimer">{Math.round(total)} estimated kcal selected. Log only foods not already recorded in your plate or history. {past ? "Calories will be added to the selected day and its weekly total. Meals from today also update your next suggestion." : "Your next suggestion will use the updated daily total."}</p>
    <button className="button primary" disabled={saving || (!pending.current && (loading || !!searchError || !selected.length))} onClick={save}>{saving ? "Saving…" : pending.current ? "Retry saving these foods" : "Log these foods"}</button>
  </section>;
}
