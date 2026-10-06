"""Filtro de correo basura. Unica copia: la usan el barrido de arranque y el triaje."""
import re, email.utils

CABECERAS_RUIDO = ("list-unsubscribe", "x-auto-response-suppress")
PRECEDENCIAS = {"bulk", "list", "junk"}
REMITENTES = re.compile(
    r"(?:^|[._-])(?:noreply|no-reply|donotreply|notifications?)(?:[._-]|@)"
    r"|^(?:mailer(?:-daemon)?|bounce|bounces\+\w+)@"
    r"|@(?:github\.com|gitlab\.|.*\.atlassian\.net|jira\.|teams\.|.*sharepointonline"
    r"|linkedin\.com|mailchimp\.com|mailchimp-|substack\.com|sendgrid\.net"
    r"|constantcontact\.com)"
    r"|mailgun|campaign-archive",
    re.I)


def _extraer_direccion(de):
    """Extrae la dirección de correo desnuda de un campo From."""
    if not de:
        return ""
    _, addr = email.utils.parseaddr(de)
    return addr.lower() if addr else ""


def es_ruido(mensaje):
    # Entrada defensiva: non-dict o None → tratar como vacío
    if not isinstance(mensaje, dict):
        return False, ""

    cab = {k.lower(): v for k, v in (mensaje.get("cabeceras") or {}).items()}
    if any(c in cab for c in CABECERAS_RUIDO):
        return True, "cabecera"
    if cab.get("precedence", "").strip().lower() in PRECEDENCIAS:
        return True, "cabecera"
    if cab.get("auto-submitted", "").strip().lower().startswith("auto-"):
        return True, "cabecera"

    partes = [p.lower() for p in (mensaje.get("partes") or [])]
    if "text/calendar" in partes or "method=" in cab.get("content-type", "").lower():
        return True, "invitacion"

    de_raw = mensaje.get("de") or ""
    de = _extraer_direccion(de_raw)

    # Verificar si es un aviso de calendario por remitente
    if de:
        local_part = de.split("@")[0]
        if local_part.startswith("calendar-"):
            return True, "invitacion"

    if REMITENTES.search(de) or de.startswith(("noreply@", "no-reply@", "donotreply@")):
        return True, "remitente"
    return False, ""


def resumen(mensajes):
    # Entrada defensiva: None o non-list → lista vacía
    if not isinstance(mensajes, list):
        mensajes = []

    datos = {"total": len(mensajes), "cabecera": 0, "remitente": 0,
             "invitacion": 0, "utiles": 0, "personas": 0}
    personas = set()
    for m in mensajes:
        descartar, motivo = es_ruido(m)
        if descartar:
            datos[motivo] += 1
        else:
            datos["utiles"] += 1
            de_direccion = _extraer_direccion(m.get("de") if isinstance(m, dict) else "")
            if de_direccion:
                personas.add(de_direccion)
    datos["personas"] = len(personas)
    return datos
