#!/usr/bin/env python3
"""
sync_projects.py — Vuelca README + último commit de los repos de trabajo a una nota por
repo en la carpeta de proyectos del vault (`<carpeta-proyectos>/_repos/<repo>.md`).
Preserva las secciones "## Notas" y "## TODOs".

La carpeta de repos se configura en `.glados/settings.json` (`repos_path`) y la
profundidad de búsqueda en `repos_depth` (por defecto 3): muchos equipos no tienen los
repos en el primer nivel, sino dentro de carpetas por cliente o por grupo
(`<repos_path>/<Cliente>/<repo>`).

La carpeta de proyectos del vault es la que declare `.glados/settings.json` →
`carpetas.proyectos`; si no se ha declarado ninguna, se usa `proyectos` tal cual, sin
ningún prefijo numérico de una convención personal.

Uso: python sync_projects.py
"""
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

PRESERVED_SECTIONS = ["## Notas", "## TODOs"]
SKIP_DIRS = {"node_modules", ".git", "dist", "build", "target", ".venv", "venv", "__pycache__"}


def repos_path() -> Path | None:
    valor = config.local_settings().get("repos_path")
    return Path(valor) if valor else None


def repos_depth() -> int:
    valor = config.local_settings().get("repos_depth")
    return valor if isinstance(valor, int) and valor > 0 else 3


def repos_notes_path() -> Path:
    nombre_proyectos = config.carpetas().get("proyectos") or "proyectos"
    return config.vault_path() / nombre_proyectos / "_repos"


def find_repos(base: Path, max_depth: int) -> list[Path]:
    """Repos git bajo base, hasta max_depth niveles. No entra dentro de un repo."""
    found = []

    def walk(directory: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(d for d in directory.iterdir() if d.is_dir())
        except OSError:
            return
        for entry in entries:
            if entry.name in SKIP_DIRS:
                continue
            if (entry / ".git").exists():
                found.append(entry)          # un repo anidado se trata aparte, no se recorre
                continue
            walk(entry, depth + 1)

    walk(base, 1)
    return found


def note_name(repo: Path, base: Path, taken: set[str]) -> str:
    """Nombre de nota único: el del repo, y si colisiona, con su carpeta padre delante."""
    name = repo.name
    if name in taken:
        rel = repo.relative_to(base).parts
        name = "-".join(rel[-2:]) if len(rel) >= 2 else name
    taken.add(name)
    return name


def run_git(cmd: list[str], cwd: Path) -> str:
    try:
        return subprocess.check_output(cmd, cwd=str(cwd), stderr=subprocess.DEVNULL, text=True,
                                       encoding="utf-8", errors="ignore").strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""


def get_readme(repo: Path) -> str:
    for name in ["README.md", "readme.md", "README.MD"]:
        p = repo / name
        if p.exists():
            content = p.read_text(encoding="utf-8", errors="ignore")[:2000]
            if content.startswith("---"):
                end = content.find("\n---", 3)
                if end != -1:
                    content = content[end + 4:].lstrip("\n")
            return content
    return "_Sin README_"


def extract_preserved(content: str) -> dict[str, str]:
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


def build_note(name: str, ruta: str, branch: str, last_commit: str, remote: str,
               readme: str, preserved: dict) -> str:
    esc = last_commit.replace("\\", "\\\\").replace('"', '\\"')
    note = f"""---
tipo: repo
sync_date: {date.today().isoformat()}
ruta: "{ruta}"
branch: "{branch or 'unknown'}"
last_commit: "{esc}"
remote: "{remote}"
---

# {name}

## Último commit
{last_commit or '_Sin commits_'}

## README
{readme}
"""
    for section in PRESERVED_SECTIONS:
        note += f"\n{preserved.get(section, section + chr(10))}\n"
    return note


def main():
    base = repos_path()
    if not base or not base.exists():
        print(f"repos_path no configurado o inexistente ({base}). Edita .glados/settings.json")
        sys.exit(1)

    depth = repos_depth()
    repos = find_repos(base, depth)
    if not repos:
        print(f"No se encontró ningún repo git bajo {base} (profundidad {depth}).")
        print("Si los repos están más abajo, sube 'repos_depth' en .glados/settings.json")
        sys.exit(1)

    notas_path = repos_notes_path()
    notas_path.mkdir(parents=True, exist_ok=True)
    taken: set[str] = set()
    synced = 0
    for repo in repos:
        rel = repo.relative_to(base).as_posix()
        print(f"  [SYNC] {rel}")
        try:
            name = note_name(repo, base, taken)
            note_path = notas_path / f"{name}.md"
            preserved = extract_preserved(note_path.read_text(encoding="utf-8")) if note_path.exists() else {}
            note = build_note(
                name,
                rel,
                run_git(["git", "symbolic-ref", "--short", "HEAD"], repo),
                run_git(["git", "log", "-1", "--pretty=%s"], repo),
                run_git(["git", "remote", "get-url", "origin"], repo),
                get_readme(repo),
                preserved,
            )
            note_path.write_text(note, encoding="utf-8")
            synced += 1
        except Exception as e:
            print(f"  [ERROR] {rel}: {e}")
    print(f"\nSincronizados: {synced} repos (profundidad {depth}, base {base})")


if __name__ == "__main__":
    main()
