#!/usr/bin/env python3
"""
google_auth.py — OAuth 2.0 propio para las APIs de Google, sin dependencias externas.

Por qué existe: los MCP de Google caducan su autorización y exigen abrir el navegador
cada vez, así que no sostienen nada programado. Este módulo obtiene un `refresh_token`
propio, que no caduca por uso, y con él cualquier script consigue un `access_token` solo.

Solo biblioteca estándar: `urllib` para las llamadas y `http.server` para recibir el código
en el bucle local. No hace falta `google-auth` ni añadir nada a requirements.txt.

El `refresh_token` se guarda en el almacén de credenciales del ecosistema
(`config.data_dir() / "secrets.json"`), nunca en el vault.

Uso:
    python google_auth.py login     # abre el navegador y guarda el refresh_token
    python google_auth.py check     # dice si hay credenciales y si el token sirve

Desde Python:
    from google_auth import access_token, api_get
    datos = api_get("https://gmail.googleapis.com/gmail/v1/users/me/profile")
"""
import json
import secrets as _stdlib_secrets
import sys
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import force_utf8
import credentials

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
PUERTO = 8765                      # el redirect_uri registrado debe coincidir
REDIRECT = f"http://localhost:{PUERTO}/callback"

# Mínimo indispensable, y nada más: leer correo, crear borradores, leer Drive y Calendar.
#
# OJO con `gmail.compose`. Su descripción oficial es «Manage drafts and send emails»: **sí
# permite enviar**. No existe ningún scope de Gmail que permita borradores sin permitir el
# envío, así que este es el mínimo disponible. **La garantía de que nada se envía es el
# código, no el permiso:** en todo el repo no hay ninguna llamada al endpoint de envío de
# mensajes ni al de envío de un borrador, y no debe haberla. Si algún día hace falta
# enviar, que sea una función aparte, explícita y con confirmación de la persona que usa
# el vault en el momento.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/calendar.readonly",
]


class _Receptor(BaseHTTPRequestHandler):
    codigo = None
    error = None
    estado_esperado = None

    def do_GET(self):  # noqa: N802
        query = urllib.parse.urlparse(self.path).query
        params = urllib.parse.parse_qs(query)
        recibido = (params.get("state") or [None])[0]
        if _Receptor.estado_esperado and recibido != _Receptor.estado_esperado:
            _Receptor.error = "el parámetro state no coincide: respuesta descartada"
        else:
            _Receptor.codigo = (params.get("code") or [None])[0]
            _Receptor.error = (params.get("error") or [None])[0]
        cuerpo = ("<h2>Listo.</h2><p>Ya puedes cerrar esta pestaña y volver a la terminal.</p>"
                  if _Receptor.codigo else
                  f"<h2>Ha fallado.</h2><p>{_Receptor.error}</p>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(cuerpo.encode("utf-8"))

    def log_message(self, *_):
        pass                       # sin ruido en la terminal


def _post_form(url: str, datos: dict) -> dict:
    cuerpo = urllib.parse.urlencode(datos).encode("utf-8")
    req = urllib.request.Request(url, data=cuerpo,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def login() -> int:
    client_id = credentials.get("google.client_id")
    client_secret = credentials.get("google.client_secret")
    if not client_id or not client_secret:
        print("Faltan las credenciales de la app de Google. Rellena en el almacén:")
        print("  google.client_id  y  google.client_secret")
        print("  python credentials.py list   (dice dónde y qué)")
        return 1

    estado = _stdlib_secrets.token_urlsafe(16)
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",      # imprescindible para recibir refresh_token
        "prompt": "consent",           # fuerza que lo devuelva aunque ya hubiera consentido
        "state": estado,
    }
    url = f"{AUTH_URL}?{urllib.parse.urlencode(params)}"
    print("Abriendo el navegador para autorizar. Si no se abre, pega esta URL:\n")
    print(f"  {url}\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    _Receptor.estado_esperado = estado
    servidor = HTTPServer(("localhost", PUERTO), _Receptor)
    servidor.timeout = 180
    print(f"Esperando la respuesta en {REDIRECT} (3 minutos)...", flush=True)
    servidor.handle_request()
    servidor.server_close()

    if not _Receptor.codigo:
        print(f"No se recibió el código. Motivo: {_Receptor.error or 'tiempo agotado'}")
        return 1

    try:
        tokens = _post_form(TOKEN_URL, {
            "code": _Receptor.codigo,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": REDIRECT,
            "grant_type": "authorization_code",
        })
    except urllib.error.HTTPError as e:
        print(f"Error al canjear el código: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}")
        return 1

    refresh = tokens.get("refresh_token")
    if not refresh:
        print("Google no devolvió refresh_token. Revoca el acceso de la app en "
              "https://myaccount.google.com/permissions y repite el login.")
        return 1
    credentials.set("google.refresh_token", refresh)
    print("\nrefresh_token guardado en el almacén. Ya no hace falta el navegador.")
    return 0


def access_token() -> str:
    """Un access_token nuevo a partir del refresh_token. No se guarda: dura una hora."""
    client_id = credentials.get("google.client_id")
    client_secret = credentials.get("google.client_secret")
    refresh = credentials.get("google.refresh_token")
    if not (client_id and client_secret and refresh):
        raise RuntimeError("Faltan credenciales de Google. Ejecuta: python google_auth.py login")
    datos = _post_form(TOKEN_URL, {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    })
    token = datos.get("access_token")
    if not token:
        raise RuntimeError(f"Google no devolvió access_token: {datos}")
    return token


class GoogleError(RuntimeError):
    """Error de una API de Google con su motivo legible."""

    def __init__(self, codigo: int, razon: str, mensaje: str):
        self.codigo, self.razon, self.mensaje = codigo, razon, mensaje
        super().__init__(f"HTTP {codigo} · {razon} · {mensaje}")


def _lanzar(e: urllib.error.HTTPError) -> None:
    """Convierte el HTTPError en algo que se pueda leer. Google explica el motivo en el
    cuerpo de la respuesta: sin mirarlo, un 403 por API sin habilitar parece un token
    caducado y se pierde media hora."""
    cuerpo = e.read().decode("utf-8", "replace")
    try:
        err = json.loads(cuerpo).get("error", {})
        razon = (err.get("errors") or [{}])[0].get("reason", "") or err.get("status", "")
        raise GoogleError(e.code, razon, err.get("message", "")) from None
    except (ValueError, KeyError, TypeError):
        raise GoogleError(e.code, "", cuerpo[:300]) from None


def api_get(url: str, token: str | None = None, params: dict | None = None) -> dict:
    """GET autenticado contra una API de Google. Devuelve el JSON."""
    token = token or access_token()
    if params:
        # doseq: sin esto, un parametro con varios valores (metadataHeaders de Gmail) se
        # codifica como el repr de la lista y la API lo ignora en silencio — devuelve el
        # mensaje sin cabeceras y parece que el correo no tiene asunto.
        url = f"{url}?{urllib.parse.urlencode(params, doseq=True)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _lanzar(e)


def api_post(url: str, cuerpo: dict, token: str | None = None) -> dict:
    token = token or access_token()
    datos = json.dumps(cuerpo).encode("utf-8")
    req = urllib.request.Request(url, data=datos, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        _lanzar(e)


def check() -> int:
    faltan = [c for c in ("google.client_id", "google.client_secret") if not credentials.get(c)]
    if faltan:
        print("Faltan en el almacén: " + ", ".join(faltan))
        return 1
    if not credentials.get("google.refresh_token"):
        print("Credenciales de app puestas, pero sin autorizar todavía.")
        print("  python google_auth.py login")
        return 1
    try:
        perfil = api_get("https://gmail.googleapis.com/gmail/v1/users/me/profile")
    except GoogleError as e:
        print(f"Gmail responde {e.codigo} ({e.razon}): {e.mensaje}")
        if e.razon == "accessNotConfigured":
            print("  → La API no está habilitada en el proyecto. Habilítala en:")
            print("     https://console.cloud.google.com/apis/library/gmail.googleapis.com")
            print("  El token es válido: no hace falta repetir el login.")
        elif e.codigo in (401, 403):
            print("  python google_auth.py login")
        return 1
    except Exception as e:
        print(f"Fallo inesperado: {type(e).__name__}: {e}")
        return 1
    print(f"Autenticado como {perfil.get('emailAddress')} · "
          f"{perfil.get('messagesTotal')} mensajes · {perfil.get('threadsTotal')} hilos")
    return 0


def main() -> int:
    force_utf8()
    accion = sys.argv[1] if len(sys.argv) > 1 else "check"
    if accion == "login":
        return login()
    if accion == "check":
        return check()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
