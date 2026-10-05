#!/usr/bin/env python3
"""
query_docs.py — Consulta semántica (embeddings) sobre las colecciones indexadas.

Cargar el modelo de embeddings cuesta ~50 s en frío, así que esta capa es para uso a
demanda, nunca dentro de un hook. La búsqueda rápida vive en `lexical.py`. Este módulo
no carga el modelo ni importa `chromadb` a nivel de módulo: todo lo pesado vive dentro
de las funciones, para que importarlo (por ejemplo desde una prueba o desde otro
script) no pague ese coste si no llega a usarse.

El modelo es configurable (`settings.json` → `modelo_embeddings`); por defecto uno
multilingüe, porque los documentos de un vault en español necesitan un modelo que
entienda español — uno solo de inglés devolvería vecindades sin sentido, en silencio.

Uso: python query_docs.py "mi consulta" --vault <ruta> [--cliente X] [--coleccion fuentes]
"""
import argparse
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

NOMBRE_COLECCION_VECTORES = "docs"
MODELO_EMBEDDINGS_DEFECTO = "paraphrase-multilingual-MiniLM-L12-v2"


def vectorstore_path() -> Path:
    """Ruta del índice semántico: `config.data_dir()`, nunca dentro del vault."""
    return config.data_dir() / "vectorstore"


def modelo_embeddings() -> str:
    valor = config.local_settings().get("modelo_embeddings")
    return valor if isinstance(valor, str) and valor else MODELO_EMBEDDINGS_DEFECTO


def has_embeddings() -> bool:
    """¿Hay vectores en el store? Se lee el sqlite de Chroma directamente: importar
    `chromadb` y construir la función de embeddings cuesta ~50 s, y no tiene sentido
    pagarlo solo para descubrir que el índice está vacío."""
    db = vectorstore_path() / "chroma.sqlite3"
    if not db.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return con.execute("SELECT EXISTS(SELECT 1 FROM embeddings)").fetchone()[0] == 1
        finally:
            con.close()
    except Exception:
        return False


def query_docs(query: str, n_results: int = 5, cliente: str | None = None,
               coleccion: str | None = None) -> list[tuple[str, str]]:
    """Devuelve [(referencia, fragmento), ...]. Vacío si no hay nada indexado todavía
    — eso no es un error, es el estado normal de un vault recién generado."""
    if not has_embeddings():
        return []
    # El modelo ya está en la caché local; sin esto sentence-transformers consulta
    # HuggingFace en cada arranque y añade latencia y dependencia de red.
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    import chromadb
    from chromadb.utils import embedding_functions

    client = chromadb.PersistentClient(path=str(vectorstore_path()))
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(model_name=modelo_embeddings())
    try:
        collection = client.get_collection(NOMBRE_COLECCION_VECTORES, embedding_function=ef)
    except Exception:
        return []
    total = collection.count()
    if total == 0:
        return []
    kwargs = {"query_texts": [query], "n_results": min(n_results, total)}
    filtros = [{"cliente": cliente}] if cliente else []
    if coleccion:
        filtros.append({"coleccion": coleccion})
    if len(filtros) == 1:
        kwargs["where"] = filtros[0]
    elif filtros:
        kwargs["where"] = {"$and": filtros}
    results = collection.query(**kwargs)
    return [(f'{meta.get("coleccion", "?")}/{meta.get("source", "desconocido")}',
             " ".join(doc.split()))
            for doc, meta in zip(results["documents"][0], results["metadatas"][0])]


def main() -> int:
    config.force_utf8()
    ap = argparse.ArgumentParser(description="Búsqueda semántica (lenta) en el vault.")
    ap.add_argument("query", nargs="+")
    ap.add_argument("--vault", required=True,
                     help="Raíz del vault. El índice semántico vive fuera, en el "
                          "directorio de datos (config.data_dir()); el flag existe "
                          "para poder probar esta herramienta contra un directorio "
                          "temporal en vez del vault real, igual que index_docs.py "
                          "y lexical.py.")
    ap.add_argument("--cliente")
    ap.add_argument("--coleccion", help="fuentes | memoria | ...")
    ap.add_argument("-n", type=int, default=5)
    args = ap.parse_args()
    query = " ".join(args.query)

    if not has_embeddings():
        print(f"El indice semantico esta vacio. Ejecuta: python index_docs.py --vault {args.vault}")
        return 1

    results = query_docs(query, n_results=args.n, cliente=args.cliente, coleccion=args.coleccion)
    if not results:
        print("Sin resultados para esa consulta.")
        return 1

    print(f'\nResultados para: "{query}"\n{"-" * 60}')
    for source, fragment in results:
        print(f"\n[{source}] -> {fragment[:400]}{'...' if len(fragment) > 400 else ''}")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
