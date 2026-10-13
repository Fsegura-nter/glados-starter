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
                       input="{}", capture_output=True, text=True, encoding="utf-8",
                       cwd=tmp_path, timeout=30)
    assert r.returncode == 0, r.stderr

def test_el_respaldo_no_escribe_fuera_del_destino_configurado(raiz, tmp_path, respaldo_configurado):
    destino = respaldo_configurado
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/respaldo_drive.py")],
                       input="{}", capture_output=True, text=True, encoding="utf-8",
                       cwd=tmp_path, timeout=30)
    assert r.returncode == 0, r.stderr
    zips = list(destino.glob("*.zip"))
    assert len(zips) == 1, f"esperaba exactamente un zip en {destino}, encontrado: {zips}"


def test_el_respaldo_no_ve_ni_borra_el_de_otra_boveda(raiz, tmp_path, respaldo_configurado):
    """Dos bóvedas de la misma máquina pueden compartir la carpeta que sincroniza la
    nube. Con un patrón global —`vault-*.zip`, como estaba hasta el 2026-10-13— cada una
    veía los respaldos de la otra: el diagnóstico de una bóveda recién creada anunciaba
    un zip ajeno de hace una semana, y `podar()` podía borrar copias que no eran suyas.
    Esto fija lo contrario: el patrón lleva el nombre del ecosistema y cada bóveda solo
    se ve a sí misma.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "rd", raiz / "nucleo/.glados/respaldo_drive.py")
    rd = importlib.util.module_from_spec(spec)
    sys.modules["rd"] = rd
    spec.loader.exec_module(rd)

    destino = respaldo_configurado
    destino.mkdir(parents=True, exist_ok=True)
    # El fixture no fija `nombre`, así que esta bóveda usa el nombre por defecto.
    mio = f"{rd._slug_nombre()}-2026-10-13.zip"
    # Nombre hostil a propósito: empieza igual que el propio. Con el patrón anterior
    # (`<nombre>-*.zip`) este fichero casaba, y por eso la prueba fallaba de verdad.
    ajeno = f"{rd._slug_nombre()}-de-otra-persona-2026-10-05.zip"
    (destino / mio).write_bytes(b"PK\x05\x06" + b"\0" * 18)
    (destino / ajeno).write_bytes(b"PK\x05\x06" + b"\0" * 18)

    # `ultimo()` encuentra el propio, nunca el ajeno, aunque los dos estén ahí.
    assert rd.ultimo(destino).name == mio

    # `podar()` a cero copias se lleva el propio y deja el ajeno intacto.
    assert rd.podar(destino, 0) == 1
    assert not (destino / mio).exists()
    assert (destino / ajeno).exists(), "podar() borró el respaldo de otra bóveda"

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
