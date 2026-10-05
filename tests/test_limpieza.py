import subprocess, sys
from herramientas.limpieza import buscar

def test_detecta_dominio_interno(tmp_path):
    (tmp_path / "a.md").write_text("ver https://gitlab.nfqsolutions.es/x", encoding="utf-8")
    assert [h.patron for h in buscar(tmp_path)] == ["dominio_interno"]

def test_detecta_correo_corporativo(tmp_path):
    (tmp_path / "a.py").write_text('MAIL = "alguien@nter.es"', encoding="utf-8")
    assert [h.patron for h in buscar(tmp_path)] == ["correo"]

def test_detecta_nombre_de_cliente(tmp_path):
    (tmp_path / "a.md").write_text("el tablero de Treyit", encoding="utf-8")
    assert [h.patron for h in buscar(tmp_path)] == ["cliente"]

def test_detecta_ruta_personal(tmp_path):
    (tmp_path / "a.ps1").write_text("C:\\Users\\EM2025007530\\Desktop", encoding="utf-8")
    assert [h.patron for h in buscar(tmp_path)] == ["ruta_personal"]

def test_repo_limpio_no_da_hallazgos(tmp_path):
    (tmp_path / "a.md").write_text("instala el plugin y ejecuta /ecosistema", encoding="utf-8")
    assert buscar(tmp_path) == []

def test_ignora_su_propia_lista_de_patrones(raiz):
    hallazgos = [h for h in buscar(raiz) if "limpieza.py" not in str(h.fichero)]
    assert hallazgos == [], f"datos de NTER en el repo: {hallazgos}"

def test_cli_sale_con_1_si_encuentra_algo(tmp_path, raiz):
    (tmp_path / "a.md").write_text("nfqsolutions.es", encoding="utf-8")
    r = subprocess.run([sys.executable, str(raiz / "herramientas/limpieza.py"), str(tmp_path)],
                       capture_output=True, text=True)
    assert r.returncode == 1
    assert "dominio_interno" in r.stdout
