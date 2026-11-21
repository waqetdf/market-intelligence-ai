"""Advisory alert formatting and outbound notification adapters."""

from datetime import datetime, timezone
import logging
import os

import httpx

log = logging.getLogger(__name__)


def format_alert(payload):
    lines = [f"MARKET INTELLIGENCE · {payload['direction'].upper()}",
             f"{payload['symbol']} · {payload['timeframe']} · {payload['price']}",
             datetime.fromtimestamp(payload["observed_at"], timezone.utc).isoformat(),
             *payload["evidence"],
             f"Invalidación: {payload['invalidation']} · Objetivo: {payload['target']}",
             f"Zona: {payload.get('interest_zone', '—')} · R/B: {payload['reward_risk']}",
             f"Calidad: {payload.get('quality', {}).get('status', 'sin calibrar')}",
             *payload["risks"],
             "Aviso informativo. No se ha ejecutado ninguna operación."]
    if assessment := payload.get("assessment"):
        lines.append(assessment["text"])
    if payload["chart"]:
        lines.append(payload["chart"])
    items = payload.get("assessment", {}).get("references") or payload["news"]
    if items:
        lines += [items[0]["title"], items[0]["url"]]
    return "\n".join(lines)


async def notify(payload, enabled):
    message = format_alert(payload)
    messages = []
    if enabled["discord"] and (discord := os.getenv("DISCORD_WEBHOOK_URL")):
        messages.append(("discord", discord, {"content": message[:1900], "allowed_mentions": {"parse": []}}))
    if enabled["telegram"] and (telegram := os.getenv("TELEGRAM_BOT_TOKEN")) and (chat := os.getenv("TELEGRAM_CHAT_ID")):
        messages.append(("telegram", f"https://api.telegram.org/bot{telegram}/sendMessage",
                         {"chat_id": chat, "text": message[:3900]}))
    if not messages:
        return
    async with httpx.AsyncClient(timeout=10) as client:
        for channel, url, body in messages:
            try:
                response = await client.post(url, json=body)
                response.raise_for_status()
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("Alert delivery failed for %s (%s)", channel, type(exc).__name__)

