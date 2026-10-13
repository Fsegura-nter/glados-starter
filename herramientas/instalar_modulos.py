#!/usr/bin/env python3
"""
instalar_modulos.py — Copia los modulos aprobados a la boveda, donde se descubren.

Por que es un script y no un parrafo de la skill: copiar N ficheros por modulo
respetando el destino de cada uno es mecanico y repetible, y lo mecanico se escribe
una vez. Mientras esto era prosa en el `SKILL.md`, el campo `destinos` del manifiesto
**no tenia ningun consumidor en codigo**: se podia escribir mal y nadie se enteraba
hasta que un compañero invocaba un comando que no existia.

Lo que esta a punto de salir mal si esto no existe, y ya salio mal una vez: Claude Code
descubre comandos, skills y agentes en rutas FIJAS bajo `.claude` —`commands/`,
`skills/<nombre>/SKILL.md`, `agents/`—. Un fichero copiado un directorio mas alla
existe en el disco y **no existe para quien lo instalo**, y nada se queja. El manifiesto
declara `destino` por defecto y, cuando hace falta, un mapa `destinos` por primer
segmento de ruta; este script es quien lo honra.

Dos tiempos, como `generar_vault.py` y por el mismo motivo:
  1. Validar TODOS los modulos pedidos. Si algo no cuadra, no se copia nada.
  2. Copiar. Nunca pisa un fichero que ya exista: una instalacion repetida completa lo
     que falte y deja intacto lo que el usuario haya tocado a mano. Por eso no hace
     falta deshacer: relanzar es seguro y es la via de recuperacion.

El manifiesto es DATO, no codigo de confianza: cada ruta de destino se comprueba
contra la raiz de la boveda antes de escribir. Un `..` en un `modulo.json` es
superficie de ataque real en un repositorio publico, no una hipotetica de examen.

Uso:
    python herramientas/instalar_modulos.py --vault <ruta> --modulos google decisiones
    python herramientas/instalar_modulos.py --vault <ruta> --modulos google --dry-run
    python herramientas/instalar_modulos.py --vault <ruta> --modulos google --json
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

RAIZ_KIT = Path(__file__).resolve().parent.parent
MODULOS_DIR = RAIZ_KIT / "modulos"

# Donde la plataforma descubre cada cosa. No es configurable: es Claude Code.
DESCUBRIMIENTO = {
    "commands": ".claude/commands",
    "skills": ".claude/skills",
    "agents": ".claude/agents",
}


def modulos_disponibles() -> list[str]:
    if not MODULOS_DIR.is_dir():
        return []
    return sorted(p.name for p in MODULOS_DIR.iterdir()
                  if p.is_dir() and (p / "modulo.json").is_file())


def leer_manifiesto(nombre: str) -> dict:
    ruta = MODULOS_DIR / nombre / "modulo.json"
    if not ruta.is_file():
        raise ValueError(f"Modulo desconocido: {nombre!r}. "
                         f"Disponibles: {', '.join(modulos_disponibles()) or 'ninguno'}")
    try:
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"{nombre}: modulo.json no es JSON valido: {e}") from e
    if not isinstance(manifiesto, dict):
        raise ValueError(f"{nombre}: modulo.json no es un objeto")
    for clave in ("nombre", "ficheros", "destino"):
        if clave not in manifiesto:
            raise ValueError(f"{nombre}: al manifiesto le falta {clave!r}")
    if not isinstance(manifiesto["ficheros"], list):
        raise ValueError(f"{nombre}: 'ficheros' tiene que ser una lista")
    return manifiesto


def destino_de(manifiesto: dict, fichero: str) -> str:
    """Subcarpeta de la boveda para un fichero: `destinos[<primer segmento>]` si el
    modulo declara excepciones, y `destino` en cualquier otro caso."""
    prefijo = fichero.split("/")[0]
    destinos = manifiesto.get("destinos")
    if isinstance(destinos, dict) and prefijo in destinos:
        return str(destinos[prefijo])
    return str(manifiesto["destino"])


def _ruta_segura(raiz: Path, relativa: str) -> Path:
    """Resuelve `relativa` dentro de `raiz` o lanza. El manifiesto es dato externo."""
    if not relativa or relativa.strip() != relativa:
        raise ValueError(f"Ruta vacia o con espacios al borde: {relativa!r}")
    if any(ord(c) < 32 for c in relativa):
        raise ValueError(f"Ruta con caracter de control: {relativa!r}")
    candidata = (raiz / relativa).resolve()
    if candidata != raiz.resolve() and raiz.resolve() not in candidata.parents:
        raise ValueError(f"Ruta fuera de la boveda: {relativa!r}")
    return candidata


def planificar(vault: Path, nombres: list[str]) -> dict:
    """Valida todo y devuelve las copias preparadas. NO toca el disco."""
    vault_resuelto = vault.resolve()
    if not vault_resuelto.is_dir():
        raise ValueError(f"La boveda no existe: {vault}")

    plan: dict = {"vault": str(vault_resuelto), "modulos": []}
    for nombre in nombres:
        manifiesto = leer_manifiesto(nombre)
        carpeta_origen = MODULOS_DIR / nombre
        copias = []
        for fichero in manifiesto["ficheros"]:
            if not isinstance(fichero, str):
                raise ValueError(f"{nombre}: entrada de 'ficheros' que no es texto: {fichero!r}")
            origen = carpeta_origen / fichero
            if not origen.is_file():
                raise ValueError(f"{nombre}: el manifiesto declara {fichero!r} y no existe")

            subcarpeta = destino_de(manifiesto, fichero)
            relativa = f"{subcarpeta}/{fichero}"
            abs_destino = _ruta_segura(vault_resuelto, relativa)

            # Un fichero descubrible que no aterrice donde se descubre no se instala
            # "a medias": es un modulo roto en silencio, y se para la instalacion.
            prefijo = fichero.split("/")[0]
            if prefijo in DESCUBRIMIENTO:
                esperado = DESCUBRIMIENTO[prefijo]
                if not relativa.startswith(esperado + "/"):
                    raise ValueError(
                        f"{nombre}: {fichero!r} iria a {relativa!r}, y la plataforma "
                        f"solo descubre en {esperado!r}. Revisa 'destinos' del manifiesto")

            copias.append({"origen": str(origen), "destino": str(abs_destino),
                           "relativa": relativa,
                           "ya_existia": abs_destino.exists()})

        plan["modulos"].append({
            "nombre": manifiesto["nombre"],
            "copias": copias,
            "prueba_de_vida": manifiesto.get("prueba_de_vida", ""),
            "requiere": manifiesto.get("requiere", []),
        })
    return plan


def instalar(vault: Path, nombres: list[str], dry_run: bool = False) -> dict:
    """Instala los modulos y devuelve el informe. Lanza `ValueError` sin escribir nada
    si algo no cuadra."""
    plan = planificar(vault, nombres)
    plan["dry_run"] = dry_run
    if dry_run:
        return plan

    for modulo in plan["modulos"]:
        for copia in modulo["copias"]:
            destino = Path(copia["destino"])
            if destino.exists():
                continue                       # nunca se pisa lo que ya esta
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(copia["origen"], destino)
    return plan


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Copia los modulos aprobados a la boveda, en las rutas donde la "
                    "plataforma los descubre.")
    ap.add_argument("--vault", required=True, help="Raiz de la boveda ya generada")
    ap.add_argument("--modulos", nargs="+", required=True,
                    help=f"Modulos a instalar. Disponibles: "
                         f"{', '.join(modulos_disponibles()) or 'ninguno'}")
    ap.add_argument("--dry-run", action="store_true", help="Valida y no escribe nada")
    ap.add_argument("--json", action="store_true", help="Informe en JSON, para la skill")
    args = ap.parse_args()

    try:
        informe = instalar(Path(args.vault), args.modulos, dry_run=args.dry_run)
    except ValueError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0

    verbo = "se copiarian" if args.dry_run else "copiados"
    for modulo in informe["modulos"]:
        nuevos = [c for c in modulo["copias"] if not c["ya_existia"]]
        previos = [c for c in modulo["copias"] if c["ya_existia"]]
        print(f"\n{modulo['nombre']}: {len(nuevos)} {verbo}, {len(previos)} ya estaban")
        for c in nuevos:
            print(f"  + {c['relativa']}")
        for c in previos:
            print(f"  = {c['relativa']}  (intacto)")
        if modulo["requiere"]:
            print(f"  credenciales que necesita: {', '.join(modulo['requiere'])}")
        if modulo["prueba_de_vida"]:
            print(f"  prueba de vida: {modulo['prueba_de_vida']}")
    if not args.dry_run:
        print("\nAhora la prueba de vida de cada modulo. La que falle se marca `fallo` "
              "en .glados/estado_modulos.json y su motivo va a los pendientes del "
              "CLAUDE.md: un modulo cojo tiene que saber que lo esta.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
