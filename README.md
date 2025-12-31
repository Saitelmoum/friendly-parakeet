# friendly-parakeet

Celery stack providing structured tasks for job collection, enrichment, application generation, and email workflows.

## Setup

1. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

2. Export broker and backend configuration (defaults use Redis):

   ```bash
   export CELERY_BROKER_URL=redis://localhost:6379/0
   export CELERY_RESULT_BACKEND=redis://localhost:6379/1
   export DEFAULT_RATE_LIMIT="30/m"
   export SOURCE_RATE_LIMITS='{"indeed": "10/m", "linkedin": "5/m"}'
   export METRICS_PORT=9100
   ```

## Running workers

Start a Celery worker with structured logging and metrics:

```bash
celery -A app.celery_app worker --loglevel=info
```

Metrics will be exposed on the configured `METRICS_PORT` (Prometheus format).

## Available tasks

All tasks support exponential retries and per-source throttling.

- `collect_jobs(source: str, parameters: dict | None = None)`
- `enrich_contacts(source: str, contacts: dict)`
- `generate_application(source: str, job: dict, applicant: dict)`
- `draft_email(source: str, application: dict)`
- `send_email(source: str, email: dict)`

Each task logs structured events; metrics capture task start/completion/failure counts and duration.
