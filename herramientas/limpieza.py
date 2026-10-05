"""Barrido anti-datos-de-NTER. Sale 1 si encuentra algo que no debe estar en un repo publico."""
import re, sys, pathlib
from collections import namedtuple

Hallazgo = namedtuple("Hallazgo", "fichero linea patron texto")

PATRONES = {
    "dominio_interno": re.compile(r"\bnfqsolutions\.es\b", re.I),
    "correo":          re.compile(r"[\w.+-]+@(?:nter|nfqsolutions)\.[a-z]{2,}", re.I),
    "cliente":         re.compile(r"\b(?:Treyit|Yiyit|SegurCaixa|Adeslas)\b", re.I),
    "ruta_personal":   re.compile(r"[A-Z]:\\Users\\[A-Za-z]{2}\d{6,}", re.I),
}
IGNORAR = {".git", ".venv", "__pycache__", ".pytest_cache", "node_modules", ".superpowers"}
BINARIOS = {".png", ".jpg", ".ico", ".zip", ".pyc", ".ttf", ".woff2"}


def buscar(raiz):
    raiz = pathlib.Path(raiz)
    out = []
    for f in raiz.rglob("*"):
        if not f.is_file() or f.suffix.lower() in BINARIOS:
            continue
        if IGNORAR & set(f.relative_to(raiz).parts):
            continue
        try:
            lineas = f.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for n, linea in enumerate(lineas, 1):
            for nombre, patron in PATRONES.items():
                m = patron.search(linea)
                if m:
                    out.append(Hallazgo(f.relative_to(raiz), n, nombre, m.group(0)))
    return out


if __name__ == "__main__":
    raiz = sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parent.parent
    hallazgos = buscar(raiz)
    for h in hallazgos:
        print(f"{h.fichero}:{h.linea}  {h.patron}  {h.texto}")
    print(f"\n{len(hallazgos)} hallazgo(s)")
    sys.exit(1 if hallazgos else 0)
