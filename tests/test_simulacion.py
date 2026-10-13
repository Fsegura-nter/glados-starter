"""Pruebas de la skill `/ecosistema` y de su modo simulado.

Las rutas son `skills/ecosistema/...`, en plural, no `skill/` como dice el plan: un
plugin de Claude Code descubre sus skills en `skills/<nombre>/SKILL.md`. Con el nombre
en singular el entregable entero seria inerte.
"""
import importlib.util, json, os, subprocess, sys

SKILL = "skills/ecosistema"
SIM = f"{SKILL}/referencias/simulacion"


def _cargar_generador(raiz):
    spec = importlib.util.spec_from_file_location(
        "gv", raiz / "nucleo/.glados/generar_vault.py")
    gv = importlib.util.module_from_spec(spec)
    sys.modules["gv"] = gv
    spec.loader.exec_module(gv)
    return gv


def _plan(raiz):
    return json.loads((raiz / SIM / "plan-esperado.json").read_text(encoding="utf-8"))


def test_la_persona_simulada_produce_un_plan_valido(raiz, tmp_path):
    gv = _cargar_generador(raiz)
    creados = gv.generar(_plan(raiz), tmp_path)
    assert creados
    assert (tmp_path / "CLAUDE.md").exists()


def test_el_barrido_simulado_no_sale_a_la_red(raiz, tmp_path):
    """Entorno desnudo a proposito: sin PATH no hay `git` ni nada que invocar, asi que
    si el barrido pasara por la red o por un subproceso, aqui se caeria."""
    salida = tmp_path / "m.json"
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/arranque_lectura.py"),
                        "--fuente", str(raiz / SIM / "fuente.json"),
                        "--salida", str(salida)],
                       capture_output=True, text=True, timeout=120,
                       env={"PATH": "", "SYSTEMROOT": "C:\Windows"})
    assert r.returncode == 0, r.stderr
    metricas = json.loads(salida.read_text(encoding="utf-8"))
    assert metricas["correo"]["personas"] > 0
    # La persona simulada tiene dos series de calendario: de ahi salen sus areas.
    assert len(metricas["calendario"]["series"]) >= 2


def test_la_skill_declara_las_cinco_fases_y_sus_pruebas_de_vida(raiz):
    texto = (raiz / SKILL / "SKILL.md").read_text(encoding="utf-8")
    for fase in ["Entrevista", "Lectura", "Propuesta", "Generación", "Verificación"]:
        assert fase in texto, fase
    assert "prueba de vida" in texto.lower()


def test_la_guia_de_google_no_pide_pegar_el_secreto_en_un_comando(raiz):
    texto = (raiz / SKILL / "referencias/google-cloud.md").read_text(encoding="utf-8")
    assert "credentials.py set" not in texto
    assert "fichero" in texto.lower()


def test_hay_seis_arquetipos_con_muestra(raiz):
    texto = (raiz / SKILL / "referencias/arquetipos.md").read_text(encoding="utf-8")
    assert texto.count("## ") >= 6
    assert texto.count("**Muestra:**") >= 6


def test_un_servicio_de_google_capado_degrada_solo_ese(raiz, tmp_path):
    """Drive deshabilitado por IT; Gmail y Calendar bien. El modulo sigue, cojo y con
    rastro: en el CLAUDE.md para que el asistente lo sepa, y en estado_modulos.json
    para que el doctor lo vea."""
    gv = _cargar_generador(raiz)
    plan = _plan(raiz)
    plan["modulos"] = ["google"]
    plan["estado_modulos"] = {
        "google": {"gmail": "ok", "calendar": "ok", "drive": "fallo"}
    }
    plan["pendientes_manuales"] = ["google/drive: la API de Drive no responde (403). "
                                   "Gmail y Calendar si. Sin busqueda en Drive."]
    gv.generar(plan, tmp_path)
    claude_md = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "Drive no responde" in claude_md
    estado = json.loads((tmp_path / ".glados/estado_modulos.json").read_text(encoding="utf-8"))
    assert estado["google"]["gmail"] == "ok"
    assert estado["google"]["drive"] == "fallo"


def test_una_pasada_simulada_entera_deja_el_doctor_sin_fallos(raiz, tmp_path):
    """Las cinco fases mecanicas de punta a punta, sin tocar una sola cuenta real:
    bootstrap, barrido por `--fuente`, generacion del plan y diagnostico.

    Esto es el Paso 5 de la tarea convertido en prueba. Un «tres pasadas limpias»
    comprobado a mano no lo vuelve a comprobar nadie; esto si.
    """
    lad = tmp_path / "_lad"
    lad.mkdir(exist_ok=True)
    vault = tmp_path / "boveda"
    env = {**os.environ, "LOCALAPPDATA": str(lad)}

    # Fase mecanica. `-SinDependencias` o cada pasada se descarga torch.
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                        str(raiz / "bootstrap.ps1"), "-Vault", str(vault),
                        "-Nombre", "boveda", "-SinDependencias"],
                       capture_output=True, text=True, encoding="utf-8",
                       env=env, timeout=900)
    assert r.returncode == 0, r.stdout + r.stderr

    # Fase 2: lectura desde el paquete simulado.
    metricas = tmp_path / "metricas.json"
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/arranque_lectura.py"),
                        "--fuente", str(raiz / SIM / "fuente.json"),
                        "--salida", str(metricas)],
                       capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stderr

    # Fase 4: generacion. El plan de la persona simulada, tal cual se entrega.
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/generar_vault.py"),
                        str(raiz / SIM / "plan-esperado.json"), "--raiz", str(vault)],
                       capture_output=True, text=True, timeout=300, env=env)
    assert r.returncode == 0, r.stdout + r.stderr

    # Fase 5: el doctor. Avisos si, fallos no.
    d = importlib.util.spec_from_file_location("doc", raiz / "nucleo/.glados/doctor.py")
    doc = importlib.util.module_from_spec(d)
    sys.modules["doc"] = doc
    d.loader.exec_module(doc)
    chequeos = doc.diagnosticar(vault)
    fallos = [(c.nombre, c.detalle) for c in chequeos if c.estado == "fallo"]
    assert not fallos, fallos
