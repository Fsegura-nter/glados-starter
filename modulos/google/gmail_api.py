#!/usr/bin/env python3
"""
gmail_api.py — Primitivas de Gmail compartidas. No se ejecuta solo.

Existe para que `gmail_perfil.py` (destila el estilo) y `gmail_bandeja.py` (triage y
borradores) no tengan dos copias de lo mismo. La lógica de limpieza de un correo —quitar la
cita, quitar la firma, decidir si es una notificación automática— se afina a base de mirar
resultados sucios; con dos copias, el siguiente arreglo se aplicaría a una sola.

Nada de esto escribe en el vault ni guarda credenciales. Ver `google_auth.py`.
"""
import base64
import re
import sys
import time
import urllib.error
from email.message import EmailMessage
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from google_auth import GoogleError, api_get, api_post

API = "https://gmail.googleapis.com/gmail/v1/users/me"

PAUSA = 0.12          # s entre llamadas: sin esto Gmail corta por cuota
REINTENTOS = 4

# ─── patrones de limpieza ─────────────────────────────────────────────────────
# Cada uno viene de un resultado contaminado real, no de imaginar casos. La firma
# corporativa de quien use el vault no se puede adivinar de antemano: se detecta por
# marcadores genéricos (separador, imagen inline, "enviado desde") y, si hace falta
# más precisión, se amplía aquí con lo propio — nunca con el nombre o la dirección de
# una persona concreta, para que este fichero siga sirviendo a cualquiera que lo use.

CORTE_CITA = re.compile(
    r"(^>.*$)|(^El .*escribió:)|(^On .*wrote:)|(^-{2,}\s*Mensaje original)|"
    r"(^De:\s)|(^From:\s)|(^_{5,})", re.MULTILINE)
CORTE_FIRMA = re.compile(
    r"(?m)^(--\s*$|\[image:|Enviado desde|Sent from)")
ES_CALENDAR = re.compile(
    r"(ha (aceptado|rechazado|respondido)[^.\n]{0,30}(esta )?invitaci[oó]n|"
    r"has (accepted|declined|responded)[^.\n]{0,20}this invitation|"
    r"Unirme con Google Meet|Join with Google Meet|"
    r"^Este evento|^This event|Unirse por tel[eé]fono|Join by phone)", re.I | re.M)
ES_AUTOMATICO = re.compile(
    r"(he compartido un|ha compartido un|has shared|I.ve shared|shared (a|an) \w+ with you|"
    r"ajustes de notificaci|notification settings|se ha compartido)", re.I)


def api_get_reintento(url: str, token: str, params: dict | None = None) -> dict | None:
    """Como api_get, pero aguanta la cuota de Gmail. Devuelve None si no hay manera.

    Sin esto se pierden mensajes **en silencio**: un lote grande puede perder la mitad
    de los correos sin que el script se caiga ni avise.
    """
    espera = 1.0
    for intento in range(REINTENTOS):
        try:
            return api_get(url, token, params)
        except GoogleError as e:
            razon = (e.razon or "").lower()
            recuperable = e.codigo in (429, 500, 502, 503) or "rate" in razon or "quota" in razon
            if not recuperable or intento == REINTENTOS - 1:
                print(f"    [error] {e.codigo} {e.razon}: {e.mensaje[:70]}", flush=True)
                return None
            time.sleep(espera)
            espera *= 2
        except urllib.error.URLError as e:
            if intento == REINTENTOS - 1:
                print(f"    [red] {e}", flush=True)
                return None
            time.sleep(espera)
            espera *= 2
    return None


# ─── extracción ───────────────────────────────────────────────────────────────

def cuerpo_de(payload: dict) -> str:
    """El primer text/plain del MIME, recorriendo las partes anidadas."""
    if payload.get("mimeType") == "text/plain":
        datos = payload.get("body", {}).get("data")
        if datos:
            return base64.urlsafe_b64decode(datos + "==").decode("utf-8", "replace")
    for parte in payload.get("parts", []) or []:
        texto = cuerpo_de(parte)
        if texto:
            return texto
    return ""


def tiene_calendario(payload: dict) -> bool:
    """Una respuesta a invitación lleva una parte text/calendar."""
    if "calendar" in (payload.get("mimeType") or ""):
        return True
    return any(tiene_calendario(p) for p in payload.get("parts", []) or [])


def adjuntos_de(payload: dict) -> list[str]:
    nombres = []
    if payload.get("filename"):
        nombres.append(payload["filename"])
    for parte in payload.get("parts", []) or []:
        nombres += adjuntos_de(parte)
    return [n for n in nombres if n]


def cabecera(msg: dict, nombre: str) -> str:
    for h in msg.get("payload", {}).get("headers", []) or []:
        if h.get("name", "").lower() == nombre.lower():
            return h.get("value", "")
    return ""


def limpiar(texto: str) -> str:
    """Solo lo escrito esta vez: sin cita previa y sin firma corporativa.

    El corte de firma importa: sin él, la mediana de longitud sube y todo lo que se
    deduzca del texto (estilo, tono, longitud típica) queda mal.
    """
    for patron in (CORTE_CITA, CORTE_FIRMA):
        m = patron.search(texto)
        if m:
            texto = texto[:m.start()]
    return texto.strip()


# ─── borradores ───────────────────────────────────────────────────────────────

def crear_borrador(*, para: str, asunto: str, cuerpo: str, thread_id: str | None = None,
                   message_id: str | None = None, cc: str = "", token: str | None = None,
                   remitente: str = "") -> dict:
    """Deja un borrador en Gmail. No lo envía.

    El scope `gmail.compose` **sí permitiría enviar** («Manage drafts and send emails»), así
    que lo que impide el envío es que en este módulo no hay ninguna función que llame al
    endpoint de envío de mensajes de Gmail, ni al de envío de un borrador. No añadir una sin
    que la persona que usa el vault lo pida explícitamente.

    `message_id` es el `Message-ID` del correo al que se responde. Sin él Gmail muestra el
    borrador fuera del hilo aunque se pase `thread_id`, y habría que reenlazarlo a mano.
    """
    msg = EmailMessage()
    msg["To"] = para
    if cc:
        msg["Cc"] = cc
    if remitente:
        msg["From"] = remitente
    msg["Subject"] = asunto if asunto.lower().startswith("re:") or not thread_id else f"Re: {asunto}"
    if message_id:
        msg["In-Reply-To"] = message_id
        msg["References"] = message_id
    msg.set_content(cuerpo)

    peticion = {"message": {"raw": base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")}}
    if thread_id:
        peticion["message"]["threadId"] = thread_id
    return api_post(f"{API}/drafts", peticion, token)


def url_borrador(draft: dict) -> str:
    """Enlace directo al borrador en la interfaz de Gmail."""
    ident = (draft.get("message") or {}).get("id") or draft.get("id", "")
    return f"https://mail.google.com/mail/u/0/#drafts/{ident}" if ident else ""
