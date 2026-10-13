"""El instalador de modulos: que cada fichero aterrice donde se descubre.

Estas pruebas existen por un fallo real del 2026-10-07: cuatro de los cinco modulos
declaraban sus comandos, su skill y sus agentes con destino `.glados`, y once ficheros
se habrian copiado al disco de un compañero sin que la plataforma los viera. Nada se
quejaba. Las pruebas de entonces solo comprobaban que el fichero existiera en el repo.
"""
import importlib.util, json, sys

import pytest


@pytest.fixture
def im(raiz):
    spec = importlib.util.spec_from_file_location(
        "im", raiz / "herramientas/instalar_modulos.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["im"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_los_comandos_skills_y_agentes_aterrizan_bajo_claude(im, tmp_path):
    """El caso que motivo todo: `gitlab` trae una skill y dos agentes, y `google` dos
    comandos. Los cinco ficheros tienen que acabar bajo `.claude`, no bajo `.glados`."""
    im.instalar(tmp_path, ["gitlab", "google"])

    assert (tmp_path / ".claude/skills/mr/SKILL.md").is_file()
    assert (tmp_path / ".claude/agents/mr-back-reviewer.md").is_file()
    assert (tmp_path / ".claude/agents/mr-front-reviewer.md").is_file()
    assert (tmp_path / ".claude/commands/responde.md").is_file()
    assert (tmp_path / ".claude/commands/correos.md").is_file()

    # Y los scripts siguen yendo a `.glados`, que es su sitio.
    assert (tmp_path / ".glados/git_credential.py").is_file()
    assert (tmp_path / ".glados/gmail_api.py").is_file()

    # Nada queda colgando en la ruta vieja, que es donde no lo descubre nadie.
    assert not (tmp_path / ".glados/agents").exists()
    assert not (tmp_path / ".glados/commands").exists()
    assert not (tmp_path / ".glados/skills").exists()


def test_todos_los_modulos_del_repo_se_instalan_donde_se_descubren(im, tmp_path):
    """Guarda generica, no el par concreto: recorre los modulos que haya."""
    nombres = im.modulos_disponibles()
    assert nombres, "el repo no declara ningun modulo"
    im.instalar(tmp_path, nombres)

    for prefijo, esperado in im.DESCUBRIMIENTO.items():
        for nombre in nombres:
            manifiesto = im.leer_manifiesto(nombre)
            for fichero in manifiesto["ficheros"]:
                if fichero.split("/")[0] != prefijo:
                    continue
                assert (tmp_path / esperado / fichero.split("/", 1)[1]).is_file(), \
                    (nombre, fichero, esperado)


def test_nunca_pisa_un_fichero_que_el_usuario_ya_toco(im, tmp_path):
    im.instalar(tmp_path, ["google"])
    comando = tmp_path / ".claude/commands/responde.md"
    comando.write_text("lo he cambiado yo", encoding="utf-8")

    informe = im.instalar(tmp_path, ["google"])

    assert comando.read_text(encoding="utf-8") == "lo he cambiado yo"
    previos = [c for c in informe["modulos"][0]["copias"] if c["ya_existia"]]
    assert any(c["relativa"].endswith("responde.md") for c in previos)


def test_una_segunda_pasada_completa_lo_que_falte(im, tmp_path):
    im.instalar(tmp_path, ["google"])
    (tmp_path / ".claude/commands/correos.md").unlink()

    im.instalar(tmp_path, ["google"])

    assert (tmp_path / ".claude/commands/correos.md").is_file()


def test_un_modulo_desconocido_no_escribe_nada(im, tmp_path):
    with pytest.raises(ValueError, match="desconocido"):
        im.instalar(tmp_path, ["google", "no-existe-este-modulo"])
    # Validar va antes de copiar: el modulo bueno de la lista tampoco se instala.
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".glados").exists()


def test_un_destino_que_se_escapa_de_la_boveda_se_rechaza(im, tmp_path, monkeypatch):
    """El manifiesto es dato, no codigo de confianza: en un repositorio publico
    cualquiera puede proponer un `..` por un pull request.

    El vector real es `destino`, no `ficheros`: una entrada de `ficheros` con `..`
    tiene que apuntar ademas a un fichero que exista dentro de la carpeta del modulo,
    y esa comprobacion va primero. El destino, en cambio, es texto libre.
    """
    falso = {
        "nombre": "decisiones",
        "descripcion": "x",
        "ficheros": ["decisiones_pendientes.py"],
        "destino": "../../fuera",
        "prueba_de_vida": "",
        "requiere": [],
    }
    monkeypatch.setattr(im, "leer_manifiesto", lambda nombre: falso)
    with pytest.raises(ValueError, match="fuera de la boveda"):
        im.instalar(tmp_path, ["decisiones"])
    assert not (tmp_path.parent.parent / "fuera").exists()


def test_un_fichero_que_no_existe_para_la_instalacion_antes_de_copiar(im, tmp_path, monkeypatch):
    """La otra mitad de la defensa: un `..` en `ficheros` no llega ni a calcular
    destino, porque antes hay que demostrar que el origen existe."""
    falso = {
        "nombre": "decisiones",
        "descripcion": "x",
        "ficheros": ["../../../../fuera.md"],
        "destino": ".glados",
        "prueba_de_vida": "",
        "requiere": [],
    }
    monkeypatch.setattr(im, "leer_manifiesto", lambda nombre: falso)
    with pytest.raises(ValueError, match="no existe"):
        im.instalar(tmp_path, ["decisiones"])
    assert not (tmp_path / ".glados").exists()


def test_un_fichero_descubrible_con_destino_equivocado_para_la_instalacion(im, tmp_path):
    """La regresion exacta del 2026-10-07: un comando con destino `.glados`. Antes se
    copiaba en silencio; ahora la instalacion se para y dice donde deberia ir."""
    falso = {
        "nombre": "mal-configurado",
        "descripcion": "x",
        "ficheros": ["commands/algo.md"],
        "destino": ".glados",
        "prueba_de_vida": "",
        "requiere": [],
    }
    carpeta = im.MODULOS_DIR / "mal-configurado"
    (carpeta / "commands").mkdir(parents=True)
    (carpeta / "commands/algo.md").write_text("x", encoding="utf-8")
    try:
        im.leer_manifiesto = lambda nombre: falso
        with pytest.raises(ValueError, match="solo descubre en"):
            im.instalar(tmp_path, ["mal-configurado"])
        assert not (tmp_path / ".glados").exists()
    finally:
        import shutil
        shutil.rmtree(carpeta)


def test_dry_run_no_escribe_nada(im, tmp_path):
    informe = im.instalar(tmp_path, ["google"], dry_run=True)
    assert informe["dry_run"] is True
    assert informe["modulos"][0]["copias"]
    assert not (tmp_path / ".claude").exists()
    assert not (tmp_path / ".glados").exists()


def test_el_informe_trae_la_prueba_de_vida_y_las_credenciales(im, tmp_path):
    informe = im.instalar(tmp_path, ["google"], dry_run=True)
    modulo = informe["modulos"][0]
    assert modulo["prueba_de_vida"]
    assert "google.client_id" in modulo["requiere"]


def test_el_cli_devuelve_json_valido(im, raiz, tmp_path):
    import subprocess
    r = subprocess.run([sys.executable, str(raiz / "herramientas/instalar_modulos.py"),
                        "--vault", str(tmp_path), "--modulos", "decisiones",
                        "--dry-run", "--json"],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 0, r.stderr
    informe = json.loads(r.stdout)
    assert informe["modulos"][0]["nombre"] == "decisiones"


def test_el_cli_falla_con_una_boveda_que_no_existe(im, raiz, tmp_path):
    import subprocess
    r = subprocess.run([sys.executable, str(raiz / "herramientas/instalar_modulos.py"),
                        "--vault", str(tmp_path / "no-existe"),
                        "--modulos", "google"],
                       capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert r.returncode == 1
    assert "no existe" in (r.stdout + r.stderr).lower()
