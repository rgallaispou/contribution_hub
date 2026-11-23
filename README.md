# Contribution Hub

A self-hosted dashboard for open-source mailing-list activity. This workspace combines the downloaded FastAPI/SQLAlchemy project with a Next.js dashboard. It imports mailbox archives, groups messages into patch series, attributes activity to configured email identities, and suggests possible replies for human review.

## Start with Docker Compose

Requires Docker Compose.

```bash
cp .env.example .env
docker compose up --build
```

Open the dashboard at http://localhost:3000 and the API docs at http://localhost:8000/docs. Both published ports bind to localhost.

To import an archive, place its `.mbox` file in `./imports`, then run:

```bash
curl -X POST "http://localhost:8000/api/import/mbox?path=archive.mbox"
```

Repeated imports are safe: messages are deduplicated by Message-ID. The dashboard refreshes its data after an import initiated from its import dialog.

## Local development

Run the API with SQLite:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=sqlite:///./data/contributions.db uvicorn app.main:app --reload
```

In another terminal, run the web app:

```bash
npm install
API_URL=http://127.0.0.1:8000 npm run dev
```

Open http://localhost:3000. The Next.js server proxies `/api/*` to FastAPI, so browser requests stay same-origin.

## Configure identities

Copy `.env.example` to `.env` and set `IDENTITIES` to the comma-separated email addresses whose activity should be attributed to you. The Compose configuration uses PostgreSQL; local development can use the SQLite override shown above. Do not add mail passwords or SMTP credentials.

## Data and limitations

This is an mbox importer, not a complete Lore-wide historical crawler. Lore archives are distributed across public-inbox instances, and searching a small set of addresses does not establish exhaustive coverage. Start with mailbox exports, validate the imported results, then add a rate-limited, paginated discovery adapter per archive before claiming complete history.

Patch series grouping is conservative and subject-based. Production reconciliation should use B4 patch IDs, `Link:` trailers, and explicit revision relationships. “Reply suggestions” are heuristic prompts, not confirmed obligations; the dashboard lets a person mark them done or dismiss them. The app does not infer that a patch was accepted or applied.

B4 remains an external companion for retrieving complete threads and validating patch-series relationships. See the [B4 documentation](https://b4.docs.kernel.org/en/latest/).

## API

- `GET /api/health`
- `GET /api/identities`
- `GET /api/dashboard/overview`
- `GET /api/identities/{email}/statistics`
- `GET /api/contributions`
- `GET /api/reply-tasks`
- `PATCH /api/reply-tasks/{id}`
- `POST /api/import/mbox?path=...`

## Security

Authentication is not included. Keep this bound to localhost or behind an authenticated reverse proxy/VPN. Before public deployment, add authentication, request protections, rate limiting, backups, and secrets management. Never expose the mbox import endpoint to untrusted users.