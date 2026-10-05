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

def test_detecta_un_correo_en_un_fichero_utf16(tmp_path):
    # Fichero UTF-16 con correo corporativo — debe detectarse
    fichero = tmp_path / "test.ps1"
    fichero.write_text("$email = 'alguien@nter.es'\n", encoding="utf-16")
    hallazgos = [h for h in buscar(tmp_path) if h.patron == "correo"]
    assert len(hallazgos) > 0, "Debe detectar correo en fichero UTF-16"
    assert any("alguien@nter.es" in h.texto for h in hallazgos)

def test_detecta_un_correo_en_un_fichero_utf8_sig(tmp_path):
    # Fichero UTF-8 con BOM — debe detectarse
    fichero = tmp_path / "config.py"
    datos = "# coding: utf-8\nMAIL = 'soporte@nfqsolutions.es'\n"
    fichero.write_bytes(b'\xef\xbb\xbf' + datos.encode('utf-8'))
    hallazgos = [h for h in buscar(tmp_path) if h.patron == "correo"]
    assert len(hallazgos) > 0, "Debe detectar correo en fichero UTF-8-sig"

def test_detecta_un_nombre_de_cliente_dentro_de_un_identificador(tmp_path):
    # Los nombres de cliente dentro de identificadores deben detectarse
    casos = [
        ("cliente_treyit = 1", "cliente_treyit"),
        ("TREYIT_API_KEY = 'x'", "TREYIT_API_KEY"),
        ("from treyit_webhook import hook", "treyit_webhook"),
        ("version = 'Treyit2024'", "Treyit2024"),
        ("yiyit_automation()", "yiyit_automation"),
        ("SegurCaixa_portal.py", "SegurCaixa_portal"),
        ("adeslas_client_v2", "adeslas_client"),
    ]
    for contenido, desc in casos:
        f = tmp_path / f"test_{desc}.py"
        f.write_text(contenido, encoding="utf-8")
        hallazgos = [h for h in buscar(tmp_path) if h.patron == "cliente"]
        assert len(hallazgos) > 0, f"Debe detectar cliente en '{contenido}'"
        # Limpiar para la siguiente iteración
        f.unlink()

def test_detecta_un_correo_corporativo_con_subdominio(tmp_path):
    # Correos corporativos con subdominio deben detectarse
    (tmp_path / "config.py").write_text("MAIL = 'admin@correo.nfqsolutions.es'", encoding="utf-8")
    hallazgos = [h for h in buscar(tmp_path) if h.patron == "correo"]
    assert len(hallazgos) > 0, "Debe detectar correo con subdominio"
    assert any("admin@correo.nfqsolutions.es" in h.texto for h in hallazgos)

def test_no_detecta_correos_de_cliente(tmp_path):
    # Correos de cliente NO deben detectarse (false positives son malos)
    (tmp_path / "config.py").write_text('CUSTOMER_MAIL = "ana@cliente.com"', encoding="utf-8")
    hallazgos = [h for h in buscar(tmp_path) if h.patron == "correo"]
    assert len(hallazgos) == 0, "No debe detectar correos de dominio externo"
