#!/usr/bin/env python3
"""
stop_hook_filter.py — Impide cerrar una sesión que dejó algo sin escribir.

Hook: Stop (command). Para bloquear el cierre imprime el bloque hookSpecificOutput
con decision=block; para dejar terminar no imprime nada.

Dos motivos de bloqueo, por orden de prioridad:

1. **Principio generalizable** — la sesión cristalizó una regla que vale más allá de este
   proyecto y no está en el fichero de principios del vault.
2. **Decisión de cliente sin registrar** — se decidió algo sobre un cliente o proyecto
   conocido y no se pasó por /decision. Lo que no se escribe en la ficha se pierde cuando la
   conversación desaparece: es el motivo de que exista este módulo.

**Sobre los falsos positivos del segundo:** detectar una decisión es más difuso que detectar
un principio, así que exige DOS señales a la vez — una frase de cierre y la mención de un
cliente o proyecto que existe en el vault — y se calla en cuanto ve que ya se está
registrando. Aun así saltará alguna vez de más. Si molesta, la lista DECISIONES es el sitio
donde afinarlo, y quitar el motivo entero es borrar una función.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

NOMBRE_CORE = config.carpetas().get("core") or "core"

RAZON_PRINCIPIO = (f"Esta sesión cristalizó un principio generalizable. "
                   f"Añádelo a {NOMBRE_CORE}/principios.md antes de terminar.")
RAZON_DECISION = ("Esta sesión tomó una decisión sobre {entidad} y no está registrada. "
                  "Regístrala con /decision antes de terminar, o di que no hace falta.")

STRONG = [
    "principio generalizable",
    "regla general",
    "para proyectos futuros",
    "lección aprendida",
    "queda como norma",
    "añadir a principios",
    "esto aplica siempre",
    "nunca más hacer",
]
CONFIRMATIONS = ["confirmado", "decidido", "cerrado", "aceptado", "vamos con", "elegimos", "queda así"]
GENERALIZATIONS = ["en general", "siempre que", "en todos los proyectos", "como norma", "de ahora en adelante"]

# Frases que marcan una decisión tomada, no una opción sobre la mesa.
DECISIONES = [
    "hemos decidido",
    "se ha decidido",
    "queda decidido",
    "decisión tomada",
    "la decisión es",
    "hemos acordado",
    "se acuerda",
    "acordamos",
    "nos quedamos con",
    "vamos a ir por",
    "queda cerrado que",
]
# Si algo de esto aparece, la decisión ya se está registrando o se acaba de registrar.
YA_REGISTRADA = ["/decision", "acuerdos y decisiones", "## decisiones", "decision.md"]

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
MIN_TERMINO = 4


def entidades() -> list[str]:
    """Nombres y aliases de clientes y proyectos. Son pocas notas: el coste es despreciable.

    Se construye del vault, no de una lista escrita a mano: una ficha nueva entra sola.
    Las carpetas son las que declare `.glados/settings.json` → `carpetas`; si ninguna de
    las dos está configurada, no hay ninguna entidad que comprobar.
    """
    nombres = []
    carpetas = config.carpetas()
    raices = [config.vault_path() / carpetas[r] for r in ("clientes", "proyectos") if carpetas.get(r)]
    for carpeta in raices:
        if not carpeta.is_dir():
            continue
        for nota in carpeta.glob("*.md"):
            if nota.name.startswith("_"):
                continue
            nombres.append(nota.stem)
            try:
                m = FRONTMATTER_RE.match(nota.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
            if not m:
                continue
            for linea in m.group(1).splitlines():
                if not linea.startswith("aliases:"):
                    continue
                crudo = linea.split(":", 1)[1].strip().strip("[]")
                nombres += [a.strip().strip("\"'") for a in crudo.split(",")]
    return [n for n in nombres if len(n) >= MIN_TERMINO]


def motivo(data: dict) -> str:
    if data.get("stop_hook_active"):
        return ""
    msg = data.get("last_assistant_message", "") or ""
    if len(msg) < 250:
        return ""
    tail = msg[-400:]
    if tail.rstrip().endswith("?") or "¿" in tail:
        return ""
    low = msg.lower()

    # 1. Principio generalizable.
    if "principios.md" not in low:
        if any(kw in low for kw in STRONG):
            return RAZON_PRINCIPIO
        if any(k in low for k in CONFIRMATIONS) and any(k in low for k in GENERALIZATIONS):
            return RAZON_PRINCIPIO

    # 2. Decisión de cliente sin registrar. Exige las dos señales a la vez.
    if any(k in low for k in YA_REGISTRADA):
        return ""
    if not any(k in low for k in DECISIONES):
        return ""
    for nombre in entidades():
        if nombre.lower() in low:
            return RAZON_DECISION.format(entidad=nombre)
    return ""


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    razon = motivo(data)
    if razon:
        # Formato vigente. El `decision`/`reason` al nivel raíz aún se acepta por
        # compatibilidad, pero hookSpecificOutput es el preferido.
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "decision": "block",
                "reason": razon,
            }
        }, ensure_ascii=False))


if __name__ == "__main__":
    main()
