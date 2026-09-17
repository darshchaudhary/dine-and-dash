# An iPhone app that does not depend on your Mac

Xcode installs the frontend, not FastAPI or PostgreSQL. Independent operation requires a public HTTPS API and a persistent PostgreSQL service. Neither the API nor database should scale to zero or sleep when idle. Internet connectivity is still required; hosting cannot guarantee uninterrupted availability or Nutrislice uptime.

## Current Azure deployment

The authenticated API is deployed at `https://dinedash-api.redhill-14ba802e.northcentralus.azurecontainerapps.io` in Container App `dinedash-api`, resource group `dinedash-demo`. PostgreSQL database `dinedash` is hosted on `dinedash-db-darsh`. HTTPS ingress targets port 8000; the database connection uses TLS certificate verification. The API currently has one minimum and one maximum replica.

Registration, login, logout, and account-owned profiles are implemented. See [AUTHENTICATION.md](AUTHENTICATION.md) for security details and remaining production requirements, including email verification and password recovery. Existing anonymous profiles are not automatically assigned to new accounts.

## Hosting configuration

Choose a container host and PostgreSQL plan before provisioning anything billable. The repository includes a Python 3.12 container:

```bash
docker build -f backend/Dockerfile -t plateful-api .
```

Configure the host with the repository root as the build context and `backend/Dockerfile` as the Dockerfile. Set these environment variables in the hosting dashboard, not in the app bundle:

- `DATABASE_URL`: your managed PostgreSQL connection string. `postgres://`, `postgresql://`, and `postgresql+asyncpg://` are accepted. For providers requiring a TLS query option with asyncpg, use `?ssl=require`; consult the provider for its CA/verification requirements.
- `FRONTEND_ORIGIN`: the public web frontend origin, if any. `capacitor://localhost` is already allowed for iOS.
- `PORT`: the port supplied by your host (defaults to 8000).
- `NUTRISLICE_BASE_URL`: `https://techdining.api.nutrislice.com` (already the default).

Use `/health/ready` as the readiness/health-check path. It checks the database; `/health` only checks the API process. Configure automatic restarts, a minimum of one running API instance, a non-sleeping database with persistent storage, and backups. The container does not include your local `.env`, database, or user profiles.

**Before a broader public rollout:** complete the production checklist in `AUTHENTICATION.md`. Existing local PostgreSQL records are not automatically migrated.

## Install with the hosted API

After the hosted `/health/ready` returns `{"status":"ok","database":"ok"}`, create `frontend/.env.production.local` with the real API base URL (no `/api` suffix):

```dotenv
VITE_API_URL=https://YOUR-HOSTED-API-DOMAIN
```

This file is ignored by Git. The URL itself is public configuration, not a secret. Never put database credentials or private service keys into any `VITE_` variable.

Then run:

```bash
cd frontend
./ios.sh release
```

This command rejects local/HTTP API addresses, verifies hosted API/database readiness, rebuilds the web bundle, copies it into iOS, and opens Xcode. Select your iPhone and press **Run**. No Mac network address is needed. Create an account and save your goals to create your account-owned profile in the hosted database.

To verify independence, turn off Wi-Fi on the phone, use cellular data, and stop the local Mac API. Relaunch, save goals, and refresh the menu. Confirm the API receives those requests; a labeled sample menu alone is not evidence of connectivity, and a reachable API can still return a sample fallback when Nutrislice is unavailable.

For local-only development, `API_PORT=8001 ./ios.sh device` still works but requires the Mac to stay awake and reachable. A `VITE_API_URL` configured in the environment or `frontend/.env.production.local` takes precedence over local address detection. Installing a new bundle through Xcode is required after changing the URL.
