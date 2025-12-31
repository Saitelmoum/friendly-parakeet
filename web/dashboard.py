from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import httpx
from fastapi import FastAPI, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


MAIL_API_URL = os.environ.get("MAIL_API_URL", "https://example.com/api/mail")


class Offer(BaseModel):
    id: int
    titre: str
    destinataire: str
    contenu: str
    statut: str = "brouillon"


BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app = FastAPI(title="Dashboard des offres")
offer_store: Dict[int, Offer] = {
    1: Offer(
        id=1,
        titre="Offre découverte",
        destinataire="client@example.com",
        contenu="Présentation succincte des services.",
        statut="brouillon",
    ),
    2: Offer(
        id=2,
        titre="Offre premium",
        destinataire="grand.compte@example.com",
        contenu="Détail complet de l'accompagnement premium.",
        statut="en revue",
    ),
}
action_log: List[dict] = []
store_lock = asyncio.Lock()


async def log_action(user: str, offer_id: int, action: str) -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    entry = {
        "user": user or "inconnu",
        "offer_id": offer_id,
        "action": action,
        "timestamp": timestamp,
    }
    async with store_lock:
        action_log.insert(0, entry)
        del action_log[50:]
    logger.info(
        "Action %s par %s sur l'offre %s à %s",
        action,
        user or "inconnu",
        offer_id,
        timestamp,
    )


async def send_offer_email(offer: Offer) -> None:
    payload = {
        "destinataire": offer.destinataire,
        "sujet": f"Nouvelle offre: {offer.titre}",
        "contenu": offer.contenu,
    }
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.post(MAIL_API_URL, json=payload)
        try:
            response.raise_for_status()
        except httpx.HTTPError as exc:
            logger.error("Erreur lors de l'envoi de l'offre %s: %s", offer.id, exc)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail="L'API mail a renvoyé une erreur.",
            ) from exc


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    async with store_lock:
        offers = list(offer_store.values())
        logs = list(action_log)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "offers": offers, "logs": logs},
    )


@app.post("/offers/{offer_id}/validate")
async def validate_offer(offer_id: int, user: str = Form("inconnu")) -> RedirectResponse:
    async with store_lock:
        offer = offer_store.get(offer_id)
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offre inconnue.")

    await send_offer_email(offer)

    async with store_lock:
        offer_store[offer_id] = offer.copy(update={"statut": "envoyée"})
    await log_action(user, offer_id, "validation (envoi mail)")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/offers/{offer_id}/reject")
async def reject_offer(offer_id: int, user: str = Form("inconnu")) -> RedirectResponse:
    async with store_lock:
        offer = offer_store.get(offer_id)
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Offre inconnue."
            )
        offer_store[offer_id] = offer.copy(update={"statut": "rejetée"})
    await log_action(user, offer_id, "rejet")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


@app.post("/offers/{offer_id}/edit")
async def mark_for_editing(
    offer_id: int, user: str = Form("inconnu")
) -> RedirectResponse:
    async with store_lock:
        offer = offer_store.get(offer_id)
        if not offer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Offre inconnue."
            )
        offer_store[offer_id] = offer.copy(update={"statut": "à modifier"})
    await log_action(user, offer_id, "modification demandée")
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web.dashboard:app", host="0.0.0.0", port=8000, reload=True)
