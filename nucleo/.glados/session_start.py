#!/usr/bin/env python3
"""
session_start.py — Carga contexto de la sesión anterior al iniciar Claude Code.

Hook: SessionStart
Acción: inyecta como `additionalContext` el snapshot de la sesión anterior
        (ver `config.snapshot_path()`) y, si el respaldo del vault se ha quedado
        desactualizado, un aviso.

**Si no hay nada que avisar no se escribe una sola línea**: un aviso que aparece
siempre deja de leerse.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()


def aviso_respaldo() -> str:
    """Avisa si el respaldo del vault se ha quedado viejo, o si no hay ninguno.

    El vault vive en un solo disco (ver `respaldo_drive.py`). Un respaldo que se cree
    que existe y no existe es peor que no tener ninguno: cualquier fallo de esta
    función se traga en silencio, porque este hook no puede impedir que arranque una
    sesión.
    """
    try:
        from datetime import datetime
        import respaldo_drive
        carpeta, explicacion = respaldo_drive.destino()
        if not carpeta:
            return f"**Sin respaldo del vault.** {explicacion}"
        previo = respaldo_drive.ultimo(carpeta)
        if not previo:
            return (f"**No hay ningún respaldo del vault** en {carpeta}. "
                    "Se crea solo al cerrar sesión; si sigue vacío, algo falla.")
        dias = (datetime.now() - datetime.fromtimestamp(previo.stat().st_mtime)).days
        if dias >= 3:
            return (f"**El último respaldo del vault tiene {dias} días** ({previo.name}). "
                    "Comprueba que el cliente de sincronización sigue arrancado.")
        return ''
    except Exception:
        return ''


def main() -> int:
    try:
        json.load(sys.stdin)  # consumir stdin
    except Exception:
        pass

    context_parts = []

    aviso = aviso_respaldo()
    if aviso:
        context_parts.append(aviso)

    snapshot = config.snapshot_path()
    if snapshot.exists():
        try:
            content = snapshot.read_text(encoding='utf-8').strip()
            if content:
                context_parts.append(f'Contexto de la sesión anterior:\n\n{content}')
        except Exception:
            pass

    result = {
        'hookSpecificOutput': {
            'hookEventName': 'SessionStart',
            'additionalContext': '\n\n'.join(context_parts)
        }
    }
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[session_start] fallo interno, continuando sin bloquear el arranque: {e}")
        sys.exit(0)
