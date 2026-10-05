"""
config.py — Rutas y ajustes del ecosistema.

El nombre del ecosistema, las colecciones indexables y el vocabulario controlado de
frontmatter son propios de cada instalación: viven en `.glados/settings.json` (ver
`settings.json.tmpl`), nunca escritos aquí. Sin ese fichero, todo cae a un valor por
defecto neutro para que el resto de scripts no se rompan en una instalación nueva.
"""
import json
import os
from pathlib import Path

VAULT_ROOT = Path(__file__).resolve().parent.parent
SETTINGS_PATH = VAULT_ROOT / ".glados" / "settings.json"

DEFAULTS = {
    "nombre": "boveda",
    "colecciones": ["fuentes", "memoria"],
    "vocabulario": {},
    "carpetas": {},
}


def vault_path() -> Path:
    """Raíz del vault: la carpeta que contiene `.glados`."""
    return VAULT_ROOT


def local_settings() -> dict:
    """Ajustes propios de esta instalación (`.glados/settings.json`).

    Faltar no es un error: una instalación recién creada a partir del `.tmpl` todavía
    no tiene valores propios, y cada función de este módulo sabe a qué default caer.
    """
    try:
        return json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def nombre_ecosistema() -> str:
    """Nombre del ecosistema. Nombra la carpeta de datos fuera del vault."""
    valor = local_settings().get("nombre")
    return valor if isinstance(valor, str) and valor else DEFAULTS["nombre"]


def data_dir() -> Path:
    """Datos regenerables fuera del vault.

    Dos motivos para que vivan aquí y no dentro del vault: una base de datos (índice
    vectorial, SQLite) dentro de una carpeta sincronizada (Drive, Dropbox…) se corrompe
    si la sincronización la toca a mitad de escritura, y pueden pesar gigabytes que no
    deben viajar junto a las notas.
    """
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("USERPROFILE") or str(Path.home())
    return Path(base) / nombre_ecosistema()


def colecciones() -> list[str]:
    """Nombres de las colecciones indexables, declaradas en `settings.json`."""
    valor = local_settings().get("colecciones")
    return valor if isinstance(valor, list) else list(DEFAULTS["colecciones"])


def vocabulario() -> dict[str, list[str]]:
    """Vocabulario controlado de frontmatter, declarado en `settings.json`."""
    valor = local_settings().get("vocabulario")
    return valor if isinstance(valor, dict) else dict(DEFAULTS["vocabulario"])


def carpetas() -> dict[str, str]:
    """Nombres de carpeta por rol (`clientes`, `proyectos`, `fuentes`, `memoria`,
    `archivo`...), declarados en `settings.json`.

    Vacío por defecto, a propósito: la estructura de carpetas de un vault nuevo la
    propone la entrevista de alta, no un valor de fábrica de este kit. Un hook que
    necesite la carpeta de un rol debe tratar su ausencia como "esa función no aplica
    en este vault", nunca como un error — el mismo principio que la capa de búsqueda
    opcional.
    """
    valor = local_settings().get("carpetas")
    return valor if isinstance(valor, dict) else dict(DEFAULTS["carpetas"])


def snapshot_path() -> Path:
    """Ruta del snapshot de sesión, compartida por `precompact_snapshot.py` (que lo
    escribe) y `session_start.py` (que lo lee). No es una carpeta de contenido del
    vault — vive siempre dentro de `.glados` — así que no depende de `carpetas()`.
    """
    return vault_path() / ".glados" / "last_session.md"


def force_utf8() -> None:
    """Fuerza UTF-8 en stdin/stdout/stderr del proceso.

    Los hooks reciben el JSON por stdin, y si la ruta del vault o los prompts llevan
    acentos, la codificación por defecto de Windows (cp1252) los corrompe y el hook
    falla en silencio. No basta con poner `PYTHONIOENCODING` delante del comando: esa
    sintaxis solo la entiende un shell POSIX, y los hooks corren en PowerShell cuando
    no encuentran Git Bash.
    """
    import sys
    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass
