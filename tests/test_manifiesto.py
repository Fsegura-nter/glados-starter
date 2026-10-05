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
    texto = (raiz / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    assert not re.search(r'\w+@\w+', texto), "plugin.json contiene una dirección de correo"
    assert "nfqsolutions" not in texto
