#!/usr/bin/env python3
"""
paneles_area.py — Genera un panel por área de trabajo en la carpeta `core` del vault.

Mucha gente no navega por carpetas, sino por bloques de trabajo. Pero mover las notas a
carpetas por área obligaría a reescribir `config.py`, el injector, el dashboard y las
plantillas de alta. Así que el disco se queda organizado por tipo y la navegación se
resuelve arriba: una nota-panel por área, anclada en los marcadores de Obsidian.

**Las áreas no son un vocabulario del kit: son la taxonomía de quien usa el vault.** Se
declaran en `.glados/settings.json` → `areas`, como un diccionario
`{slug: {titulo, lema, cliente, fuentes, carpetas}}`. Sin ninguna declarada, este script no
tiene nada que generar — no es un error, es un vault que todavía no ha pasado por la
entrevista de alta.

Cada área produce dos ficheros en `<carpeta-core>/areas/`:
  · <slug>.base — las consultas vivas (Proyectos, Propuestas, Reuniones). GENERADO,
    se sobreescribe entero en cada ejecución. No editar a mano.
  · <slug>.md   — el panel que se abre. Se regenera preservando "## Notas", igual
    que hace `sync_projects.py` con las notas de repo.

También registra los marcadores en `.obsidian/bookmarks.json` sin tocar los que ya
hubiera. Obsidian mantiene sus ajustes en memoria: recargar el vault (Ctrl+R) después.

Uso: python paneles_area.py
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

PRESERVED_SECTIONS = ["## Notas"]


def nombre_core() -> str:
    return config.carpetas().get("core") or "core"


def nombre_proyectos() -> str:
    return config.carpetas().get("proyectos") or "proyectos"


def nombre_reuniones() -> str:
    return config.carpetas().get("reuniones") or "reuniones"


def nombre_fuentes() -> str:
    return config.carpetas().get("fuentes") or "fuentes"


def areas_path() -> Path:
    return config.vault_path() / nombre_core() / "areas"


def bookmarks_path() -> Path:
    return config.vault_path() / ".obsidian" / "bookmarks.json"


def areas() -> dict:
    """Las áreas declaradas en `.glados/settings.json` → `areas`. Vacío si no hay
    ninguna: no se inventa una taxonomía por defecto."""
    valor = config.local_settings().get("areas")
    return valor if isinstance(valor, dict) else {}


def build_base(slug: str) -> str:
    """Las tres consultas de un área. Filtran por el campo `area`, no por carpeta."""
    proyectos, reuniones = nombre_proyectos(), nombre_reuniones()
    return f"""# GENERADO por paneles_area.py — no editar a mano.
properties:
  estado:
    displayName: Estado
  cliente:
    displayName: Cliente
  gitlab:
    displayName: GitLab
  fecha:
    displayName: Fecha
  proyecto:
    displayName: Proyecto
  formula.dias_desde:
    displayName: Días

formulas:
  dias_desde: '(now() - file.mtime).days'

views:
  - type: table
    name: Proyectos
    filters:
      and:
        - file.inFolder("{proyectos}")
        - file.ext == "md"
        - not:
            - file.inFolder("{proyectos}/_repos")
        - 'area == "{slug}"'
        - 'estado != "propuesta"'
    groupBy:
      property: estado
      direction: ASC
    order:
      - file.name
      - estado
      - gitlab
      - formula.dias_desde

  - type: table
    name: Propuestas
    filters:
      and:
        - file.inFolder("{proyectos}")
        - file.ext == "md"
        - 'area == "{slug}"'
        - 'estado == "propuesta"'
    order:
      - file.name
      - cliente
      - fecha
      - formula.dias_desde

  - type: table
    name: Reuniones
    limit: 15
    filters:
      and:
        - file.inFolder("{reuniones}")
        - file.ext == "md"
        - 'tipo == "reunion"'
        - 'area == "{slug}"'
    order:
      - fecha
      - file.name
      - proyecto
"""


def build_panel(slug: str, meta: dict, preserved: dict) -> str:
    cliente = meta.get("cliente")
    cabecera = f"> Cliente: [[{cliente}]]" if cliente else "> Sin cliente: es trabajo propio."
    if meta.get("fuentes"):
        cabecera += f" · Documentación indexada en `{nombre_fuentes()}/{meta['fuentes']}/`"
    for carpeta in meta.get("carpetas") or []:
        cabecera += f" · Material en `{carpeta}/`"

    if cliente:
        decisiones = (f"Las decisiones y acuerdos con el cliente se escriben en "
                      f"[[{cliente}#Acuerdos y decisiones]]. Las técnicas, en la sección "
                      f"`## Decisiones` de cada proyecto.")
    else:
        decisiones = ("Sin cliente, así que las decisiones viven en la sección "
                      "`## Decisiones` de cada proyecto.")

    nota = f"""---
tipo: panel
area: {slug}
tags: [area, panel]
---

# {meta.get('titulo', slug)}

> [!abstract] {meta.get('lema', '')}
{cabecera}

## Proyectos
![[{slug}.base#Proyectos]]

## Propuestas
![[{slug}.base#Propuestas]]

## Reuniones
![[{slug}.base#Reuniones]]

## Tareas abiertas
```query
task-todo:/.+/ [area:{slug}]
```

## Decisiones
{decisiones}

"""
    for section in PRESERVED_SECTIONS:
        nota += f"{preserved.get(section, section + chr(10))}\n"
    return nota


def extract_preserved(content: str) -> dict[str, str]:
    """Copiado en espíritu de sync_projects.py: lo escrito a mano no se pierde."""
    sections, lines, i = {}, content.split("\n"), 0
    while i < len(lines):
        title = lines[i].strip()
        if title in PRESERVED_SECTIONS:
            block = [lines[i]]
            i += 1
            while i < len(lines) and not (lines[i].startswith("## ") and lines[i].strip() != title):
                block.append(lines[i])
                i += 1
            sections[title] = "\n".join(block)
        else:
            i += 1
    return sections


def sync_bookmarks(paneles: list[tuple[str, str]]) -> int:
    """Ancla inicio + los paneles. No toca marcadores ajenos ni duplica los propios."""
    bookmarks = bookmarks_path()
    try:
        data = json.loads(bookmarks.read_text(encoding="utf-8"))
    except Exception:
        data = {"items": []}
    items = data.get("items", [])

    core = nombre_core()
    deseados = [(f"{core}/inicio.md", "Centro de Desarrollo")]
    deseados += [(f"{core}/areas/{slug}.md", titulo) for slug, titulo in paneles]
    deseados += [(f"{core}/tareas.md", "Tareas"), (f"{core}/laboratorio.md", "Laboratorio")]

    existentes = {it.get("path") for it in items if it.get("type") == "file"}
    ctime = int(time.time() * 1000)
    nuevos = 0
    for path, titulo in deseados:
        if path in existentes:
            continue
        items.append({"type": "file", "ctime": ctime, "path": path, "title": titulo})
        nuevos += 1

    data["items"] = items
    bookmarks.parent.mkdir(parents=True, exist_ok=True)
    bookmarks.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return nuevos


def main() -> None:
    todas = areas()
    if not todas:
        print("No hay ninguna área declarada en .glados/settings.json → areas. "
              "Nada que generar todavía.")
        return

    carpeta_areas = areas_path()
    carpeta_areas.mkdir(parents=True, exist_ok=True)
    core = nombre_core()
    paneles = []
    for slug, meta in todas.items():
        base_path = carpeta_areas / f"{slug}.base"
        base_path.write_text(build_base(slug), encoding="utf-8")

        panel_path = carpeta_areas / f"{slug}.md"
        preserved = (extract_preserved(panel_path.read_text(encoding="utf-8"))
                     if panel_path.exists() else {})
        panel_path.write_text(build_panel(slug, meta, preserved), encoding="utf-8")
        titulo = meta.get("titulo", slug)
        paneles.append((slug, titulo))
        print(f"  [PANEL] {titulo:20} -> {core}/areas/{slug}.md + {slug}.base")

    nuevos = sync_bookmarks(paneles)
    print(f"\nPaneles: {len(paneles)} · marcadores nuevos: {nuevos}")
    print("Recarga el vault en Obsidian (Ctrl+R) para verlos.")


if __name__ == "__main__":
    main()
