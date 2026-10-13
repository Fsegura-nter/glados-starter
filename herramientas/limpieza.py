"""Barrido de datos privados. Sale 1 si encuentra algo que no debe estar en un repo publico.

Los patrones NO viven en este fichero, y eso es el arreglo de un fallo que este propio
script tenia: los nombres de los clientes y el dominio interno estaban escritos aqui como
expresiones regulares, y la lista blanca `.limpieza-permitido` excluia este fichero del
barrido, asi que **el guardian era invisible a si mismo**. Publicar el repositorio habria
publicado la lista de clientes de la empresa dentro de la herramienta que existe
precisamente para que eso no pase.

Ahora los patrones se leen de `.limpieza-patrones.json`, que esta en `.gitignore` y no se
publica nunca. El repositorio trae `.limpieza-patrones.example.json` con marcadores de
posicion y la instruccion de copiarlo.

Si el fichero de patrones no existe, esto **falla con codigo 2** y no barre nada. Nunca
pasa en silencio: un barrido sin patrones que contesta «0 hallazgos» es peor que no tener
barrido, porque certifica que no hay fugas sin haber mirado.
"""
import json, re, sys, pathlib
from collections import namedtuple

Hallazgo = namedtuple("Hallazgo", "fichero linea patron texto")

FICHERO_PATRONES = ".limpieza-patrones.json"
EJEMPLO_PATRONES = ".limpieza-patrones.example.json"


def cargar_patrones(raiz):
    """Lee los patrones del fichero local. Lanza si no esta o si no sirve."""
    ruta = pathlib.Path(raiz) / FICHERO_PATRONES
    if not ruta.is_file():
        raise FileNotFoundError(
            f"No hay {FICHERO_PATRONES} en {raiz}. "
            f"Copia {EJEMPLO_PATRONES} a {FICHERO_PATRONES} y pon tus propios dominios, "
            "nombres de cliente y rutas. Ese fichero esta en .gitignore a proposito: los "
            "patrones nombran justo lo que no debe salir del repositorio."
        )
    crudos = json.loads(ruta.read_text(encoding="utf-8"))
    if not isinstance(crudos, dict) or not crudos:
        raise ValueError(f"{FICHERO_PATRONES} tiene que ser un objeto con al menos un patron")
    compilados = {}
    for nombre, expresion in crudos.items():
        if nombre.startswith("_"):
            continue                       # claves de documentacion dentro del JSON
        if not isinstance(expresion, str) or not expresion:
            raise ValueError(f"{FICHERO_PATRONES}: el patron {nombre!r} no es una cadena")
        try:
            compilados[nombre] = re.compile(expresion, re.I)
        except re.error as e:
            raise ValueError(f"{FICHERO_PATRONES}: el patron {nombre!r} no compila: {e}") from e
    if not compilados:
        raise ValueError(f"{FICHERO_PATRONES} no declara ningun patron utilizable")
    return compilados
IGNORAR = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".superpowers"}
BINARIOS = {".png", ".jpg", ".ico", ".zip", ".pyc", ".ttf", ".woff2"}


def _detectar_encoding(datos_bytes):
    """Detecta el encoding de un fichero: UTF-16-LE (BOM), UTF-16-BE (BOM), UTF-8-sig, o UTF-8."""
    if datos_bytes.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    if datos_bytes.startswith(b'\xfe\xff'):
        return 'utf-16-be'
    if datos_bytes.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    # Si no hay BOM, revisa los primeros 1024 bytes: si hay NUL bytes, probablemente es UTF-16-LE
    if b'\x00' in datos_bytes[:1024]:
        return 'utf-16-le'
    return 'utf-8'


def leer_permitidos(raiz):
    """Lee la lista blanca de ficheros permitidos a contener patrones buscados.

    Retorna un conjunto de rutas normalizadas (barras normales, sin ./).
    Un fichero ausente retorna un conjunto vacío sin error.
    """
    raiz = pathlib.Path(raiz)
    permitidos_file = raiz / ".limpieza-permitido"
    permitidos = set()

    if not permitidos_file.exists():
        return permitidos

    try:
        contenido = permitidos_file.read_text(encoding="utf-8")
        for linea in contenido.splitlines():
            linea = linea.strip()
            # Ignorar líneas vacías y comentarios
            if not linea or linea.startswith("#"):
                continue
            # Normalizar: forward slashes
            ruta_normalizada = linea.replace("\\", "/")
            permitidos.add(ruta_normalizada)
    except (OSError, UnicodeDecodeError):
        pass

    return permitidos


def buscar(raiz, *, permitidos=None, patrones=None):
    raiz = pathlib.Path(raiz)
    if patrones is None:
        patrones = cargar_patrones(raiz)
    out = []
    for f in raiz.rglob("*"):
        if not f.is_file() or f.suffix.lower() in BINARIOS:
            continue
        if IGNORAR & set(f.relative_to(raiz).parts):
            continue

        # Comprobar si el fichero está en la lista blanca
        ruta_relativa = str(f.relative_to(raiz)).replace("\\", "/")
        # El propio fichero de patrones nombra lo que se busca, y está en .gitignore:
        # no se puede publicar, así que delatarlo sólo haría ruido en cada barrido.
        if ruta_relativa == FICHERO_PATRONES:
            continue
        if permitidos is not None and ruta_relativa in permitidos:
            continue

        try:
            datos = f.read_bytes()
            encoding = _detectar_encoding(datos)
            lineas = datos.decode(encoding, errors="ignore").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, linea in enumerate(lineas, 1):
            for nombre, patron in patrones.items():
                m = patron.search(linea)
                if m:
                    out.append(Hallazgo(f.relative_to(raiz), n, nombre, m.group(0)))
    return out


if __name__ == "__main__":
    raiz = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    try:
        patrones = cargar_patrones(raiz)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(2)          # NUNCA 0: un barrido sin patrones no certifica nada
    permitidos = leer_permitidos(raiz)
    hallazgos = buscar(raiz, permitidos=permitidos, patrones=patrones)
    for h in hallazgos:
        print(f"{h.fichero}:{h.linea}  {h.patron}  {h.texto}")
    print(f"\n{len(hallazgos)} hallazgo(s), con {len(patrones)} patron(es)")
    if permitidos:
        print(f"{len(permitidos)} fichero(s) excluidos por .limpieza-permitido: {', '.join(sorted(permitidos))}")
    sys.exit(1 if hallazgos else 0)
