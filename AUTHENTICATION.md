# Dine&Dash authentication

Email/password registration and login are available at `/api/auth/register` and
`/api/auth/login`. Passwords are 15–128 characters and stored as Argon2id hashes.
Account IDs are generated on the server. Legacy anonymous profile IDs cannot be
claimed by a new account: complete the survey again after registering.

Sessions expire after seven days and are revocable through `/api/auth/logout`.
Only SHA-256 digests of randomly generated 256-bit session tokens are stored in
PostgreSQL. Browser sessions use Secure, HttpOnly cookies; iPhone sessions use
the device-only Keychain through the bundled SessionVault plugin. Passwords and
session tokens are never persisted in browser localStorage. Native bridge logging
is disabled to keep session values out of Xcode logs.

All profile reads/writes and recommendation requests require authentication and
matching account ownership. Invalid sessions never fall back to anonymous cached
profiles. Profile saves report network failures rather than pretending to save.
Menu demonstration fallback remains visibly labeled sample data.

Meal history (`/api/meals`) is also account-owned. The server derives ownership
from the session, never a submitted account ID. Meal logs snapshot the selected
foods, portions, calorie estimates, dining hall, and consumption timestamp; the
server sums item calories. The client generates a UUID per logging attempt so
retries do not count a meal twice. Removing a mistaken meal marks it voided and
retains the retry key. Daily/week summaries use America/New_York boundaries,
including daylight-saving transitions. No recommendation is logged implicitly,
and sample-menu logging is disabled in the app.

“Not available” rebuilds a plate excluding the user-marked food IDs while retaining
the meal calorie target and saved allergy/diet filters. This does not verify actual
station inventory. Users must confirm availability and allergen safety with staff.
The app does not silently substitute sample food if live alternatives fail.

Current-menu planning also checks the hall's configured opening hours server-side
and blocks closed halls with HTTP 409, regardless of client timestamps. The UI
rechecks hours every 30 seconds and on foregrounding. Hours are the configured
regular schedule, not a live holiday/closure feed.

Extra foods are searched through authenticated `/api/meals/menu` using the hall,
server's current Eastern date/service, and case-insensitive name/station terms.
`/api/meals/from-menu` validates selections against that current menu and computes
calories from published nutrition and user-confirmed servings. Stale services,
unknown foods, incomplete nutrition, and demo menus are rejected. Retry UUIDs use
the same account-owned idempotency mechanism as ordinary plate logging.

“Log a past meal” is available on Today and My progress. Users choose a hall,
breakfast/lunch/dinner, and a local Eastern date/time. Authenticated
`/api/meals/past-menu` fetches that exact published date/service; it never falls
back to today's or demonstration foods. `/api/meals/from-past-menu` validates
the same selection and computes calories server-side before saving the original
consumption timestamp. Future times, nonexistent daylight-saving times, closed
regular-schedule hours, mismatched services, and unavailable historical menus
are rejected. Historical menus describe published offerings, not minute-by-minute
stock or exceptional holiday hours. Backdated meals update their original day
and week; only meals dated today affect today's remaining recommendation budget.
These records use the existing meal table, ownership, retry keys, and removal flow.

Recommendations sum all non-voided meals for the signed-in account's current
Eastern day, including extras, then allocate remaining daily calories across the
current and later services using breakfast/lunch/dinner weights 25/35/40. Targets
are capped at 2,500 kcal per plate. The saved daily goal is not changed. Reaching
the goal suppresses calorie-targeted suggestions but does not prohibit recording
more food. Macro targets are scaled to the adjusted meal calories; macro intake
is not currently tracked in meal logs. Published availability and nutrition are
estimates, not a real-time station inventory or medical guidance.

## Deployment

The existing `DATABASE_URL` secret and `PGSSLROOTCERT` variable are preserved.
`COOKIE_SECURE` defaults to true. Set it to false only for local HTTP development.
Set `FRONTEND_ORIGIN` to the exact web origin when deploying a web frontend.
`capacitor://localhost` and the localhost Vite origins are also explicitly allowed.
Browser mutations require an allowed Origin (if supplied) and the custom
`X-DineDash-Client` header. Native clients use a bearer session token.

The new accounts, auth_sessions, and auth_rate_buckets tables are additive; no
existing profiles are dropped or reassigned. Initialization uses the project's
existing SQLAlchemy create_all flow. Adopt versioned migrations before expanding
the schema further. The current database runtime role is the existing demo admin;
move to a least-privilege application role before a wider production launch.

Login limits are 10 attempts per email per 15 minutes and 60 per source address
per 15 minutes. Registration allows 10 per source address per hour. Counters are
atomic and persisted in PostgreSQL across workers and restarts. Source addresses
come from ASGI request.client, not untrusted forwarded headers; reverse proxies
may share a limit until trusted proxy handling is explicitly configured.

## Limitations

This is demo-ready authentication, not a complete identity platform. There is no
email verification, forgotten-password recovery, MFA, or self-service account
deletion yet. Email addresses identify accounts but do not prove email ownership.
The registration screen explains the lack of verification and recovery. Do not
claim Georgia Tech affiliation or verified student status from an email address.
Account deletion and recovery should be added before App Store/public launch.

## Checks

Run `../.venv/bin/pytest -q` from backend and `pnpm run build` from frontend.
Tests cover credential hashing, duplicate registration, login failures, ownership,
legacy-ID protection, cookies/CSRF, session expiry/revocation, request-size limits,
rate limiting, and validation responses that do not echo submitted passwords.
