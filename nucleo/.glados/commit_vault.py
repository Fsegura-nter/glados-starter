#!/usr/bin/env python3
"""
commit_vault.py — Commit automático del vault al cerrar la sesión.

Hook: SessionEnd (después de `precompact_snapshot.py`, para que el snapshot ya esté
escrito).

El vault es un repositorio git local. El historial es la forma de deshacer un
borrado accidental, y no debería depender de que alguien se acuerde de comitear a
mano. Este hook quita eso de la lista de cosas que recordar.

Lo que NO hace, a propósito:
  · No hace push. Añadir un remoto y empujar a él es una decisión de quien usa el
    vault, nunca de un hook.
  · No commitea si no hay cambios: un historial de commits vacíos no es un historial.
  · No commitea a mitad de un merge o un rebase: ahí el índice es de git, no nuestro.

Uso manual: python .glados/commit_vault.py
"""
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

# Un commit automático nunca debe pisar una operación de git a medias.
OPERACIONES_EN_CURSO = ["MERGE_HEAD", "rebase-merge", "rebase-apply", "CHERRY_PICK_HEAD"]


def git(*args: str) -> tuple[int, str]:
    try:
        p = subprocess.run(["git", *args], cwd=str(config.vault_path()), capture_output=True,
                           text=True, encoding="utf-8", errors="replace")
        return p.returncode, (p.stdout or "").strip()
    except FileNotFoundError:
        return 127, "git no esta en el PATH"


def operacion_en_curso() -> str:
    git_dir = config.vault_path() / ".git"
    for marca in OPERACIONES_EN_CURSO:
        if (git_dir / marca).exists():
            return marca
    return ""


def main() -> int:
    # No se lee stdin a proposito: `sys.stdin.read()` se bloquea esperando un EOF que
    # no llega si el script se lanza a mano desde una terminal con stdin abierto, y el
    # proceso se cuelga en silencio. Un hook de tipo command no necesita consumir su
    # stdin.

    if not (config.vault_path() / ".git").exists():
        print("El vault no es un repositorio git. Nada que commitear.")
        return 0

    pendiente = operacion_en_curso()
    if pendiente:
        print(f"Hay un/a {pendiente} en curso: no se toca el indice.")
        return 0

    code, salida = git("status", "--porcelain")
    if code != 0:
        print(f"git status fallo: {salida}")
        return 0
    if not salida:
        print("Sin cambios: no se commitea nada.")
        return 0

    ficheros = len(salida.splitlines())
    code, salida = git("add", "-A")
    if code != 0:
        print(f"git add fallo: {salida}")
        return 0

    # Puede quedar vacio si todo lo modificado estaba en .gitignore.
    code, _ = git("diff", "--cached", "--quiet")
    if code == 0:
        print("Todo lo modificado esta ignorado: no se commitea nada.")
        return 0

    mensaje = f"chore(vault): cierre de sesion {datetime.now():%Y-%m-%d %H:%M}"
    code, salida = git("commit", "-q", "-m", mensaje)
    if code != 0:
        print(f"git commit fallo: {salida}")
        return 0

    _, sha = git("log", "--format=%h", "-1")
    print(f"Commit automatico {sha}: {ficheros} ficheros.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[commit_vault] fallo interno, continuando sin bloquear el cierre: {e}")
        sys.exit(0)
