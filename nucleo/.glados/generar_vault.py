#!/usr/bin/env python3
"""
generar_vault.py — Ejecutor del plan de alta: escribe en disco lo que la entrevista
decidió.

Separa decidir de escribir: un modelo redacta el plan (JSON), este script lo ejecuta.
Esa separación es lo que permite relanzar la generación si falla a medias, y probarla
sin un humano delante.

Dos tiempos, en este orden exacto y sin mezclarlos:
  1. Validar el plan ENTERO contra las reglas de abajo. Si algo no cuadra, no se toca
     el disco todavía: media bóveda es peor que ninguna, porque obliga a averiguar
     qué quedó a medias en vez de simplemente volver a lanzar el mismo plan.
  2. Escribir. Nunca pisa un fichero que ya exista — relanzar sobre una bóveda a medio
     hacer tiene que completarla, no destruir lo que el usuario ya haya tocado a mano.
     Y si algo falla a mitad de esta fase por un motivo que la validación no pudo ver
     (un error real del sistema de ficheros), se deshace exactamente lo que esta
     llamada había creado y se relanza como `ValueError`: la garantía de "nada a
     medias" vale también para los fallos que no se pueden predecir de antemano.

Reglas de validación, todas antes de cualquier escritura:
  - Cada `ruta` tiene que quedarse dentro del vault. El plan lo escribe un modelo de
    lenguaje, así que una ruta con `..` o una ruta absoluta es superficie de ataque
    real, no una hipotética de examen.
  - Ninguna ruta puede llevar caracteres de control, un nombre reservado de Windows
    (CON, PRN, AUX, NUL, COM1-9, LPT1-9, con o sin extensión) ni un componente con
    punto o espacio final: Windows los trata de forma especial o los recorta en
    silencio, y el plan dejaría de coincidir con lo que de verdad queda en disco.
  - Ningún camino del árbol a escribir puede necesitar, a la vez, ser una carpeta y
    ser un fichero — ni por conflicto dentro del propio plan ni porque ya exista así
    en disco (de una ejecución anterior a medias, o de algo que el usuario haya
    puesto ahí).
  - Ninguna nota (frontmatter + cuerpo) supera los 250 KB: el visor de notas al que
    va destinado este markdown parsea todo el vault al arrancar y muere por falta de
    memoria si el volumen es excesivo.
  - Toda `area` usada en una carpeta o en el frontmatter de una nota tiene que estar
    declarada en `plan["areas"]`.
  - Los nombres de módulo se validan contra la carpeta `modulos/` SOLO SI esa carpeta
    existe. Llega en una tarea posterior de este mismo kit: mientras no exista, los
    nombres se aceptan tal cual.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

# Límite de nota: 250 KB. Ver el porqué en el docstring de arriba.
LIMITE_NOTA_BYTES = 250 * 1024

# nucleo/.glados/generar_vault.py -> parent=.glados, parent.parent=nucleo,
# parent.parent.parent = raíz del kit (mismo patrón que `_modulo_google_dir()` en
# arranque_lectura.py, para que las dos búsquedas de "modulos/" coincidan siempre).
RAIZ_KIT = Path(__file__).resolve().parent.parent.parent
PLANTILLAS_DIR = RAIZ_KIT / "plantillas"
MODULOS_DIR = RAIZ_KIT / "modulos"

# Nombres reservados del sistema de ficheros de Windows, con o sin extensión
# (p.ej. "con" y "con.md" son igual de inválidos como nombre de fichero o carpeta).
_RUTA_RESERVADA = re.compile(r"^(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(\..*)?$", re.IGNORECASE)


# --------------------------------------------------------------------------- utilidades

def _validar_ruta_literal(ruta_relativa: str) -> None:
    """Rechaza, sobre el TEXTO crudo del plan y antes de resolver nada, lo que
    `Path.resolve()` no objeta por sí solo pero que Windows trata de forma especial:

    - un carácter de control (un NUL en una ruta no lo objeta `resolve()`; solo
      revienta más tarde, a mitad de la escritura, con un error mucho más confuso);
    - un nombre reservado del sistema (CON, PRN, AUX, NUL, COM1-9, LPT1-9);
    - un componente con punto o espacio final, que Windows recorta en silencio y que
      dejaría al plan en desacuerdo con lo que de verdad queda en disco.
    """
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F for ch in ruta_relativa):
        raise ValueError(f"Ruta con carácter de control: {ruta_relativa!r}")
    for parte in re.split(r"[\\/]+", ruta_relativa):
        if parte in ("", ".", ".."):
            continue
        if parte != parte.rstrip(" ."):
            raise ValueError(
                f"Componente con punto o espacio final (Windows lo recorta en "
                f"silencio): {parte!r} en {ruta_relativa!r}"
            )
        if _RUTA_RESERVADA.match(parte):
            raise ValueError(
                f"Nombre reservado de Windows en la ruta: {parte!r} en {ruta_relativa!r}"
            )


def _ruta_segura(raiz_resuelta: Path, ruta_relativa: str) -> Path:
    """Resuelve `ruta_relativa` dentro de `raiz_resuelta` y rechaza cualquier intento
    de escapar.

    Cubre tanto `../..` como una ruta absoluta (`C:\\Windows`): en `pathlib`, unir una
    ruta absoluta con `/` descarta la parte izquierda entera, así que el resultado cae
    fuera de `raiz_resuelta` igual que con `..` y el `relative_to` de abajo lo atrapa
    igual.
    """
    _validar_ruta_literal(ruta_relativa)
    candidata = (raiz_resuelta / ruta_relativa).resolve()
    try:
        candidata.relative_to(raiz_resuelta)
    except ValueError:
        raise ValueError(f"Ruta fuera del vault: {ruta_relativa!r}")
    return candidata


def _validar_arbol_destino(raiz_resuelta: Path, carpetas: list, archivos: list) -> None:
    """Comprueba que el árbol de carpetas y ficheros que el plan quiere escribir es
    consistente, ANTES de escribir nada: ninguna ruta puede hacer falta a la vez como
    carpeta (para contener a otra) y como fichero — ni por conflicto dentro del propio
    plan ni porque ya exista así en disco (de una ejecución anterior a medias, o de
    algo que el usuario haya puesto ahí). Esta es la comprobación que sustituye a
    dejar que `mkdir`/`write_text` lo descubran solos a mitad de la escritura.
    """
    carpetas_set = set(carpetas)
    archivos_set = set(archivos)

    comunes = carpetas_set & archivos_set
    if comunes:
        raise ValueError(
            f"{next(iter(comunes))} se usa a la vez como carpeta y como fichero en el plan"
        )

    necesarias = set()
    for destino in list(carpetas) + list(archivos):
        ancestro = destino if destino in carpetas_set else destino.parent
        while True:
            necesarias.add(ancestro)
            if ancestro == raiz_resuelta or ancestro == ancestro.parent:
                break
            ancestro = ancestro.parent

    for ancestro in necesarias:
        if ancestro in archivos_set:
            raise ValueError(
                f"{ancestro} se necesita como carpeta pero el plan lo escribe como fichero"
            )
        if ancestro.exists() and not ancestro.is_dir():
            raise ValueError(
                f"{ancestro} ya existe en disco como fichero: no se puede usar como carpeta"
            )


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
    """YAML mínimo para frontmatter: escalares, listas de escalares y un nivel de
    dict. Suficiente para lo que trae un plan de alta (estado, área, aliases,
    tags...); no es un serializador YAML general, y no pretende serlo."""
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
    """Nombre de fichero para el output style: minúsculas, solo alfanumérico y '-'."""
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
    """Lista markdown donde cada elemento puede ocupar varias líneas físicas: las de
    continuación se indentan dos espacios para quedarse dentro del mismo punto de la
    lista (si no, la segunda línea pierde el `- ` y Markdown la separa del ítem)."""
    if not items:
        return "Ninguno."
    lineas = []
    for item in items:
        partes = str(item).split("\n")
        lineas.append(f"- {partes[0]}")
        lineas.extend(f"  {resto}" for resto in partes[1:])
    return "\n".join(lineas)


def _servicios_de_modulo(nombre: str) -> list[str]:
    """Servicios declarados por un módulo, a partir de sus ficheros `<servicio>_api.py`
    (convención ya en uso: ver `modulos/google/gmail_api.py` en `arranque_lectura.py`).

    Si la carpeta del módulo no existe todavía, o no declara ningún `_api.py`, el
    propio nombre del módulo hace de único servicio: es el único valor neutro posible
    sin inventar una lista de servicios que el kit aún no conoce.
    """
    carpeta = MODULOS_DIR / nombre
    if not carpeta.is_dir():
        return [nombre]
    servicios = sorted(
        p.name[: -len("_api.py")] for p in carpeta.glob("*_api.py")
    )
    return servicios or [nombre]


def _construir_estado_modulos(plan: dict) -> dict:
    """Una entrada por SERVICIO dentro de cada módulo activo, nunca un interruptor
    único por módulo (Google es Gmail, Calendar y Drive; uno puede fallar sin tumbar
    los otros dos). `plan["estado_modulos"]` puede aportar el estado real de alguno o
    de todos; lo que falte nace `"sin_probar"`.

    Esto construye el estado DESEADO a partir del plan actual; `generar()` es quien
    lo fusiona con lo que ya hubiera en disco de una ejecución anterior (ver
    `_fusionar_estado_modulos`), porque este fichero es estado compartido y no prosa
    del usuario: una llamada posterior añade lo que falte y nunca pisa un valor que
    ya estaba.
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


# --------------------------------------------------------------------------- validación

def _validar_plan(plan: dict, raiz: Path) -> dict:
    """Valida el plan entero y devuelve las operaciones de escritura ya preparadas
    (rutas resueltas, contenidos renderizados), SIN tocar el disco de destino.

    Cualquier fallo lanza `ValueError` antes de que se haya escrito nada: es lo que
    hace posible que `generar()` deje el directorio intacto cuando el plan falla a
    medias. Lo que esta función no puede ver por sí sola (un fallo real del sistema
    de ficheros durante la escritura) lo cubre `generar()` deshaciendo lo ya escrito.
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
            raise ValueError(f"Área {area!r} no declarada en plan['areas'] ({origen})")

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
                f"(límite del visor de notas de este vault)"
            )
        notas_resueltas.append((ruta_abs, contenido))

    # --- módulos ---
    modulos_plan = plan.get("modulos", [])
    if not isinstance(modulos_plan, list):
        raise ValueError("plan['modulos'] tiene que ser una lista")
    if MODULOS_DIR.is_dir():
        for modulo in modulos_plan:
            if not (MODULOS_DIR / modulo).is_dir():
                raise ValueError(f"Módulo desconocido: {modulo!r}")
    # Si MODULOS_DIR no existe todavía (llega en una tarea posterior), los nombres se
    # aceptan tal cual: no hay nada contra lo que comprobarlos.

    # --- pendientes manuales ---
    pendientes = plan.get("pendientes_manuales", [])
    if not isinstance(pendientes, list):
        raise ValueError("plan['pendientes_manuales'] tiene que ser una lista")

    estado_modulos = _construir_estado_modulos(plan)

    # --- rutas fijas (no dependen del contenido, solo del nombre del asistente) ---
    ruta_claude_md = raiz_resuelta / "CLAUDE.md"
    ruta_output_style = raiz_resuelta / ".claude" / "output-styles" / f"{_slug(nombre_asistente)}.md"
    ruta_estado_modulos = raiz_resuelta / ".glados" / "estado_modulos.json"

    rutas_plantillas_nota: list[tuple[Path, Path]] = []  # (destino, origen)
    for nombre_fichero in ("proyecto.md", "cliente.md", "reunion.md"):
        origen = PLANTILLAS_DIR / nombre_fichero
        if origen.is_file():
            rutas_plantillas_nota.append(
                (raiz_resuelta / "99_PROMPTS" / "plantillas" / nombre_fichero, origen)
            )

    # --- consistencia del árbol completo, ANTES de leer plantillas o escribir nada ---
    archivos_resueltos = (
        [ruta for ruta, _ in notas_resueltas]
        + [ruta_claude_md, ruta_output_style, ruta_estado_modulos]
        + [destino for destino, _ in rutas_plantillas_nota]
    )
    _validar_arbol_destino(raiz_resuelta, carpetas_resueltas, archivos_resueltos)

    # --- contenidos (lecturas de las plantillas del kit, no del destino) ---
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

    plantillas_nota: list[tuple[Path, str]] = [
        (destino, origen.read_text(encoding="utf-8"))
        for destino, origen in rutas_plantillas_nota
    ]

    return {
        "carpetas": carpetas_resueltas,
        "notas": notas_resueltas,
        "claude_md": (ruta_claude_md, claude_md_contenido),
        "output_style": (ruta_output_style, output_style_contenido),
        "plantillas_nota": plantillas_nota,
        "estado_modulos": (ruta_estado_modulos, estado_modulos),
    }


# --------------------------------------------------------------------------- escritura

def generar(plan: dict, raiz) -> list[str]:
    """Ejecuta un plan de alta ya aprobado. Lanza `ValueError` si el plan es inválido
    SIN escribir nada; si es válido, escribe y devuelve las rutas creadas en esta
    llamada. Lo que ya existía se deja intacto y nunca se pisa — salvo
    `estado_modulos.json`, que es estado y no prosa: ahí se fusionan las claves que
    falten sin tocar las que ya tenía.

    Si algo falla a mitad de la escritura por un motivo que la validación no pudo
    prever (un error real del sistema de ficheros), se deshace exactamente lo que
    esta llamada había creado — del más profundo al más superficial, y nunca algo que
    ya existiera antes de la llamada — y se relanza como `ValueError`: nada sale de
    aquí para un plan fallido salvo `ValueError`.
    """
    raiz = Path(raiz)
    operaciones = _validar_plan(plan, raiz)

    creadas: list[str] = []
    deshacer_acciones: list = []  # callables; se deshacen en orden inverso al de creación

    def _crear_carpeta(carpeta: Path) -> None:
        if carpeta.is_dir():
            return
        pendientes = []
        actual = carpeta
        while not actual.exists():
            pendientes.append(actual)
            if actual == actual.parent:
                break
            actual = actual.parent
        carpeta.mkdir(parents=True, exist_ok=True)
        for p in reversed(pendientes):  # de la más superficial a la más profunda
            creadas.append(str(p))
            deshacer_acciones.append(
                lambda p=p: p.rmdir() if p.is_dir() and not any(p.iterdir()) else None
            )

    def _escribir_si_falta(ruta: Path, contenido: str) -> None:
        if ruta.exists():
            return
        _crear_carpeta(ruta.parent)
        ruta.write_text(contenido, encoding="utf-8")
        creadas.append(str(ruta))
        deshacer_acciones.append(lambda ruta=ruta: ruta.unlink() if ruta.is_file() else None)

    def _fusionar_estado_modulos(ruta: Path, estado_nuevo: dict) -> None:
        existia = ruta.exists()
        original_texto = ruta.read_text(encoding="utf-8") if existia else None
        actual = {}
        if existia:
            try:
                leido = json.loads(original_texto)
                if isinstance(leido, dict):
                    actual = leido
            except json.JSONDecodeError:
                actual = {}

        cambiado = False
        for modulo, servicios in estado_nuevo.items():
            destino = actual.get(modulo)
            if not isinstance(destino, dict):
                destino = {}
                actual[modulo] = destino
                cambiado = True
            for servicio, valor in servicios.items():
                if servicio not in destino:
                    destino[servicio] = valor
                    cambiado = True

        if not existia:
            _crear_carpeta(ruta.parent)
            ruta.write_text(
                json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            creadas.append(str(ruta))
            deshacer_acciones.append(lambda ruta=ruta: ruta.unlink() if ruta.is_file() else None)
        elif cambiado:
            ruta.write_text(
                json.dumps(actual, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            deshacer_acciones.append(
                lambda ruta=ruta, original=original_texto: ruta.write_text(original, encoding="utf-8")
            )
        # si existía y no hay nada que fusionar, no se toca: coherente con "nunca pisa".

    def _deshacer() -> None:
        for accion in reversed(deshacer_acciones):
            try:
                accion()
            except OSError:
                pass  # mejor esfuerzo: un fallo de limpieza no debe tapar la excepción original

    try:
        for carpeta in operaciones["carpetas"]:
            _crear_carpeta(carpeta)

        for ruta_abs, contenido in operaciones["notas"]:
            _escribir_si_falta(ruta_abs, contenido)

        _escribir_si_falta(*operaciones["claude_md"])
        _escribir_si_falta(*operaciones["output_style"])

        for ruta_abs, contenido in operaciones["plantillas_nota"]:
            _escribir_si_falta(ruta_abs, contenido)

        ruta_estado, estado_nuevo = operaciones["estado_modulos"]
        _fusionar_estado_modulos(ruta_estado, estado_nuevo)
    except Exception as e:
        _deshacer()
        raise ValueError(
            f"Fallo al escribir la bóveda, deshecho sin dejar rastro: {e}"
        ) from e

    return creadas


# --------------------------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ejecuta en disco un plan de alta de bóveda ya aprobado."
    )
    ap.add_argument("plan", help="Ruta al plan.json aprobado")
    ap.add_argument("--dry-run", action="store_true",
                     help="Solo valida el plan; no escribe nada")
    ap.add_argument("--raiz", default=".",
                     help="Carpeta donde nace la bóveda (por defecto, la actual)")
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
            print(f"Plan válido. Hasta {total} elemento(s) por crear en {raiz} "
                  f"(los que ya existan se dejan como están).")
            return 0
        creadas = generar(plan, raiz)
    except ValueError as e:
        print(f"[ERROR] plan inválido: {e}")
        return 1

    print(f"Bóveda generada: {len(creadas)} elemento(s) nuevo(s) en {raiz}")
    for ruta in creadas:
        print(f"  + {ruta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
