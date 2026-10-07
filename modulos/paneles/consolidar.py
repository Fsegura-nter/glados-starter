#!/usr/bin/env python3
"""
consolidar.py — Encuentra lo que el vault ya sabe de una entidad y su ficha no dice.

El problema que resuelve: una ficha de cliente con pocas líneas y «(pendiente)» en varias
secciones, mientras la carpeta de memoria ya guarda decenas de ficheros con el modelo
operativo, los roles y el flujo de trabajo, y hay funcionales indexados al lado. El
conocimiento estaba; estaba en la capa de historia en vez de en la de estado.

Reparto de trabajo, según el principio de «scripts antes que tokens»: **este script busca y
recorta; el modelo solo redacta el diff.** Nunca escribe en la ficha — imprime una tabla de
huecos y, por hueco, los fragmentos candidatos con su ruta y su fecha.

Las memorias son historia, no estado: cada evidencia sale fechada y lo que pase de
ANTIGUO_DIAS se marca [VERIFICAR], porque puede describir algo que ya cambió.

Uso: python consolidar.py <entidad> [-n 4] [--seccion "Contexto"]
"""
import argparse
import re
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()
import lexical
import index_docs

ANTIGUO_DIAS = 90
MAX_FRAGMENTO = 320
# Por debajo de esto, una seccion no dice nada: solo tiene el comentario de la plantilla,
# la cabecera de una tabla vacia o un "(pendiente)".
MIN_UTIL = 40

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---", re.DOTALL)
COMENTARIO_RE = re.compile(r"<!--.*?-->", re.DOTALL)
VACIO_RE = re.compile(r"_?\(?pendiente\)?_?|_?\(?por confirmar\)?_?|tbd", re.IGNORECASE)

# Que buscar para cada seccion. La clave se compara normalizada y sin acentos.
CONSULTAS = {
    "contexto": "sector negocio alcance encargo contrata servicio producto",
    "contactos": "contacto responsable interlocutor rol equipo persona",
    "proyectos": "proyecto modulo repositorio aplicacion",
    "acuerdos y decisiones": "decision acordado acuerdo criterio alcance version",
    "descripcion": "que es para que sirve objetivo funcionalidad",
    "arquitectura": "arquitectura stack componentes integraciones base datos framework",
    "estado actual": "estado avance pendiente bloqueo entregado",
    "decisiones": "decision motivo eleccion patron contrato",
    "documentacion": "documento funcional requisitos especificacion",
}

# Secciones que son punteros, no contenido: no tiene sentido buscarles evidencias.
IGNORAR = {"documentacion", "notas", "todos"}

# Claves de metadata de las memorias. El primer fragmento de cada fichero es su cabecera
# YAML, y FTS lo puntua alto porque repite el nombre del cliente: sin esto, las evidencias
# son catorce lineas de `node_type: memory` y ni una de contenido.
META_RE = re.compile(
    r"\b(tipo|cliente|proyecto|tags|fecha|name|metadata|node_type|originSessionId|modified|"
    r"type|description):", re.IGNORECASE)


def limpiar_fragmento(frag: str) -> str:
    """Quita la cabecera de metadata y deja el contenido. Si no queda nada, usa description."""
    descripcion = ""
    m = re.search(r"description:\s*\"?([^\"]{10,200}?)\"?(?:\s+\w+:|$)", frag)
    if m:
        descripcion = m.group(1).strip()
    cuerpo = frag
    if cuerpo.lstrip().startswith("---"):
        cuerpo = re.sub(r"^\s*---.*?---\s*", "", cuerpo, count=1, flags=re.DOTALL)
    # Los chunks parten el YAML por la mitad: el cierre `---` puede no estar en este trozo.
    trozos = [t for t in re.split(r"\s{2,}|\. ", cuerpo) if t.strip()]
    cuerpo = " ".join(t for t in trozos if not META_RE.search(t)).strip(" -")
    if len(cuerpo) < 60:
        return f"(resumen) {descripcion}" if descripcion else cuerpo
    return cuerpo


def sin_acentos(t: str) -> str:
    tabla = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
    return t.translate(tabla)


def frontmatter(texto: str) -> dict:
    m = FRONTMATTER_RE.match(texto)
    if not m:
        return {}
    datos = {}
    for linea in m.group(1).splitlines():
        kv = re.match(r"^([\w-]+):\s*(.*)$", linea)
        if kv:
            datos[kv.group(1)] = kv.group(2).strip().strip("\"'")
    return datos


def _carpeta(rol: str) -> Path | None:
    nombre = config.carpetas().get(rol)
    return (config.vault_path() / nombre) if nombre else None


def resolver(nombre: str) -> tuple[Path, str] | tuple[None, None]:
    """Ficha de la entidad, por nombre de fichero o por alias. (ruta, tipo)."""
    objetivo = sin_acentos(nombre).lower().strip()
    candidatas = []
    for rol, tipo in (("clientes", "cliente"), ("proyectos", "proyecto")):
        carpeta = _carpeta(rol)
        if not carpeta or not carpeta.is_dir():
            continue
        for nota in carpeta.glob("*.md"):
            if nota.name.startswith("_"):
                continue
            if sin_acentos(nota.stem).lower() == objetivo:
                return nota, tipo
            fm = frontmatter(nota.read_text(encoding="utf-8", errors="ignore"))
            alias = [a.strip().strip("\"'").lower()
                     for a in fm.get("aliases", "").strip("[]").split(",")]
            if objetivo in alias:
                candidatas.append((nota, tipo))
    return candidatas[0] if candidatas else (None, None)


def secciones(texto: str) -> list[tuple[str, str]]:
    """[(titulo, cuerpo)] de los encabezados de nivel 2."""
    cuerpo = FRONTMATTER_RE.sub("", texto)
    partes = re.split(r"^## +(.+)$", cuerpo, flags=re.M)
    return [(partes[i].strip(), partes[i + 1]) for i in range(1, len(partes) - 1, 2)]


def es_hueco(cuerpo: str) -> str:
    """Motivo por el que la seccion no dice nada, o '' si si dice algo."""
    util = COMENTARIO_RE.sub("", cuerpo)
    util = "\n".join(l for l in util.splitlines()
                     if not re.match(r"^\s*\|[\s\-|]*\|\s*$", l))   # filas de tabla vacias
    tiene_pendiente = bool(VACIO_RE.search(util))
    util = VACIO_RE.sub("", util)
    util = re.sub(r"[|\-\s_]+", " ", util).strip()
    if len(util) < MIN_UTIL:
        return "marcada como pendiente" if tiene_pendiente else "vacia"
    if tiene_pendiente:
        return "tiene partes pendientes"
    return ""


def fecha_de(referencia: str) -> tuple[str, bool]:
    """(fecha, es_antigua) de la fuente de un fragmento. ('?', False) si no se sabe.

    La raíz de cada colección la resuelve `index_docs._carpeta_coleccion`: es la misma
    resolución que usó el indexador para escribir esa referencia, así que las dos
    nunca pueden discrepar sobre dónde vive el fichero.
    """
    coleccion, _, relativa = referencia.partition("/")
    raiz = index_docs._carpeta_coleccion(config.vault_path(), coleccion)
    if not raiz:
        return "?", False
    ruta = raiz / relativa
    if not ruta.is_file():
        return "?", False
    try:
        cabeza = ruta.read_text(encoding="utf-8", errors="ignore")[:1200]
    except OSError:
        return "?", False
    fm = frontmatter(cabeza)
    cruda = fm.get("fecha") or fm.get("modified") or ""
    m = re.search(r"\d{4}-\d{2}-\d{2}", cruda)
    if not m:
        # Sin frontmatter util (los volcados sin destilar no lo tienen): vale el mtime.
        stamp = date.fromtimestamp(ruta.stat().st_mtime).isoformat()
        return stamp, (date.today() - date.fromisoformat(stamp)).days > ANTIGUO_DIAS
    stamp = m.group(0)
    try:
        dias = (date.today() - datetime.strptime(stamp, "%Y-%m-%d").date()).days
    except ValueError:
        return stamp, False
    return stamp, dias > ANTIGUO_DIAS


def main() -> int:
    ap = argparse.ArgumentParser(description="Huecos de una ficha y evidencias para rellenarlos.")
    ap.add_argument("entidad", help="Nombre o alias del cliente o proyecto")
    ap.add_argument("-n", type=int, default=4, help="Evidencias por hueco (def. 4)")
    ap.add_argument("--seccion", help="Solo esta seccion")
    args = ap.parse_args()

    ficha, tipo = resolver(args.entidad)
    if not ficha:
        nombre_clientes = config.carpetas().get("clientes") or "clientes"
        nombre_proyectos = config.carpetas().get("proyectos") or "proyectos"
        print(f"No hay ficha para '{args.entidad}' en {nombre_clientes} ni en {nombre_proyectos}.")
        print("Si es una entidad nueva, se da de alta con /new-client o /new-project.")
        return 1

    texto = ficha.read_text(encoding="utf-8")
    fm = frontmatter(texto)
    alias = [a.strip().strip("\"'") for a in fm.get("aliases", "").strip("[]").split(",") if a.strip()]
    rel = ficha.relative_to(ficha.parent.parent).as_posix()

    print(f"Ficha    : {rel}  ({tipo} - area {fm.get('area', '?')}, estado {fm.get('estado', '?')})")
    print(f"Aliases  : {', '.join(alias) or '(ninguno)'}")
    print(f"Tamano   : {len(texto)} bytes")

    todas = secciones(texto)
    huecos = [(t, m) for t, c in todas
              if (m := es_hueco(c)) and sin_acentos(t).lower() not in IGNORAR]
    if args.seccion:
        objetivo = sin_acentos(args.seccion).lower()
        huecos = [(t, m) for t, m in huecos if sin_acentos(t).lower() == objetivo]

    print(f"\nHUECOS: {len(huecos)} de {len(todas)} secciones")
    for titulo, motivo in huecos:
        print(f"  - {titulo:26} {motivo}")
    if not huecos:
        print("  (ninguno: la ficha esta completa)")
        return 0

    print("\n" + "=" * 78)
    print("EVIDENCIAS — el modelo redacta a partir de esto, citando la referencia.")
    print("=" * 78)

    colecciones = config.colecciones()
    sin_nada = []
    for titulo, _ in huecos:
        extra = CONSULTAS.get(sin_acentos(titulo).lower(), titulo)
        consulta = f"{ficha.stem} {' '.join(alias)} {extra}"
        # La consulta FTS es un OR de terminos, asi que arrastra material de otros clientes
        # que comparte vocabulario. Se exige que la entidad aparezca en la ruta o en el texto.
        marcadores = [sin_acentos(ficha.stem).lower()] + [sin_acentos(a).lower() for a in alias]
        vistos, resultados = set(), []
        for coleccion in colecciones:
            for ref, frag in lexical.search(consulta, coleccion=coleccion, limit=args.n * 3):
                if ref in vistos:
                    continue
                donde = sin_acentos(f"{ref} {frag}").lower()
                if not any(mk in donde for mk in marcadores):
                    continue
                limpio = limpiar_fragmento(frag)
                if len(limpio) < 40:
                    continue
                vistos.add(ref)
                resultados.append((ref, limpio))
        resultados = resultados[:args.n]

        print(f"\n## {titulo}")
        if not resultados:
            print("  (sin evidencias: esto el vault no lo sabe, hay que preguntarlo)")
            sin_nada.append(titulo)
            continue
        for i, (ref, frag) in enumerate(resultados, 1):
            stamp, antigua = fecha_de(ref)
            marca = f" [VERIFICAR: mas de {ANTIGUO_DIAS} dias]" if antigua else ""
            print(f"  [{i}] {ref}  ({stamp}){marca}")
            print(f"      {frag[:MAX_FRAGMENTO]}")

    if sin_nada:
        print(f"\nSIN FUENTE (preguntar): {', '.join(sin_nada)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
