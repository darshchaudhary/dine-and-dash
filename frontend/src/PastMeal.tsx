import { useEffect, useRef, useState } from "react";
import { CalendarDays, X } from "lucide-react";
import ExtraFoods from "./ExtraFoods";
import { easternToday } from "./MealHistory";
import type { Hall, MealRecord, PastMealContext, Profile } from "./types";
import "./PastMeal.css";

type Props = {
  halls: Hall[];
  initialHall: string;
  profile: Profile;
  onClose: () => void;
  onSaved: (record: MealRecord) => void;
};

export default function PastMeal({ halls, initialHall, profile, onClose, onSaved }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [date, setDate] = useState(easternToday);
  const [time, setTime] = useState("12:00");
  const [meal, setMeal] = useState<PastMealContext["meal"]>("lunch");
  const [hallSlug, setHallSlug] = useState(initialHall);
  const [context, setContext] = useState<PastMealContext | null>(null);
  const [busy, setBusy] = useState(false);
  const hall = halls.find(value => value.slug === hallSlug) || halls[0];

  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    return () => element.close();
  }, []);

  return (
    <dialog ref={dialog} className="past-meal" aria-labelledby="past-meal-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
      <header className="past-meal-heading">
        <div>
          <span className="eyebrow"><CalendarDays size={16} /> Catch up</span>
          <h1 id="past-meal-title">Log a past meal</h1>
        </div>
        <button type="button" className="icon-button" disabled={busy} onClick={onClose} aria-label="Close past meal"><X size={20} /></button>
      </header>
      {context ? (
        <ExtraFoods hall={hall} profile={profile} past={context} onLockChange={setBusy} onSaved={onSaved} onClose={() => setContext(null)} />
      ) : (
        <form onSubmit={event => { event.preventDefault(); setContext({ local_time: `${date}T${time}:00`, meal }); }}>
          <p className="past-meal-note">Forgot to log breakfast, lunch, or dinner? Choose when and where you ate. All times are Eastern, even when you’re traveling.</p>
          <div className="past-meal-fields">
            <label>Dining hall
              <select value={hallSlug} onChange={event => setHallSlug(event.target.value)}>
                {halls.map(value => <option key={value.slug} value={value.slug}>{value.short_name}</option>)}
              </select>
            </label>
            <label>Meal
              <select value={meal} onChange={event => { const value = event.target.value as PastMealContext["meal"]; setMeal(value); setTime({ breakfast: "09:00", lunch: "12:00", dinner: "18:00" }[value]); }}>
                <option value="breakfast">Breakfast</option>
                <option value="lunch">Lunch</option>
                <option value="dinner">Dinner</option>
              </select>
            </label>
            <label>Date eaten
              <input type="date" required min="2000-01-01" max={easternToday()} value={date} onChange={event => setDate(event.target.value)} />
            </label>
            <label>Time eaten (Eastern)
              <input type="time" required value={time} onChange={event => { setTime(event.target.value); const hour = Number(event.target.value.split(":")[0]); setMeal(hour < 11 ? "breakfast" : hour < 17 ? "lunch" : "dinner"); }} />
            </label>
          </div>
          <p className="past-meal-note">Search uses the published menu for that date and service, within configured hall hours. Holiday schedules and station stock may differ.</p>
          <button type="submit" className="button primary past-meal-search">Find foods from this meal</button>
        </form>
      )}
    </dialog>
  );
}
