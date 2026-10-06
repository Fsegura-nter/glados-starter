import json, subprocess, sys

def ejecutar(raiz, tmp_path, datos):
    fuente = tmp_path / "fuente.json"; fuente.write_text(json.dumps(datos), encoding="utf-8")
    salida = tmp_path / "metricas.json"
    r = subprocess.run([sys.executable, str(raiz / "nucleo/.glados/arranque_lectura.py"),
                        "--fuente", str(fuente), "--salida", str(salida)],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(salida.read_text(encoding="utf-8")), r.stdout

def test_cuenta_interlocutores_reales(raiz, tmp_path):
    datos = {"mensajes": [
        {"de": "ana@acme.com", "cabeceras": {}, "partes": ["text/plain"], "asunto": "pedido"},
        {"de": "ana@acme.com", "cabeceras": {}, "partes": ["text/plain"], "asunto": "pedido 2"},
        {"de": "noreply@x.com", "cabeceras": {}, "partes": ["text/plain"], "asunto": "alta"},
    ], "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert m["correo"]["personas"] == 1
    assert m["correo"]["interlocutores"][0]["direccion"] == "ana@acme.com"
    assert m["correo"]["interlocutores"][0]["mensajes"] == 2

def test_informa_de_lo_que_descarto(raiz, tmp_path):
    datos = {"mensajes": [{"de": "noreply@x.com", "cabeceras": {}, "partes": ["text/plain"]}],
             "eventos": [], "drive": [], "repos": []}
    _, salida = ejecutar(raiz, tmp_path, datos)
    assert "descartado" in salida.lower()

def test_detecta_una_serie_recurrente_del_calendario(raiz, tmp_path):
    eventos = [{"titulo": "Daily equipo", "inicio": f"2026-09-{d:02d}T09:00", "minutos": 15,
                "asistentes": ["ana@acme.com"]} for d in (1, 2, 3, 4, 7, 8, 9, 10)]
    datos = {"mensajes": [], "eventos": eventos, "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    series = m["calendario"]["series"]
    assert series[0]["titulo"] == "Daily equipo"
    assert series[0]["cadencia"] == "diaria"

def test_buzon_sin_nada_util_termina_y_avisa(raiz, tmp_path):
    datos = {"mensajes": [{"de": "noreply@x.com", "cabeceras": {}, "partes": ["text/plain"]}
                          for _ in range(200)],
             "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert m["correo"]["personas"] == 0
    assert any("material" in a.lower() for a in m["avisos"])
    assert m["escritura"] == {}

def test_las_muestras_de_escritura_van_redactadas(raiz, tmp_path):
    datos = {"mensajes": [{"de": "yo@mio.com", "enviado": True, "cabeceras": {},
                           "partes": ["text/plain"], "asunto": "token",
                           "cuerpo": "el token es eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.firma"}],
             "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert "eyJhbGciOiJIUzI1NiJ9" not in json.dumps(m)

def test_no_vuelca_cuerpos_enteros_en_las_metricas(raiz, tmp_path):
    cuerpo = "palabra " * 500
    datos = {"mensajes": [{"de": "yo@mio.com", "enviado": True, "cabeceras": {},
                           "partes": ["text/plain"], "asunto": "largo", "cuerpo": cuerpo}],
             "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert len(json.dumps(m)) < 20000
