#!/usr/bin/env python3
"""
redact.py — Sustituye credenciales por marcadores antes de escribir texto en el vault.

Pensado para limpiar extractos de conversación antes de guardarlos a disco: un resumen
de sesión puede incluir un token pegado sin querer en el chat, y lo que queda escrito en
el vault no debe conservarlo. Mejor redactar de más que fallar en silencio sin cobertura
alguna, así que ante la duda un patrón entra en la lista.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

# (etiqueta, patrón). Varias filas pueden compartir etiqueta: lo que importa a quien
# llama es el TIPO de credencial encontrado, no el servicio exacto al que pertenece.
PATRONES: list[tuple[str, re.Pattern]] = [
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_\-]{4,}\.eyJ[A-Za-z0-9_\-]{4,}\.[A-Za-z0-9_\-]*")),
    ("clave_privada", re.compile(
        r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z0-9 ]*PRIVATE KEY-----")),
    ("contrasena", re.compile(r"(?<=://)[^/\s:@\"']+:[^/\s@\"']{8,}(?=@)")),
    ("token", re.compile(r"glpat-[A-Za-z0-9_\-\.]{20,}")),           # GitLab PAT
    ("token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}")),             # GitHub
    ("token", re.compile(r"github_pat_[A-Za-z0-9_]{30,}")),
    ("token", re.compile(r"ya29\.[A-Za-z0-9_\-]{20,}")),              # Google OAuth access token
    ("token", re.compile(r"1//[A-Za-z0-9_\-]{15,}")),                 # Google OAuth refresh token
    ("token", re.compile(r"AIza[0-9A-Za-z_\-]{35}")),                 # Google API key
    ("token", re.compile(r"xox[abprs]-[A-Za-z0-9\-]{10,}")),          # Slack
    ("token", re.compile(r"AKIA[0-9A-Z]{16}")),                       # AWS access key id
]


def redactar(texto: str) -> tuple[str, list[str]]:
    """Devuelve (texto_limpio, [tipos de credencial encontrados]), sin duplicados."""
    encontrados: list[str] = []
    for etiqueta, patron in PATRONES:
        if patron.search(texto):
            if etiqueta not in encontrados:
                encontrados.append(etiqueta)
            texto = patron.sub(f"<REDACTADO-{etiqueta.upper()}>", texto)
    return texto, encontrados


if __name__ == "__main__":
    from config import force_utf8
    force_utf8()
    entrada = sys.stdin.read() if len(sys.argv) == 1 else Path(sys.argv[1]).read_text(encoding="utf-8")
    salida, hallados = redactar(entrada)
    if hallados:
        print(f"[redact] encontrados: {', '.join(hallados)}", file=sys.stderr)
    print(salida, end="")
