import json, os, subprocess, sys

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


# --- Fix round 1: hallazgos 1-5 del revisor ------------------------------------------

def test_el_tope_de_64kb_se_respeta_de_verdad(raiz, tmp_path):
    """Hallazgo 1: el tope se media en una forma (sin indent) y se escribia en otra (con
    indent=2), asi que un sweep podia "caber" en la medicion y superar igualmente el
    tope en el fichero real. La fixture es deliberadamente grande para forzar el recorte
    de verdad, no solo para reproducir el tamano exacto que vio el revisor."""
    mensajes = [{"de": f"persona{i % 500}@acme.com", "cabeceras": {}, "partes": ["text/plain"],
                 "asunto": f"Tema recurrente de seguimiento numero {i % 300}"}
                for i in range(5000)]
    eventos = [{"titulo": f"Serie de reunion numero {s}", "inicio": "2026-01-01T09:00",
                "minutos": 30, "asistentes": []} for s in range(150)]
    drive = [{"carpeta": f"Carpeta de trabajo compartida numero {i}", "propia": True,
              "compartido_con": [f"persona{i}@acme.com"]} for i in range(400)]
    datos = {"mensajes": mensajes, "eventos": eventos, "drive": drive, "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    salida = tmp_path / "metricas.json"
    # El tamano en DISCO es lo que cuenta, no una medicion interna.
    assert os.path.getsize(salida) <= 64 * 1024
    # ejecutar() ya hizo json.loads() sobre el fichero: si no fuera JSON valido, habria
    # lanzado antes de llegar aqui. Lo dejamos explicito para que la intencion se lea sola.
    json.loads(salida.read_text(encoding="utf-8"))


def test_los_repos_de_fuente_pasan_por_redaccion(raiz, tmp_path):
    """Hallazgo 2: las entradas de `repos` que llegan por --fuente (modo simulado) se
    copiaban tal cual, sin pasar por redact.redactar como el resto de fuentes."""
    credencial = "glpat-" + "A" * 25
    datos = {"mensajes": [], "eventos": [], "drive": [],
             "repos": [{"nombre": "repo-simulado", "remoto": "https://ejemplo.invalido/x.git",
                        "lenguaje_principal": "Python", "commits_usuario": 3,
                        "primera_linea_readme": f"token interno: {credencial}"}]}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert credencial not in json.dumps(m)
    assert m["repos"]["repositorios"][0]["nombre"] == "repo-simulado"


def test_las_muestras_se_redactan_y_se_truncan(raiz, tmp_path):
    """Hallazgo 3 (segunda vuelta): la version anterior de este test ponia la
    credencial alrededor del caracter 800 de un cuerpo largo. El recorte a 300
    caracteres la eliminaba por si solo, asi que el test pasaba aunque se desactivara
    `_redactar(...)` por completo — la tercera version de la misma trampa.

    Esta version separa las dos cosas que hay que probar en DOS mensajes distintos:
      - indice 0: la credencial va en los primeros caracteres del cuerpo, y el cuerpo
        entero mide menos de 300 caracteres. Si desaparece de la salida, solo puede ser
        porque `_redactar` la sustituyo — el recorte no llega a tocarla, este cuerpo
        nunca se acerca al limite.
      - indice 2: un cuerpo de mas de 300 caracteres sin ninguna credencial, para
        probar que el recorte a 300 caracteres SIGUE pasando (no basta con quitar el
        recorte para que la credencial se cuele: hay que demostrar que ambas cosas
        conviven).
    Con 6 enviados utiles, `paso = max(1, 6 // 3) == 2`, asi que se muestrean los
    indices 0, 2 y 4 (`enviados_utiles[::2][:3]`): los indices 0 y 2 estan garantizados
    dentro de la muestra para este `n` concreto. Los indices 1, 3 y 5 son relleno solo
    para superar el minimo de 5 enviados utiles que exige un perfil de escritura.
    """
    credencial = "eyJhbGciOiJIUzI1NiJ9.eyJhIjoxfQ.firma"
    cuerpo_credencial = f"Token: {credencial}\nUn saludo"  # < 300 caracteres a proposito
    cuerpo_largo = "palabra " * 100  # 800 caracteres, sin ninguna credencial
    cuerpos = {0: cuerpo_credencial, 2: cuerpo_largo}
    mensajes = [{"de": "yo@mio.com", "enviado": True, "cabeceras": {}, "partes": ["text/plain"],
                 "asunto": f"m{i}",
                 "cuerpo": cuerpos.get(i, f"Hola,\nmensaje numero {i}.\nUn saludo")}
                for i in range(6)]
    datos = {"mensajes": mensajes, "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert m["escritura"] != {}
    muestras = m["escritura"]["muestras"]
    # La credencial no sobrevive (prueba de redaccion: su cuerpo nunca se acerca a 300).
    assert credencial not in json.dumps(m)
    # El recorte a 300 caracteres sigue pasando (prueba de truncado, sobre el cuerpo
    # largo sin credencial): si el recorte se hubiera roto, esta muestra mediria 800.
    assert any(len(s) == 300 for s in muestras)
    for muestra in muestras:
        assert len(muestra) <= 300


def test_avisa_cuando_el_material_es_escaso_pero_no_nulo(raiz, tmp_path):
    """Hallazgo 4: 3 mensajes utiles de 200 no generaban ningun aviso de escasez; a
    quien lea solo metricas.json, 3 parecia tan sano como 300."""
    ruido_msgs = [{"de": "noreply@x.com", "cabeceras": {}, "partes": ["text/plain"]}
                  for _ in range(197)]
    utiles_msgs = [{"de": f"persona{i}@acme.com", "cabeceras": {}, "partes": ["text/plain"],
                    "asunto": "hola"} for i in range(3)]
    datos = {"mensajes": ruido_msgs + utiles_msgs, "eventos": [], "drive": [], "repos": []}
    m, _ = ejecutar(raiz, tmp_path, datos)
    assert m["correo"]["utiles"] == 3
    assert any("escaso" in a.lower() for a in m["avisos"])


def test_informa_de_los_registros_ilegibles(raiz, tmp_path):
    """Hallazgo 5: un registro individual malformado por fuente (mensaje, evento, Drive,
    repo) se absorbia sin dejar rastro en avisos. Un hueco silencioso aqui es justo lo
    que el fichero existe para evitar.

    Segunda vuelta (hallazgo 5 seguia abierto): ademas del string suelto, se anaden tres
    mensajes que SI son dict (pasan `isinstance(m, dict)`) pero con un campo del tipo
    equivocado: `cabeceras` como lista, `de` como numero, `partes` como texto suelto.
    `ruido.es_ruido` los tolera sin lanzar (coacciona el campo a su default), que es
    justo por lo que antes se colaban en 'utiles' como si fueran correo sano."""
    datos = {
        "mensajes": [
            "esto no es un mensaje",
            {"de": "ana@acme.com", "cabeceras": {}, "partes": ["text/plain"], "asunto": "ok"},
            {"de": "x@y.com", "cabeceras": ["no-es-un-dict"], "partes": ["text/plain"]},
            {"de": 12345, "cabeceras": {}, "partes": ["text/plain"]},
            {"de": "x@y.com", "cabeceras": {}, "partes": "text/plain"},
        ],
        "eventos": [
            {"titulo": "Evento con fecha rota", "inicio": "fecha-invalida", "minutos": 30,
             "asistentes": []},
        ],
        "drive": [None],
        "repos": ["esto tampoco es un repo"],
    }
    m, _ = ejecutar(raiz, tmp_path, datos)
    avisos = m["avisos"]
    # 1 string suelto + 3 dict con un campo de tipo incorrecto = 4 mensajes ilegibles.
    assert any("Correo: 4 mensaje" in a for a in avisos)
    assert any("Calendario: 1 evento" in a and "fecha" in a for a in avisos)
    assert any("Drive: 1 entrada" in a for a in avisos)
    assert any("Repos: 1 entrada" in a for a in avisos)
    # Los tres mensajes mal tipados no deben contar como correo sano: solo el mensaje
    # de ana@acme.com es valido, asi que utiles y personas tienen que quedarse en 1.
    assert m["correo"]["utiles"] == 1
    assert m["correo"]["personas"] == 1
