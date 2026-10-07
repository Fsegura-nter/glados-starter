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

# --- fix round 1: atomicidad de la fase de escritura, acentos, fusion de estado,
# listas markdown multilinea ---

def test_un_byte_nulo_en_la_ruta_no_deja_nada(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(notas=[
        {"ruta": "00_CORE/buena.md", "frontmatter": {}, "cuerpo": "ok"},
        {"ruta": "00_CORE/mal\x00a.md", "frontmatter": {}, "cuerpo": "no"},
    ])
    with pytest.raises(ValueError):
        g.generar(plan, tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_una_carpeta_que_ya_es_fichero_no_deja_nada(raiz, tmp_path):
    g = cargar(raiz)
    plan = plan_minimo(notas=[
        {"ruta": "00_CORE/buena.md", "frontmatter": {}, "cuerpo": "ok"},
        {"ruta": "00_CORE/buena.md/otra.md", "frontmatter": {}, "cuerpo": "no"},
    ])
    with pytest.raises(ValueError):
        g.generar(plan, tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_deshace_un_fallo_de_escritura(raiz, tmp_path, monkeypatch):
    g = cargar(raiz)
    plan = plan_minimo(notas=[
        {"ruta": "00_CORE/una.md", "frontmatter": {}, "cuerpo": "contenido-1"},
        {"ruta": "00_CORE/otra.md", "frontmatter": {}, "cuerpo": "contenido-2"},
    ])
    original = g.Path.write_text
    llamadas = {"n": 0}

    def roto(self, *a, **kw):
        llamadas["n"] += 1
        if llamadas["n"] == 2:
            raise OSError("fallo forzado de escritura (prueba)")
        return original(self, *a, **kw)

    monkeypatch.setattr(g.Path, "write_text", roto)
    with pytest.raises(ValueError):
        g.generar(plan, tmp_path)
    assert list(tmp_path.iterdir()) == []

def test_estado_modulos_se_fusiona_al_anadir_un_modulo(raiz, tmp_path):
    # "google" y "decisiones" son módulos reales de modulos/ (Tarea 12): desde que esa
    # carpeta existe, _validar_plan comprueba los nombres contra ella, así que el test ya
    # no puede usar un módulo inventado como "otro". El servicio de "google" es "gmail"
    # (de modulos/google/gmail_api.py, vía _servicios_de_modulo); "decisiones" no declara
    # ningún `*_api.py`, así que su único servicio es su propio nombre.
    g = cargar(raiz)
    g.generar(plan_minimo(modulos=["google"]), tmp_path)
    ruta_estado = tmp_path / ".glados" / "estado_modulos.json"
    estado = json.loads(ruta_estado.read_text(encoding="utf-8"))
    assert estado["google"]["gmail"] == "sin_probar"

    estado["google"]["gmail"] = "ok"
    ruta_estado.write_text(json.dumps(estado), encoding="utf-8")

    g.generar(plan_minimo(modulos=["google", "decisiones"]), tmp_path)
    estado_final = json.loads(ruta_estado.read_text(encoding="utf-8"))
    assert estado_final["google"]["gmail"] == "ok"
    assert estado_final["decisiones"]["decisiones"] == "sin_probar"

def test_pendientes_manuales_con_salto_de_linea_mantiene_ambas_lineas(raiz, tmp_path):
    g = cargar(raiz)
    g.generar(plan_minimo(pendientes_manuales=["google: fallo\nver detalle en el log"]), tmp_path)
    contenido = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    assert "- google: fallo" in contenido
    assert "\n  ver detalle en el log" in contenido
