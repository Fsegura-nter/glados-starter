import importlib.util, sys, pathlib

def cargar(raiz):
    ruta = raiz / "nucleo/.glados/ruido.py"
    spec = importlib.util.spec_from_file_location("ruido", ruta)
    m = importlib.util.module_from_spec(spec); sys.modules["ruido"] = m
    spec.loader.exec_module(m); return m

def msg(de="ana@cliente.com", cabeceras=None, partes=None):
    return {"de": de, "cabeceras": cabeceras or {}, "partes": partes or ["text/plain"]}

def test_descarta_boletin_por_cabecera(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(cabeceras={"List-Unsubscribe": "<mailto:x>"})) == (True, "cabecera")

def test_descarta_automatico_por_cabecera(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(cabeceras={"Auto-Submitted": "auto-generated"})) == (True, "cabecera")

def test_descarta_invitacion_por_parte_mime(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(partes=["text/plain", "text/calendar"])) == (True, "invitacion")

def test_descarta_notificacion_por_remitente(raiz):
    r = cargar(raiz)
    for d in ["noreply@x.com", "notifications@github.com", "jira@empresa.atlassian.net"]:
        assert r.es_ruido(msg(de=d))[0] is True

def test_no_descarta_a_una_persona(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg()) == (False, "")

def test_no_descarta_a_alguien_que_se_llama_noreply_de_apellido(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(de="ana.noreyes@cliente.com")) == (False, "")

def test_el_resumen_cuadra(raiz):
    r = cargar(raiz)
    datos = r.resumen([
        msg(), msg(de="luis@otro.com"),
        msg(cabeceras={"Precedence": "bulk"}),
        msg(partes=["text/calendar"]),
        msg(de="noreply@x.com"),
    ])
    assert datos["total"] == 5
    assert datos["utiles"] == 2
    assert datos["personas"] == 2
    assert datos["cabecera"] + datos["invitacion"] + datos["remitente"] == 3

def test_la_misma_persona_con_nombre_para_mostrar_cuenta_una_vez(raiz):
    r = cargar(raiz)
    datos = r.resumen([
        msg(de="ana@cliente.com"),
        msg(de="Ana@cliente.com"),
        msg(de='"Ana Perez" <ana@cliente.com>'),
        msg(de="luis@otro.com"),
    ])
    assert datos["personas"] == 2
    assert datos["utiles"] == 4

def test_un_noreply_escondido_tras_un_nombre_se_descarta(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(de='"Equipo" <noreply@x.com>')) == (True, "remitente")

def test_no_revienta_con_campos_nulos_ni_basura(raiz):
    r = cargar(raiz)
    pruebas = [
        {"cabeceras": None},
        {"cabeceras": ["x"]},
        {"cabeceras": 42},
        {"de": None},
        {"de": 123},
        {"de": ["a"]},
        {"partes": None},
        {"partes": "texto"},
        {"partes": 7},
        {},
        None,
        "texto",
        42,
    ]
    for entrada in pruebas:
        resultado = r.es_ruido(entrada)
        assert isinstance(resultado, tuple) and len(resultado) == 2

    # Verify resumen doesn't raise with mixed valid and invalid
    datos = r.resumen([
        {"de": "ana@cliente.com", "cabeceras": {}, "partes": []},
        {"cabeceras": ["x"]},
        {"de": 123},
        {"de": "luis@otro.com", "cabeceras": {}, "partes": []},
    ])
    assert datos["cabecera"] + datos["remitente"] + datos["invitacion"] + datos["utiles"] == datos["total"]

def test_descarta_boletines_y_redes_por_dominio(raiz):
    r = cargar(raiz)
    for d in [
        "member@linkedin.com",
        "hello@mailchimp.com",
        "news@substack.com",
        "bounce@sendgrid.net",
        "notify@mg.mailgun.org",
        "campaign@campaign-archive.com",
        "hello@constantcontact.com",
    ]:
        assert r.es_ruido(msg(de=d))[0] is True

def test_descarta_avisos_de_calendario_por_remitente(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(de="calendar-notification@google.com")) == (True, "invitacion")
    assert r.es_ruido(msg(de="calendar-server@google.com")) == (True, "invitacion")

def test_no_descarta_a_alguien_que_se_llama_mailer_o_bounce(raiz):
    r = cargar(raiz)
    for d in [
        "ana.mailer@cliente.com",
        "juan.bounce@cliente.com",
        "maria.notario@cliente.com",
        "jose.teams@cliente.com",
    ]:
        assert r.es_ruido(msg(de=d)) == (False, "")

def test_descarta_un_mailer_daemon_de_verdad(raiz):
    r = cargar(raiz)
    assert r.es_ruido(msg(de="mailer-daemon@x.com")) == (True, "remitente")
    assert r.es_ruido(msg(de="bounce@x.com")) == (True, "remitente")
    assert r.es_ruido(msg(de="bounces+algo@x.com")) == (True, "remitente")

def test_las_reglas_de_dominio_no_tocan_la_parte_local(raiz):
    r = cargar(raiz)
    # Debe conservar: la parte local no es ruido, aunque contenga palabras ruido
    for d in [
        "mailgun@cliente.com",
        "ana.mailgun@cliente.com",
        "ana@mailgunning.com",
        "jose.campaign-archive@cliente.com",
        "ana.sendgrid@cliente.com",
        "ana.linkedin@cliente.com",
    ]:
        assert r.es_ruido(msg(de=d)) == (False, ""), f"False positive: {d}"

    # Debe descartar: dominios de ruido reales
    for d in [
        "x@mg.mailgun.org",
        "x@mailgun.com",
        "x@campaign-archive.com",
        "member@linkedin.com",
    ]:
        assert r.es_ruido(msg(de=d))[0] is True, f"False negative: {d}"
