# Ulai Voice Studio

Build, test and run AI voice agents on **Ulai Voice Infra**: design an agent, talk to it in the browser, give it phone numbers, and place calls through your SIP trunks. Every call keeps its live transcript, tool calls and outcome.

One admin account, no sign-up. No LiveKit anywhere (`scripts/check-no-livekit.sh` enforces it).

## What's in it

- **Agents.** Prompt, greeting and closing with `{{variables}}`; who speaks first; Gemini voice, model, language and temperature; interruptions, silence and backchannel handling, background noise, voicemail detection, maximum call length; and **tools**, webhooks the agent can call mid-conversation.
- **Test calls in the browser**, beside the agent editor, with live transcript and agent state.
- **Phone numbers.**
  - **Inbound trunks:** assign an agent and it answers calls to those numbers.
  - **Outbound trunks:** your SIP provider plus the caller IDs you may use.
- **Calls.** Outbound dialling with a ring timeout. Live history with filters, search and CSV export, and a per-call timeline of what was said, the tools used with their results, and status changes.
- **Overview.** Today's and this week's volume, answer rate, durations, and system status.

## How it works

```
Browser ──(ulai-js-sdk: WebRTC audio)──────────────▶ Ulai media node
   │
   └─ /api ─▶ Next.js ─▶ FastAPI backend ──(ulai-api SDK)──▶ Ulai: sessions, SIP trunks,
                              │                              dispatch rules, hosted Gemini agents
                              └─▶ Postgres
```

- **The backend owns the agents**, because Ulai doesn't store them. For each call it sends the agent's profile (prompt, voice, tools, Gemini credentials) to Ulai's hosted agent, then attaches to the call's event stream. It saves the transcript and answers tool calls by calling the tool's URL.
- **Web calls.** The backend creates the session, puts the agent in it, and hands the browser a short-lived join ticket. The Ulai API key never reaches the browser.
- **Outbound calls.** The backend creates the session, joins the agent, dials through the trunk, and follows the phone leg on Ulai's control plane to see pick-up and hang-up.
- **Inbound calls.** Each inbound trunk with an agent gets a Ulai dispatch rule. The backend subscribes to call assignments for those agents and attaches with the agent's profile when a call arrives.
- **Restarts.** The backend picks in-flight calls back up on restart. Ulai replays each call's history, and lines already saved aren't stored twice.

## Run it

You need Docker, a checkout of the private `ulai-python-sdk` next to this repo (`../ulai-cloud-python-sdk`, or set `ULAI_SDK_PATH`), a Ulai API key, and a Google Cloud service account for Gemini.

1. **Google credentials.** Save the service account key as `credentials/google-service-account.json`. It's git-ignored and mounted read-only.
2. **Configuration.** Run `cp .env.example .env`, then fill it in:
   - `ADMIN_PASSWORD_HASH`: run `cd backend && python -m app.auth hash-password` (needs the dev setup below, or `pip install bcrypt`). Keep the single quotes around the hash.
   - `SESSION_SECRET`: `openssl rand -hex 32`
   - `POSTGRES_PASSWORD` and `ULAI_API_KEY`
   - `COOKIE_SECURE=false` only if you open it over plain `http` in Safari.
3. **Start it:**
   ```sh
   docker compose up --build -d
   ```
   Open http://localhost:3000 and sign in. Migrations run automatically.

The **Overview** page's status card tells you if the Ulai key, the Google credentials or the inbound listener needs attention.

## Develop

```sh
# Backend: Python 3.11
cd backend
python3.11 -m venv .venv
.venv/bin/pip install -e '.[dev]' -e ../../ulai-cloud-python-sdk
.venv/bin/alembic upgrade head          # needs DATABASE_URL pointing at a Postgres
.venv/bin/uvicorn app.main:create_app --factory --reload --port 8000
.venv/bin/pytest                         # runs against SQLite with a fake Ulai; no network
.venv/bin/ruff check app tests

# Frontend: Node 20+
cd frontend
npm install
npm run dev                              # http://localhost:3000, proxies /api to BACKEND_URL (default :8000)

# Whole repo
./scripts/check-no-livekit.sh
```

## Security notes

- **Login:** one admin, from config. The password is checked against a bcrypt hash in constant time. Sessions are signed, HttpOnly, SameSite=Lax cookies, Secure by default. After 5 failed logins from an address, it's locked out for 15 minutes.
- **Secrets:** the Ulai API key, SIP trunk passwords (stored by Ulai, never here), TURN credentials and the Google key stay on the server. `.env` and `credentials/` are git-ignored.
- **Ports:** the backend isn't published by Docker Compose; only the frontend's port is.

## Known limits

- **No recordings yet:** Ulai Voice Infra doesn't produce call recordings, so calls have transcripts but no audio.
- **Models:** the list contains the Gemini model Ulai's hosted agents are known to run (`app/catalog.py`). Add others there once Ulai supports them.
- **Outbound dialling:** goes to `ULAI_SIP_ORIGINATE_URL`. The Python SDK hard-codes that address, so the studio makes the request itself.
