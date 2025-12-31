# friendly-parakeet

Outils basiques pour générer des brouillons d’e-mails depuis des templates Jinja et les enregistrer via Gmail ou Microsoft Graph, tout en conservant l’ID et le statut dans une base SQLite.

## Structure
- `emails/drafts.py` : service principal regroupant le rendu de template, la création de brouillons (Gmail/Graph) et la persistance.
- `requirements.txt` : dépendances Python (Jinja2 et Requests).

## Pré-requis
- Python 3.11+
- Un token OAuth avec les scopes nécessaires pour Gmail (`https://www.googleapis.com/auth/gmail.compose`) ou Microsoft Graph (`Mail.ReadWrite`).

## Exemple d’utilisation
```python
from pathlib import Path
from emails.drafts import (
    DraftRepository,
    DraftService,
    EmailTemplateRenderer,
    GmailDraftClient,
    GraphDraftClient,
)

renderer = EmailTemplateRenderer(template_dirs=[Path("templates")])
repository = DraftRepository(Path("data/drafts.db"))
clients = {
    "gmail": GmailDraftClient(access_token="<GMAIL_TOKEN>"),
    "graph": GraphDraftClient(access_token="<GRAPH_TOKEN>"),
}

service = DraftService(renderer=renderer, repository=repository, clients=clients)

record = service.create_draft_from_template(
    template=Path("templates/offer_email.html"),
    context={"offer_title": "Offre spéciale", "price": "99€"},
    subject="Votre nouvelle offre",
    to=["client@example.com"],
    provider="gmail",
)
print(record)
```

> Remarque : la base SQLite est stockée dans `data/drafts.db` (ignorée par Git). Les réponses des fournisseurs sont conservées dans la colonne `metadata` pour audit.
