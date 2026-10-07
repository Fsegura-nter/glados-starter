import os, subprocess, sys, json, importlib.util


def cargar(raiz):
    ruta = raiz / "nucleo/.glados/doctor.py"
    spec = importlib.util.spec_from_file_location("doctor", ruta)
    m = importlib.util.module_from_spec(spec); sys.modules["doctor"] = m
    spec.loader.exec_module(m); return m


def vault_sano(raiz, tmp_path):
    """Lanza `bootstrap.ps1` con `-SinDependencias` (si no, cada prueba descarga
    torch, dos o tres gigabytes) y con `LOCALAPPDATA` redirigido a una HERMANA de
    `tmp_path` (`_lad`), nunca a `tmp_path` directamente: el directorio de datos que
    crea el script es `LOCALAPPDATA\\boveda`, el mismo nombre que la carpeta del vault
    bajo `tmp_path`, y si coincidieran el venv acabaría dentro de la bóveda. Mismo
    patrón que `ps()` en `tests/test_bootstrap.py`.
    """
    lad = tmp_path / "_lad"
    lad.mkdir(exist_ok=True)
    env = {**os.environ, "LOCALAPPDATA": str(lad)}
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                    str(raiz / "bootstrap.ps1"), "-Vault", str(tmp_path / "boveda"),
                    "-Nombre", "boveda", "-SinDependencias"],
                   capture_output=True, text=True, encoding="utf-8", env=env, timeout=900)
    return tmp_path / "boveda"


def test_un_vault_recien_generado_pasa(raiz, tmp_path):
    d = cargar(raiz)
    v = vault_sano(raiz, tmp_path)
    # Movido aquí desde la Tarea 6: `doctor.py` todavía no existía cuando se escribió
    # esa prueba de bootstrap, así que la comprobación de que se copia a toda bóveda
    # nueva queda pendiente hasta ahora.
    assert (v / ".glados/doctor.py").exists()
    estados = {c.estado for c in d.diagnosticar(v)}
    assert "fallo" not in estados


def test_detecta_un_remoto_git_anadido_despues(raiz, tmp_path):
    d = cargar(raiz); v = vault_sano(raiz, tmp_path)
    subprocess.run(["git", "remote", "add", "origin",
                    "https://github.com/alguien/privado.git"], cwd=v, capture_output=True)
    fallos = [c for c in d.diagnosticar(v) if c.estado == "fallo"]
    assert any("remoto" in c.nombre.lower() for c in fallos)


def test_detecta_una_nota_de_mas_de_250kb(raiz, tmp_path):
    d = cargar(raiz); v = vault_sano(raiz, tmp_path)
    (v / "gorda.md").write_text("a" * 300_000, encoding="utf-8")
    assert any(c.estado == "fallo" and "250" in c.detalle for c in d.diagnosticar(v))


def test_detecta_un_hook_que_no_compila(raiz, tmp_path):
    d = cargar(raiz); v = vault_sano(raiz, tmp_path)
    (v / ".glados/session_start.py").write_text("def roto(:", encoding="utf-8")
    assert any(c.estado == "fallo" and "hook" in c.nombre.lower()
               for c in d.diagnosticar(v))


def test_nunca_imprime_el_valor_de_una_credencial(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    v = vault_sano(raiz, tmp_path)
    almacen = tmp_path / "boveda/secrets.json"
    almacen.parent.mkdir(parents=True, exist_ok=True)
    almacen.write_text(json.dumps({"google.client_secret": "secretisimo-999"}), encoding="utf-8")
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/doctor.py"),
                        "--vault", str(v)], capture_output=True, text=True, timeout=300)
    assert "secretisimo-999" not in r.stdout + r.stderr


def test_el_cli_sale_1_cuando_hay_un_fallo(raiz, tmp_path):
    v = vault_sano(raiz, tmp_path)
    (v / "gorda.md").write_text("a" * 300_000, encoding="utf-8")
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/doctor.py"),
                        "--vault", str(v)], capture_output=True, text=True, timeout=300)
    assert r.returncode == 1


def test_avisa_si_la_boveda_no_es_un_repositorio_git(raiz, tmp_path):
    """Fix round 1, hallazgo 1: `git remote -v` también sale vacío por `stdout` en una
    carpeta que nunca tuvo `git init` (sale por `stderr` con código 128), y antes del
    arreglo eso se leía como "sin remoto, ok" -- el peor falso positivo posible, porque
    este chequeo es la única barrera entre datos de cliente y un host público.
    """
    d = cargar(raiz)
    v = tmp_path / "no_es_un_repositorio"
    v.mkdir()
    chequeos = {c.nombre: c for c in d.diagnosticar(v)}
    assert chequeos["remoto git"].estado == "fallo"

    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/doctor.py"),
                        "--vault", str(v)], capture_output=True, text=True, timeout=60)
    assert r.returncode == 1


def test_la_boveda_sana_sigue_dando_ok_en_remoto_git(raiz, tmp_path):
    """Compañera de la prueba anterior: el arreglo no puede sobrecorregir y gritar
    lobo en el caso normal (una bóveda recién creada por bootstrap.ps1, que SÍ es un
    repositorio git y SÍ está sin remoto)."""
    d = cargar(raiz)
    v = vault_sano(raiz, tmp_path)
    chequeos = {c.nombre: c for c in d.diagnosticar(v)}
    assert chequeos["remoto git"].estado == "ok"


def test_un_settings_json_que_no_es_un_objeto_se_explica_en_castellano(raiz, tmp_path):
    """Fix round 1, hallazgo 2: `settings.json` como una lista en vez de un objeto
    hacía que `datos.get("hooks")` lanzara `AttributeError` sin capturar, y ese texto
    de excepción en inglés llegaba tal cual al detalle del chequeo. Este kit no tiene
    soporte: ese mensaje es lo único que alguien va a leer, y tiene que decir qué
    arreglar, en castellano.
    """
    d = cargar(raiz)
    v = vault_sano(raiz, tmp_path)
    (v / ".claude" / "settings.json").write_text("[]", encoding="utf-8")

    chequeos = {c.nombre: c for c in d.diagnosticar(v)}
    hooks = chequeos["hooks"]
    assert hooks.estado == "fallo"
    detalle_bajo = hooks.detalle.lower()
    assert "object has no attribute" not in detalle_bajo
    assert "attribute" not in detalle_bajo
    assert "traceback" not in detalle_bajo
    assert "objeto" in detalle_bajo
