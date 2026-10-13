"""Todo import externo del kit está declarado en requirements.txt.

Por qué existe esta prueba: `auditar_vault.py` llegó del vault de origen haciendo
`import yaml` sin declararlo. Allí funcionaba porque chromadb arrastra PyYAML de
forma transitiva; aquí el kit se entrega SIN SOPORTE, así que un módulo que muere
al importar en una instalación limpia es un módulo roto y el compañero no tiene a
quién preguntar. Un `grep` lo encontró una vez; esto lo vigila siempre.
"""
import ast, sys, pytest

# El nombre que se importa no es el que se instala. Solo las excepciones reales.
PAQUETE = {"docx": "python-docx", "yaml": "PyYAML"}


def _fuentes(raiz):
    return sorted(
        list((raiz / "nucleo" / ".glados").glob("*.py"))
        + list(raiz.glob("modulos/*/*.py"))
        + list((raiz / "herramientas").glob("*.py"))
    )


def _importados(raiz):
    """Todos los imports, incluidos los que viven dentro de una función: un
    import diferido también revienta, solo lo hace más tarde y peor."""
    vistos = {}
    for f in _fuentes(raiz):
        arbol = ast.parse(f.read_text(encoding="utf-8"), filename=str(f))
        for n in ast.walk(arbol):
            if isinstance(n, ast.Import):
                for a in n.names:
                    vistos.setdefault(a.name.split(".")[0], f)
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                vistos.setdefault(n.module.split(".")[0], f)
    return vistos


def test_todo_import_externo_esta_declarado(raiz):
    declarados = {
        linea.split("==")[0].split(">=")[0].strip().lower()
        for linea in (raiz / "nucleo" / ".glados" / "requirements.txt")
        .read_text(encoding="utf-8")
        .splitlines()
        if linea.strip() and not linea.startswith("#")
    }
    locales = {p.stem for p in _fuentes(raiz)}
    sin_declarar = [
        (nombre, str(fichero.relative_to(raiz)))
        for nombre, fichero in _importados(raiz).items()
        if nombre not in sys.stdlib_module_names
        and nombre not in locales
        and PAQUETE.get(nombre, nombre).lower() not in declarados
    ]
    assert not sin_declarar, sin_declarar
