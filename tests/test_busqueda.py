import subprocess, sys

def test_indexar_y_buscar_un_documento(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fuentes = tmp_path / "vault/05_FUENTES/Acme"; fuentes.mkdir(parents=True)
    (fuentes / "nota.md").write_text("el plazo de renovacion es de treinta dias",
                                     encoding="utf-8")
    idx = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/index_docs.py"),
                          "--solo-lexico", "--vault", str(tmp_path / "vault")],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert idx.returncode == 0
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/lexical.py"),
                        "renovacion", "--vault", str(tmp_path / "vault")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert "nota.md" in r.stdout

def test_buscar_sin_indice_avisa_en_vez_de_reventar(raiz, tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/lexical.py"), "lo que sea",
                        "--vault", str(tmp_path / "vacio")],
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert r.returncode == 0
    assert "índice" in r.stdout.lower()

def test_indexa_un_fichero_con_tilde_en_el_nombre(raiz, tmp_path, monkeypatch):
    """Cubre el agujero real: un nombre de fichero o de carpeta con una mayúscula
    acentuada (`Índice general.md`) no debe tumbar la captura de stdout del proceso
    padre. Antes de la corrección, `index_docs.py` salía con returncode 0 pero
    `stdout` llegaba como `None` — un fallo silencioso peor que un crash, porque un
    llamador que solo mira el código de salida pasa de largo y revienta más tarde con
    un TypeError en el primer `"x" in r.stdout`. Por eso se comprueba `stdout is not
    None` explícitamente, además del contenido.
    """
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    fuentes = tmp_path / "vault/05_FUENTES/Acme"; fuentes.mkdir(parents=True)
    (fuentes / "Índice general.md").write_text(
        "información general revisada por José y María",
        encoding="utf-8")
    idx = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/index_docs.py"),
                          "--solo-lexico", "--vault", str(tmp_path / "vault")],
                         capture_output=True, text=True, encoding="utf-8", timeout=120)
    assert idx.stdout is not None
    assert idx.returncode == 0
    assert "Índice general.md" in idx.stdout
