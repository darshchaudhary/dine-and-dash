# Dine&Dash

Dine&Dash turns the menu currently published for Georgia Tech's three dining halls into a practical, personalized plate: what to take, how much to take, and how that meal fits the user's calorie and macro targets.

The app includes:

- A three-step onboarding survey for calorie, macro, fiber, sodium, dietary, and allergy settings
- PostgreSQL profile persistence through a Python 3.12 FastAPI service
- Live Nutrislice integration for Brittain, North Avenue, and West Village
- Automatic meal selection based on the current time in `America/New_York`
- Allergen and dietary filtering before recommendation scoring
- A bounded integer plate optimizer with practical portions, meal structure, calorie and macro targets, and a validated beam-search fallback
- Account-owned meal plans, likes/dislikes, kept foods, diverse alternatives, and remaining-day nutrient planning
- Honest handling of missing upstream nutrition and a clearly labeled demo fallback
- A responsive React interface with keyboard-friendly controls and reduced-motion support

See [the plate planner guide](PLATE_PLANNER.md) for the algorithm, controls, API, deployment, and real-menu benchmark.

## Architecture

```text
React + TypeScript (Vite)
        │
        ▼
FastAPI /api
   ├── PostgreSQL user_profiles
   ├── Nutrislice menu adapter + 5-minute cache
   └── allergy filter → plate optimizer
```

## Run locally

For a demo on this Mac and an iPhone on the same Wi-Fi, run from the project root:

```bash
zsh ./demo.sh
```

This starts Docker's PostgreSQL service, FastAPI on port **8001**, and the frontend on port **5173**, using the bundled Node runtime if necessary. Open the printed phone URL in Safari and complete (or re-save) the setup survey to store your profile in PostgreSQL. Keep the terminal and Mac running during the demo; Ctrl+C stops the web/API processes. Sample fallback meals are labeled in the app when live menu data is unavailable.

For a native iPhone demo, keep that command running and use a second terminal:

```bash
cd frontend
API_PORT=8001 ./ios.sh device
```

Select your connected iPhone and signing team in Xcode, then Run. Rebuild if the Mac's IP changes. Browser previews do not require Xcode.

Requirements: Python 3.12, Node.js 20+, pnpm (or npm), and Docker.

1. Copy the environment defaults:

   ```bash
   cp .env.example .env
   ```

2. Start PostgreSQL:

   ```bash
   docker compose up -d db
   ```

3. Start the API:

   ```bash
   python3.12 -m venv .venv
   .venv/bin/pip install -r backend/requirements.txt
   .venv/bin/uvicorn backend.app.main:app --reload --port 8000
   ```

4. Start the web app in another terminal:

   ```bash
   cd frontend
   pnpm install
   pnpm dev
   ```

Open [http://localhost:5173](http://localhost:5173). FastAPI documentation is available at [http://localhost:8000/docs](http://localhost:8000/docs).

## Preview on an iPhone browser

Dine&Dash is an installable Progressive Web App with a standalone phone layout, home-screen icon, safe-area support, offline app shell, and bottom-tab navigation.

Put the Mac and iPhone on the same Wi-Fi network, then run the API on the Mac:

```bash
docker compose up -d db
.venv/bin/uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

In a second terminal, expose the frontend to the local network:

```bash
cd frontend
pnpm dev:phone
```

Vite prints a **Network** URL such as `http://192.168.1.20:5173`. Open that URL in Safari on the iPhone. The frontend automatically sends API requests to port `8000` on the same Mac. For a deployed HTTPS build, use Safari's **Share → Add to Home Screen** to install the PWA.

The **My plate** tab is a real application view backed by `#plate`, so it works from the desktop app bar, the mobile bottom bar, direct links, and the installed-app shortcut.

## Run the native iOS app

For an iPhone app that works when your Mac is off or on a different network, see [the hosted API setup](DEPLOYMENT.md). Once hosting is configured, `./ios.sh release` checks the public API and prepares an Xcode build. The local demo commands below do not provide always-on hosting.

The frontend includes a Capacitor 7 iOS shell in `frontend/ios`. Capacitor 7 is used because it supports Xcode 16 and iOS 14 or newer.

### iOS Simulator

```bash
cd frontend
./ios.sh simulator
```

In Xcode, select an iPhone Simulator in the run-destination menu and press **Run**. If no simulator is listed, install an iOS runtime from **Xcode → Settings → Components**.

### Your physical iPhone

Keep the API running on `0.0.0.0:8000`, connect the Mac and iPhone to the same Wi-Fi, then prepare a device build:

```bash
cd frontend
./ios.sh device
```

Connect the iPhone by USB for the first run. In Xcode:

1. Open **Xcode → Settings → Accounts** and add your Apple Account.
2. Select the **App** target, open **Signing & Capabilities**, and choose your development team. Change `com.plateful.gatech` if Xcode says the bundle ID is unavailable.
3. Select the connected iPhone as the run destination and press **Run**.
4. If prompted, enable **Developer Mode** on the iPhone under **Settings → Privacy & Security**.

The launcher uses Codex's bundled Node and pnpm runtime when those commands are not installed globally. Its `device` mode detects the Mac's Wi-Fi address and builds that address into the development app so the phone can reach FastAPI. Re-run it whenever the Mac's Wi-Fi address changes. After the first cable pairing, Finder's **Show this iPhone when on Wi-Fi** option enables wireless Xcode runs.

## Nutrislice connection

The adapter uses Georgia Tech's currently published Nutrislice host:

```text
https://techdining.api.nutrislice.com
```

Configured dining locations:

| Hall | Nutrislice school ID | Menu services |
| --- | ---: | --- |
| Brittain Dining Hall | 40536 | Lunch, dinner |
| North Ave Dining Hall | 40132 | Breakfast, lunch, dinner, overnight |
| West Village | 40126 | Breakfast, lunch, dinner |

If the live service is unavailable or has no published items, the API returns `source: "demo"` with an explanatory note. Items without credible calories and macros remain visible in raw menus but are never used by the optimizer.

## Verify

```bash
cd backend && ../.venv/bin/pytest -q
cd frontend && pnpm run build
```

## Safety

Allergen matching uses Nutrislice's allergen icons plus an ingredient-text fallback. It is a screening aid, not a guarantee against recipe changes or cross-contact. The product keeps a persistent warning visible and directs users to confirm labels and ask dining staff before eating.
