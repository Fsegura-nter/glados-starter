#!/usr/bin/env python3
"""
gmail_bandeja.py — Lo mecánico del correo, fuera del contexto del modelo.

Sirve a dos comandos con necesidades distintas, y por eso los modos se combinan:

  - `/responde` — el caso principal: contestar **un** correo concreto en nombre del usuario.
    Buscar (`--consulta`) → leer el hilo entero (`--hilo`) → dejar el borrador (`--borrador`).
  - `/correos` — vaciar la bandeja de un periodo. Tabla (`--listar`) → cuerpos de los pocos
    que hay que contestar (`--leer`) → borradores.

Por qué existe: leer cada hilo con el MCP de Gmail son decenas de miles de tokens **cada vez**,
y buena parte se descarta como ruido. El script devuelve lo justo; el modelo decide.

    --consulta "<q>"        Tabla para cualquier búsqueda de Gmail ("from:alguien sprint").
    --listar [periodo]      Tabla de no leídos. `1d` (por defecto), `3d`, `1w`, `2w`.
                            Marca [AUTO:motivo] el ruido demostrable por cabeceras y
                            remitente (vía el filtro compartido `ruido.py`), para no gastar
                            razonamiento en concluir que una newsletter es una newsletter.
    --leer <id> [<id>...]   Cuerpo limpio de esos mensajes, sin cita ni firma.
    --hilo <id>             La conversación entera, del mensaje más viejo al más nuevo.
                            Es lo que hace falta para contestar: `--leer` da el último
                            mensaje, y media conversación se entiende al revés sin lo previo.
    --borrador <json>       Crea los borradores **en Gmail**, dentro de su hilo. El JSON es
                            [{"id": "<id del mensaje a contestar>", "cuerpo": "<texto>"}]:
                            el destinatario, el asunto y las cabeceras de hilo las saca el
                            script de la fuente, que el modelo no tiene por qué adivinar.
    --nuevo <json>          Lo mismo para un correo **nuevo**, sin hilo previo: aquí no hay
                            original del que sacar nada, así que el JSON los trae. Es
                            [{"para", "asunto", "cuerpo" | "cuerpo_fichero", "cc"?}].
                            `cuerpo_fichero` es una ruta relativa al propio JSON: un cuerpo
                            largo metido inline, con los saltos de línea escapados, es donde
                            se cuelan los errores de formato.

**No envía.** No hay código de envío en el repo, a propósito: el scope `gmail.compose` sí lo
permitiría, así que la garantía es la ausencia. Enviar lo hace la persona que usa el vault,
desde Gmail.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import force_utf8
from google_auth import access_token, api_get
from gmail_api import (API, PAUSA, adjuntos_de, api_get_reintento, cabecera, crear_borrador,
                       cuerpo_de, limpiar, url_borrador)
import ruido

PERIODOS = {"1d": "1d", "3d": "3d", "1w": "7d", "2w": "14d"}
TOPE = 60                 # por encima de esto la tabla deja de ser legible
ANCHO_VISTA = 160         # caracteres de cuerpo por fila


def _mensaje_para_ruido(msg: dict) -> dict:
    """Adapta un mensaje de la API de Gmail a la forma que espera `ruido.es_ruido`
    (compartido con el barrido de arranque del núcleo): `cabeceras` como dict,
    `partes` como lista de mimeTypes, y `de` como cadena cruda.

    Una sola copia del filtro de ruido para todo el ecosistema: ver `ruido.py`.
    """
    payload = msg.get("payload", {}) or {}
    cabeceras = {h.get("name", ""): h.get("value", "")
                for h in payload.get("headers", []) or [] if h.get("name")}

    def _mime_types(p: dict) -> list[str]:
        tipos = [p.get("mimeType", "")] if p.get("mimeType") else []
        for parte in p.get("parts", []) or []:
            tipos += _mime_types(parte)
        return tipos

    return {
        "cabeceras": cabeceras,
        "partes": _mime_types(payload),
        "de": cabecera(msg, "From"),
    }


def es_automatico(msg: dict) -> str:
    """Ruido demostrable por cabeceras y remitente, no por criterio. Devuelve el motivo
    o cadena vacía. Delega en `ruido.es_ruido`, el filtro único del ecosistema: así el
    modelo no gasta razonamiento en concluir que una newsletter es una newsletter, y el
    criterio no diverge entre el triaje de bandeja y el barrido de arranque.
    """
    _, motivo = ruido.es_ruido(_mensaje_para_ruido(msg))
    return motivo


def corto(texto: str, n: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= n else texto[:n - 1] + "…"


def remitente(msg: dict) -> str:
    de = cabecera(msg, "From")
    if "<" in de:
        nombre, correo = de.split("<", 1)
        nombre = nombre.strip().strip('"')
        correo = correo.rstrip(">").strip()
        return f"{nombre} <{correo}>" if nombre else correo
    return de


def listar(periodo: str, token: str, consulta: str = "") -> int:
    """La misma tabla para los no leídos del periodo o para una consulta cualquiera de Gmail."""
    newer = PERIODOS.get(periodo, periodo) if periodo else ""
    q = consulta or f"is:unread newer_than:{newer}"
    datos = api_get_reintento(f"{API}/messages", token,
                              {"q": q, "maxResults": TOPE}) or {}
    ids = [m["id"] for m in datos.get("messages", [])]
    total = datos.get("resultSizeEstimate", len(ids))
    if not ids:
        print(f"Sin resultados para: {q}")
        return 0

    aviso = f" (hay ~{total}, se muestran los {TOPE} más recientes)" if total > len(ids) else ""
    print(f"Correos que cumplen «{q}»: {len(ids)}{aviso}")
    print("\nid · fecha · remitente / asunto · [AUTO:motivo] · [adj:n] · vista del cuerpo")
    print("-" * 78)

    fallos = 0
    for ident in ids:
        msg = api_get_reintento(f"{API}/messages/{ident}", token, {"format": "full"})
        time.sleep(PAUSA)
        if not msg:
            fallos += 1
            continue
        auto = es_automatico(msg)
        adj = [a for a in adjuntos_de(msg.get("payload", {})) if not a.endswith(".ics")]
        cuerpo = limpiar(cuerpo_de(msg.get("payload", {})))
        etiquetas = "".join([f" [AUTO:{auto}]" if auto else "",
                             f" [adj:{len(adj)}]" if adj else ""])
        print(f"\n{ident} · {cabecera(msg, 'Date')[:22]} · {remitente(msg)}")
        print(f"  ASUNTO: {corto(cabecera(msg, 'Subject'), 90)}{etiquetas}")
        print(f"  {corto(cuerpo, ANCHO_VISTA) or '(sin texto plano)'}")

    if fallos:
        print(f"\n{fallos} correo(s) no se pudieron leer. No están en la tabla: no dar por "
              f"hecho que no existen.")
    print("\nPara el cuerpo completo: --leer <id> [<id> ...]")
    return 0


def leer(ids: list[str], token: str) -> int:
    for ident in ids:
        msg = api_get_reintento(f"{API}/messages/{ident}", token, {"format": "full"})
        time.sleep(PAUSA)
        if not msg:
            print(f"\n=== {ident}: no se pudo leer")
            continue
        bruto = cuerpo_de(msg.get("payload", {}))
        limpio = limpiar(bruto)
        print("\n" + "=" * 78)
        print(f"id      : {ident}")
        print(f"hilo    : {msg.get('threadId')}")
        print(f"de      : {remitente(msg)}")
        print(f"para    : {cabecera(msg, 'To')}")
        if cabecera(msg, "Cc"):
            print(f"cc      : {cabecera(msg, 'Cc')}")
        print(f"fecha   : {cabecera(msg, 'Date')}")
        print(f"asunto  : {cabecera(msg, 'Subject')}")
        adj = [a for a in adjuntos_de(msg.get("payload", {})) if not a.endswith(".ics")]
        if adj:
            print(f"adjuntos: {', '.join(adj)}")
        print("-" * 78)
        print(limpio or "(sin texto plano)")
        resto = bruto[len(limpio):].strip()
        if resto:
            print(f"\n--- hilo previo y firma recortados ({len(resto)} caracteres). "
                  f"Si hace falta el contexto del hilo, pedirlo aparte ---")
    return 0


def hilo(ident: str, token: str) -> int:
    """Todos los mensajes de una conversación, del más viejo al más nuevo y ya limpios.

    Para contestar hace falta el hilo, no el último mensaje: media conversación se entiende al
    revés sin saber qué se dijo antes. `--leer` recorta la parte citada, que es lo correcto
    para clasificar y lo insuficiente para redactar.

    Acepta el id de un mensaje o el del hilo: Gmail los distingue solo.
    """
    # Se sondea primero como hilo, y el 404 de ese sondeo se calla: no es un fallo, es la
    # forma de saber si el id era de un mensaje. Un error falso en la salida hace perder
    # tiempo buscando un problema que no existe.
    try:
        datos = api_get(f"{API}/threads/{ident}", token, {"format": "full"})
    except Exception:
        datos = None
    if not datos:
        msg = api_get_reintento(f"{API}/messages/{ident}", token, {"format": "metadata"})
        if not msg:
            print(f"No se pudo leer {ident} ni como hilo ni como mensaje.")
            return 1
        datos = api_get_reintento(f"{API}/threads/{msg['threadId']}", token, {"format": "full"})
        if not datos:
            return 1

    mensajes = datos.get("messages", [])
    print(f"Hilo {datos.get('id')} · {len(mensajes)} mensaje(s)")
    print(f"Asunto: {cabecera(mensajes[0], 'Subject') if mensajes else '(vacío)'}")
    for n, msg in enumerate(mensajes, 1):
        adj = [a for a in adjuntos_de(msg.get("payload", {})) if not a.endswith(".ics")]
        print("\n" + "=" * 78)
        print(f"[{n}/{len(mensajes)}] id {msg.get('id')}")
        print(f"de    : {remitente(msg)}")
        print(f"para  : {cabecera(msg, 'To')}")
        if cabecera(msg, "Cc"):
            print(f"cc    : {cabecera(msg, 'Cc')}")
        print(f"fecha : {cabecera(msg, 'Date')}")
        if adj:
            print(f"adj   : {', '.join(adj)}")
        print("-" * 78)
        print(limpiar(cuerpo_de(msg.get("payload", {}))) or "(sin texto plano)")
    print(f"\nPara dejar la respuesta: --borrador con el id del ÚLTIMO mensaje "
          f"({mensajes[-1].get('id') if mensajes else '?'}).")
    return 0


def borradores(ruta: Path, token: str) -> int:
    """Crea en Gmail un borrador por entrada del JSON, dentro del hilo del original."""
    try:
        entradas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"No se pudo leer {ruta}: {e}")
        return 1
    if isinstance(entradas, dict):
        entradas = [entradas]

    perfil = api_get_reintento(f"{API}/profile", token) or {}
    yo = perfil.get("emailAddress", "")
    creados = errores = 0
    for entrada in entradas:
        ident, cuerpo = entrada.get("id"), entrada.get("cuerpo")
        if not ident or not cuerpo:
            print(f"  [salto] entrada sin 'id' o sin 'cuerpo': {str(entrada)[:60]}")
            errores += 1
            continue
        msg = api_get_reintento(f"{API}/messages/{ident}", token, {"format": "metadata"})
        if not msg:
            print(f"  [error] {ident}: no se pudo leer el original, no creo el borrador")
            errores += 1
            continue
        # Reply-To antes que From: contestar al From de una lista de correo manda la
        # respuesta a la lista entera.
        para = cabecera(msg, "Reply-To") or cabecera(msg, "From")
        try:
            draft = crear_borrador(
                para=para,
                asunto=cabecera(msg, "Subject"),
                cuerpo=cuerpo,
                thread_id=msg.get("threadId"),
                message_id=cabecera(msg, "Message-ID"),
                cc=entrada.get("cc", ""),
                token=token,
            )
        except Exception as e:
            print(f"  [error] {ident}: {type(e).__name__}: {e}")
            errores += 1
            continue
        creados += 1
        print(f"  [ok] borrador para {corto(para, 44)}")
        print(f"       asunto: {corto(cabecera(msg, 'Subject'), 60)}")
        if url_borrador(draft):
            print(f"       {url_borrador(draft)}")
        time.sleep(PAUSA)

    print(f"\nBorradores creados en Gmail: {creados}"
          + (f" · errores: {errores}" if errores else ""))
    if creados:
        print(f"Están en Borradores de {yo}, cada uno dentro de su hilo. "
              f"Nada se ha enviado: revisar y enviar a mano.")
    return 1 if errores and not creados else 0


def nuevos(ruta: Path, token: str) -> int:
    """Crea en Gmail un borrador de correo NUEVO por entrada del JSON, fuera de todo hilo."""
    try:
        entradas = json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        print(f"No se pudo leer {ruta}: {e}")
        return 1
    if isinstance(entradas, dict):
        entradas = [entradas]

    perfil = api_get_reintento(f"{API}/profile", token) or {}
    yo = perfil.get("emailAddress", "")
    creados = errores = 0
    for entrada in entradas:
        para, asunto = entrada.get("para"), entrada.get("asunto")
        cuerpo = entrada.get("cuerpo")
        fichero = entrada.get("cuerpo_fichero")
        if fichero and not cuerpo:
            try:
                cuerpo = (ruta.parent / fichero).read_text(encoding="utf-8")
            except OSError as e:
                print(f"  [error] no se pudo leer {fichero}: {e}")
                errores += 1
                continue
        if not (para and asunto and cuerpo):
            print(f"  [salto] falta 'para', 'asunto' o cuerpo: {str(entrada)[:60]}")
            errores += 1
            continue
        try:
            draft = crear_borrador(para=para, asunto=asunto, cuerpo=cuerpo,
                                   cc=entrada.get("cc", ""), token=token)
        except Exception as e:
            print(f"  [error] {corto(para, 40)}: {type(e).__name__}: {e}")
            errores += 1
            continue
        creados += 1
        print(f"  [ok] borrador para {corto(para, 44)}")
        print(f"       asunto: {corto(asunto, 60)}")
        if url_borrador(draft):
            print(f"       {url_borrador(draft)}")
        time.sleep(PAUSA)

    print(f"\nBorradores nuevos creados en Gmail: {creados}"
          + (f" · errores: {errores}" if errores else ""))
    if creados:
        print(f"Están en Borradores de {yo}, fuera de ningún hilo. "
              f"Nada se ha enviado: revisar y enviar a mano.")
    return 1 if errores and not creados else 0


def main() -> int:
    force_utf8()
    p = argparse.ArgumentParser(description="Triage de bandeja de entrada para /correos")
    p.add_argument("--listar", nargs="?", const="1d", metavar="PERIODO",
                   help="tabla de no leídos (1d, 3d, 1w, 2w)")
    p.add_argument("--leer", nargs="+", metavar="ID", help="cuerpo completo de esos correos")
    p.add_argument("--borrador", metavar="FICHERO.JSON",
                   help="crea borradores en Gmail desde un JSON [{id, cuerpo}]")
    p.add_argument("--nuevo", metavar="FICHERO.JSON",
                   help="crea correos NUEVOS (sin hilo) desde un JSON "
                        "[{para, asunto, cuerpo | cuerpo_fichero}]")
    p.add_argument("--consulta", metavar="Q",
                   help="la misma tabla para una consulta cualquiera de Gmail "
                        "(ej. 'from:alguien newer_than:7d'), no solo para los no leídos")
    p.add_argument("--hilo", metavar="ID",
                   help="la conversación entera, del mensaje más viejo al más nuevo. "
                        "Es lo que hace falta para contestar")
    args = p.parse_args()

    if not (args.listar or args.leer or args.borrador or args.nuevo or args.consulta or args.hilo):
        p.print_help()
        return 2
    try:
        token = access_token()
    except Exception as e:
        print(f"Sin acceso a Google: {e}")
        print("  python google_auth.py check")
        return 1

    if args.consulta:
        return listar("", token, args.consulta)
    if args.hilo:
        return hilo(args.hilo, token)
    if args.listar:
        return listar(args.listar, token)
    if args.leer:
        return leer(args.leer, token)
    if args.nuevo:
        return nuevos(Path(args.nuevo), token)
    return borradores(Path(args.borrador), token)


if __name__ == "__main__":
    sys.exit(main())
