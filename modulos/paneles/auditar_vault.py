#!/usr/bin/env python3
"""
auditar_vault.py — ¿cumple el vault el vocabulario de frontmatter que declaró al nacer?

Por qué existe: el `CLAUDE.md` de un vault generado define un **vocabulario controlado**
de frontmatter, y de él dependen cosas que fallan en silencio. Una nota de proyecto sin
`area` no aparece en ningún panel de bloque: sigue en disco, sigue indexada, y es invisible
en la única vía de navegación que se usa. Un `estado` inventado rompe las vistas del
dashboard sin dar error. Un `cliente: "[[X]]"` que apunta a una ficha que no existe no se
nota leyendo la nota.

Hasta que existe este script, eso es confianza. Esto lo mide.

**Este script NO arregla nada.** Solo informa y sale 1 si hay fallos. Decidir si un campo no
declarado es deriva o vocabulario nuevo sin documentar lo hace la persona, no una heurística.

**Las áreas y los nombres de carpeta no son del kit, son de cada vault.** Las áreas vienen de
`.glados/settings.json` → `areas`; las carpetas, de `.glados/settings.json` → `carpetas`. Sin
ninguna área declarada, la comprobación de vocabulario se salta en vez de fallar: no hay
vocabulario contra el que comparar todavía.

Uso:
    python auditar_vault.py              # audita y sale 1 si hay fallos
    python auditar_vault.py --solo <n>   # una sola comprobación por su número
"""
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

MAX_KB = 250          # Por encima, Obsidian puede morir de OOM al arrancar.
OBSIDIAN_CLI = Path(
    __import__("os").environ.get("LOCALAPPDATA", "")
) / "Programs" / "Obsidian" / "Obsidian.com"

fallos: list[str] = []
avisos: list[str] = []


def err(msg: str) -> None:
    print(f"  \033[31mx\033[0m {msg}")
    fallos.append(msg)


def ok(msg: str) -> None:
    print(f"  \033[32mv\033[0m {msg}")


def avi(msg: str) -> None:
    print(f"  \033[33m!\033[0m {msg}")
    avisos.append(msg)


def _areas() -> set[str]:
    valor = config.local_settings().get("areas")
    return set(valor.keys()) if isinstance(valor, dict) else set()


def _vocabulario_rol(rol: str) -> dict:
    """El vocabulario declarado para ese rol en `.glados/settings.json` → `vocabulario`,
    o un esqueleto vacío si no se ha declarado ninguno todavía."""
    valor = config.vocabulario().get(rol)
    return valor if isinstance(valor, dict) else {}


def _normas() -> dict[str, dict]:
    """Carpeta -> {ruta, obligatorios, cerrados, opcionales}, solo para los roles que
    esta instalación haya nombrado en `carpetas`. `area` se añade siempre a los campos
    cerrados cuando hay áreas declaradas: es el campo que hace o rompe la navegación
    por paneles, y conviene auditarlo aunque `vocabulario` no diga nada de él.
    """
    carpetas = config.carpetas()
    areas = _areas()
    normas = {}
    # (rol, obligatorios_por_defecto, cerrados_por_defecto, opcionales_por_defecto):
    # son la forma de frontmatter que ya traen las plantillas de alta del kit, no un
    # vocabulario propio de ningún vault concreto.
    defecto = {
        "clientes": ({"estado", "area"},
                    {"estado": {"activo", "en_pausa", "cerrado"}},
                    {"aliases", "tags", "fecha"}),
        "proyectos": ({"estado", "area"},
                      {"estado": {"propuesta", "activo", "pausado", "completado", "archivado"}},
                      {"cliente", "gitlab", "aliases", "tags", "fecha"}),
        "reuniones": ({"tipo", "area"},
                      {"tipo": {"reunion"}},
                      {"cliente", "proyecto", "fecha", "tags", "aliases"}),
    }
    for rol, (obligatorios_def, cerrados_def, opcionales_def) in defecto.items():
        nombre_carpeta = carpetas.get(rol)
        if not nombre_carpeta:
            continue
        declarado = _vocabulario_rol(rol)
        obligatorios = set(declarado.get("obligatorios", obligatorios_def))
        cerrados = {k: set(v) for k, v in (declarado.get("cerrados") or cerrados_def).items()}
        if areas:
            cerrados.setdefault("area", areas)
        opcionales = set(declarado.get("opcionales", opcionales_def))
        normas[nombre_carpeta] = {
            "ruta": config.vault_path() / nombre_carpeta,
            "obligatorios": obligatorios,
            "cerrados": cerrados,
            "opcionales": opcionales,
        }
    return normas


def _repos_notes_path() -> Path:
    nombre = config.carpetas().get("proyectos") or "proyectos"
    return config.vault_path() / nombre / "_repos"


def _visibles() -> tuple[str, ...]:
    """Carpetas que el explorador muestra, para la comprobación de huérfanas: las que
    esta instalación haya nombrado para los roles de contenido normal. Las de
    solo-lectura o archivo no se incluyen: no se enlazan por diseño, y contarlas
    ahogaría la señal en ruido.
    """
    carpetas = config.carpetas()
    roles = ("core", "clientes", "proyectos", "reuniones")
    return tuple(carpetas[r] for r in roles if carpetas.get(r))


def frontmatter(md: Path) -> dict | None:
    """El frontmatter como dict, o None si la nota no tiene o está corrupto."""
    vault = config.vault_path()
    try:
        texto = md.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        err(f"{md.relative_to(vault)} — no se puede leer: {e}")
        return None
    if not texto.startswith("---"):
        return None
    fin = texto.find("\n---", 3)
    if fin == -1:
        err(f"{md.relative_to(vault)} — frontmatter sin cerrar")
        return None
    try:
        datos = yaml.safe_load(texto[3:fin])
    except yaml.YAMLError as e:
        err(f"{md.relative_to(vault)} — YAML invalido: {str(e)[:90]}")
        return None
    return datos if isinstance(datos, dict) else {}


def notas(ruta: Path) -> list[Path]:
    """Los .md de una carpeta, saltando lo generado y lo que empieza por _ o punto."""
    if not ruta.exists():
        return []
    repos_notes = _repos_notes_path()
    return sorted(
        p for p in ruta.rglob("*.md")
        if repos_notes not in p.parents
        and not any(parte.startswith(("_", ".")) for parte in p.relative_to(ruta).parts)
    )


# ── 1. Vocabulario de frontmatter ─────────────────────────────────────────────
def comprobar_vocabulario() -> None:
    print("-- 1. Vocabulario de frontmatter --")
    vault = config.vault_path()
    normas = _normas()
    if not normas:
        avi("ninguna carpeta de clientes/proyectos/reuniones configurada en "
            ".glados/settings.json: comprobacion saltada")
        return
    total = 0
    for carpeta, norma in normas.items():
        ficheros = notas(norma["ruta"])
        if not ficheros:
            avi(f"{carpeta} esta vacia: no hay nada que auditar")
            continue
        total += len(ficheros)
        for md in ficheros:
            rel = md.relative_to(vault)
            fm = frontmatter(md)
            if fm is None:
                err(f"{rel} — sin frontmatter, y en {carpeta} es obligatorio")
                continue
            for campo in norma["obligatorios"]:
                if not fm.get(campo):
                    err(f"{rel} — falta `{campo}`"
                        + (" (no aparecera en ningun panel de bloque)" if campo == "area" else ""))
            for campo, validos in norma["cerrados"].items():
                valor = fm.get(campo)
                if valor and valor not in validos:
                    err(f"{rel} — `{campo}: {valor}` no esta en el vocabulario "
                        f"({', '.join(sorted(validos))})")
            declarados = norma["obligatorios"] | set(norma["cerrados"]) | norma["opcionales"]
            for campo in sorted(set(fm) - declarados):
                avi(f"{rel} — propiedad `{campo}` no declarada para {carpeta}")
    if total and not fallos:
        ok(f"{total} notas normadas, vocabulario correcto")


# ── 2. Los enlaces de frontmatter resuelven ───────────────────────────────────
def comprobar_enlaces_cliente() -> None:
    print("-- 2. `cliente:` apunta a una ficha que existe --")
    vault = config.vault_path()
    carpetas = config.carpetas()
    ruta_clientes = vault / carpetas["clientes"] if carpetas.get("clientes") else None
    ruta_proyectos = vault / carpetas["proyectos"] if carpetas.get("proyectos") else None
    ruta_reuniones = vault / carpetas["reuniones"] if carpetas.get("reuniones") else None
    if not ruta_clientes or not (ruta_proyectos or ruta_reuniones):
        avi("faltan carpetas de clientes/proyectos/reuniones en settings.json: "
            "comprobacion saltada")
        return

    fichas = {p.stem for p in notas(ruta_clientes)}
    candidatas = notas(ruta_proyectos) + notas(ruta_reuniones) if ruta_proyectos and ruta_reuniones \
        else notas(ruta_proyectos or ruta_reuniones)
    revisadas = roto = 0
    for md in candidatas:
        fm = frontmatter(md) or {}
        valor = (fm.get("cliente") or "").strip()
        if not valor:
            continue
        revisadas += 1
        nombre = valor.strip('"\'').removeprefix("[[").removesuffix("]]").split("|")[0].strip()
        if nombre and nombre not in fichas:
            err(f"{md.relative_to(vault)} — `cliente: {valor}` no existe en "
                f"{carpetas['clientes']}")
            roto += 1
    if revisadas and not roto:
        ok(f"{revisadas} referencias a cliente, todas resuelven")
    elif not revisadas:
        avi("ninguna nota declara `cliente`")


# ── 3. Huerfanas en las carpetas visibles ─────────────────────────────────────
def comprobar_huerfanas() -> None:
    print("-- 3. Notas visibles sin enlaces entrantes --")
    visibles = _visibles()
    if not visibles:
        avi("ninguna carpeta visible configurada en settings.json: comprobacion saltada")
        return
    if not OBSIDIAN_CLI.exists():
        avi("no se encuentra el CLI de Obsidian: comprobacion saltada")
        return
    try:
        r = subprocess.run([str(OBSIDIAN_CLI), "orphans"], capture_output=True,
                           text=True, timeout=60, encoding="utf-8", errors="replace")
    except (OSError, subprocess.TimeoutExpired) as e:
        avi(f"el CLI de Obsidian no responde ({type(e).__name__}): comprobacion saltada")
        return
    if r.returncode != 0 or "not enabled" in (r.stdout + r.stderr):
        avi("el CLI de Obsidian no esta habilitado (Ajustes > General > Avanzado)")
        return
    # Ojo al filtrar: una carpeta `_repos` cuelga de proyectos, asi que pasaria el
    # startswith. Se excluye lo generado y lo oculto igual que en notas(): cualquier
    # tramo con _ o punto.
    sueltas = [l.strip() for l in r.stdout.splitlines()
               if l.strip().startswith(visibles) and l.strip().endswith(".md")
               and not any(t.startswith(("_", ".")) for t in l.strip().split("/"))]
    if not sueltas:
        ok("ninguna nota visible esta huerfana")
        return
    avi(f"{len(sueltas)} notas visibles sin enlaces entrantes:")
    for s in sueltas:
        print(f"      {s}")
    print("      (se llega a ellas por marcadores y paneles, asi que no siempre es un fallo)")


# ── 4. Tamano de nota ─────────────────────────────────────────────────────────
def comprobar_tamano() -> None:
    print(f"-- 4. Ninguna nota supera {MAX_KB} KB --")
    vault = config.vault_path()
    limite = MAX_KB * 1024
    grandes = [(p, p.stat().st_size) for p in vault.rglob("*.md")
               if ".git" not in p.parts and p.stat().st_size > limite]
    if not grandes:
        ok(f"todas por debajo de {MAX_KB} KB")
        return
    for p, size in sorted(grandes, key=lambda x: -x[1]):
        err(f"{p.relative_to(vault)} — {size // 1024} KB. Obsidian puede morir al arrancar")


COMPROBACIONES = [comprobar_vocabulario, comprobar_enlaces_cliente,
                  comprobar_huerfanas, comprobar_tamano]


def main() -> None:
    solo = None
    if "--solo" in sys.argv:
        try:
            solo = int(sys.argv[sys.argv.index("--solo") + 1])
        except (IndexError, ValueError):
            print(f"--solo necesita un numero entre 1 y {len(COMPROBACIONES)}")
            sys.exit(2)

    for i, fn in enumerate(COMPROBACIONES, 1):
        if solo in (None, i):
            fn()
            print()

    if fallos:
        print(f"\033[31mFALLA\033[0m — {len(fallos)} problema(s)"
              + (f", {len(avisos)} aviso(s)" if avisos else ""))
        sys.exit(1)
    print(f"\033[32mVAULT CONFORME\033[0m"
          + (f" — {len(avisos)} aviso(s) a decidir" if avisos else ""))


if __name__ == "__main__":
    main()
