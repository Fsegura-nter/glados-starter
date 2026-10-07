import json, py_compile, pytest

MODULOS = ["google", "gitlab", "decisiones", "paneles", "statusline"]

@pytest.mark.parametrize("nombre", MODULOS)
def test_el_modulo_se_declara_entero(raiz, nombre):
    m = json.loads((raiz / "modulos" / nombre / "modulo.json").read_text(encoding="utf-8"))
    assert set(m) >= {"nombre", "descripcion", "ficheros", "destino", "prueba_de_vida", "requiere"}
    for f in m["ficheros"]:
        assert (raiz / "modulos" / nombre / f).exists(), f

@pytest.mark.parametrize("nombre", MODULOS)
def test_los_scripts_del_modulo_compilan(raiz, nombre):
    for f in (raiz / "modulos" / nombre).rglob("*.py"):
        py_compile.compile(str(f), doraise=True)

def test_ningun_modulo_envia_correo(raiz):
    for f in (raiz / "modulos").rglob("*.py"):
        texto = f.read_text(encoding="utf-8", errors="ignore")
        assert "messages/send" not in texto, f
        assert "drafts/send" not in texto, f

def test_el_modulo_gitlab_no_trae_el_host_de_nadie(raiz):
    for f in (raiz / "modulos/gitlab").rglob("*"):
        if f.is_file():
            assert "nfqsolutions" not in f.read_text(encoding="utf-8", errors="ignore")
