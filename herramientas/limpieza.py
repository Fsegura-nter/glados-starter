"""Barrido anti-datos-de-NTER. Sale 1 si encuentra algo que no debe estar en un repo publico."""
import re, sys, pathlib
from collections import namedtuple

Hallazgo = namedtuple("Hallazgo", "fichero linea patron texto")

PATRONES = {
    "dominio_interno": re.compile(r"\bnfqsolutions\.es\b", re.I),
    "correo":          re.compile(r"[\w.+-]+@(?:[\w-]+\.)*(?:nter|nfqsolutions)\.[a-z]{2,}", re.I),
    "cliente":         re.compile(r"Treyit|Yiyit|SegurCaixa|Adeslas", re.I),
    "ruta_personal":   re.compile(r"[A-Z]:\\Users\\[A-Za-z]{2}\d{6,}", re.I),
}
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


def buscar(raiz, *, permitidos=None):
    raiz = pathlib.Path(raiz)
    out = []
    for f in raiz.rglob("*"):
        if not f.is_file() or f.suffix.lower() in BINARIOS:
            continue
        if IGNORAR & set(f.relative_to(raiz).parts):
            continue

        # Comprobar si el fichero está en la lista blanca
        ruta_relativa = str(f.relative_to(raiz)).replace("\\", "/")
        if permitidos is not None and ruta_relativa in permitidos:
            continue

        try:
            datos = f.read_bytes()
            encoding = _detectar_encoding(datos)
            lineas = datos.decode(encoding, errors="ignore").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for n, linea in enumerate(lineas, 1):
            for nombre, patron in PATRONES.items():
                m = patron.search(linea)
                if m:
                    out.append(Hallazgo(f.relative_to(raiz), n, nombre, m.group(0)))
    return out


if __name__ == "__main__":
    raiz = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    permitidos = leer_permitidos(raiz)
    hallazgos = buscar(raiz, permitidos=permitidos)
    for h in hallazgos:
        print(f"{h.fichero}:{h.linea}  {h.patron}  {h.texto}")
    print(f"\n{len(hallazgos)} hallazgo(s)")
    if permitidos:
        print(f"{len(permitidos)} fichero(s) excluidos por .limpieza-permitido: {', '.join(sorted(permitidos))}")
    sys.exit(1 if hallazgos else 0)
