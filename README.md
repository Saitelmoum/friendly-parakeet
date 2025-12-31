# friendly-parakeet

Dashboard FastAPI pour gérer l'envoi des offres.

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Démarrage

```bash
uvicorn web.dashboard:app --reload
```

Visitez ensuite http://127.0.0.1:8000/dashboard pour afficher les offres et utiliser les actions **Valider / Rejeter / Modifier**. L'action de validation envoie l'offre via l'API mail (URL configurable par `MAIL_API_URL`) et met à jour le statut à `envoyée`. Toutes les actions sont journalisées avec horodatage.
