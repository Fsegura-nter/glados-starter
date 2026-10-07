#!/usr/bin/env python3
"""
decisiones_pendientes.py — Red de seguridad para las decisiones que no se escribieron.

Hook: SessionEnd (command), y **debe correr antes del commit del vault**: comprueba el
árbol de trabajo con `git diff`, así que si el commit ya pasó no hay nada que ver.

El problema que resuelve
------------------------
`stop_hook_filter.py` bloquea el cierre cuando detecta una decisión sin registrar, pero solo
mira el ÚLTIMO mensaje del asistente y se calla si ese mensaje acaba en pregunta. Una sesión
de diseño colaborativo —donde cada turno termina preguntando— no lo activa jamás, y las
decisiones de hace diez turnos le son invisibles. Una sesión puede tomar varias decisiones
sobre un proyecto sin que ese hook diga nada.

La detección, al revés
----------------------
En vez de adivinar si hubo una decisión leyendo prosa —difícil y ruidoso—, se comprueba algo
verificable: **una entidad se trabajó a fondo y su ficha no cambió**. Tres señales, y hacen
falta las tres:

1. El cliente o proyecto se menciona en el transcripto por encima de `UMBRAL_MENCIONES`.
2. Aparece vocabulario de cierre, **el que se usa de verdad** («me parece bien», «adelante»,
   «movemos»), no el de acta que nadie escribe.
3. Su ficha **no** figura entre los ficheros que la sesión modificó, según git.

La tercera es la que quita el ruido: si la ficha del proyecto cambió, algo se registró y no
hay nada que avisar. Si no cambió, no se registró. Sin interpretación.

Qué escribe
-----------
Casillas sin marcar en `decisiones_pendientes.md`, en la carpeta `core` del vault, que
aparece en el panel de Tareas. **No toca las fichas de proyecto**: eso lo sigue haciendo
`/decision` con la persona delante. Conserva las casillas pendientes de sesiones anteriores
y no duplica una entidad ya avisada.

Límite que no se puede salvar: si el proceso muere a lo bruto, este hook no corre. Por eso
`session_start.py` también avisa al arrancar si la nota tiene pendientes.

Uso manual: `python decisiones_pendientes.py --check` (no escribe, solo informa).
"""
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

UMBRAL_MENCIONES = 3
MIN_TERMINO = 4
MAX_TRANSCRIPT_MSG = 4000          # por mensaje; evita que un volcado enorme cueste tiempo

# Vocabulario de cierre real, de los dos lados de la conversación.
CIERRE = [
    "me parece bien", "adelante", "vamos con", "vamos a por", "movemos", "lo movemos",
    "aprobado", "apruebo", "dale", "hazlo", "perfecto", "de acuerdo", "conforme",
    "hemos decidido", "se ha decidido", "queda decidido", "decisión tomada", "decidido",
    "acordamos", "hemos acordado", "nos quedamos con", "elegimos", "queda así",
    "empezamos por", "el piloto es", "mejor la opción", "tiro por",
]
# Si algo de esto aparece, o ya se registró o se dijo que no hacía falta.
SILENCIO = [
    "/decision", "no hace falta registrarla", "no hace falta registrar",
    "ya está registrada", "ya la he registrado",
]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
PENDIENTE_RE = re.compile(r"^- \[ \] .*?`(?P<ruta>[^`]+)`", re.MULTILINE)


def _nombre_core() -> str:
    return config.carpetas().get("core") or "core"


def nota_path() -> Path:
    return config.vault_path() / _nombre_core() / "decisiones_pendientes.md"


def fichas() -> dict[Path, list[str]]:
    """{ruta de la ficha: [nombre y aliases]}. Se construye del vault, no de una lista.

    Las carpetas de clientes y proyectos son las que declare `.glados/settings.json` →
    `carpetas`; si ninguna de las dos está configurada, no hay nada que comprobar y la
    red de seguridad simplemente no aplica en este vault.
    """
    salida: dict[Path, list[str]] = {}
    carpetas = config.carpetas()
    raices = [config.vault_path() / carpetas[r] for r in ("clientes", "proyectos") if carpetas.get(r)]
    for carpeta in raices:
        if not carpeta.is_dir():
            continue
        for nota in carpeta.glob("*.md"):
            if nota.name.startswith("_"):
                continue
            nombres = [nota.stem]
            try:
                m = FRONTMATTER_RE.match(nota.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if m:
                for linea in m.group(1).splitlines():
                    if not linea.startswith("aliases:"):
                        continue
                    crudo = linea.split(":", 1)[1].strip().strip("[]")
                    nombres += [a.strip().strip("\"'") for a in crudo.split(",")]
            nombres = [n for n in nombres if len(n) >= MIN_TERMINO]
            if nombres:
                salida[nota] = nombres
    return salida


def texto_de(mensaje: dict) -> str:
    """El texto plano de un mensaje del transcripto, sea string o lista de bloques."""
    contenido = (mensaje.get("message") or {}).get("content")
    if isinstance(contenido, str):
        return contenido[:MAX_TRANSCRIPT_MSG]
    if isinstance(contenido, list):
        trozos = [b.get("text", "") for b in contenido
                  if isinstance(b, dict) and b.get("type") == "text"]
        return " ".join(trozos)[:MAX_TRANSCRIPT_MSG]
    return ""


def lee_transcript(path: Path) -> str:
    """Todo el texto de la conversación, de los dos roles, en minúsculas."""
    if not path or not path.is_file():
        return ""
    trozos = []
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for linea in f:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    m = json.loads(linea)
                except ValueError:
                    continue
                if m.get("type") in ("user", "assistant"):
                    trozos.append(texto_de(m))
    except OSError:
        return ""
    return "\n".join(trozos).lower()


def tocados() -> set[str]:
    """Ficheros que la sesión modificó, en rutas relativas al vault con barras normales."""
    rutas: set[str] = set()
    vault = config.vault_path()
    for cmd in (["git", "diff", "--name-only", "HEAD"],
                ["git", "ls-files", "--others", "--exclude-standard"]):
        try:
            r = subprocess.run(cmd, cwd=vault, capture_output=True, text=True,
                               encoding="utf-8", timeout=30)
        except (OSError, subprocess.SubprocessError):
            continue
        if r.returncode == 0:
            rutas |= {l.strip() for l in r.stdout.splitlines() if l.strip()}
    return rutas


def pendientes(transcripto: str) -> list[tuple[Path, int]]:
    """Las fichas que se trabajaron, no se tocaron, y la sesión cerró algo."""
    if not transcripto:
        return []
    if any(s in transcripto for s in SILENCIO):
        return []
    if not any(c in transcripto for c in CIERRE):
        return []
    vault = config.vault_path()
    cambiados = tocados()
    salida = []
    for ruta, nombres in fichas().items():
        rel = ruta.relative_to(vault).as_posix()
        if rel in cambiados:
            continue
        menciones = sum(transcripto.count(n.lower()) for n in nombres)
        if menciones >= UMBRAL_MENCIONES:
            salida.append((ruta, menciones))
    salida.sort(key=lambda x: -x[1])
    return salida


CABECERA = """---
tags: [core, decisiones]
---

# Decisiones sin registrar

Lo escribe `decisiones_pendientes.py` al cerrar sesión, cuando se trabajó a fondo sobre un
cliente o un proyecto y **su ficha no cambió**. No es una acusación: puede que no hubiera nada
que registrar. Si es el caso, marque la casilla y listo.

Para registrarlas bien: `/decision <lo que se decidió>`.

## Pendientes
"""


def escribe(nuevos: list[tuple[Path, int]]) -> list[str]:
    """Añade las nuevas sin duplicar ni borrar las que ya estaban. Devuelve lo añadido."""
    nota = nota_path()
    vault = config.vault_path()
    previo = nota.read_text(encoding="utf-8") if nota.is_file() else CABECERA
    ya = set(PENDIENTE_RE.findall(previo))
    hoy = date.today().isoformat()
    lineas = []
    for ruta, menciones in nuevos:
        rel = ruta.relative_to(vault).as_posix()
        if rel in ya:
            continue
        lineas.append(f"- [ ] **{ruta.stem}** — la sesión del {hoy} lo trabajó "
                      f"({menciones} menciones) y su ficha no cambió: `{rel}`")
    if not lineas:
        return []
    if "## Pendientes" not in previo:
        previo = CABECERA
    cuerpo = previo.rstrip() + "\n" + "\n".join(lineas) + "\n"
    nota.parent.mkdir(parents=True, exist_ok=True)
    nota.write_text(cuerpo, encoding="utf-8")
    return lineas


def main() -> int:
    check = "--check" in sys.argv
    transcripto = ""
    if check:
        # En manual no hay stdin del hook: se usa el último transcripto del proyecto si existe.
        print("modo --check: no escribe nada")
    else:
        try:
            data = json.load(sys.stdin)
        except Exception:
            return 0
        transcripto = lee_transcript(Path(data.get("transcript_path") or ""))

    if check and not transcripto:
        vault = config.vault_path()
        cambiados = tocados()
        print(f"ficheros que la sesión modificó: {len(cambiados)}")
        for ruta, nombres in sorted(fichas().items()):
            rel = ruta.relative_to(vault).as_posix()
            print(f"  {'tocada  ' if rel in cambiados else 'sin tocar'}  {rel}")
        return 0

    nuevos = pendientes(transcripto)
    if not nuevos:
        return 0
    lineas = escribe(nuevos)
    if lineas and check:
        for l in lineas:
            print(l)
    return 0


if __name__ == "__main__":
    sys.exit(main())
