import json
import re

def test_el_manifiesto_declara_el_plugin(raiz):
    datos = json.loads((raiz / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert datos["name"] == "glados-starter"
    assert isinstance(datos["version"], str) and datos["version"]
    assert isinstance(datos["description"], str) and datos["description"]

    allowed_keys = {"name", "description", "version", "author", "license", "homepage", "repository", "keywords"}
    assert set(datos.keys()) == allowed_keys, f"Unknown keys in manifest: {set(datos.keys()) - allowed_keys}"

def test_el_manifiesto_no_lleva_correo_ni_host_interno(raiz):
    """El manifiesto es lo primero que se lee de un plugin publicado, así que no lleva
    ni una dirección de correo ni un host que no sea el del propio repositorio.

    El host se comprueba por FORMA, no nombrando el dominio interno de nadie: una prueba
    que afirma la ausencia de algo nombrándolo lo publica, que es el fallo que tenía el
    propio barrido hasta el 2026-10-13.
    """
    texto = (raiz / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    assert not re.search(r"\w+@\w+", texto), "plugin.json contiene una dirección de correo"

    PERMITIDOS = {"github.com"}
    hosts = {h.lower() for h in re.findall(r"https?://([A-Za-z0-9.-]+)", texto)}
    assert hosts <= PERMITIDOS, f"plugin.json apunta a hosts inesperados: {hosts - PERMITIDOS}"
