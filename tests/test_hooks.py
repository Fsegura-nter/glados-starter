import json, py_compile, subprocess, sys, pytest

HOOKS = ["session_start", "precompact_snapshot", "commit_vault",
         "respaldo_drive", "context_injector"]

@pytest.mark.parametrize("nombre", HOOKS)
def test_el_hook_compila(raiz, nombre):
    py_compile.compile(str(raiz / "nucleo/.glados" / f"{nombre}.py"), doraise=True)

@pytest.mark.parametrize("nombre", HOOKS)
def test_el_hook_sobrevive_a_stdin_vacio(raiz, nombre, tmp_path):
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados" / f"{nombre}.py")],
                       input="{}", capture_output=True, text=True, cwd=tmp_path, timeout=30)
    assert r.returncode == 0, r.stderr

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
