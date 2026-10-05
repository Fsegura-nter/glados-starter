#!/usr/bin/env python3
"""
credentials.py — Almacén único de credenciales del ecosistema.

No se llama `secrets.py` a propósito: `.glados` va al principio de `sys.path` y ese
nombre tapa el módulo `secrets` de la biblioteca estándar, que usan `urllib3` y otras
dependencias.

Vive en `%LOCALAPPDATA%\\<nombre>\\secrets.json`, FUERA del vault y de cualquier repo:
el vault puede terminar sincronizado a la nube o llevar git, y un token dentro sería un
commit para siempre.

ESTRUCTURA
----------
Cada valor puede ser una cadena suelta o una entrada con metadatos. Las dos formas
funcionan; la segunda dice QUÉ token es sin tener que mirar el valor:

    "gitlab": {
      "token": { "value": "glpat-…", "name": "mi-token", "expires": "2027-01-01" },
      "tokens": {                      ← uno por proyecto, cuando no hay token general
        "grupo/repo": { "value": "…" }
      }
    },
    "google": {
      "client_id": "…",
      "client_secret": "…",
      "refresh_token": "…"
    }

NUNCA imprime un valor completo. Para inspeccionar el almacén, usar `list`: enmascara
por diseño.

Uso:
    python .glados/credentials.py list
    python .glados/credentials.py get <clave>
    python .glados/credentials.py set <clave> <valor>

Desde Python:
    from credentials import get, set, listar, ruta_almacen
"""
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

TOKENS_KEY = "tokens"
VALUE_KEY = "value"

# Claves conocidas. Un kit nuevo arranca solo con GitLab (lectura de repos) y Google
# (Gmail/Drive/Calendar); añadir un servicio nuevo es una entrada más aquí.
ENV_MAP: dict[str, dict[str, str]] = {
    "gitlab": {"token": "GITLAB_PERSONAL_ACCESS_TOKEN"},
    "google": {
        "client_id": "GOOGLE_CLIENT_ID",
        "client_secret": "GOOGLE_CLIENT_SECRET",
        "refresh_token": "GOOGLE_REFRESH_TOKEN",
    },
}


# ─── lectura y escritura ──────────────────────────────────────────────────────

def ruta_almacen() -> Path:
    """`%LOCALAPPDATA%\\<nombre>\\secrets.json` — fuera del vault y fuera de git."""
    return config.data_dir() / "secrets.json"


def _load() -> dict:
    try:
        return json.loads(ruta_almacen().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    ruta = ruta_almacen()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    _restrict_acl(ruta)


def _restrict_acl(path: Path) -> None:
    """Restringe el fichero al usuario actual. Falla en silencio si `icacls` no está
    (no-Windows) o si el usuario no tiene permiso: no es motivo para romper el guardado."""
    usuario = os.environ.get("USERNAME")
    if not usuario:
        return
    try:
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", f"{usuario}:F"],
                        check=False, capture_output=True, timeout=10)
    except Exception:
        pass


def _valor_de(entrada) -> str:
    """Una entrada puede ser cadena o {value, …}. Devuelve siempre la cadena."""
    if isinstance(entrada, str):
        return entrada
    if isinstance(entrada, dict):
        v = entrada.get(VALUE_KEY, "")
        return v if isinstance(v, str) else ""
    return ""


def _partes(clave: str) -> tuple[str, str, str]:
    """'gitlab.tokens.grupo/repo' → ('gitlab', 'tokens', 'grupo/repo')."""
    p = clave.split(".", 2)
    if len(p) >= 3 and p[1] == TOKENS_KEY:
        return p[0], TOKENS_KEY, p[2]
    if len(p) >= 2:
        return p[0], p[1], ""
    return clave, "", ""


def _entrada(data: dict, clave: str):
    servicio, campo, proyecto = _partes(clave)
    cont = data.get(servicio) or {}
    if campo == TOKENS_KEY:
        return (cont.get(TOKENS_KEY) or {}).get(proyecto)
    return cont.get(campo)


def _set_entrada(data: dict, clave: str, nueva) -> None:
    servicio, campo, proyecto = _partes(clave)
    cont = data.setdefault(servicio, {})
    if campo == TOKENS_KEY:
        cont.setdefault(TOKENS_KEY, {})[proyecto] = nueva
    else:
        cont[campo] = nueva


# ─── interfaz pública ─────────────────────────────────────────────────────────

def get(clave: str) -> str | None:
    """get("gitlab.token") o get("gitlab.tokens.grupo/repo") → el valor, o None."""
    valor = _valor_de(_entrada(_load(), clave))
    return valor or None


def set(clave: str, valor: str) -> None:
    """Guarda el valor, conservando los metadatos que ya tuviera la entrada."""
    data = _load() or {}
    actual = _entrada(data, clave)
    if isinstance(actual, dict):
        actual[VALUE_KEY] = valor
        _set_entrada(data, clave, actual)
    else:
        _set_entrada(data, clave, valor)
    _save(data)


def _enmascarar(valor: str) -> str:
    """Nunca revela el valor: solo si está puesto y cuántos caracteres tiene."""
    if not valor:
        return "— vacío"
    return f"puesto · {len(valor)} car."


def listar() -> list[tuple[str, str]]:
    """[(clave, valor_enmascarado), …] de todo lo guardado. Nunca el valor entero."""
    filas: list[tuple[str, str]] = []
    for servicio, cont in _load().items():
        if servicio.startswith("_") or not isinstance(cont, dict):
            continue
        for campo, entrada in cont.items():
            if campo == TOKENS_KEY and isinstance(entrada, dict):
                for proyecto, e in entrada.items():
                    filas.append((f"{servicio}.{TOKENS_KEY}.{proyecto}", _enmascarar(_valor_de(e))))
                continue
            filas.append((f"{servicio}.{campo}", _enmascarar(_valor_de(entrada))))
    return filas


def huerfanas() -> list[str]:
    """Claves guardadas que ningún consumidor sabe leer: el campo no está declarado
    en `ENV_MAP` para ese servicio. La forma por proyecto (`<servicio>.tokens.<ruta>`)
    es siempre legítima y nunca se marca huérfana, aunque el servicio solo declare un
    `token` general: es la vía documentada para guardar un token por repositorio.

    Sin esto, un error tipográfico al guardar (`gitlab.toekn` en vez de `gitlab.token`)
    se guarda, `listar()` lo muestra como puesto para siempre, y todo consumidor sigue
    leyendo vacío sin que nada lo avise: peor que no tener la credencial, porque esa
    sí se nota.
    """
    salida: list[str] = []
    for servicio, cont in _load().items():
        if servicio.startswith("_") or not isinstance(cont, dict):
            continue
        conocidas = ENV_MAP.get(servicio, {})
        for campo, entrada in cont.items():
            if campo == TOKENS_KEY:
                continue
            if campo not in conocidas and _valor_de(entrada):
                salida.append(f"{servicio}.{campo}")
    return salida


def env_for(servicio: str) -> dict[str, str]:
    """{VARIABLE_DE_ENTORNO: valor} de un servicio, solo con lo que esté puesto."""
    cont = _load().get(servicio) or {}
    salida = {}
    for clave, var in ENV_MAP.get(servicio, {}).items():
        valor = _valor_de(cont.get(clave))
        if valor:
            salida[var] = valor
    return salida


# ─── CLI ───────────────────────────────────────────────────────────────────────

def _cmd_list() -> int:
    print(f"Almacén: {ruta_almacen()}")
    filas = listar()
    if not filas:
        print("(vacío)")
        return 0
    for clave, forma in filas:
        print(f"  {clave:<30} {forma}")
    huerfanas_ = huerfanas()
    if huerfanas_:
        print()
        print("Guardadas pero NO usables — ningún consumidor sabe leerlas:")
        for h in huerfanas_:
            print(f"  · {h}")
    return 0


def main() -> int:
    config.force_utf8()
    args = sys.argv[1:]
    accion = args[0] if args else "help"

    if accion in ("help", "-h", "--help"):
        print(__doc__)
        return 0
    if accion == "list":
        return _cmd_list()
    if accion == "get" and len(args) == 2:
        valor = get(args[1])
        if not valor:
            print(f"(vacío: {args[1]})", file=sys.stderr)
            return 1
        print(valor)
        return 0
    if accion == "set" and len(args) == 3:
        set(args[1], args[2])
        print(f"Guardado {args[1]}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
