import subprocess, sys

def test_indexar_y_buscar_un_documento(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fuentes = tmp_path / "vault/05_FUENTES/Acme"; fuentes.mkdir(parents=True)
    (fuentes / "nota.md").write_text("el plazo de renovacion es de treinta dias",
                                     encoding="utf-8")
    idx = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/index_docs.py"),
                          "--solo-lexico", "--vault", str(tmp_path / "vault")],
                         capture_output=True, text=True, timeout=120)
    assert idx.returncode == 0
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/lexical.py"),
                        "renovacion", "--vault", str(tmp_path / "vault")],
                       capture_output=True, text=True, timeout=60)
    assert "nota.md" in r.stdout

def test_buscar_sin_indice_avisa_en_vez_de_reventar(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/lexical.py"), "lo que sea",
                        "--vault", str(tmp_path / "vacio")],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0
    assert "indice" in r.stdout.lower()
