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
