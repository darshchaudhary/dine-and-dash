import "./App.css";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  Check,
  ChevronDown,
  CircleUserRound,
  ClipboardList,
  Clock3,
  House,
  Leaf,
  LoaderCircle,
  LogOut,
  Minus,
  Plus,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Utensils,
  UserRound,
  WheatOff,
  X,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { authenticate, fetchHalls, getAccount, getMealHistory, getProfile, getRecommendation, HALLS, logMeal, logout, saveProfile } from "./api";
import MealHistoryPage, { easternToday } from "./MealHistory";
import ExtraFoods from "./ExtraFoods";
import { restoreSession } from "./auth";
import type { Account, Hall, MealRecord, Nutrition, PlateItem, Profile, Recommendation } from "./types";

const defaultProfile: Profile = {
  name: "",
  goal: "balanced",
  daily_calorie_goal: 2200,
  protein_goal_g: 130,
  carb_goal_g: 250,
  fat_goal_g: 70,
  fiber_goal_g: 30,
  sodium_limit_mg: 2300,
  meals_per_day: 3,
  allergies: [],
  dietary_preferences: [],
};

export default function App() {
  const [account, setAccount] = useState<Account | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [profileLoading, setProfileLoading] = useState(true);
  const [bootError, setBootError] = useState("");

  useEffect(() => {
    let active = true;
    restoreSession().then(getAccount).then((value) => {
      if (active) setAccount(value);
    }).catch((error) => { if (active) setBootError(error.message); })
      .finally(() => { if (active) setLoading(false); });
    const signedOut = () => { setAccount(null); setProfile(null); setEditing(false); };
    window.addEventListener("dinedash:signed-out", signedOut);
    return () => { active = false; window.removeEventListener("dinedash:signed-out", signedOut); };
  }, []);

  useEffect(() => {
    let active = true;
    setProfile(null);
    setEditing(false);
    if (!account) return;
    setProfileLoading(true);
    getProfile(account.id).then((value) => { if (active) setProfile(value); })
      .catch((error) => { if (active) setBootError(error.message); })
      .finally(() => { if (active) setProfileLoading(false); });
    return () => { active = false; };
  }, [account]);

  const handleProfile = async (value: Profile) => {
    if (!account) return;
    const saved = await saveProfile(account.id, value);
    setProfile(saved);
    setEditing(false);
  };

  const signOut = async () => {
    try {
      await logout();
      setAccount(null); setProfile(null); setEditing(false);
    } catch (error) { setBootError(error instanceof Error ? error.message : "Could not sign out. Please retry."); }
  };

  if (bootError) return <main className="auth-shell"><section className="auth-card"><Brand /><h1>Let’s reconnect.</h1><p role="alert">{bootError}</p><button className="button primary" onClick={() => window.location.reload()}>Try again</button></section></main>;
  if (loading || (account && profileLoading)) return <LoadingScreen />;
  if (!account) return <AuthScreen onAuthenticated={(value) => { setProfileLoading(true); setAccount(value); }} />;

  return (
    <AnimatePresence mode="wait">
      {!profile || editing ? (
        <Onboarding key="onboarding" initial={profile || defaultProfile} onComplete={handleProfile} onClose={profile ? () => setEditing(false) : undefined} onSignOut={signOut} />
      ) : (
        <Dashboard key={account.id} userId={account.id} profile={profile} onEdit={() => setEditing(true)} onSignOut={signOut} />
      )}
    </AnimatePresence>
  );
}

function AuthScreen({ onAuthenticated }: { onAuthenticated: (account: Account) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [visible, setVisible] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setError("");
    if (mode === "register" && password !== confirmation) { setError("Your passwords don’t match."); return; }
    setBusy(true);
    try {
      const user = await authenticate(mode, email, password);
      setPassword(""); setConfirmation(""); onAuthenticated(user);
    } catch (error) { setError(error instanceof Error ? error.message : "Unable to sign in."); }
    finally { setBusy(false); }
  };
  return <main className="auth-shell">
    <motion.section className="auth-card" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
      <Brand />
      <span className="auth-eyebrow">GOOD FOOD. YOUR GOALS.</span>
      <h1>{mode === "login" ? "Welcome back." : "A plate that’s yours."}</h1>
      <p>{mode === "login" ? "Sign in to your goals, preferences, and next meal." : "Create your account. We’ll personalize the rest together."}</p>
      <form onSubmit={submit}>
        <label htmlFor="auth-email" className="field-label">Email</label>
        <input id="auth-email" className="text-input" type="email" autoComplete="username" autoCapitalize="none" spellCheck={false} required maxLength={254} value={email} onChange={(event) => setEmail(event.target.value)} disabled={busy} placeholder="you@example.com" />
        <label htmlFor="auth-password" className="field-label">Password</label>
        <div className="password-field"><input id="auth-password" className="text-input" type={visible ? "text" : "password"} autoComplete={mode === "login" ? "current-password" : "new-password"} required minLength={15} maxLength={128} value={password} onChange={(event) => setPassword(event.target.value)} disabled={busy} aria-describedby={mode === "register" ? "password-hint" : undefined} /><button type="button" className="text-button" aria-label={visible ? "Hide password" : "Show password"} onClick={() => setVisible(!visible)}>{visible ? "Hide" : "Show"}</button></div>
        {mode === "register" && <>
          <small id="password-hint">Use at least 15 characters. A unique passphrase works well.</small>
          <label htmlFor="auth-confirm" className="field-label">Confirm password</label>
          <input id="auth-confirm" className="text-input" type="password" autoComplete="new-password" required value={confirmation} maxLength={128} onChange={(event) => setConfirmation(event.target.value)} disabled={busy} />
        </>}
        {error && <p className="auth-error" role="alert">{error}</p>}
        <button className="button primary auth-submit" disabled={busy} type="submit">{busy ? <LoaderCircle className="spin" size={18} /> : <ArrowRight size={18} />}{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
      </form>
      <button className="text-button auth-switch" disabled={busy} onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); setPassword(""); setConfirmation(""); setVisible(false); }}>{mode === "login" ? "New here? Create an account" : "Already have an account? Sign in"}</button>
      {mode === "register" && <small className="auth-footnote">Demo accounts: email verification and password recovery are not available yet. Save your password securely.</small>}
      <div className="auth-privacy"><ShieldCheck size={15} /><span>Your nutrition profile is private to your account.</span></div>
    </motion.section>
  </main>;
}

function LoadingScreen() {
  return (
    <main className="loading-screen">
      <Brand />
      <LoaderCircle className="spin" size={22} />
    </main>
  );
}

function Brand({ inverse = false }: { inverse?: boolean }) {
  return (
    <div className={`brand ${inverse ? "brand-inverse" : ""}`}>
      <span className="brand-mark"><Utensils size={18} strokeWidth={2.5} /></span>
      <span>Dine&amp;Dash</span>
    </div>
  );
}

function Onboarding({ initial, onComplete, onClose, onSignOut }: { initial: Profile; onComplete: (profile: Profile) => Promise<void>; onClose?: () => void; onSignOut: () => Promise<void> }) {
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState<Profile>(initial);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const steps = ["Your goal", "Daily targets", "Diet & safety"];

  const next = async () => {
    if (step < 2) return setStep(step + 1);
    setSaving(true);
    setError("");
    try { await onComplete(profile); }
    catch (error) { setError(error instanceof Error ? error.message : "Could not save your profile."); }
    finally { setSaving(false); }
  };

  return (
    <motion.main className="setup-shell" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <aside className="setup-aside">
        <Brand inverse />
        <div className="setup-copy">
          <h1>Make room for your goals.</h1>
          <p>Your targets, dietary preferences, and allergies. All in one place.</p>
        </div>
        <div className="privacy-note"><ShieldCheck size={17} /> Your dietary profile stays in your account.</div>
      </aside>

      <section className="setup-panel">
        <div className="setup-toolbar">
          <span>{onClose ? "Your preferences" : "Welcome to Dine&Dash"}</span>
          <button className="text-button" disabled={saving} onClick={onSignOut}>Sign out</button>
          {onClose && <button className="icon-button close-button" onClick={onClose} aria-label="Close settings"><X size={20} /></button>}
        </div>
        <div className="stepper" aria-label={`Step ${step + 1} of 3`}>
          {steps.map((label, index) => (
            <div className={`step ${index <= step ? "active" : ""}`} key={label}>
              <span>{index < step ? <Check size={13} /> : index + 1}</span>
              <small>{label}</small>
            </div>
          ))}
        </div>

        <AnimatePresence mode="wait">
          <motion.div className="setup-form" key={step} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: -6 }}>
            {step === 0 && <GoalStep profile={profile} setProfile={setProfile} />}
            {step === 1 && <TargetsStep profile={profile} setProfile={setProfile} />}
            {step === 2 && <SafetyStep profile={profile} setProfile={setProfile} />}
          </motion.div>
        </AnimatePresence>

        {error && <p className="auth-error" role="alert">{error}</p>}
        <div className="setup-actions">
          <button className="button secondary" onClick={() => step > 0 ? setStep(step - 1) : onClose?.()} disabled={step === 0 && !onClose}>
            <ArrowLeft size={17} /> Back
          </button>
          <button className="button primary" onClick={next} disabled={!profile.name.trim() || saving}>
            {saving ? <LoaderCircle className="spin" size={17} /> : step === 2 ? <Check size={17} /> : <ArrowRight size={17} />}
            {step === 2 ? "Build my plate" : "Continue"}
          </button>
        </div>
      </section>
    </motion.main>
  );
}

function GoalStep({ profile, setProfile }: FormProps) {
  const goals = [
    ["balanced", "Eat more balanced", "Build consistent, well-rounded plates"],
    ["lose", "Lose weight", "Stay satisfied in a calorie deficit"],
    ["maintain", "Maintain weight", "Keep energy and intake steady"],
    ["gain", "Build & gain", "Prioritize calories and protein"],
  ] as const;
  return (
    <>
      <FormHeading kicker="A little about you" title="What are you working toward?" description="This shapes how we score each possible plate." />
      <label className="field-label" htmlFor="name">First name</label>
      <input id="name" className="text-input" placeholder="e.g. Maya" value={profile.name} onChange={(event) => setProfile({ ...profile, name: event.target.value })} />
      <div className="goal-grid">
        {goals.map(([value, title, detail]) => (
          <button key={value} className={`choice-card ${profile.goal === value ? "selected" : ""}`} onClick={() => setProfile({ ...profile, goal: value })}>
            <span className="choice-check">{profile.goal === value && <Check size={14} />}</span>
            <strong>{title}</strong><small>{detail}</small>
          </button>
        ))}
      </div>
    </>
  );
}

function TargetsStep({ profile, setProfile }: FormProps) {
  return (
    <>
      <FormHeading kicker="Personalize your day" title="Set your nutrition targets" description="You can change these anytime. We’ll divide them across your meals." />
      <div className="calorie-target">
        <div><span>Daily energy</span><strong>{profile.daily_calorie_goal.toLocaleString()} <small>kcal</small></strong></div>
        <input type="range" min="1200" max="4000" step="50" value={profile.daily_calorie_goal} onChange={(event) => setProfile({ ...profile, daily_calorie_goal: +event.target.value })} />
        <div className="range-labels"><span>1,200</span><span>4,000</span></div>
      </div>
      <div className="macro-inputs">
        <NumberField label="Protein" suffix="g" value={profile.protein_goal_g} onChange={(value) => setProfile({ ...profile, protein_goal_g: value })} />
        <NumberField label="Carbohydrates" suffix="g" value={profile.carb_goal_g} onChange={(value) => setProfile({ ...profile, carb_goal_g: value })} />
        <NumberField label="Fat" suffix="g" value={profile.fat_goal_g} onChange={(value) => setProfile({ ...profile, fat_goal_g: value })} />
        <NumberField label="Fiber" suffix="g" value={profile.fiber_goal_g} onChange={(value) => setProfile({ ...profile, fiber_goal_g: value })} />
        <NumberField label="Sodium limit" suffix="mg" value={profile.sodium_limit_mg} onChange={(value) => setProfile({ ...profile, sodium_limit_mg: value })} />
        <label className="number-field"><span>Meals per day</span><select value={profile.meals_per_day} onChange={(event) => setProfile({ ...profile, meals_per_day: +event.target.value })}>{[2, 3, 4, 5, 6].map((value) => <option key={value}>{value}</option>)}</select></label>
      </div>
    </>
  );
}

const allergens = ["milk", "eggs", "peanuts", "tree nuts", "wheat", "soy", "fish", "shellfish", "sesame", "gluten"];
const diets = ["vegan", "vegetarian", "halal"];

function SafetyStep({ profile, setProfile }: FormProps) {
  const toggle = (key: "allergies" | "dietary_preferences", value: string) => {
    const values = profile[key].includes(value) ? profile[key].filter((item) => item !== value) : [...profile[key], value];
    setProfile({ ...profile, [key]: values });
  };
  return (
    <>
      <FormHeading kicker="Safety first" title="Anything we should avoid?" description="We’ll exclude matching Nutrislice allergen flags before building a plate." />
      <div className="safety-callout"><AlertTriangle size={19} /><p><strong>Allergy note</strong> Always confirm ingredients and cross-contact risk with dining staff. Menu data can change.</p></div>
      <fieldset className="chip-fieldset"><legend>Food allergies</legend><div className="chips">{allergens.map((item) => <button className={`chip ${profile.allergies.includes(item) ? "selected" : ""}`} key={item} onClick={() => toggle("allergies", item)}>{profile.allergies.includes(item) && <Check size={14} />}{item}</button>)}</div></fieldset>
      <fieldset className="chip-fieldset"><legend>Dietary preferences</legend><div className="chips">{diets.map((item) => <button className={`chip ${profile.dietary_preferences.includes(item) ? "selected" : ""}`} key={item} onClick={() => toggle("dietary_preferences", item)}>{profile.dietary_preferences.includes(item) && <Check size={14} />}{item}</button>)}</div></fieldset>
    </>
  );
}

type FormProps = { profile: Profile; setProfile: (profile: Profile) => void };

function FormHeading({ kicker, title, description }: { kicker: string; title: string; description: string }) {
  return <div className="form-heading"><span>{kicker}</span><h2>{title}</h2><p>{description}</p></div>;
}

function NumberField({ label, suffix, value, onChange }: { label: string; suffix: string; value: number; onChange: (value: number) => void }) {
  return <label className="number-field"><span>{label}</span><div><input type="number" value={value} onChange={(event) => onChange(+event.target.value)} /><small>{suffix}</small></div></label>;
}

function Dashboard({ userId, profile, onEdit, onSignOut }: { userId: string; profile: Profile; onEdit: () => void; onSignOut: () => Promise<void> }) {
  const scrollArea = useRef<HTMLElement>(null);
  const [activeView, setActiveView] = useState<"today" | "plate" | "history">(() => window.location.hash === "#history" ? "history" : window.location.hash === "#plate" ? "plate" : "today");
  const [halls, setHalls] = useState<Hall[]>(HALLS);
  const [hallSlug, setHallSlug] = useState("north-ave-dining-hall");
  const [recommendation, setRecommendation] = useState<Recommendation | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completed, setCompleted] = useState<Set<string>>(new Set());
  const [excluded, setExcluded] = useState<string[]>([]);
  const [swapping, setSwapping] = useState(false);
  const [savingMeal, setSavingMeal] = useState(false);
  const [logged, setLogged] = useState(false);
  const [mealError, setMealError] = useState("");
  const [alternativeMessage, setAlternativeMessage] = useState("");
  const [todayMeals, setTodayMeals] = useState<MealRecord[] | null>(null);
  const [historyVersion, setHistoryVersion] = useState(0);
  const [hallAvailable, setHallAvailable] = useState(false);
  const [showExtra, setShowExtra] = useState(false);
  const [extraNotice, setExtraNotice] = useState("");
  const pendingLog = useRef<Parameters<typeof logMeal>[0] | null>(null);
  const logLock = useRef(false);
  const requestVersion = useRef(0);
  const menuAt = useRef("");
  const lastHallOpen = useRef(false);
  const plateLocked = !hallAvailable || showExtra || swapping || savingMeal || logged || !!pendingLog.current;

  const load = useCallback(async () => {
    if (logLock.current || pendingLog.current) return;
    const version = ++requestVersion.current;
    setLoading(true); setError(null); setCompleted(new Set());
    setExcluded([]); setLogged(false); setMealError(""); setAlternativeMessage(""); setSwapping(false);
    try {
      const fresh = await fetchHalls();
      if (version !== requestVersion.current) return;
      setHalls(fresh);
      const open = fresh.some(hall => hall.slug === hallSlug && hall.open_now);
      lastHallOpen.current = open;
      setHallAvailable(open);
      if (!open) { setRecommendation(null); return; }
      const result = await getRecommendation(userId, hallSlug, profile);
      if (version === requestVersion.current) { menuAt.current = result.generated_at; setRecommendation(result); }
    }
    catch (err) { if (version === requestVersion.current) { setRecommendation(null); setError(err instanceof Error ? err.message : "We couldn’t build a plate right now. Please refresh."); } }
    finally { if (version === requestVersion.current) setLoading(false); }
  }, [hallSlug, profile, userId]);

  useEffect(() => {
    let stale = false;
    getMealHistory(easternToday()).then(result => { if (!stale) setTodayMeals(result.meals.filter(meal => new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date(meal.consumed_at)) === easternToday())); }).catch(() => { if (!stale) setTodayMeals(null); });
    return () => { stale = true; };
  }, [historyVersion, activeView]);

  const findAlternative = async (id: string) => {
    if (!recommendation || plateLocked) return;
    const version = ++requestVersion.current;
    const nextExcluded = [...new Set([...excluded, id])];
    setSwapping(true); setMealError(""); setAlternativeMessage("");
    try {
      const result = await getRecommendation(userId, hallSlug, profile, { excluded_item_ids: nextExcluded, meal: recommendation.meal, at: menuAt.current, meal_calorie_target: recommendation.target_calories });
      if (version !== requestVersion.current) return;
      if (result.data_source !== "nutrislice") throw new Error("Live alternatives are unavailable right now. Your original plate was kept; try refreshing or choose another hall.");
      setRecommendation(result); setExcluded(nextExcluded); setCompleted(new Set());
      setAlternativeMessage(result.plate.length ? `Alternative plate ready: ${Math.round(result.progress.total.calories)} kcal, ${Math.round(Math.abs(result.progress.total.calories - result.target_calories))} kcal ${result.progress.total.calories > result.target_calories ? "above" : "below"} your meal target. Review the new portions.` : "No alternatives remain with your dietary filters. Try another dining hall.");
    } catch (err) { if (version === requestVersion.current) setMealError(err instanceof Error ? err.message : "Could not find alternatives."); }
    finally { if (version === requestVersion.current) setSwapping(false); }
  };

  const recordMeal = async () => {
    if (!recommendation || logLock.current || logged || swapping || (!hallAvailable && !pendingLog.current)) return;
    if (!pendingLog.current) {
      const eaten = recommendation.plate.filter(item => completed.has(item.id));
      if (!eaten.length || recommendation.data_source !== "nutrislice") return;
      pendingLog.current = { id: crypto.randomUUID(), consumed_at: new Date().toISOString(), hall_slug: recommendation.hall.slug, meal: recommendation.meal, items: eaten.map(item => ({ id: item.id, name: item.name, portion_label: item.portion_label, calories: item.line_nutrition.calories })) };
    }
    logLock.current = true; setSavingMeal(true); setMealError("");
    try {
      await logMeal(pendingLog.current);
      pendingLog.current = null; setLogged(true); setHistoryVersion(v => v + 1);
    } catch (err) { setMealError(`${err instanceof Error ? err.message : "Could not save meal."} Tap retry to check/save this same meal without double-counting.`); }
    finally { logLock.current = false; setSavingMeal(false); }
  };

  useEffect(() => {
    let stale = false;
    const updateHours = () => fetchHalls().then(fresh => {
      if (stale) return;
      setHalls(fresh);
      const open = fresh.some(hall => hall.slug === hallSlug && hall.open_now);
      const wasOpen = lastHallOpen.current;
      lastHallOpen.current = open;
      setHallAvailable(open);
      if (!open) { ++requestVersion.current; setLoading(false); setSwapping(false); }
      else if (!wasOpen && !showExtra) load();
    }).catch(() => { if (!stale) { setHallAvailable(false); setError("Could not verify current dining hall hours. Refresh to try again."); } });
    const timer = window.setInterval(updateHours, 30000);
    const wake = () => { if (!document.hidden) updateHours(); };
    document.addEventListener("visibilitychange", wake);
    return () => { stale = true; window.clearInterval(timer); document.removeEventListener("visibilitychange", wake); };
  }, [hallSlug, load, showExtra]);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { scrollArea.current?.scrollTo({ top: 0, behavior: "instant" }); }, [activeView]);
  useEffect(() => {
    const syncFromHash = () => setActiveView(window.location.hash === "#history" ? "history" : window.location.hash === "#plate" ? "plate" : "today");
    window.addEventListener("hashchange", syncFromHash);
    return () => window.removeEventListener("hashchange", syncFromHash);
  }, []);

  const setServings = (id: string, servings: number) => {
    if (!recommendation || plateLocked) return;
    const plate = recommendation.plate.map((item) => item.id === id ? {
      ...item,
      servings,
      portion_label: portion(item, servings),
      line_nutrition: scaleNutrition(item.nutrition, servings),
    } : item);
    const total = plate.reduce((sum, item) => addNutrition(sum, item.line_nutrition), emptyNutrition());
    setRecommendation({ ...recommendation, plate, progress: { ...recommendation.progress, total } });
  };

  const currentHall = halls.find((hall) => hall.slug === hallSlug) || halls[0];
  const total = recommendation?.progress.total || emptyNutrition();
  const caloriePercent = recommendation && recommendation.target_calories > 0 ? Math.min(100, Math.round(total.calories / recommendation.target_calories * 100)) : 0;
  const navigate = (view: "today" | "plate" | "history") => {
    setActiveView(view);
    window.history.replaceState(null, "", `#${view}`);
    scrollArea.current?.scrollTo({ top: 0, behavior: "instant" });
  };

  return (
    <div className="app-shell">
      <header className="topbar">
        <Brand />
        <nav aria-label="Primary navigation">
          <button className={activeView === "today" ? "active" : ""} onClick={() => navigate("today")}>Today</button>
          <button disabled={!hallAvailable} className={activeView === "plate" ? "active" : ""} onClick={() => navigate("plate")}>My plate</button>
        </nav>
        <div className="topbar-actions">
          <button className="icon-button" onClick={onSignOut} title="Sign out" aria-label="Sign out"><LogOut size={18} /></button>
          <button className="icon-button" disabled={showExtra || loading || swapping || savingMeal || !!pendingLog.current} onClick={load} title="Refresh menu"><RefreshCw size={18} /></button>
          <button className="profile-button" onClick={() => navigate("history")} aria-label="Your meal history and progress"><span>{profile.name.slice(0, 1).toUpperCase()}</span><div><small>My progress</small><strong>{profile.name}</strong></div><ChevronDown size={16} /></button>
        </div>
      </header>

      <main ref={scrollArea} className={`dashboard view-${activeView}`} tabIndex={0} aria-label={activeView === "history" ? "Meal history" : activeView === "today" ? "Today's meal" : "Plate checklist"}>
        {activeView === "history" ? <MealHistoryPage key={historyVersion} profile={profile} onEdit={onEdit} /> : <>
        {activeView === "today" ? <>
        <section className="welcome-row">
          <div><h1>Good {dayPart()}, {profile.name}.</h1><p>What’s on your plate today?</p></div>
        </section>

        <section className="hall-section">
          <div className="section-label"><span>Dining hall</span></div>
          <div className="hall-picker">
            {halls.map((hall) => (
              <button key={hall.slug} disabled={showExtra || swapping || savingMeal || !!pendingLog.current} onClick={() => { if (hall.slug !== hallSlug) { setHallAvailable(false); setExtraNotice(""); setHallSlug(hall.slug); } }} aria-pressed={hallSlug === hall.slug} className={hallSlug === hall.slug ? "selected" : ""}>
                <strong>{hall.short_name}</strong>
              </button>
            ))}
          </div>
          <p className="hall-hours">{currentHall.open_now ? "Open now" : "Currently closed"} · {currentHall.hours}</p>
        </section>
        </> : (
          <section className="plate-view-heading">
            <div><span className="eyebrow"><ClipboardList size={15} /> Meal checklist</span><h1>My plate</h1><p>Adjust portions, then select the items you actually ate to log your meal.</p></div>
            <label><span>Dining hall</span><select disabled={showExtra || swapping || savingMeal || !!pendingLog.current} value={hallSlug} onChange={(event) => { setHallAvailable(false); setExtraNotice(""); setHallSlug(event.target.value); }}>{halls.map((hall) => <option key={hall.slug} value={hall.slug}>{hall.short_name}</option>)}</select></label>
          </section>
        )}

        {todayMeals !== null && <button className="today-journal" onClick={() => navigate("history")}><span><strong>{Math.round(todayMeals.reduce((sum, meal) => sum + meal.calories, 0)).toLocaleString()} kcal</strong> logged today · {todayMeals.length} meals{todayMeals.some(meal => meal.hall_slug === hallSlug) ? ` · Already ate at ${currentHall.short_name}` : ""}</span><ArrowRight size={17} /></button>}
        {extraNotice && <p className="journal-status" role="status">{extraNotice}</p>}
        {showExtra ? <ExtraFoods hall={currentHall} profile={profile} onClose={() => setShowExtra(false)} onSaved={() => { setShowExtra(false); setExtraNotice("Extra foods saved. Your daily total and next suggestion have been updated."); setHistoryVersion(v => v + 1); load(); }} /> : <button className="button secondary extra-open" disabled={!hallAvailable || loading || savingMeal || swapping || !!pendingLog.current} onClick={() => { setExtraNotice(""); setShowExtra(true); }}>Ate something else? Search this hall’s menu <Plus size={17} /></button>}

        <AnimatePresence mode="wait">
          {loading ? <PlateSkeleton key="loading" /> : error ? <ErrorState key="error" message={error} onRetry={load} /> : !hallAvailable ? <section className="closed-hall" role="status"><Clock3 size={26} /><h2>{currentHall.short_name} is closed</h2><p>Plate building is disabled. Select an open dining hall or come back during service.</p><p>{currentHall.hours}</p><small>Based on configured regular hours; holiday hours may differ.</small></section> : recommendation && (
            activeView === "today" ? (
              <TodayOverview key={`today-${hallSlug}-${recommendation.generated_at}`} recommendation={recommendation} profile={profile} currentHall={currentHall} onOpenPlate={() => navigate("plate")} />
            ) : <motion.div key={`plate-${hallSlug}-${recommendation.generated_at}`} className="dashboard-grid" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ type: "tween", duration: 0.18 }}>
              <section className="plate-card" id="plate">
                <div className="plate-card-header">
                  <div><span className="eyebrow navy"><Sparkles size={14} /> Your best-fit plate</span><h2>{titleCase(recommendation.meal)} at {currentHall.short_name}</h2><p><Clock3 size={15} /> For right now · {formatDate(recommendation.date)}</p></div>
                  <div className="source-badge"><span className={recommendation.data_source === "nutrislice" ? "live-dot" : "demo-dot"} />{recommendation.data_source === "nutrislice" ? "Live Nutrislice" : "Demo preview"}</div>
                </div>

                {recommendation.note && <div className="data-note"><AlertTriangle size={16} /><span>{recommendation.note}</span></div>}
                {recommendation.planning_note && <p className="journal-status">{recommendation.planning_note}</p>}
                <div className="alternative-help"><strong>Something unavailable?</strong><p>Tap “Not available” on a food to rebuild your plate near the same calorie target. Menu listings don’t guarantee station stock.</p>{excluded.length > 0 && <small>{excluded.length} unavailable foods excluded · Refresh menu to reset.</small>}</div>
                {alternativeMessage && <p className="journal-status" role="status">{alternativeMessage}</p>}
                {swapping && <p className="journal-status" role="status">Finding another plate with your dietary filters…</p>}
                {mealError && <p className="journal-error" role="alert">{mealError}</p>}

                <div className="plate-summary">
                  <ProgressRing value={caloriePercent} label={Math.round(total.calories).toString()} sublabel={`of ${recommendation.target_calories} kcal`} />
                  <div className="macro-summary">
                    <MacroBar label="Protein" value={total.protein_g} target={recommendation.progress.target.protein_g} color="teal" />
                    <MacroBar label="Carbs" value={total.carbs_g} target={recommendation.progress.target.carbs_g} color="blue" />
                    <MacroBar label="Fat" value={total.fat_g} target={recommendation.progress.target.fat_g} color="gold" />
                  </div>
                </div>

                <div className="plate-list">
                  {recommendation.plate.length ? recommendation.plate.map((item) => (
                    <FoodRow key={item.id} item={item} disabled={plateLocked} canSwap={recommendation.data_source === "nutrislice"} onUnavailable={() => findAlternative(item.id)} checked={completed.has(item.id)} onCheck={() => setCompleted((current) => { const next = new Set(current); next.has(item.id) ? next.delete(item.id) : next.add(item.id); return next; })} onServings={(value) => setServings(item.id, value)} />
                  )) : <div className="empty-plate"><WheatOff size={26} /><strong>{recommendation.target_calories === 0 ? "Daily goal reached" : "No matching plate found"}</strong><p>{recommendation.target_calories === 0 ? "You can still log anything else you eat. Calorie needs vary; this is a planning guide, not a limit on eating." : "Try another hall or revisit your dietary settings. Always ask dining staff for help."}</p></div>}
                </div>

                <div className="log-meal-panel"><p>{logged ? "Meal saved to your account. View it in My progress." : recommendation.data_source === "demo" ? "Sample menus cannot be logged as meals. Refresh to retrieve live menu data." : `${completed.size} items selected · ${Math.round(recommendation.plate.filter(item => completed.has(item.id)).reduce((sum, item) => sum + item.line_nutrition.calories, 0))} estimated kcal. Only log what you actually ate.`}</p><button className="button primary" disabled={savingMeal || swapping || logged || (!pendingLog.current && (!completed.size || recommendation.data_source === "demo"))} onClick={recordMeal}>{savingMeal ? "Saving meal…" : logged ? "Meal logged ✓" : pendingLog.current ? "Retry saving meal" : "Log eaten items"}</button>{logged && <button className="journal-link" onClick={() => navigate("history")}>View meal history <ArrowRight size={15} /></button>}</div>

                <div className="safety-footer"><ShieldCheck size={20} /><div><strong>Allergen guard is on</strong><p>{recommendation.safety_message}</p></div><span>{recommendation.excluded_for_allergies} excluded</span></div>
              </section>

              <aside className="side-column">
                <div className="daily-card">
                  <div className="card-heading"><div><span>Daily targets</span><strong>Your bigger picture</strong></div><CircleUserRound size={21} /></div>
                  <DailyStat label="Calories" value={`${profile.daily_calorie_goal.toLocaleString()} kcal`} detail="daily target" />
                  <DailyStat label="Protein" value={`${profile.protein_goal_g} g`} detail={`${Math.round(total.protein_g)} g on this plate`} />
                  <DailyStat label="Fiber" value={`${profile.fiber_goal_g} g`} detail={`${Math.round(total.fiber_g)} g on this plate`} />
                  <DailyStat label="Sodium" value={`< ${profile.sodium_limit_mg.toLocaleString()} mg`} detail={`${Math.round(total.sodium_mg)} mg on this plate`} />
                  <button className="text-button" onClick={onEdit}>Edit nutrition targets <ArrowRight size={15} /></button>
                </div>
              </aside>
            </motion.div>
          )}
        </AnimatePresence>
        </>}
      </main>
      <footer><span>Dine&amp;Dash uses menu data published through Nutrislice.</span><span>Nutrition is an estimate, not medical advice.</span></footer>
      <nav className="mobile-tabbar" aria-label="Mobile navigation">
        <button className={activeView === "today" ? "active" : ""} onClick={() => navigate("today")}><House size={21} /><span>Today</span></button>
        <button disabled={!hallAvailable} className={activeView === "plate" ? "active" : ""} onClick={() => navigate("plate")}><ClipboardList size={21} /><span>My plate</span></button>
        <button className={activeView === "history" ? "active" : ""} onClick={() => navigate("history")}><UserRound size={21} /><span>My progress</span></button>
      </nav>
    </div>
  );
}

function TodayOverview({ recommendation, profile, currentHall, onOpenPlate }: { recommendation: Recommendation; profile: Profile; currentHall: Hall; onOpenPlate: () => void }) {
  const total = recommendation.progress.total;
  const previewItems = recommendation.plate.slice(0, 3);
  return (
    <motion.section className="today-overview" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ type: "tween", duration: 0.18 }}>
      <article className="today-plan-card">
        <div className="today-plan-copy">
          <span className="meal-source"><span className={recommendation.data_source === "nutrislice" ? "live-dot" : "demo-dot"} />{recommendation.data_source === "nutrislice" ? "Today’s menu" : "Sample menu"} · {formatDate(recommendation.date)}</span>
          <h2>{titleCase(recommendation.meal)} at {currentHall.short_name}</h2>
          <div className="today-macros">
            <span><strong>{Math.round(total.calories)}</strong> kcal</span>
            <span><strong>{Math.round(total.protein_g)}g</strong> protein</span>
            <span><strong>{recommendation.plate.length}</strong> items</span>
          </div>
          <div className="preview-list">
            {previewItems.map((item) => <div key={item.id}><p>{item.name}</p><strong>{item.portion_label}</strong></div>)}
          </div>
          <button className="button mobile-cta" onClick={onOpenPlate}>View my plate <ArrowRight size={17} /></button>
        </div>
      </article>
      {recommendation.planning_note && <p className="journal-status">{recommendation.planning_note}</p>}
      {recommendation.note && <p className="menu-note">{recommendation.note}</p>}
      <div className="today-safety-card"><ShieldCheck size={18} /><div><strong>{profile.allergies.length ? `Avoiding ${profile.allergies.join(", ")}` : "No allergies saved"}</strong><span>Confirm ingredients and cross-contact with dining staff.</span></div></div>
    </motion.section>
  );
}

function FoodRow({ item, checked, disabled, canSwap, onUnavailable, onCheck, onServings }: { item: PlateItem; checked: boolean; disabled: boolean; canSwap: boolean; onUnavailable: () => void; onCheck: () => void; onServings: (value: number) => void }) {
  return (
    <article className={`food-row ${checked ? "checked" : ""}`}>
      <button className="food-check" disabled={disabled} onClick={onCheck} aria-pressed={checked} aria-label={`Mark ${item.name} eaten`}>{checked && <Check size={16} />}</button>
      <div className={`food-icon ${item.category}`}><FoodGlyph category={item.category} /></div>
      <div className="food-info"><div className="food-title"><h3>{item.name}</h3>{item.dietary_tags.slice(0, 1).map((tag) => <span key={tag}>{tag.replace("-", " ")}</span>)}</div><p>{item.station} · {item.why}</p><div className="food-macros"><span><strong>{Math.round(item.line_nutrition.calories)}</strong> kcal</span><span><strong>{Math.round(item.line_nutrition.protein_g)}g</strong> protein</span><span><strong>{Math.round(item.line_nutrition.carbs_g)}g</strong> carbs</span></div></div>
      <div className="portion-control"><span>Portion</span><strong>{item.portion_label}</strong><div><button onClick={() => onServings(Math.max(0.5, item.servings - 0.5))} disabled={disabled || item.servings <= 0.5} title="Decrease portion"><Minus size={14} /></button><span>{item.servings}×</span><button onClick={() => onServings(Math.min(3, item.servings + 0.5))} disabled={disabled || item.servings >= 3} title="Increase portion"><Plus size={14} /></button></div></div>
      <button className="unavailable-button" disabled={disabled || !canSwap} onClick={onUnavailable} aria-label={`${item.name} is not available`}>Not available · Find alternatives</button>
    </article>
  );
}

function FoodGlyph({ category }: { category: string }) {
  if (category === "vegetable") return <Leaf size={22} />;
  if (category === "grain") return <span className="grain-glyph">•••</span>;
  if (category === "protein") return <span className="protein-glyph">P</span>;
  return <Utensils size={20} />;
}

function ProgressRing({ value, label, sublabel }: { value: number; label: string; sublabel: string }) {
  const circumference = 2 * Math.PI * 47;
  return (
    <div className="progress-ring">
      <svg viewBox="0 0 110 110" aria-hidden="true"><circle className="ring-track" cx="55" cy="55" r="47" /><motion.circle className="ring-fill" cx="55" cy="55" r="47" strokeDasharray={circumference} initial={{ strokeDashoffset: circumference }} animate={{ strokeDashoffset: circumference * (1 - value / 100) }} transition={{ duration: 0.75, ease: "easeOut" }} /></svg>
      <div><strong>{label}</strong><small>{sublabel}</small></div>
    </div>
  );
}

function MacroBar({ label, value, target, color }: { label: string; value: number; target: number; color: string }) {
  const reduceMotion = useReducedMotion();
  const percent = Math.min(100, value / Math.max(target, 1) * 100);
  return <div className="macro-bar"><div><span>{label}</span><strong>{Math.round(value)}<small> / {Math.round(target)}g</small></strong></div><div className="bar-track"><motion.span className={color} initial={false} animate={{ scaleX: percent / 100 }} transition={{ type: "tween", duration: reduceMotion ? 0 : 0.25, ease: "easeOut" }} /></div></div>;
}

function DailyStat({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="daily-stat"><span>{label}</span><div><strong>{value}</strong><small>{detail}</small></div></div>;
}

function PlateSkeleton() {
  return <div className="dashboard-grid"><section className="plate-card skeleton-card"><div className="skeleton wide" /><div className="skeleton medium" /><div className="skeleton-block" />{[1, 2, 3].map((item) => <div className="skeleton-row" key={item}><div className="skeleton circle" /><div><div className="skeleton medium" /><div className="skeleton short" /></div></div>)}</section><aside className="side-column"><div className="skeleton-side" /><div className="skeleton-side tall" /></aside></div>;
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return <div className="error-state"><AlertTriangle size={28} /><h2>Plate planner paused</h2><p>{message}</p><button className="button primary" onClick={onRetry}><RefreshCw size={17} /> Try again</button></div>;
}

function emptyNutrition(): Nutrition { return { calories: 0, protein_g: 0, carbs_g: 0, fat_g: 0, fiber_g: 0, sodium_mg: 0 }; }
function scaleNutrition(nutrition: Nutrition, factor: number): Nutrition { return Object.fromEntries(Object.entries(nutrition).map(([key, value]) => [key, value * factor])) as Nutrition; }
function addNutrition(a: Nutrition, b: Nutrition): Nutrition { return Object.fromEntries(Object.keys(a).map((key) => [key, a[key as keyof Nutrition] + b[key as keyof Nutrition]])) as Nutrition; }
function portion(item: PlateItem, servings: number) { const amount = item.serving_amount * servings; return `${Number.isInteger(amount) ? amount : amount.toFixed(1)} ${item.serving_unit}${amount > 1 && ["cup", "piece", "slice", "serving"].includes(item.serving_unit) ? "s" : ""}`; }
function dayPart() { const hour = new Date().getHours(); return hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"; }
function titleCase(value: string) { return value.charAt(0).toUpperCase() + value.slice(1); }
function formatDate(value: string) { return new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" }).format(new Date(`${value}T12:00:00`)); }
