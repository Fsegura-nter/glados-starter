import json, py_compile, subprocess, sys
import pytest

HOOKS = ["session_start", "precompact_snapshot", "commit_vault",
         "respaldo_drive", "context_injector"]


@pytest.fixture
def respaldo_configurado(raiz, tmp_path):
    """Apunta `respaldo_path` a una carpeta dentro de `tmp_path`, usando la propia
    interfaz de configuracion del script (`.glados/settings.json`), para que
    `respaldo_drive.py` nunca llegue a la autodeteccion de un disco de sincronizacion
    real mientras corren las pruebas. `config.py` resuelve `settings.json` a partir de
    la ubicacion del propio fichero (`nucleo/.glados/`), no del cwd del subproceso, asi
    que hay que escribirlo ahi — es el unico sitio que el script de verdad lee.
    Restaura el fichero a su estado anterior al terminar.
    """
    settings_path = raiz / "nucleo" / ".glados" / "settings.json"
    previo = settings_path.read_text(encoding="utf-8") if settings_path.exists() else None
    destino = tmp_path / "respaldo"
    settings_path.write_text(json.dumps({"respaldo_path": str(destino)}), encoding="utf-8")
    try:
        yield destino
    finally:
        if previo is None:
            settings_path.unlink(missing_ok=True)
        else:
            settings_path.write_text(previo, encoding="utf-8")


@pytest.mark.parametrize("nombre", HOOKS)
def test_el_hook_compila(raiz, nombre):
    py_compile.compile(str(raiz / "nucleo/.glados" / f"{nombre}.py"), doraise=True)

@pytest.mark.parametrize("nombre", HOOKS)
def test_el_hook_sobrevive_a_stdin_vacio(raiz, nombre, tmp_path, respaldo_configurado):
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados" / f"{nombre}.py")],
                       input="{}", capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert r.returncode == 0, r.stderr

def test_el_respaldo_no_escribe_fuera_del_destino_configurado(raiz, tmp_path, respaldo_configurado):
    destino = respaldo_configurado
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/respaldo_drive.py")],
                       input="{}", capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert r.returncode == 0, r.stderr
    zips = list(destino.glob("vault-*.zip"))
    assert len(zips) == 1, f"esperaba exactamente un zip en {destino}, encontrado: {zips}"

def test_los_comandos_de_hook_no_llevan_comillas_ni_ampersand(raiz):
    texto = (raiz / "nucleo/.claude/settings.json.tmpl").read_text(encoding="utf-8")
    for h in json.loads(texto)["hooks"].values():
        for entrada in h:
            for orden in entrada["hooks"]:
                cmd = orden["command"]
                assert "'" not in cmd, f"comillas en: {cmd}"
                assert "&" not in cmd, f"ampersand en: {cmd}"

def test_la_plantilla_usa_marcadores_y_no_rutas_reales(raiz):
    texto = (raiz / "nucleo/.claude/settings.json.tmpl").read_text(encoding="utf-8")
    assert "{{PYTHON}}" in texto and "{{VAULT}}" in texto
    assert "C:\\Users" not in texto
