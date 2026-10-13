"""El barrido de datos privados.

Estas pruebas usan patrones FICTICIOS inyectados, no los reales. Hasta el 2026-10-13 este
fichero traía el dominio interno de la empresa, correos corporativos, los nombres de
cuatro clientes y la matrícula de empleado del autor — y estaba en la lista blanca del
propio barrido, así que nada lo veía. Publicar el repositorio habría publicado
exactamente lo que la herramienta existe para impedir, en su propia suite de pruebas.

El mecanismo se prueba igual de bien con `miempresa.example` y `ClienteFicticio`.
"""
import json, re, subprocess, sys

import pytest

from herramientas.limpieza import FICHERO_PATRONES, buscar, cargar_patrones, leer_permitidos

# Los mismos cuatro patrones que usa el kit de verdad, con valores inventados.
# `buscar` espera patrones YA compilados, igual que los devuelve `cargar_patrones`.
FALSOS = {nombre: re.compile(expresion, re.I) for nombre, expresion in {
    "dominio_interno": r"\bmiempresa\.example\b",
    "correo_interno": r"[\w.+-]+@(?:[\w-]+\.)*miempresa\.[a-z]{2,}",
    "cliente": r"ClienteFicticio|OtroCliente",
    "ruta_personal": r"[A-Z]:\\Users\\[A-Za-z]{2}\d{6,}",
}.items()}


def barrer(ruta, **kw):
    return buscar(ruta, patrones=FALSOS, **kw)


# --- los cuatro patrones -----------------------------------------------------

def test_detecta_dominio_interno(tmp_path):
    (tmp_path / "a.md").write_text("ver https://gitlab.miempresa.example/x", encoding="utf-8")
    assert [h.patron for h in barrer(tmp_path)] == ["dominio_interno"]


def test_detecta_correo_corporativo(tmp_path):
    (tmp_path / "a.py").write_text('MAIL = "alguien@miempresa.example"', encoding="utf-8")
    assert {h.patron for h in barrer(tmp_path)} == {"dominio_interno", "correo_interno"}


def test_detecta_nombre_de_cliente(tmp_path):
    (tmp_path / "a.md").write_text("el tablero de ClienteFicticio", encoding="utf-8")
    assert [h.patron for h in barrer(tmp_path)] == ["cliente"]


def test_detecta_ruta_personal(tmp_path):
    (tmp_path / "a.ps1").write_text("C:\\Users\\AB1234567\\Desktop", encoding="utf-8")
    assert [h.patron for h in barrer(tmp_path)] == ["ruta_personal"]


def test_repo_limpio_no_da_hallazgos(tmp_path):
    (tmp_path / "a.md").write_text("instala el plugin y ejecuta /ecosistema", encoding="utf-8")
    assert barrer(tmp_path) == []


# --- los casos que costó encontrar -------------------------------------------

def test_detecta_un_correo_en_un_fichero_utf16(tmp_path):
    (tmp_path / "test.ps1").write_text("$email = 'alguien@miempresa.example'\n", encoding="utf-16")
    hallazgos = [h for h in barrer(tmp_path) if h.patron == "correo_interno"]
    assert hallazgos, "tiene que detectar un correo en un fichero UTF-16"
    assert any("alguien@miempresa.example" in h.texto for h in hallazgos)


def test_detecta_un_correo_en_un_fichero_utf8_sig(tmp_path):
    datos = "# coding: utf-8\nMAIL = 'soporte@miempresa.example'\n"
    (tmp_path / "config.py").write_bytes(b"\xef\xbb\xbf" + datos.encode("utf-8"))
    assert [h for h in barrer(tmp_path) if h.patron == "correo_interno"]


@pytest.mark.parametrize("contenido", [
    "cliente_clienteficticio = 1",
    "CLIENTEFICTICIO_API_KEY = 'x'",
    "from clienteficticio_webhook import hook",
    "version = 'ClienteFicticio2024'",
    "otrocliente_automation()",
])
def test_detecta_un_nombre_de_cliente_dentro_de_un_identificador(tmp_path, contenido):
    """Un nombre de cliente pegado a un identificador sigue siendo el nombre del
    cliente. Sin esto, una constante tipo `<CLIENTE>_API_KEY` pasaba el barrido.

    Y no, aquí no va el nombre del cliente de verdad para ilustrarlo: eso es justo lo
    que el barrido acaba de cazarme al escribir esta prueba, con la lista blanca vacía.
    """
    (tmp_path / "a.py").write_text(contenido, encoding="utf-8")
    assert [h for h in barrer(tmp_path) if h.patron == "cliente"], contenido


def test_detecta_un_correo_corporativo_con_subdominio(tmp_path):
    (tmp_path / "config.py").write_text("MAIL = 'admin@correo.miempresa.example'",
                                        encoding="utf-8")
    hallazgos = [h for h in barrer(tmp_path) if h.patron == "correo_interno"]
    assert any("admin@correo.miempresa.example" in h.texto for h in hallazgos)


def test_no_detecta_correos_de_dominio_externo(tmp_path):
    """Los falsos positivos son caros: obligan a ampliar la lista blanca, que es por
    donde se cuelan las fugas de verdad."""
    (tmp_path / "config.py").write_text('CUSTOMER_MAIL = "ana@cliente.invalido"',
                                        encoding="utf-8")
    assert [h for h in barrer(tmp_path) if h.patron == "correo_interno"] == []


# --- la lista blanca ---------------------------------------------------------

def test_la_lista_blanca_excluye_un_fichero(tmp_path):
    (tmp_path / "a.md").write_text("gitlab.miempresa.example", encoding="utf-8")
    assert barrer(tmp_path), "sin lista blanca tiene que encontrarlo"

    (tmp_path / ".limpieza-permitido").write_text("a.md", encoding="utf-8")
    assert barrer(tmp_path, permitidos=leer_permitidos(tmp_path)) == []


def test_la_lista_blanca_ignora_comentarios_y_lineas_vacias(tmp_path):
    (tmp_path / "config.py").write_text("MAIL = 'admin@miempresa.example'", encoding="utf-8")
    (tmp_path / ".limpieza-permitido").write_text(
        "# Comentario de cabecera\n\nconfig.py\n\n# Otro comentario\n\n", encoding="utf-8")
    permitidos = leer_permitidos(tmp_path)
    assert "config.py" in permitidos
    assert barrer(tmp_path, permitidos=permitidos) == []


def test_sin_fichero_de_lista_blanca_no_falla(tmp_path):
    assert leer_permitidos(tmp_path) == set()
    (tmp_path / "a.md").write_text("instala el plugin", encoding="utf-8")
    assert barrer(tmp_path, permitidos=set()) == []


# --- los patrones viven fuera del repositorio --------------------------------

def test_el_fichero_de_patrones_no_esta_rastreado_por_git(raiz):
    """La prueba que impide repetir el fallo: los patrones nombran dominios, clientes y
    rutas reales, así que el fichero que los contiene no puede estar en el repositorio.
    """
    r = subprocess.run(["git", "ls-files", FICHERO_PATRONES],
                       cwd=raiz, capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip("git no disponible")
    assert r.stdout.strip() == "", \
        f"{FICHERO_PATRONES} está rastreado por git: sus patrones se publicarían"


def test_el_ejemplo_de_patrones_si_se_publica_y_no_trae_nada_real(raiz):
    ejemplo = raiz / ".limpieza-patrones.example.json"
    assert ejemplo.is_file(), "sin el ejemplo, nadie sabe qué fichero tiene que crear"
    crudos = json.loads(ejemplo.read_text(encoding="utf-8"))
    patrones = {k: v for k, v in crudos.items() if not k.startswith("_")}
    assert patrones, "el ejemplo tiene que traer patrones de muestra"
    # Compilan todos: un ejemplo que no compila manda a la gente a depurar regex.
    for nombre, expresion in patrones.items():
        import re
        re.compile(expresion)


def test_sin_patrones_el_cli_sale_2_y_no_certifica_nada(raiz, tmp_path):
    """La mitad que importa de este arreglo. Un barrido sin patrones contestaría
    «0 hallazgos» y daría por limpio un repositorio que nadie ha mirado."""
    r = subprocess.run([sys.executable, str(raiz / "herramientas/limpieza.py"), str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 2, r.stdout + r.stderr
    assert FICHERO_PATRONES in (r.stdout + r.stderr)
    assert "0 hallazgo" not in r.stdout


def test_un_patron_que_no_compila_se_rechaza(tmp_path):
    (tmp_path / FICHERO_PATRONES).write_text(json.dumps({"roto": "([a-z"}), encoding="utf-8")
    with pytest.raises(ValueError, match="no compila"):
        cargar_patrones(tmp_path)


def test_un_fichero_de_patrones_vacio_se_rechaza(tmp_path):
    (tmp_path / FICHERO_PATRONES).write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError):
        cargar_patrones(tmp_path)


# --- el CLI ------------------------------------------------------------------

def test_el_cli_sale_1_si_encuentra_algo(tmp_path, raiz):
    (tmp_path / FICHERO_PATRONES).write_text(json.dumps(
        {"dominio_interno": r"\bmiempresa\.example\b"}), encoding="utf-8")
    (tmp_path / "a.md").write_text("miempresa.example", encoding="utf-8")
    r = subprocess.run([sys.executable, str(raiz / "herramientas/limpieza.py"), str(tmp_path)],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 1
    assert "dominio_interno" in r.stdout


def test_el_cli_sale_0_sobre_el_repo_real(raiz):
    """Sólo significa algo con los patrones reales delante: en un clon recién hecho no
    existen todavía, y entonces esta comprobación no aplica."""
    if not (raiz / FICHERO_PATRONES).is_file():
        pytest.skip(f"no hay {FICHERO_PATRONES} en este clon")
    r = subprocess.run([sys.executable, str(raiz / "herramientas/limpieza.py")],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, f"el repo tiene hallazgos:\n{r.stdout}"
