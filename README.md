# Sentinel

Sentinel is a credit-card fraud scoring service with a human review workflow. It
accepts a transaction containing `Time`, `V1` through `V28`, and `Amount`, scores it
with XGBoost, stores the top three SHAP contributions for flagged transactions, and
lets an analyst review the result through a small React dashboard.

## Current model results

These are the committed results from the untouched 20% test split in
[`models/metrics.json`](models/metrics.json):

| Metric | Test result |
|---|---:|
| PR-AUC | 0.8639 |
| Precision | 0.9639 |
| Recall | 0.8081 |
| Tuned threshold | 0.9430 |
| Test fraud rate | 0.1738% |
| Confusion matrix | [[56860, 3], [19, 80]] |

Accuracy is not used because the dataset is highly imbalanced. The threshold is
tuned on validation data; the test set is used only once for the final report.
Recall is uncertain because the test set contains only 99 fraud cases.

## Architecture

- FastAPI and Pydantic validate and score requests.
- SQLAlchemy supports SQLite locally and PostgreSQL in Compose.
- API keys protect admin ingestion; the analyst dashboard is intentionally open for this demo.
- A unique idempotency key makes retries safe and rejects payload reuse.
- XGBoost is the primary scorer; an `Amount > 2000` rule is an explicit availability fallback.
- SHAP explanations name anonymized PCA features such as `V14`; they are not business concepts.
- Groq summaries are checked for allowed numbers and feature names. Invalid or unavailable
  LLM output falls back to a deterministic template.
- Reviews are append-only rows in the `reviews` audit table.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
$env:ADMIN_API_KEY="local-admin"
uvicorn app.main:app --reload
```

The API is at `http://localhost:8000`. The React development UI runs separately.
Open the dashboard and click **Load demo transactions**; no analyst key or seed script
is needed. The button creates ten bounded demo transactions.

```powershell
cd dashboard
npm install
npm run dev
```

Set `VITE_API_URL=http://localhost:8000` if the dashboard is served from another
origin. The API permits the Vite origin for local development.

## API examples

```powershell
$headers = @{ "X-API-Key" = "local-admin" }
$body = Get-Content tests\sample_rows.json | ConvertFrom-Json
curl.exe -X POST http://localhost:8000/transactions -H "X-API-Key: local-admin" `
  -H "Content-Type: application/json" `
  -d (@{ idempotency_key = "demo-00000001"; features = $body.legit } | ConvertTo-Json -Depth 4)
curl.exe http://localhost:8000/health
```

Endpoints:

| Method | Path | Role | Purpose |
|---|---|---|---|
| GET | `/health` | none | Service/model health |
| POST | `/transactions` | admin | Validate and score a transaction |
| GET | `/flags` | public | List flagged transactions |
| POST | `/flags/{id}/review` | public | Append a review decision |
| POST | `/flags/{id}/summary` | public | Generate a grounded case note |
| GET | `/stats` | public | Hourly, bucket, and review aggregates |
| POST | `/demo/seed` | public | Add ten bounded demo transactions |

## Test and lint

Tests are offline and monkeypatch network/model failure paths where needed:

```powershell
pytest --cov=app
ruff check .
```

The CI workflow runs both checks and builds the dashboard. The repository does not
claim a coverage or latency number unless the command is run; use
[`scripts/latency.py`](scripts/latency.py) against a running server for local
measurements.

## Docker and EC2

For PostgreSQL Compose and the single-instance EC2 procedure, see
[`DEPLOY.md`](DEPLOY.md). Docker requires a built dashboard because the API serves
`dashboard/dist` when that directory exists.

## Limitations

- This is a portfolio demonstration, not a production banking system.
- The Kaggle data is historical and anonymized; it does not establish real-world
  performance or fairness.
- The rules fallback is intentionally crude and should trigger operational alerts.
- The LLM grounding checker constrains numbers and feature names, but does not verify
  semantic truth or detect every misleading sentence.
- Admin ingestion is protected by a shared API key, but dashboard reads and reviews are
  intentionally public for this demo. Do not expose this mode to sensitive data without
  adding analyst authentication, TLS, rate limits, and stronger observability.
- The current schema is created automatically and has no migration history.
