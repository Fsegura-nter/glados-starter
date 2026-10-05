#!/usr/bin/env python3
"""
context_injector.py — Inyector automático de contexto para Claude Code.

Hook: UserPromptSubmit
Acción: detecta en el mensaje menciones a clientes o proyectos del vault (por su
        nombre de fichero o sus `aliases` de frontmatter) y carga la nota relevante
        como `additionalContext`. Si el mensaje pide documentación, añade fragmentos
        indexados de la carpeta de fuentes.

El mapa de palabras clave no está escrito a mano: se construye en cada ejecución a
partir del nombre de archivo y los `aliases` del frontmatter de las notas de cliente
y de proyecto. Nota nueva = palabra clave nueva, sin tocar código.

Presupuesto de tiempo: este hook corre en cada mensaje, así que solo usa la stdlib y
la capa de búsqueda léxica (milisegundos). La capa semántica (embeddings) no entra
aquí: carga un modelo y tarda muchísimo más que el timeout del hook, así que se
consulta aparte, a mano.

La capa léxica (`lexical.py`) es opcional: un vault recién creado no tiene índice
todavía. Si el módulo no está, si no hay base de datos o si la búsqueda falla por lo
que sea, el resultado es "sin contexto que inyectar", nunca un error — este hook no
puede romper el envío de un mensaje.
"""
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

try:
    import lexical
except Exception:
    lexical = None

MAX_NOTES = 3
MAX_NOTE_CHARS = 6000
MIN_KEYWORD_LEN = 3
# La nota de proyecto reciente solo se inyecta si de verdad es reciente: sin esto,
# cada mensaje sin entidad arrastraba una nota entera de hasta 6000 caracteres.
FALLBACK_MAX_AGE = timedelta(hours=48)

# Peticiones de documentación → buscar en la carpeta de fuentes aunque no haya entidad
DOC_KEYWORDS = [
    'documentación', 'documentacion', 'funcional', 'análisis funcional', 'analisis funcional',
    'requisito', 'requisitos', 'especificación', 'especificacion', 'spec', 'historia de usuario',
    'criterio de aceptación', 'criterios de aceptación', 'según el doc', 'segun el doc',
    'qué dice el doc', 'que dice el doc', 'cómo funciona', 'como funciona', 'regla de negocio',
]

FRONTMATTER_RE = re.compile(r'^---\s*\n(.*?)\n---', re.DOTALL)


def parse_frontmatter(text: str) -> dict:
    """Parser mínimo de frontmatter: claves simples, listas inline y listas con guiones."""
    m = FRONTMATTER_RE.match(text)
    if not m:
        return {}
    data, current = {}, None
    for line in m.group(1).splitlines():
        if re.match(r'^\s+-\s+', line) and current:
            data.setdefault(current, []).append(line.split('-', 1)[1].strip().strip('"\''))
            continue
        kv = re.match(r'^([\w-]+):\s*(.*)$', line)
        if not kv:
            continue
        key, value = kv.group(1), kv.group(2).strip()
        current = key
        if value.startswith('[') and value.endswith(']'):
            data[key] = [v.strip().strip('"\'') for v in value[1:-1].split(',') if v.strip()]
        elif value:
            data[key] = value.strip('"\'')
    return data


def note_keywords(path: Path, fm: dict) -> set[str]:
    stem = path.stem.lower()
    keys = {k for k in (stem, stem.replace('-', ' ').replace('_', ' ')) if len(k) >= MIN_KEYWORD_LEN}
    aliases = fm.get('aliases', [])
    if isinstance(aliases, str):
        aliases = [aliases]
    # Los aliases son deliberados: se aceptan cortos (siglas); el match por límite de
    # palabra evita falsos positivos.
    keys.update(a.lower() for a in aliases if len(a) >= 2)
    return keys


def carpeta(rol: str) -> Path | None:
    """Carpeta del vault para ese rol (`clientes`, `proyectos`...), o None si el
    usuario no le puso nombre en `settings.json`. Sin nombre configurado, quien llama
    a esto simplemente no encuentra nada que indexar — no es un error, esa parte del
    hook no aplica en este vault.
    """
    nombre = config.carpetas().get(rol)
    return (config.vault_path() / nombre) if nombre else None


def build_entity_index() -> list[tuple[set[str], str, str | None]]:
    """[(keywords, ruta_relativa, cliente_o_None)] para clientes y proyectos."""
    index = []
    for rol, kind in (('clientes', 'cliente'), ('proyectos', 'proyecto')):
        base = carpeta(rol)
        if not base or not base.exists():
            continue
        for path in base.glob('*.md'):
            try:
                text = path.read_text(encoding='utf-8')
            except Exception:
                continue
            fm = parse_frontmatter(text)
            if kind == 'cliente':
                client = path.stem
            else:
                # cliente: "[[Nombre]]" o "[[Nombre|alias]]" → Nombre
                raw = re.sub(r'[\[\]]', '', fm.get('cliente', '') or '')
                client = raw.split('|')[0].strip() or None
            rel = path.relative_to(config.vault_path()).as_posix()
            index.append((note_keywords(path, fm), rel, client))
    return index


def mentions(prompt: str, keyword: str) -> bool:
    return re.search(r'(?<!\w)' + re.escape(keyword) + r'(?!\w)', prompt) is not None


def load(relative_path: str) -> str | None:
    full = config.vault_path() / relative_path
    try:
        if full.is_dir():
            parts = [f'## {p.name}\n{p.read_text(encoding="utf-8")}' for p in sorted(full.glob('*.md'))]
            content = '\n\n'.join(parts)
        else:
            content = full.read_text(encoding='utf-8')
    except Exception:
        return None
    if not content.strip():
        return None
    return content[:MAX_NOTE_CHARS] + ('\n[...truncado]' if len(content) > MAX_NOTE_CHARS else '')


def recent_project() -> str | None:
    """Proyecto tocado en las últimas FALLBACK_MAX_AGE horas, si hay alguno."""
    base = carpeta('proyectos')
    if not base or not base.exists():
        return None
    cutoff = (datetime.now() - FALLBACK_MAX_AGE).timestamp()
    latest, latest_t = None, cutoff
    for path in base.glob('*.md'):
        try:
            t = path.stat().st_mtime
        except OSError:
            continue
        if t > latest_t:
            latest, latest_t = path.relative_to(config.vault_path()).as_posix(), t
    return latest


def doc_results(prompt: str, client: str | None) -> list[tuple[str, str]]:
    """Fragmentos de la carpeta de fuentes por búsqueda literal. Nunca carga un modelo.

    Si la capa léxica no está disponible —módulo ausente, índice sin construir
    todavía, o la búsqueda falla por cualquier motivo— no hay fragmentos. Eso no es un
    fallo del hook: un vault recién creado no tiene nada que buscar aún.
    """
    if lexical is None:
        return []
    try:
        hits = lexical.search(prompt, cliente=client, limit=3)
        if not hits and client:
            hits = lexical.search(prompt, limit=3)
        return hits or []
    except Exception:
        return []


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0

    prompt = (data.get('prompt') or data.get('tool_input', {}).get('prompt', '') or '').lower()
    if not prompt:
        return 0

    parts, loaded, matched_clients = [], set(), []

    for keywords, rel, client in build_entity_index():
        if len(loaded) >= MAX_NOTES:
            break
        if rel not in loaded and any(mentions(prompt, k) for k in keywords):
            content = load(rel)
            if content:
                parts.append(f'[Vault → {rel}]\n{content}')
                loaded.add(rel)
                if client:
                    matched_clients.append(client)

    wants_docs = any(k in prompt for k in DOC_KEYWORDS)
    if wants_docs or matched_clients:
        client = matched_clients[0] if len(set(matched_clients)) == 1 else None
        hits = doc_results(prompt, client)
        if hits:
            frags = '\n\n'.join(
                f'[Docs → {src}]\n{frag[:500]}{"..." if len(frag) > 500 else ""}'
                for src, frag in hits
            )
            parts.append('Fragmentos indexados, por búsqueda LITERAL. Si la pregunta usa '
                         'otras palabras que el documento, una búsqueda semántica aparte '
                         'encuentra lo que esta no.'
                         '\n\n' + frags)

    if not parts:
        recent = recent_project()
        if recent:
            content = load(recent)
            if content:
                parts.append(f'[Vault → {recent} (actividad reciente)]\n{content}')

    if parts:
        result = {
            'hookSpecificOutput': {
                'hookEventName': 'UserPromptSubmit',
                'additionalContext': 'Contexto auto-cargado del vault (relevante al mensaje actual):\n\n'
                                     + '\n\n---\n\n'.join(parts)
            }
        }
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[context_injector] fallo interno, continuando sin bloquear el mensaje: {e}")
        sys.exit(0)
