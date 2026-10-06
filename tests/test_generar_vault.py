import json, subprocess, sys, pytest, importlib.util

def cargar(raiz):
    ruta = raiz / "nucleo/.glados/generar_vault.py"
    spec = importlib.util.spec_from_file_location("generar_vault", ruta)
    m = importlib.util.module_from_spec(spec); sys.modules["generar_vault"] = m
    spec.loader.exec_module(m); return m

def plan_minimo(**extra):
    base = {"vault": {"nombre": "boveda", "idioma": "es"},
            "asistente": {"nombre": "Nombre", "arquetipo": "clinico"},
            "areas": ["interno"], "carpetas": [{"ruta": "00_CORE", "descripcion": "nucleo"}],
            "modulos": [], "notas": [], "pendientes_manuales": []}
    base.update(extra); return base

def test_crea_las_carpetas_del_plan(raiz, tmp_path):
    g = cargar(raiz)
    g.generar(plan_minimo(), tmp_path)
    assert (tmp_path / "00_CORE").is_dir()

def test_escribe_claude_md_y_output_style(raiz, tmp_path):
    g = cargar(raiz)
    g.generar(plan_minimo(), tmp_path)
    assert "Nombre" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert (tmp_path / ".claude/output-styles").is_dir()

def test_rechaza_una_ruta_que_escapa_del_vault(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(carpetas=[{"ruta": "../../Windows", "descripcion": "no"}])
    with pytest.raises(ValueError, match="fuera del vault"):
        g.generar(plan, tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_rechaza_una_ruta_absoluta(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(carpetas=[{"ruta": "C:\\Windows", "descripcion": "no"}])
    with pytest.raises(ValueError, match="fuera del vault"):
        g.generar(plan, tmp_path)

def test_rechaza_una_nota_de_mas_de_250kb(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(notas=[{"ruta": "00_CORE/x.md", "frontmatter": {}, "cuerpo": "a" * 300_000}])
    with pytest.raises(ValueError, match="250"):
        g.generar(plan, tmp_path)

def test_los_modulos_saltados_quedan_escritos_en_claude_md(raiz, tmp_path):
    g = cargar(raiz)
    g.generar(plan_minimo(pendientes_manuales=["google: Drive capado por IT"]), tmp_path)
    assert "Drive capado por IT" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")

def test_no_escribe_nada_si_el_plan_falla_a_medias(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(carpetas=[{"ruta": "00_CORE", "descripcion": "ok"},
                                 {"ruta": "../fuera", "descripcion": "no"}])
    with pytest.raises(ValueError):
        g.generar(plan, tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_relanzarlo_con_el_mismo_plan_no_duplica_ni_pisa(raiz, tmp_path):
    g = cargar(raiz)
    g.generar(plan_minimo(), tmp_path)
    (tmp_path / "00_CORE/mia.md").write_text("mia", encoding="utf-8")
    g.generar(plan_minimo(), tmp_path)
    assert (tmp_path / "00_CORE/mia.md").read_text(encoding="utf-8") == "mia"
