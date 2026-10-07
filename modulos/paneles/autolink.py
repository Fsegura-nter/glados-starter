#!/usr/bin/env python3
"""
autolink.py — Añade [[wikilinks]] a las notas del vault cuando mencionan otra nota.

Hook: PostToolUse (matcher Write|Edit), tipo command.

Sustituye a un hook de tipo `agent` que lanzaba un subagente en cada escritura: costaba
una llamada de modelo por fichero tocado y, al editar la nota, volvía a disparar el
mismo PostToolUse. Este script escribe con Python, no con una herramienta, así que no
puede reentrar.

Reglas:
  · Solo notas del vault en .md, fuera de las carpetas de sistema y de las de solo
    lectura o generadas (fuentes, archivo, memoria, repos sincronizados, plantillas).
  · Enlaza la PRIMERA aparición de cada nota, una vez por fichero. Sin enlaces forzados.
  · Nunca toca frontmatter, bloques de código, código en línea, enlaces ya existentes,
    URLs, comentarios HTML ni encabezados.
  · Alias que no coincide con el nombre del fichero → [[archivo|Texto mostrado]].
Siempre termina con exit 0: un fallo aquí no debe romper la escritura del usuario.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

# Carpetas de sistema/herramienta, fijas en cualquier instalación.
DIRS_FIJOS = {'.claude', '.glados', '.obsidian'}
# Carpetas generadas o de referencia que no se tocan nunca, fijas por convención del kit
# (no dependen de cómo el usuario nombre sus propias carpetas de contenido).
DIRS_GENERADAS = {'_repos', 'areas', '99_PROMPTS'}
EXCLUDED_NAMES = {'CLAUDE.md', 'MEMORY.md'}   # no son notas: son instrucciones e índices
MIN_TERM_LEN = 4

# Nombres de nota que además son palabras corrientes del idioma. Enlazarlos en cada
# aparición produce enlaces falsos: una frase como «gestor de tareas tipo Trello» en la
# ficha de un cliente puede acabar apuntando a la lista de tareas abiertas de quien usa
# el vault, sin relación alguna con el cliente. La nota sigue existiendo y se enlaza a
# mano donde de verdad toque.
TERMINOS_GENERICOS = {'tareas', 'notas', 'inicio', 'stack', 'proyectos', 'clientes',
                      'principios', 'credenciales', 'maquina', 'máquina',
                      'formacion', 'formación', 'conocimiento', 'recruiting', 'gdpr'}

FRONTMATTER_RE = re.compile(r'^(---\s*\n.*?\n---\s*\n)', re.DOTALL)
# Zonas que no se tocan nunca. Sin DOTALL global: solo los patrones multilínea lo activan
# con (?s:...), porque un `.*$` con DOTALL se traga el resto del documento.
PROTECTED_RE = re.compile(
    r'(?s:```.*?```)'            # bloque de código
    r'|`[^`\n]*`'                # código en línea
    r'|\[\[[^\]]*\]\]'           # wikilink existente
    r'|\[[^\]]*\]\([^)]*\)'      # enlace markdown
    r'|(?s:<!--.*?-->)'          # comentario HTML
    r'|^#{1,6} [^\n]*$'          # encabezado
    r'|https?://\S+'             # URL
    r'|^\s*(?:tipo|cliente|proyecto|aliases|tags|estado|fecha|gitlab):[^\n]*$',  # propiedad
    re.MULTILINE,
)


def excluded_parts() -> set[str]:
    """Carpetas que nunca se tocan: las fijas, las generadas, y las de solo lectura o
    archivo que esta instalación haya nombrado en `.glados/settings.json` → `carpetas`.
    Las memorias describen lo que era cierto cuando se escribieron; meterles enlaces
    nuevos falsea el documento.
    """
    carpetas = config.carpetas()
    extra = {carpetas[r] for r in ('fuentes', 'archivo', 'memoria') if carpetas.get(r)}
    return DIRS_FIJOS | DIRS_GENERADAS | extra


def parse_aliases(text: str) -> list[str]:
    m = FRONTMATTER_RE.match(text)
    if not m:
        return []
    fm = m.group(1)
    inline = re.search(r'^aliases:\s*\[(.*?)\]', fm, re.MULTILINE)
    if inline:
        return [a.strip().strip('"\'') for a in inline.group(1).split(',') if a.strip()]
    block = re.search(r'^aliases:\s*\n((?:\s+-\s+.*\n)+)', fm, re.MULTILINE)
    if block:
        return [line.split('-', 1)[1].strip().strip('"\'') for line in block.group(1).splitlines()]
    return []


def is_vault_note(path: Path, vault_root: Path, excluded: set[str]) -> bool:
    try:
        rel = path.resolve().relative_to(vault_root)
    except ValueError:
        return False
    if path.suffix.lower() != '.md' or path.name in EXCLUDED_NAMES:
        return False
    return not (excluded & set(rel.parts))


def build_targets(exclude: Path, vault_root: Path, excluded: set[str]) -> list[tuple[str, str]]:
    """[(término, nombre_de_nota)] ordenado de más largo a más corto."""
    targets: dict[str, str] = {}
    for note in vault_root.rglob('*.md'):
        if not is_vault_note(note, vault_root, excluded) or note.resolve() == exclude.resolve():
            continue
        stem = note.stem
        try:
            aliases = parse_aliases(note.read_text(encoding='utf-8'))
        except Exception:
            aliases = []
        for term in [stem, *aliases]:
            if len(term) >= MIN_TERM_LEN and term.lower() not in TERMINOS_GENERICOS:
                targets[term.lower()] = stem
    return sorted(targets.items(), key=lambda kv: -len(kv[0]))


def link_for(matched_text: str, note_stem: str) -> str:
    if matched_text.lower() == note_stem.lower():
        return f'[[{matched_text}]]'
    return f'[[{note_stem}|{matched_text}]]'


def already_linked(text: str) -> set[str]:
    """Notas que ya tienen un wikilink en el documento. No se vuelven a enlazar: una
    nota se cita una vez, y lo que se enlazó a mano se respeta."""
    return {m.group(1).split('|')[0].split('#')[0].strip().lower()
            for m in re.finditer(r'\[\[([^\]]+)\]\]', text)}


def process(text: str, targets: list[tuple[str, str]]) -> tuple[str, list[str]]:
    fm_match = FRONTMATTER_RE.match(text)
    head = fm_match.group(1) if fm_match else ''
    body = text[len(head):]
    ya = already_linked(text)

    # Trocea el cuerpo en zonas protegidas y libres, y solo modifica las libres.
    piezas, cursor = [], 0
    for m in PROTECTED_RE.finditer(body):
        piezas.append(('libre', body[cursor:m.start()]))
        piezas.append(('bloqueada', m.group(0)))
        cursor = m.end()
    piezas.append(('libre', body[cursor:]))

    usados: list[str] = []
    for i, (clase, trozo) in enumerate(piezas):
        if clase != 'libre' or not trozo.strip():
            continue
        for term, stem in targets:
            if stem in usados or stem.lower() in ya:
                continue
            rx = re.compile(r'(?<!\w)(' + re.escape(term) + r')(?!\w)', re.IGNORECASE)
            m = rx.search(trozo)
            if not m:
                continue
            trozo = trozo[:m.start()] + link_for(m.group(1), stem) + trozo[m.end():]
            usados.append(stem)
        piezas[i] = (clase, trozo)

    return head + ''.join(t for _, t in piezas), usados


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return
    vault_root = config.vault_path()
    excluded = excluded_parts()
    raw = (data.get('tool_input') or {}).get('file_path') or ''
    if not raw:
        return
    path = Path(raw)
    if not path.is_absolute():
        path = Path(data.get('cwd', str(vault_root))) / path
    if not path.exists() or not is_vault_note(path, vault_root, excluded):
        return
    try:
        original = path.read_text(encoding='utf-8')
    except Exception:
        return
    nuevo, usados = process(original, build_targets(path, vault_root, excluded))
    if usados and nuevo != original:
        try:
            path.write_text(nuevo, encoding='utf-8')
            print(f'autolink: {path.name} → {", ".join(usados)}', file=sys.stderr)
        except Exception:
            pass


if __name__ == '__main__':
    try:
        main()
    finally:
        sys.exit(0)
