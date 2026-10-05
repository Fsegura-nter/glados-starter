#!/usr/bin/env python3
"""
lexical.py — Búsqueda literal sobre las colecciones indexadas, con SQLite FTS5.

Existe por una razón medida: cargar el modelo de embeddings cuesta ~50 s en frío y el
hook `UserPromptSubmit` (ver `context_injector.py`) no puede esperar tanto sin colgar
el envío del mensaje. Esta capa usa solo la stdlib y responde en milisegundos, así que
puede vivir dentro del hook. La capa semántica (`query_docs.py`) queda para consultas a
demanda, donde esperar sí tiene sentido. No fusionar las dos capas, y no hacer que esta
importe el modelo.

Cada fragmento lleva su `coleccion` (fuentes, memoria, …) y su `cliente` (la primera
carpeta bajo la raíz de la colección), de forma que se puede buscar dentro de un solo
origen. La escribe `index_docs.py`.

El índice vive FUERA del vault, bajo `config.data_dir()`: una base SQLite dentro de una
carpeta que además sincroniza a la nube se corrompe si la sincronización la toca a
mitad de escritura.

Uso:
    python lexical.py "consulta" --vault <ruta> [--cliente X] [--coleccion fuentes]
"""
import argparse
import re
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

SCHEMA = """
CREATE VIRTUAL TABLE IF NOT EXISTS chunks USING fts5(
    source, coleccion, cliente, texto, chunk UNINDEXED,
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TABLE IF NOT EXISTS files (
    source TEXT NOT NULL, coleccion TEXT NOT NULL, mtime REAL NOT NULL,
    PRIMARY KEY (coleccion, source)
);
"""

# Palabras que no aportan selección en una consulta en español.
STOPWORDS = {
    'que', 'como', 'para', 'por', 'con', 'sin', 'del', 'las', 'los', 'una', 'uno', 'unos', 'unas',
    'sobre', 'este', 'esta', 'esto', 'esos', 'esas', 'dice', 'dicen', 'hay', 'son', 'era', 'ser',
    'the', 'and', 'dime', 'cual', 'cuales', 'donde', 'cuando', 'quien', 'segun', 'mas', 'algo',
}
MIN_TERM_LEN = 4


def lexical_db_path() -> Path:
    """Ruta del índice léxico: `config.data_dir()`, nunca dentro del vault."""
    return config.data_dir() / "lexical.sqlite3"


def connect(readonly: bool = False) -> sqlite3.Connection:
    path = lexical_db_path()
    if readonly:
        return sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA)
    return con


def indexed_state(coleccion: str) -> dict[str, float]:
    """{source: mtime} de lo que ya está indexado en esa colección."""
    try:
        with connect() as con:
            return {s: m for s, m in
                    con.execute("SELECT source, mtime FROM files WHERE coleccion = ?", (coleccion,))}
    except Exception:
        return {}


def replace_file(source: str, coleccion: str, cliente: str, mtime: float, chunks: list[str]) -> None:
    with connect() as con:
        con.execute("DELETE FROM chunks WHERE source = ? AND coleccion = ?", (source, coleccion))
        con.executemany(
            "INSERT INTO chunks (source, coleccion, cliente, texto, chunk) VALUES (?, ?, ?, ?, ?)",
            [(source, coleccion, cliente, texto, i) for i, texto in enumerate(chunks)],
        )
        con.execute("INSERT OR REPLACE INTO files (source, coleccion, mtime) VALUES (?, ?, ?)",
                    (source, coleccion, mtime))


def forget_file(source: str, coleccion: str) -> None:
    with connect() as con:
        con.execute("DELETE FROM chunks WHERE source = ? AND coleccion = ?", (source, coleccion))
        con.execute("DELETE FROM files WHERE source = ? AND coleccion = ?", (source, coleccion))


def is_populated() -> bool:
    if not lexical_db_path().exists():
        return False
    try:
        with connect(readonly=True) as con:
            return con.execute("SELECT EXISTS(SELECT 1 FROM files)").fetchone()[0] == 1
    except Exception:
        return False


def stats() -> list[tuple[str, int, int]]:
    """[(coleccion, ficheros, fragmentos)] para inspección."""
    if not lexical_db_path().exists():
        return []
    try:
        with connect(readonly=True) as con:
            return con.execute(
                "SELECT f.coleccion, COUNT(DISTINCT f.source), "
                "(SELECT COUNT(*) FROM chunks c WHERE c.coleccion = f.coleccion) "
                "FROM files f GROUP BY f.coleccion ORDER BY f.coleccion").fetchall()
    except Exception:
        return []


def _fts_query(texto: str) -> str:
    """Convierte lenguaje natural en una consulta FTS5 segura: términos OR con prefijo."""
    palabras = re.findall(r"[0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{2,}", texto)
    terminos = []
    for p in palabras:
        low = p.lower()
        if len(low) < MIN_TERM_LEN or low in STOPWORDS or low in terminos:
            continue
        terminos.append(low)
    return " OR ".join(f'"{t}"*' for t in terminos[:12])


def search(texto: str, cliente: str | None = None, coleccion: str | None = None,
           limit: int = 3) -> list[tuple[str, str]]:
    """[(referencia, fragmento), ...] por relevancia. La referencia incluye la colección.

    Firma y forma de retorno fijadas por `context_injector.py`, que ya la consume así
    (`for src, frag in lexical.search(...)`). Nunca lanza: si algo falla, o si el índice
    no existe todavía, devuelve vacío — un vault recién creado no tiene nada que buscar.
    """
    consulta = _fts_query(texto)
    if not consulta or not is_populated():
        return []
    sql = ["SELECT coleccion, source, texto FROM chunks WHERE chunks MATCH ?"]
    args: list = [consulta]
    if cliente:
        sql.append("AND cliente = ?")
        args.append(cliente)
    if coleccion:
        sql.append("AND coleccion = ?")
        args.append(coleccion)
    sql.append("ORDER BY rank LIMIT ?")
    args.append(limit)
    try:
        with connect(readonly=True) as con:
            filas = con.execute(" ".join(sql), args).fetchall()
    except Exception:
        return []
    return [(f"{col}/{src}", " ".join(txt.split())) for col, src, txt in filas]


def main() -> int:
    ap = argparse.ArgumentParser(description="Búsqueda literal en el vault (rápida).")
    ap.add_argument("query", nargs="*")
    ap.add_argument("--vault", required=True,
                     help="Raíz del vault. El índice vive fuera, en el directorio de "
                          "datos (config.data_dir()); el flag existe para poder probar "
                          "esta herramienta contra un directorio temporal en vez del "
                          "vault real.")
    ap.add_argument("--cliente")
    ap.add_argument("--coleccion")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--stats", action="store_true", help="Qué hay indexado, sin buscar nada")
    args = ap.parse_args()

    if not is_populated():
        print("No hay índice todavía. Ejecuta primero: python index_docs.py --vault "
              f"{args.vault}")
        return 0

    if args.stats or not args.query:
        filas = stats()
        print(f"{'colección':<12} {'ficheros':>9} {'fragmentos':>11}")
        for col, nf, nc in filas:
            print(f"{col:<12} {nf:>9} {nc:>11}")
        return 0

    resultados = search(" ".join(args.query), cliente=args.cliente,
                        coleccion=args.coleccion, limit=args.n)
    if not resultados:
        print("Sin resultados léxicos para esa búsqueda.")
        return 1
    for ref, frag in resultados:
        print(f"\n[{ref}] → {frag[:400]}{'...' if len(frag) > 400 else ''}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
