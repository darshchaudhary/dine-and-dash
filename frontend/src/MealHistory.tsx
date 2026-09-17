import "./MealHistory.css";
import { useEffect, useState } from "react";
import { ArrowLeft, ArrowRight, CalendarDays, Settings2 } from "lucide-react";
import { getMealHistory, removeMeal } from "./api";
import type { MealHistory as History, Profile } from "./types";

export function easternToday() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
export function shiftDay(day: string, offset: number) {
  const date = new Date(`${day}T12:00:00Z`);
  date.setUTCDate(date.getUTCDate() + offset);
  return date.toISOString().slice(0, 10);
}
function monday(day: string) {
  return shiftDay(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7));
}
const label = (day: string, weekday = false) => new Intl.DateTimeFormat("en-US", weekday ? { weekday: "short", timeZone: "UTC" } : { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${day}T12:00:00Z`));
const localDay = (stamp: string) => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(stamp));

export default function MealHistory({ profile, onEdit }: { profile: Profile; onEdit: () => void }) {
  const today = easternToday();
  const [start, setStart] = useState(() => monday(today));
  const [selected, setSelected] = useState(today);
  const [period, setPeriod] = useState<"day" | "week">("day");
  const [history, setHistory] = useState<History | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [version, setVersion] = useState(0);
  const [removing, setRemoving] = useState("");
  const [confirmRemove, setConfirmRemove] = useState("");
  useEffect(() => {
    let stale = false;
    setLoading(true); setError(""); setHistory(null);
    getMealHistory(start).then(value => { if (!stale) setHistory(value); })
      .catch(err => { if (!stale) setError(err.message); })
      .finally(() => { if (!stale) setLoading(false); });
    return () => { stale = true; };
  }, [start, version]);
  const move = (offset: number) => { const next = shiftDay(start, offset); setStart(next); setSelected(next); setConfirmRemove(""); };
  const erase = async (id: string) => {
    setRemoving(id); setError("");
    try { await removeMeal(id); setConfirmRemove(""); setVersion(v => v + 1); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not remove meal."); }
    finally { setRemoving(""); }
  };
  const total = history ? period === "week" ? history.total_calories : history.days.find(day => day.date === selected)?.calories || 0 : 0;
  const meals = history?.meals.filter(meal => period === "week" || localDay(meal.consumed_at) === selected) || [];
  return <section className="history-page">
    <header className="history-heading"><div><span className="eyebrow"><CalendarDays size={15} /> Your food journal</span><h1>My progress</h1><p>{profile.name}’s meals, one day at a time.</p></div><button className="button secondary" onClick={onEdit}><Settings2 size={17} /> Edit goals</button></header>
    <div className="history-period" aria-label="Summary period"><button aria-pressed={period === "day"} onClick={() => setPeriod("day")}>Daily</button><button aria-pressed={period === "week"} onClick={() => setPeriod("week")}>Weekly</button></div>
    <div className="week-switch"><button className="icon-button" aria-label="Previous week" onClick={() => move(-7)}><ArrowLeft size={18} /></button><strong>{label(start)} – {label(shiftDay(start, 6))}</strong><button className="icon-button" aria-label="Next week" disabled={start >= monday(today)} onClick={() => move(7)}><ArrowRight size={18} /></button></div>
    {error && <div className="journal-error" role="alert">{error}<button onClick={() => setVersion(v => v + 1)}>Retry</button></div>}
    {loading ? <p role="status">Loading your saved meals…</p> : history && <>
      <div className="history-total"><span>{period === "day" ? selected === today ? "Today’s logged calories" : `${label(selected)} · logged calories` : "This week’s logged calories"}</span><strong>{Math.round(total).toLocaleString()} <small>kcal</small></strong><p>{period === "day" ? `${profile.daily_calorie_goal.toLocaleString()} kcal daily goal · ${Math.round(Math.abs(profile.daily_calorie_goal - total)).toLocaleString()} ${total > profile.daily_calorie_goal ? "above" : "below"} goal` : `${meals.length} meals logged · ${Math.round(total / 7).toLocaleString()} kcal/day across this 7-day week`}</p></div>
      <div className="history-days" aria-label="Daily calorie totals">{history.days.map(day => <button key={day.date} aria-pressed={period === "day" && selected === day.date} onClick={() => { setSelected(day.date); setPeriod("day"); }}><span>{label(day.date, true)}</span><div className="day-bar"><i style={{ height: `${Math.min(100, day.calories / Math.max(profile.daily_calorie_goal, ...history.days.map(d => d.calories)) * 100)}%` }} /></div><strong>{Math.round(day.calories)}</strong><small>{new Date(`${day.date}T12:00:00Z`).getUTCDate()}</small></button>)}</div>
      <p className="history-disclaimer">Estimated calories from meals you explicitly logged. Missing days mean no meals logged, not necessarily no food eaten. All dates use Eastern time.</p>
      <h2>{period === "day" ? `${label(selected)} meals` : "Meals this week"}</h2>
      {!meals.length && <div className="history-empty"><strong>No meals logged yet.</strong><p>Open My plate, select the foods you ate, adjust portions, and tap “Log eaten items.”</p></div>}
      <div className="history-meals">{meals.map(meal => <article key={meal.id} className="history-meal"><div className="history-meal-title"><div><h3>{meal.hall_name}</h3><p>{meal.meal} · {new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(new Date(meal.consumed_at))}</p></div><strong>{Math.round(meal.calories)} <small>kcal</small></strong></div><ul>{meal.items.map((item, i) => <li key={`${item.id}-${i}`}>{item.name}<span>{item.portion_label} · {Math.round(item.calories)} kcal</span></li>)}</ul>{confirmRemove === meal.id ? <div className="remove-confirm"><span>Remove this meal from your totals?</span><button disabled={!!removing} onClick={() => erase(meal.id)}>{removing ? "Removing…" : "Yes, remove"}</button><button disabled={!!removing} onClick={() => setConfirmRemove("")}>Cancel</button></div> : <button className="journal-link" onClick={() => setConfirmRemove(meal.id)}>Logged by mistake? Remove</button>}</article>)}</div>
    </>}
  </section>;
}
