import json

def test_el_manifiesto_declara_el_plugin(raiz):
    datos = json.loads((raiz / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    assert datos["name"] == "glados-starter"
    assert datos["capabilities"]["skills"] is True

def test_el_manifiesto_no_lleva_correo_ni_host_interno(raiz):
    texto = (raiz / ".claude-plugin/plugin.json").read_text(encoding="utf-8")
    assert "@" not in texto.split('"description"')[0]
    assert "nfqsolutions" not in texto
