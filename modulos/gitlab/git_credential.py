#!/usr/bin/env python3
"""
git_credential.py — Credential helper de git que lee del almacén de credenciales.

Por qué existe: el Gestor de credenciales de Windows abre un diálogo que **no aparece**
en muchas terminales integradas (la de Obsidian, entre otras), así que `git push` se queda
colgado para siempre. Las alternativas son peores: el token en la URL del remoto —**nunca
hacer esto**: es exactamente la misma causa, y además deja el token en claro en
`.git/config` y en el historial de la terminal—, o `credential.helper store`, que lo
escribe en claro en `~/.git-credentials`.

Este helper no copia el token a ningún sitio: lo lee del almacén de credenciales del
ecosistema (`config.data_dir() / "secrets.json"`), que ya tiene ACL restringida al usuario.

Soporta tokens por proyecto: con `credential.<url>.useHttpPath true`, git envía el
`path` del repo y aquí se busca `gitlab.tokens.<ruta>` antes de caer al general
(`gitlab.token`).

Protocolo (git-credential): recibe `clave=valor` por stdin hasta línea vacía, y para la
operación `get` responde `username` y `password`. `store` y `erase` no hacen nada: el
almacén se gestiona con `credentials.py`, no desde git.

Instalación (una vez por host), que se hace sola:

    python git_credential.py --registrar [host]

Sin `host`, se usa el que declare `.glados/settings.json` → `gitlab_host`. Registra dos
helpers en este orden: primero uno con **valor vacío**, que borra la lista heredada para
que `manager` no intervenga y no haya diálogos, y después este fichero. Luego comprueba
que el primero es de verdad una cadena vacía, porque ahí es donde falla el registro hecho
desde PowerShell y el síntoma («no puedo autenticar») no se parece a la causa.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import credentials

# host de git → servicio en el almacén. El de GitLab no es un literal: viene de
# `.glados/settings.json` → `gitlab_host`, porque el host de una instancia propia es un
# dato de cada instalación, nunca del kit.
SERVICIOS_FIJOS = {
    "github.com": "github",
    "bitbucket.org": "bitbucket",
}
# Usuario que espera cada sitio cuando se autentica con token.
USUARIOS = {
    "gitlab": "oauth2",
    "github": "x-access-token",
}


def gitlab_host() -> str:
    """Host de la instancia de GitLab de esta instalación, o cadena vacía si no se ha
    configurado todavía (`.glados/settings.json` → `gitlab_host`)."""
    valor = config.local_settings().get("gitlab_host")
    return valor if isinstance(valor, str) else ""


def servicio_de(host: str) -> str | None:
    """Servicio del almacén para ese host de git, o None si no se reconoce."""
    if host and host == gitlab_host():
        return "gitlab"
    return SERVICIOS_FIJOS.get(host)


def leer_peticion() -> dict:
    datos = {}
    for linea in sys.stdin:
        linea = linea.rstrip("\n")
        if not linea:
            break
        if "=" in linea:
            clave, _, valor = linea.partition("=")
            datos[clave] = valor
    return datos


def registrar(host: str | None = None) -> int:
    """Se registra a sí mismo como credential helper de `host` en la config global de git.

    Existe porque hacerlo desde PowerShell no es fiable: el primer valor de la lista tiene
    que ser una **cadena vacía** (así git descarta los helpers heredados y `manager` no
    interviene), y PowerShell 5.1 descarta los argumentos vacíos al llamar a un programa
    externo. Escribir `'""'` para esquivarlo registra dos comillas literales, git intenta
    ejecutar un helper llamado `""` y el fallo aparece como «no puedo autenticar», sin pista.
    Aquí la cadena vacía es una cadena vacía.
    """
    import subprocess
    host = host or gitlab_host()
    if not host:
        print("No hay host de GitLab. Pásalo como argumento o pon `gitlab_host` en "
              ".glados/settings.json.")
        return 1
    clave = f"credential.https://{host}.helper"
    yo = Path(__file__).resolve()
    python = Path(sys.executable).resolve()
    ordenes = [
        ["git", "config", "--global", "--unset-all", clave],
        ["git", "config", "--global", "--add", clave, ""],
        ["git", "config", "--global", "--add", clave, f"!'{python.as_posix()}' '{yo.as_posix()}'"],
        ["git", "config", "--global", f"credential.https://{host}.useHttpPath", "true"],
    ]
    for orden in ordenes:
        r = subprocess.run(orden, capture_output=True, text=True, encoding="utf-8")
        # --unset-all devuelve 5 si la clave no existía: no es un error.
        if r.returncode not in (0, 5):
            print(f"Falló: {' '.join(orden[:5])}\n  {r.stderr.strip()[:200]}")
            return 1

    valores = subprocess.run(["git", "config", "--global", "--get-all", clave],
                             capture_output=True, text=True, encoding="utf-8").stdout.split("\n")
    if valores[:1] != [""]:
        print(f"El primer helper de {host} no es la cadena vacía, sino {valores[:1]!r}. "
              f"Sin eso el Gestor de credenciales de Windows abre un diálogo que cuelga "
              f"la terminal.")
        return 1
    print(f"Registrado para {host}:")
    print(f"  helper vacío (descarta los heredados) + {yo.name}")
    print(f"  useHttpPath true → un token por repo (gitlab.tokens.<ruta>)")
    return 0


def main() -> None:
    config.force_utf8()
    operacion = sys.argv[1] if len(sys.argv) > 1 else ""
    if operacion == "--registrar":
        # Antes de leer stdin: si no, se queda esperando una petición que nadie va a enviar.
        sys.exit(registrar(sys.argv[2] if len(sys.argv) > 2 else None))
    peticion = leer_peticion()
    if operacion != "get":
        return                                   # store / erase: no gestionamos nada aquí

    host = peticion.get("host", "")
    servicio = servicio_de(host)
    if not servicio:
        return                                   # host desconocido: que lo resuelva otro helper

    # path llega solo con useHttpPath activado; sin él se usa el token general.
    proyecto = peticion.get("path", "").removesuffix(".git").strip("/")
    token = None
    if proyecto:
        token = credentials.get(f"{servicio}.tokens.{proyecto}")
    token = token or credentials.get(f"{servicio}.token")
    if not token:
        return

    usuario = USUARIOS.get(servicio) or credentials.get(f"{servicio}.email") or "oauth2"
    print(f"username={usuario}")
    print(f"password={token}")


if __name__ == "__main__":
    main()
