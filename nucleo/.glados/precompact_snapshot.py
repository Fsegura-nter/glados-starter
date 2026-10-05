#!/usr/bin/env python3
"""
precompact_snapshot.py — Guarda el estado de la sesión para recuperarlo en la siguiente.

Hooks: PreCompact y SessionEnd.

Guarda cuatro cosas, en este orden de utilidad:
  1. Las peticiones que escribió el usuario (promptSource == "typed").
  2. Los últimos mensajes sustanciales de la respuesta — ahí viven los pendientes.
  3. Los commits recientes del vault: el registro de lo que de verdad se hizo.
  4. Los ficheros .md tocados en las últimas horas.

Guardar solo (4) —una lista de rutas y una hora— no basta para saber de qué se habló
al reanudar una sesión compactada: una lista de ficheros no es memoria de una
conversación.

Todo lo que sale de la conversación pasa por `redact.py` antes de escribirse: un
mensaje puede llevar un token pegado sin querer, y este fichero vive dentro del vault.
"""
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from redact import redactar

config.force_utf8()

# Carpetas de sistema/herramienta: no son contenido del vault y no dependen de cómo
# el usuario nombre sus propias carpetas.
DIRS_FIJOS = {'.obsidian', '.git', '__pycache__', '.glados', '.claude'}
HOURS_LOOKBACK = 4
MAX_PETICIONES = 6
MAX_PETICION_CHARS = 400
MAX_RESPUESTAS = 2
MAX_RESPUESTA_CHARS = 2500
MIN_RESPUESTA_CHARS = 250          # un "voy a mirar esto" no es estado de sesión
MAX_SNAPSHOT_CHARS = 30_000        # el vault tiene un límite de tamaño por nota; sobra margen


def dirs_a_ignorar() -> set[str]:
    """Carpetas que no aportan al "qué se tocó hoy": las de sistema, siempre, más las
    de solo-lectura/archivo/historia si el usuario les puso nombre en `settings.json`.
    Sin configurar, simplemente se recorren igual: no es un error, solo menos preciso.
    """
    carpetas = config.carpetas()
    extra = {carpetas[rol] for rol in ('fuentes', 'archivo', 'memoria') if carpetas.get(rol)}
    return DIRS_FIJOS | extra


def texto_de(mensaje: dict) -> str:
    content = mensaje.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content
                         if isinstance(b, dict) and b.get("type") == "text")
    return ""


def lee_transcript(path: Path) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """([(hora, petición del usuario)], [(hora, respuesta sustancial)])"""
    peticiones, respuestas = [], []
    try:
        with path.open(encoding="utf-8", errors="ignore") as f:
            for linea in f:
                try:
                    o = json.loads(linea)
                except Exception:
                    continue
                if o.get("isSidechain"):
                    continue
                tipo = o.get("type")
                if tipo not in ("user", "assistant"):
                    continue
                texto = texto_de(o.get("message") or {}).strip()
                if not texto:
                    continue
                hora = (o.get("timestamp") or "")[11:16]
                if tipo == "user":
                    # promptSource == "typed" es lo que escribió el usuario; lo demás
                    # son reinyecciones del sistema y resultados de herramienta.
                    if o.get("promptSource") == "typed":
                        peticiones.append((hora, texto))
                elif len(texto) >= MIN_RESPUESTA_CHARS:
                    respuestas.append((hora, texto))
    except Exception:
        return [], []
    return peticiones, respuestas


def commits_recientes() -> list[str]:
    try:
        salida = subprocess.check_output(
            ["git", "log", "--format=%h %ad %s", "--date=format:%H:%M", "-8"],
            cwd=str(config.vault_path()), stderr=subprocess.DEVNULL, text=True,
            encoding="utf-8", errors="ignore")
        return [l for l in salida.splitlines() if l.strip()]
    except Exception:
        return []


def md_recientes(hours: int) -> list[tuple[datetime, str]]:
    import os
    cutoff = datetime.now() - timedelta(hours=hours)
    raiz = config.vault_path()
    ignorar = dirs_a_ignorar()
    recent = []
    for root, dirs, files in os.walk(raiz):
        dirs[:] = [d for d in dirs if d not in ignorar]
        for file in files:
            if not file.endswith('.md'):
                continue
            path = os.path.join(root, file)
            try:
                mtime = datetime.fromtimestamp(os.path.getmtime(path))
                if mtime > cutoff:
                    recent.append((mtime, os.path.relpath(path, raiz).replace('\\', '/')))
            except Exception:
                pass
    recent.sort(reverse=True)
    return recent[:10]


def recorta(texto: str, limite: int) -> str:
    texto = " ".join(texto.split())
    return texto if len(texto) <= limite else texto[:limite].rstrip() + " […]"


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    evento = data.get("hook_event_name", "desconocido")
    motivo = data.get("reason", "")
    transcript = data.get("transcript_path")

    peticiones, respuestas = ([], [])
    if transcript:
        peticiones, respuestas = lee_transcript(Path(transcript))

    ahora = datetime.now().strftime('%Y-%m-%d %H:%M')
    lineas = [
        f'# Snapshot de sesión — {ahora}',
        '',
        f'_Disparado por `{evento}`{f" ({motivo})" if motivo else ""}._',
        '',
    ]

    if peticiones:
        lineas += ['## Lo que pidió el usuario', '']
        for hora, texto in peticiones[-MAX_PETICIONES:]:
            lineas.append(f'- **{hora}** — {recorta(texto, MAX_PETICION_CHARS)}')
        lineas.append('')

    if respuestas:
        lineas += ['## Estado al cerrar', '']
        for hora, texto in respuestas[-MAX_RESPUESTAS:]:
            lineas += [f'**{hora}**', '', '> ' + recorta(texto, MAX_RESPUESTA_CHARS), '']

    commits = commits_recientes()
    if commits:
        lineas += ['## Commits del vault', '', '```']
        lineas += [f'{c}' for c in commits]
        lineas += ['```', '']

    recientes = md_recientes(HOURS_LOOKBACK)
    lineas += [f'## Notas tocadas en las últimas {HOURS_LOOKBACK} h', '']
    if recientes:
        lineas += [f'- `{rel}` _(modificado {mtime.strftime("%H:%M")})_' for mtime, rel in recientes]
    else:
        lineas.append('- (ninguna)')

    lineas += [
        '',
        '---',
        '_Generado por `precompact_snapshot.py` (PreCompact y SessionEnd). Se sobreescribe_',
        '_en cada ejecución. No editar a mano. Las credenciales van redactadas._',
    ]

    contenido = '\n'.join(lineas)
    contenido, encontrados = redactar(contenido)
    if encontrados:
        contenido += (f'\n\n> [!warning] Se redactaron credenciales de este snapshot: '
                      f'{", ".join(encontrados)}.\n> Si aparecieron en la conversación, '
                      'siguen activas hasta que las revoques.\n')
    if len(contenido) > MAX_SNAPSHOT_CHARS:
        contenido = contenido[:MAX_SNAPSHOT_CHARS] + '\n\n_[snapshot recortado por tamaño]_\n'

    snapshot = config.snapshot_path()
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_text(contenido, encoding='utf-8')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[precompact_snapshot] fallo interno, continuando sin bloquear el cierre: {e}")
        sys.exit(0)
