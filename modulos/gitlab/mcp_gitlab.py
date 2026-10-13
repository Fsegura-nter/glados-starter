#!/usr/bin/env python3
"""
mcp_gitlab.py — Lanzador del servidor MCP de GitLab con las credenciales del almacén.

Por qué existe: `.mcp.json` solo sabe interpolar variables de entorno (`${GITLAB_TOKEN}`),
así que obliga a definirlas a mano en el entorno de usuario. Si no están definidas, el
servidor muere con un `CONNECTION_CLOSED` que no dice nada. Este lanzador lee el token del
almacén de credenciales del ecosistema, lo pasa en el entorno del hijo y, si algo falta, lo
dice en claro por stderr en vez de morir en silencio.

Modo solo lectura forzado aquí, no en la configuración: es una decisión de este módulo, no
un ajuste que se pueda olvidar al editar un JSON.
"""
import os
import subprocess
import sys
from pathlib import Path
from shutil import which

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import credentials

config.force_utf8()

PAQUETE = "@zereight/mcp-gitlab"


def fail(mensaje: str) -> None:
    print(f"[mcp_gitlab] {mensaje}", file=sys.stderr, flush=True)
    sys.exit(1)


def cualquier_token(servicio: str) -> tuple[str | None, str | None]:
    """(clave, token) del primer token disponible para el servicio: el general
    (`<servicio>.token`) si existe, o si no el primero por proyecto
    (`<servicio>.tokens.<ruta>`). (None, None) si no hay ninguno.
    """
    general = credentials.get(f"{servicio}.token")
    if general:
        return f"{servicio}.token", general
    for clave, _ in credentials.listar():
        if clave.startswith(f"{servicio}.tokens."):
            return clave, credentials.get(clave)
    return None, None


def main() -> None:
    origen, token = cualquier_token("gitlab")
    if not token:
        # El token se pega en el FICHERO del almacén, nunca en un comando: en la línea
        # de comandos queda en el historial de la terminal para siempre, y de ahí no lo
        # saca nadie el día que haya que revocarlo.
        fail("No hay ningún token de GitLab. Pégalo en el fichero del almacén, con la\n"
             "clave `gitlab.token` para toda la instancia o\n"
             "`gitlab.tokens.<grupo>/<repo>` para uno solo. Nunca en un comando: ahí\n"
             "queda en el historial de la terminal.\n"
             "    python .glados/credentials.py list   (dice dónde está y qué hay)")
    if origen != "gitlab.token":
        # Un token de proyecto tiene scope limitado: sirve para ese repo, no para
        # listar la instancia. Se usa, pero avisando de por qué puede fallar.
        print(f"[mcp_gitlab] Aviso: no hay `gitlab.token` general; uso {origen}. "
              "Si es un token de proyecto, solo verás ese proyecto.",
              file=sys.stderr, flush=True)

    npx = which("npx") or which("npx.cmd")
    if not npx:
        fail("npx no está en el PATH: Node no está instalado en esta máquina.\n"
             "    winget install OpenJS.NodeJS.LTS  y reabre la terminal.")

    # GITLAB_PERMISSION_MODE es la variable vigente; READ_ONLY_MODE está deprecada pero se
    # mantiene para no depender de la versión que resuelva npx.
    entorno = {**os.environ, **credentials.env_for("gitlab"),
               "GITLAB_PERSONAL_ACCESS_TOKEN": token,
               "GITLAB_PERMISSION_MODE": "readonly",
               "GITLAB_READ_ONLY_MODE": "true"}

    gitlab_host = config.local_settings().get("gitlab_host")
    if gitlab_host:
        entorno["GITLAB_API_URL"] = f"https://{gitlab_host}/api/v4"

    # En Windows npx es un .cmd y CreateProcess no lo ejecuta directamente.
    if npx.lower().endswith((".cmd", ".bat")):
        comando = ["cmd", "/c", npx, "-y", PAQUETE]
    else:
        comando = [npx, "-y", PAQUETE]

    try:
        sys.exit(subprocess.call(comando, env=entorno))
    except FileNotFoundError:
        fail(f"No se pudo ejecutar: {' '.join(comando)}")


if __name__ == "__main__":
    main()
