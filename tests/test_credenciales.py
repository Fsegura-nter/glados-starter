import importlib.util, os, subprocess, sys

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

def test_una_clave_no_mapeada_se_marca_como_huerfana(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    c = cargar(raiz, "credentials")
    c.set("servicio.inventado", "valor-cualquiera")
    assert "servicio.inventado" in c.huerfanas()

def test_una_clave_por_proyecto_no_es_huerfana(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    c = cargar(raiz, "credentials")
    c.set("gitlab.tokens.grupo/repo", "valor-cualquiera")
    assert "gitlab.tokens.grupo/repo" not in c.huerfanas()

def test_el_cli_list_nombra_las_huerfanas(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    ruta = raiz / "nucleo/.glados" / "credentials.py"
    env = {**os.environ, "LOCALAPPDATA": str(tmp_path)}
    subprocess.run([sys.executable, str(ruta), "set", "servicio.inventado", "valor-secretisimo-999"],
                   env=env, check=True, capture_output=True, text=True)
    resultado = subprocess.run([sys.executable, str(ruta), "list"],
                                env=env, capture_output=True, text=True)
    assert "servicio.inventado" in resultado.stdout
    assert "valor-secretisimo-999" not in resultado.stdout

def test_vocabulario_vacio_no_rompe(raiz, tmp_path, monkeypatch):
    cfg = cargar(raiz, "config")
    settings = tmp_path / "settings.json"
    settings.write_text('{"vocabulario": {}}', encoding="utf-8")
    monkeypatch.setattr(cfg, "SETTINGS_PATH", settings)
    assert cfg.vocabulario() == {}
