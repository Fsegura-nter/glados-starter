#!/usr/bin/env python3
"""
generar_vault.py — Ejecutor del plan de alta: escribe en disco lo que la entrevista
decidio.

Separa decidir de escribir: un modelo redacta el plan (JSON), este script lo ejecuta.
Esa separacion es lo que permite relanzar la generacion si falla a medias, y probarla
sin un humano delante.

Dos tiempos, en este orden exacto y sin mezclarlos:
  1. Validar el plan ENTERO contra las reglas de abajo. Si algo no cuadra, no se toca
     el disco todavia: media boveda es peor que ninguna, porque obliga a averiguar
     que quedo a medias en vez de simplemente volver a lanzar el mismo plan.
  2. Escribir. Nunca pisa un fichero que ya exista — relanzar sobre una boveda a medio
     hacer tiene que completarla, no destruir lo que el usuario ya haya tocado a mano.

Reglas de validacion, todas antes de cualquier escritura:
  - Cada `ruta` tiene que quedarse dentro del vault. El plan lo escribe un modelo de
    lenguaje, asi que una ruta con `..` o una ruta absoluta es superficie de ataque
    real, no una hipotetica de examen.
  - Ninguna nota (frontmatter + cuerpo) supera los 250 KB: el visor de notas al que
    va destinado este markdown parsea todo el vault al arrancar y muere por falta de
    memoria si el volumen es excesivo.
  - Toda `area` usada en una carpeta o en el frontmatter de una nota tiene que estar
    declarada en `plan["areas"]`.
  - Los nombres de modulo se validan contra la carpeta `modulos/` SOLO SI esa carpeta
    existe. Llega en una tarea posterior de este mismo kit: mientras no exista, los
    nombres se aceptan tal cual.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

# Limite de nota: 250 KB. Ver el porque en el docstring de arriba.
LIMITE_NOTA_BYTES = 250 * 1024

# nucleo/.glados/generar_vault.py -> parent=.glados, parent.parent=nucleo,
# parent.parent.parent = raiz del kit (mismo patron que `_modulo_google_dir()` en
# arranque_lectura.py, para que las dos busquedas de "modulos/" coincidan siempre).
RAIZ_KIT = Path(__file__).resolve().parent.parent.parent
PLANTILLAS_DIR = RAIZ_KIT / "plantillas"
MODULOS_DIR = RAIZ_KIT / "modulos"


# --------------------------------------------------------------------------- utilidades

def _ruta_segura(raiz: Path, ruta_relativa: str) -> Path:
    """Resuelve `ruta_relativa` dentro de `raiz` y rechaza cualquier intento de escapar.

    Cubre tanto `../..` como una ruta absoluta (`C:\\Windows`): en `pathlib`, unir una
    ruta absoluta con `/` descarta la parte izquierda entera, asi que el resultado cae
    fuera de `raiz` igual que con `..` y el `relative_to` de abajo lo atrapa igual.
    """
    raiz_resuelta = raiz.resolve()
    candidata = (raiz_resuelta / ruta_relativa).resolve()
    try:
        candidata.relative_to(raiz_resuelta)
    except ValueError:
        raise ValueError(f"Ruta fuera del vault: {ruta_relativa!r}")
    return candidata


def _valor_yaml(valor) -> str:
    if valor is None:
        return "null"
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (int, float)):
        return str(valor)
    texto = str(valor)
    necesita_comillas = (
        texto == ""
        or texto != texto.strip()
        or texto.lower() in ("true", "false", "null", "yes", "no", "~")
        or texto[0] in "\"'[]{}#&*!|>%@`-:,"
        or ": " in texto
        or texto.endswith(":")
    )
    if necesita_comillas:
        escapado = texto.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escapado}"'
    return texto


def _frontmatter_yaml(datos: dict) -> str:
    """YAML minimo para frontmatter: escalares, listas de escalares y un nivel de
    dict. Suficiente para lo que trae un plan de alta (estado, area, aliases, tags...);
    no es un serializador YAML general, y no pretende serlo."""
    lineas = []
    for clave, valor in datos.items():
        if isinstance(valor, list):
            if not valor:
                lineas.append(f"{clave}: []")
            else:
                lineas.append(f"{clave}:")
                lineas.extend(f"  - {_valor_yaml(v)}" for v in valor)
        elif isinstance(valor, dict):
            lineas.append(f"{clave}:")
            lineas.extend(f"  {k}: {_valor_yaml(v)}" for k, v in valor.items())
        else:
            lineas.append(f"{clave}: {_valor_yaml(valor)}")
    return "\n".join(lineas)


def _render_nota(frontmatter: dict, cuerpo: str) -> str:
    cuerpo = cuerpo or ""
    if frontmatter:
        return f"---\n{_frontmatter_yaml(frontmatter)}\n---\n\n{cuerpo}"
    return cuerpo


def _slug(texto: str) -> str:
    """Nombre de fichero para el output style: minusculas, solo alfanumerico y '-'."""
    texto = texto.strip().lower()
    piezas = []
    anterior_guion = False
    for ch in texto:
        if ch.isalnum():
            piezas.append(ch)
            anterior_guion = False
        elif not anterior_guion:
            piezas.append("-")
            anterior_guion = True
    slug = "".join(piezas).strip("-")
    return slug or "asistente"


def _lista_markdown(items: list) -> str:
    if not items:
        return "Ninguno."
    return "\n".join(f"- {item}" for item in items)


def _servicios_de_modulo(nombre: str) -> list[str]:
    """Servicios declarados por un modulo, a partir de sus ficheros `<servicio>_api.py`
    (convencion ya en uso: ver `modulos/google/gmail_api.py` en `arranque_lectura.py`).

    Si la carpeta del modulo no existe todavia, o no declara ningun `_api.py`, el
    propio nombre del modulo hace de unico servicio: es el unico valor neutro posible
    sin inventar una lista de servicios que el kit aun no conoce.
    """
    carpeta = MODULOS_DIR / nombre
    if not carpeta.is_dir():
        return [nombre]
    servicios = sorted(
        p.name[: -len("_api.py")] for p in carpeta.glob("*_api.py")
    )
    return servicios or [nombre]


def _construir_estado_modulos(plan: dict) -> dict:
    """Una entrada por SERVICIO dentro de cada modulo activo, nunca un interruptor
    unico por modulo (Google es Gmail, Calendar y Drive; uno puede fallar sin tumbar
    los otros dos). `plan["estado_modulos"]` puede aportar el estado real de alguno o
    de todos; lo que falte nace `"sin_probar"`.
    """
    modulos = plan.get("modulos") or []
    aportado = plan.get("estado_modulos")
    aportado = aportado if isinstance(aportado, dict) else {}

    resultado = {}
    for modulo in modulos:
        servicios_aportados = aportado.get(modulo)
        if isinstance(servicios_aportados, dict) and servicios_aportados:
            resultado[modulo] = dict(servicios_aportados)
        else:
            resultado[modulo] = {s: "sin_probar" for s in _servicios_de_modulo(modulo)}
    return resultado


# --------------------------------------------------------------------------- validacion

def _validar_plan(plan: dict, raiz: Path) -> dict:
    """Valida el plan entero y devuelve las operaciones de escritura ya preparadas
    (rutas resueltas, contenidos renderizados), SIN tocar el disco de destino.

    Cualquier fallo lanza `ValueError` antes de que se haya escrito nada: es lo que
    hace posible que `generar()` deje el directorio intacto cuando el plan falla a
    medias.
    """
    if not isinstance(plan, dict):
        raise ValueError("El plan no es un objeto JSON")

    raiz_resuelta = raiz.resolve()

    areas = plan.get("areas")
    if not isinstance(areas, list):
        raise ValueError("plan['areas'] tiene que ser una lista")

    asistente = plan.get("asistente")
    if not isinstance(asistente, dict) or not asistente.get("nombre"):
        raise ValueError("plan['asistente']['nombre'] es obligatorio")
    nombre_asistente = str(asistente["nombre"])
    arquetipo = str(asistente.get("arquetipo") or "")

    def _validar_area(area, origen: str):
        if area is not None and area not in areas:
            raise ValueError(f"area {area!r} no declarada en plan['areas'] ({origen})")

    # --- carpetas ---
    carpetas_plan = plan.get("carpetas")
    if not isinstance(carpetas_plan, list):
        raise ValueError("plan['carpetas'] tiene que ser una lista")

    carpetas_resueltas: list[Path] = []
    for carpeta in carpetas_plan:
        if not isinstance(carpeta, dict) or not carpeta.get("ruta"):
            raise ValueError("Cada carpeta del plan necesita 'ruta'")
        _validar_area(carpeta.get("area"), f"carpeta {carpeta['ruta']!r}")
        carpetas_resueltas.append(_ruta_segura(raiz_resuelta, carpeta["ruta"]))

    # --- notas ---
    notas_plan = plan.get("notas")
    if not isinstance(notas_plan, list):
        raise ValueError("plan['notas'] tiene que ser una lista")

    notas_resueltas: list[tuple[Path, str]] = []
    for nota in notas_plan:
        if not isinstance(nota, dict) or not nota.get("ruta"):
            raise ValueError("Cada nota del plan necesita 'ruta'")
        ruta_nota = nota["ruta"]
        ruta_abs = _ruta_segura(raiz_resuelta, ruta_nota)

        frontmatter = nota.get("frontmatter") or {}
        if not isinstance(frontmatter, dict):
            raise ValueError(f"El frontmatter de {ruta_nota!r} tiene que ser un objeto")
        _validar_area(frontmatter.get("area"), f"nota {ruta_nota!r}")

        cuerpo = nota.get("cuerpo", "")
        if not isinstance(cuerpo, str):
            raise ValueError(f"El cuerpo de {ruta_nota!r} tiene que ser texto")

        contenido = _render_nota(frontmatter, cuerpo)
        if len(contenido.encode("utf-8")) > LIMITE_NOTA_BYTES:
            raise ValueError(
                f"La nota {ruta_nota!r} supera los 250 KB "
                f"(limite del visor de notas de este vault)"
            )
        notas_resueltas.append((ruta_abs, contenido))

    # --- modulos ---
    modulos_plan = plan.get("modulos", [])
    if not isinstance(modulos_plan, list):
        raise ValueError("plan['modulos'] tiene que ser una lista")
    if MODULOS_DIR.is_dir():
        for modulo in modulos_plan:
            if not (MODULOS_DIR / modulo).is_dir():
                raise ValueError(f"Modulo desconocido: {modulo!r}")
    # Si MODULOS_DIR no existe todavia (llega en una tarea posterior), los nombres se
    # aceptan tal cual: no hay nada contra lo que comprobarlos.

    # --- pendientes manuales ---
    pendientes = plan.get("pendientes_manuales", [])
    if not isinstance(pendientes, list):
        raise ValueError("plan['pendientes_manuales'] tiene que ser una lista")

    estado_modulos = _construir_estado_modulos(plan)

    # --- preparar contenidos (lecturas de las plantillas del kit, no del destino) ---
    claude_md_tmpl = (PLANTILLAS_DIR / "CLAUDE.md.tmpl").read_text(encoding="utf-8")
    claude_md_contenido = (
        claude_md_tmpl
        .replace("{{ASISTENTE}}", nombre_asistente)
        .replace("{{ARQUETIPO}}", arquetipo)
        .replace("{{PENDIENTES_MANUALES}}", _lista_markdown([str(p) for p in pendientes]))
    )

    output_style_tmpl = (PLANTILLAS_DIR / "output-style.tmpl").read_text(encoding="utf-8")
    output_style_contenido = (
        output_style_tmpl
        .replace("{{ASISTENTE}}", nombre_asistente)
        .replace("{{ARQUETIPO}}", arquetipo)
    )

    plantillas_nota: list[tuple[Path, str]] = []
    for nombre_fichero in ("proyecto.md", "cliente.md", "reunion.md"):
        origen = PLANTILLAS_DIR / nombre_fichero
        if origen.is_file():
            plantillas_nota.append((
                raiz_resuelta / "99_PROMPTS" / "plantillas" / nombre_fichero,
                origen.read_text(encoding="utf-8"),
            ))

    estado_modulos_json = json.dumps(estado_modulos, ensure_ascii=False, indent=2, sort_keys=True)

    return {
        "carpetas": carpetas_resueltas,
        "notas": notas_resueltas,
        "claude_md": (raiz_resuelta / "CLAUDE.md", claude_md_contenido),
        "output_style": (
            raiz_resuelta / ".claude" / "output-styles" / f"{_slug(nombre_asistente)}.md",
            output_style_contenido,
        ),
        "plantillas_nota": plantillas_nota,
        "estado_modulos": (raiz_resuelta / ".glados" / "estado_modulos.json", estado_modulos_json),
    }


# --------------------------------------------------------------------------- escritura

def generar(plan: dict, raiz) -> list[str]:
    """Ejecuta un plan de alta ya aprobado. Lanza `ValueError` si el plan es invalido
    SIN escribir nada; si es valido, escribe y devuelve las rutas creadas en esta
    llamada (las que ya existian se dejan intactas, nunca se pisan)."""
    raiz = Path(raiz)
    operaciones = _validar_plan(plan, raiz)

    creadas: list[str] = []

    for carpeta in operaciones["carpetas"]:
        existia = carpeta.is_dir()
        carpeta.mkdir(parents=True, exist_ok=True)
        if not existia:
            creadas.append(str(carpeta))

    def _escribir_si_falta(ruta: Path, contenido: str) -> None:
        if ruta.exists():
            return
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(contenido, encoding="utf-8")
        creadas.append(str(ruta))

    for ruta_abs, contenido in operaciones["notas"]:
        _escribir_si_falta(ruta_abs, contenido)

    _escribir_si_falta(*operaciones["claude_md"])
    _escribir_si_falta(*operaciones["output_style"])

    for ruta_abs, contenido in operaciones["plantillas_nota"]:
        _escribir_si_falta(ruta_abs, contenido)

    _escribir_si_falta(*operaciones["estado_modulos"])

    return creadas


# --------------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ejecuta en disco un plan de alta de boveda ya aprobado."
    )
    ap.add_argument("plan", help="Ruta al plan.json aprobado")
    ap.add_argument("--dry-run", action="store_true",
                     help="Solo valida el plan; no escribe nada")
    ap.add_argument("--raiz", default=".",
                     help="Carpeta donde nace la boveda (por defecto, la actual)")
    args = ap.parse_args()

    try:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"[ERROR] no se pudo leer el plan: {e}")
        return 1

    raiz = Path(args.raiz).resolve()

    try:
        if args.dry_run:
            operaciones = _validar_plan(plan, raiz)
            total = (
                len(operaciones["carpetas"]) + len(operaciones["notas"])
                + len(operaciones["plantillas_nota"]) + 3
            )
            print(f"Plan valido. Hasta {total} elemento(s) por crear en {raiz} "
                  f"(los que ya existan se dejan como estan).")
            return 0
        creadas = generar(plan, raiz)
    except ValueError as e:
        print(f"[ERROR] plan invalido: {e}")
        return 1

    print(f"Boveda generada: {len(creadas)} elemento(s) nuevo(s) en {raiz}")
    for ruta in creadas:
        print(f"  + {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
