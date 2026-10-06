"""Filtro de correo basura. Unica copia: la usan el barrido de arranque y el triaje."""
import re

CABECERAS_RUIDO = ("list-unsubscribe", "x-auto-response-suppress")
PRECEDENCIAS = {"bulk", "list", "junk"}
REMITENTES = re.compile(
    r"(?:^|[._-])(?:noreply|no-reply|donotreply|notifications?|mailer|bounce)(?:[._-]|@)"
    r"|@(?:github\.com|gitlab\.|.*\.atlassian\.net|jira\.|teams\.|.*sharepointonline)",
    re.I)


def es_ruido(mensaje):
    cab = {k.lower(): v for k, v in mensaje.get("cabeceras", {}).items()}
    if any(c in cab for c in CABECERAS_RUIDO):
        return True, "cabecera"
    if cab.get("precedence", "").strip().lower() in PRECEDENCIAS:
        return True, "cabecera"
    if cab.get("auto-submitted", "").strip().lower().startswith("auto-"):
        return True, "cabecera"
    partes = [p.lower() for p in mensaje.get("partes", [])]
    if "text/calendar" in partes or "method=" in cab.get("content-type", "").lower():
        return True, "invitacion"
    de = mensaje.get("de", "")
    if REMITENTES.search(de) or de.lower().startswith(("noreply", "no-reply", "donotreply")):
        return True, "remitente"
    return False, ""


def resumen(mensajes):
    datos = {"total": len(mensajes), "cabecera": 0, "remitente": 0,
             "invitacion": 0, "utiles": 0, "personas": 0}
    personas = set()
    for m in mensajes:
        descartar, motivo = es_ruido(m)
        if descartar:
            datos[motivo] += 1
        else:
            datos["utiles"] += 1
            personas.add(m.get("de", "").lower())
    datos["personas"] = len(personas)
    return datos
