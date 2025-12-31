# friendly-parakeet

Un petit service FastAPI qui expose des métriques Prometheus pour un pipeline de mails
et envoie des alertes via webhook (Slack ou autre).

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Démarrage

```bash
uvicorn app.server:app --reload --host 0.0.0.0 --port 8000
```

- Santé : `GET /health`
- Capture d'événements :
  - `POST /events/job-found` `{ "source": "crawler" }`
  - `POST /events/email-draft` `{ "campaign": "welcome" }`
  - `POST /events/send-validated` `{ "campaign": "welcome" }`
  - `POST /events/error` `{ "stage": "compose", "reason": "timeout" }`
  - `POST /events/retry` `{ "stage": "compose" }`
- Instantané JSON : `GET /metrics/snapshot`
- Export Prometheus : `GET /metrics`

## Métriques clés

- `email_jobs_found_total{source}` : jobs trouvés
- `email_drafts_created_total{campaign}` : brouillons créés
- `email_send_validated_total{campaign}` : envois validés
- `processing_errors_total{stage,reason}` : erreurs par étape/raison
- `processing_retry_attempts_total{stage}` : retries
- `processing_error_rate{window="lifetime"}` : taux d'erreur global
- `processing_retry_ratio{window="lifetime"}` : taux de retry global

## Alerting webhook

Définir une URL de webhook et des seuils via variables d'environnement :

```bash
export ALERT_WEBHOOK_URL="https://hooks.slack.com/services/..."
export ERROR_RATE_THRESHOLD=0.1      # 10% par défaut
export RETRY_RATE_THRESHOLD=0.2      # 20% par défaut
export ALERT_COOLDOWN_SECONDS=300    # éviter le spam
```

Chaque événement poste un snapshot; si un seuil est dépassé, un message est envoyé :
`[SEVERITY] Taux d'erreur élevé - Taux d'erreur: 15.0%`.

## Exemple de curl

```bash
curl -X POST http://localhost:8000/events/job-found \
  -H "Content-Type: application/json" \
  -d '{"source": "crawler"}'

curl -X POST http://localhost:8000/events/error \
  -H "Content-Type: application/json" \
  -d '{"stage": "compose", "reason": "timeout"}'

curl http://localhost:8000/metrics
```

## Prometheus & Alertmanager (extrait minimal)

```yaml
# prometheus.yml
scrape_configs:
  - job_name: "friendly-parakeet"
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: /metrics

# alerting rules (rules.yml)
groups:
  - name: parakeet.rules
    rules:
      - alert: HighErrorRate
        expr: processing_error_rate{window="lifetime"} > 0.1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Taux d'erreur élevé"
      - alert: HighRetryRatio
        expr: processing_retry_ratio{window="lifetime"} > 0.2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Taux de retry élevé"
```

Adapter `alertmanager.yml` pour pointer vers votre webhook Slack/Teams.
