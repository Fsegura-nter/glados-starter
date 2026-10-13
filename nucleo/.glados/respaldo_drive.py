#!/usr/bin/env python3
"""
respaldo_drive.py — Snapshot comprimido del vault a una carpeta sincronizada en la nube.

El riesgo que cubre: el vault vive en un disco. `commit_vault.py` deja historial para
deshacer un borrado accidental, pero un disco muerto se lleva ese historial por
delante igual. Un zip fechado en una carpeta que ya sincroniza un cliente de nube
(Google Drive, Dropbox…) cubre ese hueco sin añadir infraestructura propia.

**No usa ninguna API de nube.** Escribe un zip en una carpeta local y es el propio
cliente de sincronización quien lo sube. Así no hace falta ampliar ningún scope de
token, no hay nada que reautenticar y no existe la posibilidad de que un fallo de
este script borre algo remoto.

Por qué un zip y no sincronizar el vault carpeta a carpeta:
  · Es atómico: o sube entero o no sube. Un `.git` sincronizado fichero a fichero
    mientras se escribe un commit puede quedar corrupto en destino — el mismo motivo
    por el que una base de datos local no debe vivir dentro de una carpeta sincronizada.
  · Sincronizar el vault fichero a fichero a mano es reinventar el cliente de
    sincronización, con la parte entretenida de que un error de ese código sí puede
    borrar en el destino.

Qué entra: todo el vault, menos la carpeta de archivo (si el usuario le dio nombre al
rol `archivo` en `settings.json` → `carpetas`) y los temporales. El `.git` SÍ entra:
es el historial, y sin él el respaldo vale la mitad.

Configuración, en `.glados/settings.json`:
    "respaldo_path": "<ruta de la carpeta que sincroniza tu cliente de nube>"
    "respaldo_copias": 7          (opcional, por defecto 7)

Uso:
    python .glados/respaldo_drive.py            # respalda si toca
    python .glados/respaldo_drive.py --check    # solo informa, no escribe
    python .glados/respaldo_drive.py --forzar   # aunque el ultimo sea reciente
"""
import argparse
import sys
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

EXCLUIR_PARTES = {"__pycache__", ".trash"}
EXCLUIR_SUFIJOS = {".pyc", ".tmp"}
HORAS_MINIMAS = 20          # un cierre de sesion por la tarde no duplica el del mediodia
COPIAS_POR_DEFECTO = 7

# Donde suelen montar los clientes de sincronizacion mas comunes, por si
# `respaldo_path` no esta configurado a mano.
CANDIDATOS = [Path("G:/Mi unidad"), Path("G:/My Drive"),
              Path.home() / "Mi unidad", Path.home() / "My Drive"]


def _slug_nombre() -> str:
    """Nombre del ecosistema reducido a un prefijo de fichero seguro."""
    texto = config.nombre_ecosistema().strip().lower()
    piezas = []
    anterior_guion = False
    for ch in texto:
        if ch.isalnum():
            piezas.append(ch)
            anterior_guion = False
        elif not anterior_guion:
            piezas.append("-")
            anterior_guion = True
    return "".join(piezas).strip("-") or "vault"


def patron() -> str:
    """`<nombre>-*.zip`, NO un patron global.

    El prefijo lleva el nombre del ecosistema a proposito. La carpeta de destino es una
    carpeta de sincronizacion que puede compartir varias bovedas de la misma maquina, y
    con un patron global cada una veria los respaldos de las otras: `ultimo()` informaria
    de un respaldo ajeno —una boveda recien creada diciendo que se respaldo hace una
    semana— y, peor, `podar()` borraria copias que no son suyas. Medido el 2026-10-13 en
    tres pasadas simuladas: el diagnostico de una boveda nueva anunciaba un zip de otra.

    La fecha va ANCLADA con `?`, no con `*`: un `<nombre>-*.zip` casa con cualquier
    boveda cuyo nombre empiece igual, asi que `boveda` se llevaria los respaldos de
    `boveda-qa`. Con la forma fija, la unica cosa que puede ir detras del nombre es una
    fecha.
    """
    return f"{_slug_nombre()}-????-??-??.zip"


def _raiz_a_excluir() -> set[str]:
    """La carpeta de archivo, si el usuario le puso nombre en `settings.json`.

    Sin configurar, no se excluye nada: es mas seguro respaldar de mas que fallar al
    adivinar un nombre de carpeta que no existe en este vault.
    """
    archivo = config.carpetas().get("archivo")
    return {archivo} if archivo else set()


def destino() -> tuple[Path | None, str]:
    """(carpeta, explicacion). None si no hay donde escribir."""
    configurado = config.local_settings().get("respaldo_path", "")
    if configurado:
        p = Path(configurado)
        if p.parent.exists() or p.exists():
            return p, "configurado en .glados/settings.json"
        return None, (f"`respaldo_path` apunta a {p}, que no existe. "
                      "Si el cliente de sincronizacion no esta arrancado, arrancalo; "
                      "si la ruta cambio, corrigela.")

    for base in CANDIDATOS:
        if base.exists():
            return base / "respaldos-vault", f"detectado en {base}"
    return None, ("No hay `respaldo_path` en .glados/settings.json y no se encuentra "
                  "ningun cliente de sincronizacion conocido. Arrancalo y anota la ruta "
                  "en ese fichero.")


def entradas() -> list[Path]:
    raiz = config.vault_path()
    excluir_raiz = _raiz_a_excluir()
    salida = []
    for p in raiz.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(raiz)
        if rel.parts and rel.parts[0] in excluir_raiz:
            continue
        if EXCLUIR_PARTES & set(rel.parts):
            continue
        if p.suffix.lower() in EXCLUIR_SUFIJOS:
            continue
        salida.append(p)
    return salida


def ultimo(carpeta: Path) -> Path | None:
    if not carpeta.is_dir():
        return None
    zips = sorted(carpeta.glob(patron()), key=lambda p: p.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


def podar(carpeta: Path, copias: int) -> int:
    """Deja solo las `copias` mas recientes de ESTA boveda. Solo toca ficheros que
    coincidan con `patron()`, que lleva el nombre del ecosistema: nunca borra el
    respaldo de otra boveda que comparta la carpeta de sincronizacion."""
    zips = sorted(carpeta.glob(patron()), key=lambda p: p.stat().st_mtime, reverse=True)
    borrados = 0
    for viejo in zips[copias:]:
        try:
            viejo.unlink()
            borrados += 1
        except OSError:
            pass
    return borrados


def main() -> int:
    ap = argparse.ArgumentParser(description="Snapshot del vault a una carpeta sincronizada.")
    ap.add_argument("--check", action="store_true", help="Solo informa; no escribe nada")
    ap.add_argument("--forzar", action="store_true", help="Aunque el ultimo sea reciente")
    args = ap.parse_args()

    # Aqui NO se lee stdin. El hook manda JSON por ahi, pero `sys.stdin.read()` se
    # queda bloqueado esperando un EOF que no llega cuando el script se lanza a mano
    # desde una terminal cuyo stdin sigue abierto: el proceso se cuelga sin imprimir
    # nada y parece que la compresion va lenta. Un hook de tipo command no necesita
    # consumir su stdin.

    raiz = config.vault_path()
    carpeta, explicacion = destino()
    if not carpeta:
        print(f"Sin respaldo: {explicacion}")
        return 0                                  # nunca romper el cierre de sesion

    previo = ultimo(carpeta)
    if previo:
        edad = datetime.now() - datetime.fromtimestamp(previo.stat().st_mtime)
        horas = edad.total_seconds() / 3600
        print(f"Ultimo respaldo: {previo.name} ({horas:.0f} h, "
              f"{previo.stat().st_size // 1024 // 1024} MB)")
        if not args.forzar and edad < timedelta(hours=HORAS_MINIMAS):
            print(f"Menos de {HORAS_MINIMAS} h: no toca.")
            return 0
    else:
        print(f"No hay respaldos previos en {carpeta} ({explicacion}).")

    ficheros = entradas()
    crudo = sum(f.stat().st_size for f in ficheros)
    excluidas = _raiz_a_excluir()
    aviso_exclusion = f" (sin {', '.join(sorted(excluidas))})" if excluidas else ""
    print(f"A comprimir: {len(ficheros)} ficheros, {crudo // 1024 // 1024} MB{aviso_exclusion}")
    if args.check:
        print("--check: no se escribe nada.")
        return 0

    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / f"{_slug_nombre()}-{datetime.now():%Y-%m-%d}.zip"
    parcial = salida.with_suffix(".zip.parcial")
    try:
        with zipfile.ZipFile(parcial, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            for f in ficheros:
                z.write(f, f.relative_to(raiz).as_posix())
        parcial.replace(salida)                   # atomico: nunca se ve un zip a medias
    except OSError as e:
        print(f"[ERROR] no se pudo escribir el respaldo: {e}")
        if parcial.exists():
            parcial.unlink(missing_ok=True)
        return 0

    copias = int(config.local_settings().get("respaldo_copias", COPIAS_POR_DEFECTO))
    borrados = podar(carpeta, copias)
    print(f"[OK] {salida.name} — {salida.stat().st_size // 1024 // 1024} MB "
          f"({100 - salida.stat().st_size * 100 // max(crudo, 1)}% de ahorro)")
    if borrados:
        print(f"Podados {borrados} respaldos por encima de {copias} copias.")
    print("El cliente de sincronizacion lo sube solo. Nada sale de aqui por API.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[respaldo_drive] fallo interno, continuando sin bloquear el cierre: {e}")
        sys.exit(0)
