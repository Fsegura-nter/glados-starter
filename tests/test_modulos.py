import json, py_compile, re, pytest

MODULOS = ["google", "gitlab", "decisiones", "paneles", "statusline"]

# Una skill invoca un subagente nombrándolo en negrita en la misma línea que menciona
# la herramienta Agent o `subagent_type` (es la convención que ya usa /mr: "Launch
# **mr-back-reviewer** ... with the Agent tool"). No es un parser de prosa: es el
# patrón mínimo para no tener que mantener a mano la lista de pares skill→agente.
_MENCION_AGENTE = re.compile(r"\*\*([a-z][a-z0-9-]*)\*\*")
_PISTA_AGENTE = re.compile(r"agent tool|subagent_type", re.IGNORECASE)

@pytest.mark.parametrize("nombre", MODULOS)
def test_el_modulo_se_declara_entero(raiz, nombre):
    m = json.loads((raiz / "modulos" / nombre / "modulo.json").read_text(encoding="utf-8"))
    assert set(m) >= {"nombre", "descripcion", "ficheros", "destino", "prueba_de_vida", "requiere"}
    for f in m["ficheros"]:
        assert (raiz / "modulos" / nombre / f).exists(), f

@pytest.mark.parametrize("nombre", MODULOS)
def test_los_scripts_del_modulo_compilan(raiz, nombre):
    for f in (raiz / "modulos" / nombre).rglob("*.py"):
        py_compile.compile(str(f), doraise=True)

def test_ningun_modulo_envia_correo(raiz):
    for f in (raiz / "modulos").rglob("*.py"):
        texto = f.read_text(encoding="utf-8", errors="ignore")
        assert "messages/send" not in texto, f
        assert "drafts/send" not in texto, f

def test_el_modulo_gitlab_no_trae_el_host_de_nadie(raiz):
    """El host sale siempre de `.glados/settings.json` (`gitlab_host`), nunca de un
    literal: una instancia hospedada por una empresa escrita en un repositorio público
    es el tipo de dato que no debe viajar.

    Esta prueba busca la FORMA de un host de GitLab, no el nombre concreto de ninguna
    empresa. Antes nombraba el dominio interno real, que es precisamente lo que no puede
    estar aquí: un fichero que afirma la ausencia de algo nombrándolo lo publica.
    """
    # Un host concreto es o una URL (`https://gitlab.x.y`) o un nombre con un TLD de
    # verdad detrás. La lista de TLD evita el falso positivo que encontré escribiendo
    # esto: `gitlab.tokens.group` es una CLAVE de credencial, no un dominio.
    host = re.compile(
        r"(?:https?://|//)gitlab\.[a-z0-9.-]+"
        r"|\bgitlab\.[a-z0-9-]+\.(?:es|com|net|org|io|dev|eu|local|cloud)\b", re.I)
    PERMITIDOS = ("ejemplo.invalido", "miempresa.example", "example.com", "gitlab.com",
                  "gitlab.host")        # marcador de posición en la ayuda de /mr
    for f in (raiz / "modulos/gitlab").rglob("*"):
        if not f.is_file() or f.suffix == ".pyc":
            continue
        for n, linea in enumerate(f.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            m = host.search(linea)
            if m and not any(p in m.group(0) for p in PERMITIDOS):
                pytest.fail(f"{f.relative_to(raiz)}:{n} trae un host concreto: {m.group(0)}")

def test_toda_skill_declara_los_agentes_que_invoca(raiz):
    """Guarda genérica, no el par /mr concreto: cualquier SKILL.md que lance un
    subagente por nombre tiene que traer su definición, o se queda huérfano en
    silencio hasta que alguien lo ejecuta de verdad. Los agentes definidos son
    cualquier `*.md` dentro de una carpeta llamada `agents`, identificados por su
    `name:` de frontmatter — nunca una lista de nombres mantenida a mano aquí.
    """
    definidos = {}
    for md in raiz.rglob("agents/*.md"):
        texto = md.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\s*\n(.*?)\n---", texto, re.DOTALL)
        if not m:
            continue
        nm = re.search(r"^name:\s*(\S+)\s*$", m.group(1), re.MULTILINE)
        if nm:
            definidos[nm.group(1).strip()] = md

    faltan = []
    for skill in raiz.rglob("SKILL.md"):
        texto = skill.read_text(encoding="utf-8", errors="ignore")
        for linea in texto.splitlines():
            if not _PISTA_AGENTE.search(linea):
                continue
            for nombre in _MENCION_AGENTE.findall(linea):
                if nombre not in definidos:
                    faltan.append((skill, nombre))
    assert not faltan, faltan


# --- Destino de instalación -------------------------------------------------
#
# Claude Code descubre comandos, skills y agentes en rutas FIJAS bajo `.claude`.
# No es una convención del kit: es la plataforma. Un fichero instalado un
# directorio más allá no existe para el compañero, y NADA se queja — ni el
# bootstrap, ni el doctor, ni la skill que lo invoca. Por eso estas pruebas
# miran el DESTINO calculado, no la existencia del fichero en el repo, que es
# lo único que comprobaba `test_el_modulo_se_declara_entero`.
DESCUBRIMIENTO = {
    "commands": ".claude/commands",
    "skills":   ".claude/skills",
    "agents":   ".claude/agents",
}

# Nombres "casi" correctos: la carpeta existe, el fichero se copia, y el
# descubrimiento no mira ahí. Es el fallo real del módulo gitlab el 2026-10-07.
CARPETAS_CIEGAS = {
    "comandos": "commands",
    "skill":    "skills",
    "agentes":  "agents",
    "agent":    "agents",
    "command":  "commands",
}


def _manifiesto(raiz, nombre):
    return json.loads(
        (raiz / "modulos" / nombre / "modulo.json").read_text(encoding="utf-8")
    )


def _destino_de(m, fichero):
    """Destino declarado para un fichero: `destinos[<primer segmento>]` si el
    módulo declara excepciones, y `destino` en cualquier otro caso."""
    prefijo = fichero.split("/")[0]
    destinos = m.get("destinos") or {}
    return destinos.get(prefijo, m["destino"])


@pytest.mark.parametrize("nombre", MODULOS)
def test_los_ficheros_descubribles_aterrizan_donde_se_descubren(raiz, nombre):
    m = _manifiesto(raiz, nombre)
    mal = []
    for f in m["ficheros"]:
        prefijo = f.split("/")[0]
        if prefijo not in DESCUBRIMIENTO:
            continue
        instalado = f"{_destino_de(m, f)}/{f}"
        if not instalado.startswith(DESCUBRIMIENTO[prefijo] + "/"):
            mal.append((f, instalado, DESCUBRIMIENTO[prefijo]))
    assert not mal, mal


@pytest.mark.parametrize("nombre", MODULOS)
def test_ningun_modulo_usa_una_carpeta_que_nadie_descubre(raiz, nombre):
    mal = [
        (str(p.relative_to(raiz)), CARPETAS_CIEGAS[p.name])
        for p in (raiz / "modulos" / nombre).rglob("*")
        if p.is_dir() and p.name in CARPETAS_CIEGAS
    ]
    assert not mal, mal


@pytest.mark.parametrize("nombre", MODULOS)
def test_todo_fichero_descubrible_del_modulo_esta_declarado(raiz, nombre):
    """Un agente o un comando que está en el repo pero no en `ficheros` no se
    instala nunca: la skill que lo invoca muere y el fichero parece presente."""
    carpeta = raiz / "modulos" / nombre
    declarados = set(_manifiesto(raiz, nombre)["ficheros"])
    sin_declarar = [
        str(p.relative_to(carpeta)).replace("\\", "/")
        for p in carpeta.rglob("*")
        if p.is_file()
        and p.suffix == ".md"
        and p.relative_to(carpeta).parts[0] in DESCUBRIMIENTO
        and str(p.relative_to(carpeta)).replace("\\", "/") not in declarados
    ]
    assert not sin_declarar, sin_declarar


@pytest.mark.parametrize("nombre", MODULOS)
def test_cada_skill_del_modulo_vive_en_su_propia_carpeta(raiz, nombre):
    """`skills/<nombre>/SKILL.md`, exactamente: un SKILL.md a cualquier otra
    profundidad no lo carga nadie."""
    mal = [
        f for f in _manifiesto(raiz, nombre)["ficheros"]
        if f.endswith("SKILL.md") and not re.fullmatch(r"skills/[^/]+/SKILL\.md", f)
    ]
    assert not mal, mal
