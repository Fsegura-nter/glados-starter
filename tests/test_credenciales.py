import importlib.util, sys

def cargar(raiz, nombre):
    ruta = raiz / "nucleo/.glados" / f"{nombre}.py"
    spec = importlib.util.spec_from_file_location(nombre, ruta)
    mod = importlib.util.module_from_spec(spec); sys.modules[nombre] = mod
    spec.loader.exec_module(mod)
    return mod

def test_listar_nunca_devuelve_el_valor_entero(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    c = cargar(raiz, "credentials")
    c.set("servicio.clave", "valor-secretisimo-123456")
    assert all("valor-secretisimo" not in v for _, v in c.listar())

def test_redactar_tapa_un_jwt(raiz):
    r = cargar(raiz, "redact")
    limpio, tipos = r.redactar("token eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.firma")
    assert "eyJhbGciOiJIUzI1NiJ9" not in limpio
    assert "JWT" in tipos

def test_el_almacen_vive_fuera_del_vault(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    c = cargar(raiz, "credentials")
    assert tmp_path in c.ruta_almacen().parents
