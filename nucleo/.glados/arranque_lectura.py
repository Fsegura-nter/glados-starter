#!/usr/bin/env python3
"""
arranque_lectura.py — Barrido de arranque de la fase 2: correo, calendario, Drive y repos.

Lee sin límite y devuelve sin límite sería al revés de lo que hace falta aquí: todo lo que
el kit propondrá después —carpetas, áreas, la voz del asistente— se deduce de la SALIDA de
este script, nunca del material en bruto. Por eso la regla es sencilla y no negociable: esto
cuenta, agrupa y mide; no cita cuerpos de mensaje ni contenido de documento. Lo único que se
asoma del material real son hasta tres muestras de escritura de como mucho 300 caracteres,
y pasan por `redact.redactar` antes de salir.

Cuatro barridos, cada uno tolerante a que su fuente no esté disponible: lo apunta en
`avisos` y sigue con los demás. Un hueco silencioso aquí se convierte, dos fases después, en
una estructura inventada para encajar con datos que nunca se leyeron.

Fuentes:
  - `--fuente FICHERO`: un JSON con las claves `mensajes`, `eventos`, `drive` y `repos`, en
    vez de ir a la red. Es lo que hace el barrido probable con pytest, y lo que usa el modo
    simulado de una fase posterior: nunca debe hacer falta una cuenta de Google real para
    probar este script.
  - Sin `--fuente`: intenta leer en vivo a través de `modulos/google/gmail_api.py`. Ese
    módulo todavía no existe (llega en otra tarea de este plan); el contrato que deberá
    cumplir cuando exista es `listar_mensajes(meses)`, `listar_eventos(meses)` y
    `listar_drive()`, con la misma forma de mensaje/evento que acepta `--fuente`. Hasta
    entonces, cualquier intento de usarlo —módulo ausente, credencial ausente, llamada que
    falla— se recoge en `avisos` y el barrido sigue con listas vacías. Nunca una excepción
    sin capturar por una fuente que no está.
  - `--repos RUTA`: recorre el disco (no es parte de `--fuente`) hasta 3 niveles buscando
    repositorios git y lee cada uno con `git`. Si `--fuente` trae una lista `repos` no vacía
    y no se pasó `--repos`, se usan esas entradas ya calculadas (pensadas para simular repos
    sin tocar disco ni red) — pero no tal cual: se validan sus claves y todo texto libre
    pasa por `redact.redactar`, igual que el resto de fuentes externas.

Uso:
    python arranque_lectura.py --salida metricas.json [--meses 12] [--repos RUTA]
                                [--fuente FICHERO]
"""
import argparse
import importlib.util
import json
import re
import statistics
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
import redact
import ruido
from ruido import _extraer_direccion  # misma extracción que ruido.resumen(): que nunca discrepen

config.force_utf8()

TOPE_SALIDA_BYTES = 64 * 1024
MUESTRA_MAX_CHARS = 300
MUESTRAS_MAXIMAS = 3
ENVIADOS_MINIMOS_PARA_ESTILO = 5

# Listas que se recortan, en orden, si la salida se acerca al tope de tamaño. Nunca se
# trunca una estructura a medias: lo que se recorta son elementos enteros de una lista.
LISTAS_RECORTABLES = [
    ("correo", "interlocutores"),
    ("correo", "dominios_externos"),
    ("correo", "asuntos_repetidos"),
    ("calendario", "series"),
    ("drive", "carpetas_con_actividad"),
    ("drive", "compartidas"),
    ("repos", "repositorios"),
]

SALUDOS = re.compile(
    r"^\s*(hola|buenas(?: tardes| dias|noches)?|buenos dias|estimad[oa]s?|querid[oa]s?)\b",
    re.I)
CIERRES = re.compile(
    r"\b(un saludo|saludos|atentamente|cordialmente|un abrazo|gracias)\b\.?\s*$", re.I)
PRON_TUTEO = re.compile(r"\b(t[uú]|contigo|tienes|puedes|quieres)\b", re.I)
PRON_USTED = re.compile(r"\b(usted|ustedes|tiene|puede|quiere)\b", re.I)

EXTENSION_LENGUAJE = {
    ".py": "Python", ".ts": "TypeScript", ".tsx": "TypeScript", ".js": "JavaScript",
    ".jsx": "JavaScript", ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust",
    ".rb": "Ruby", ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".c": "C", ".swift": "Swift",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS", ".vue": "Vue", ".sql": "SQL",
    ".sh": "Shell", ".ps1": "PowerShell",
}
DIRS_IGNORADAS_REPO = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}


# --------------------------------------------------------------------------- correo


def _redactar(texto: str) -> str:
    limpio, _ = redact.redactar(texto or "")
    return limpio


def _barrer_correo(mensajes: list, avisos: list[str]) -> dict:
    resumen = ruido.resumen(mensajes)

    interlocutores: dict[str, int] = {}
    dominios: dict[str, int] = {}
    asuntos: dict[str, int] = {}
    ilegibles = 0

    for m in mensajes:
        if not isinstance(m, dict):
            ilegibles += 1
            continue
        descartar, _ = ruido.es_ruido(m)
        if descartar:
            continue
        direccion = _extraer_direccion(m.get("de"))
        if not direccion:
            continue
        interlocutores[direccion] = interlocutores.get(direccion, 0) + 1
        if "@" in direccion:
            dominio = direccion.split("@", 1)[1]
            dominios[dominio] = dominios.get(dominio, 0) + 1
        asunto = m.get("asunto")
        if isinstance(asunto, str) and asunto.strip():
            asuntos[asunto.strip()] = asuntos.get(asunto.strip(), 0) + 1

    print(f"correo: {resumen['total']} mensajes, "
          f"{resumen['cabecera'] + resumen['remitente'] + resumen['invitacion']} descartados "
          f"(cabecera {resumen['cabecera']}, remitente {resumen['remitente']}, "
          f"invitacion {resumen['invitacion']}), {resumen['utiles']} utiles, "
          f"{resumen['personas']} personas.")

    if resumen["utiles"] == 0:
        avisos.append(
            f"Correo: sin mensajes utiles tras descartar ruido (0 de {resumen['total']}); "
            "no hay material suficiente para deducir interlocutores ni estructura.")
    elif (resumen["utiles"] < ENVIADOS_MINIMOS_PARA_ESTILO
          or resumen["personas"] < ENVIADOS_MINIMOS_PARA_ESTILO):
        # Material escaso pero no nulo: tres correos utiles parecen tan sanos como
        # trescientos a quien lea solo este fichero. Mismo umbral que el perfil de
        # escritura, para no inventar un segundo numero sin motivo.
        avisos.append(
            f"Correo: material escaso ({resumen['utiles']} utiles, {resumen['personas']} "
            f"personas); por debajo de {ENVIADOS_MINIMOS_PARA_ESTILO} no basta para proponer "
            "una estructura por si solo, la entrevista debe completarlo.")

    if ilegibles:
        avisos.append(f"Correo: {ilegibles} mensaje(s) ilegible(s) omitido(s) "
                       "(no son objetos validos).")

    return {
        "total": resumen["total"],
        "descartados": {
            "cabecera": resumen["cabecera"],
            "remitente": resumen["remitente"],
            "invitacion": resumen["invitacion"],
        },
        "utiles": resumen["utiles"],
        "personas": resumen["personas"],
        "interlocutores": [
            {"direccion": d, "mensajes": n} for d, n in
            sorted(interlocutores.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "dominios_externos": [
            {"dominio": d, "mensajes": n} for d, n in
            sorted(dominios.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "asuntos_repetidos": [
            {"asunto": _redactar(a), "veces": n} for a, n in
            sorted(asuntos.items(), key=lambda kv: (-kv[1], kv[0])) if n > 1
        ],
    }


# ------------------------------------------------------------------------ calendario


def _normalizar_titulo(titulo: str) -> str:
    return re.sub(r"\s+", " ", titulo or "").strip().lower()


def _cadencia(mediana_dias: float) -> str:
    if mediana_dias <= 1.5:
        return "diaria"
    if mediana_dias <= 8:
        return "semanal"
    if mediana_dias <= 16:
        return "quincenal"
    if mediana_dias <= 35:
        return "mensual"
    return "esporadica"


def _barrer_calendario(eventos: list, avisos: list[str]) -> dict:
    import datetime

    grupos: dict[str, dict] = {}
    sin_titulo = 0
    sin_fecha = 0
    for ev in eventos:
        if not isinstance(ev, dict):
            sin_titulo += 1
            continue
        titulo = ev.get("titulo")
        if not isinstance(titulo, str) or not titulo.strip():
            sin_titulo += 1
            continue
        clave = _normalizar_titulo(titulo)
        grupo = grupos.setdefault(clave, {
            "titulo": titulo.strip(), "fechas": [], "asistentes": set(), "minutos": [],
        })
        inicio = ev.get("inicio")
        fecha_leida = False
        if isinstance(inicio, str):
            try:
                grupo["fechas"].append(datetime.datetime.fromisoformat(inicio))
                fecha_leida = True
            except ValueError:
                pass
        if not fecha_leida:
            sin_fecha += 1
        asistentes = ev.get("asistentes")
        if isinstance(asistentes, list):
            for a in asistentes:
                direccion = _extraer_direccion(a) if isinstance(a, str) else ""
                if direccion:
                    grupo["asistentes"].add(direccion)
        minutos = ev.get("minutos")
        if isinstance(minutos, (int, float)):
            grupo["minutos"].append(minutos)

    series = []
    for grupo in grupos.values():
        fechas = sorted(grupo["fechas"])
        if len(fechas) >= 2:
            gaps = [(fechas[i + 1] - fechas[i]).total_seconds() / 86400
                    for i in range(len(fechas) - 1)]
            cadencia = _cadencia(statistics.median(gaps))
        else:
            cadencia = "esporadica"
        series.append({
            "titulo": grupo["titulo"],
            "cadencia": cadencia,
            "ocurrencias": len(fechas) or len(grupo["minutos"]) or 1,
            "asistentes": sorted(grupo["asistentes"]),
            "duracion_minutos": (round(statistics.mean(grupo["minutos"]))
                                  if grupo["minutos"] else None),
        })
    series.sort(key=lambda s: -s["ocurrencias"])

    if not series:
        avisos.append("Calendario: sin eventos con titulo; no hay series que detectar.")
    if sin_titulo:
        avisos.append(f"Calendario: {sin_titulo} evento(s) sin titulo utilizable omitido(s).")
    if sin_fecha:
        avisos.append(f"Calendario: {sin_fecha} evento(s) sin fecha utilizable "
                       "(no contaron para la cadencia).")

    return {"series": series}


# ----------------------------------------------------------------------------- drive


def _barrer_drive(items: list, avisos: list[str]) -> dict:
    carpetas: dict[str, int] = {}
    compartidas: dict[str, set] = {}
    ilegibles = 0

    for it in items:
        if not isinstance(it, dict):
            ilegibles += 1
            continue
        carpeta = it.get("carpeta")
        if not isinstance(carpeta, str) or not carpeta.strip():
            ilegibles += 1
            continue
        carpeta = carpeta.strip()
        if it.get("propia"):
            carpetas[carpeta] = carpetas.get(carpeta, 0) + 1
        con = it.get("compartido_con")
        if isinstance(con, list) and con:
            compartidas.setdefault(carpeta, set()).update(
                c for c in con if isinstance(c, str) and c)

    if not items:
        avisos.append("Drive: sin material disponible (ni --fuente ni modulo google); "
                       "no hay carpetas que proponer.")
    if ilegibles:
        avisos.append(f"Drive: {ilegibles} entrada(s) ilegible(s) omitida(s) "
                       "(sin carpeta valida).")

    return {
        "carpetas_con_actividad": [
            {"carpeta": _redactar(c), "eventos": n} for c, n in
            sorted(carpetas.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
        "compartidas": [
            {"carpeta": _redactar(c), "con": sorted(con)} for c, con in
            sorted(compartidas.items(), key=lambda kv: kv[0])
        ],
    }


# ----------------------------------------------------------------------------- repos


def _git(repo_dir: Path, *args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=str(repo_dir), capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _buscar_repos_git(raiz: Path, max_nivel: int) -> list[Path]:
    encontrados: list[Path] = []

    def recorrer(carpeta: Path, nivel: int) -> None:
        if (carpeta / ".git").exists():
            encontrados.append(carpeta)
            return
        if nivel >= max_nivel:
            return
        try:
            hijos = [e for e in carpeta.iterdir()
                     if e.is_dir() and e.name not in DIRS_IGNORADAS_REPO]
        except OSError:
            return
        for hijo in hijos:
            recorrer(hijo, nivel + 1)

    recorrer(raiz, 0)
    return encontrados


def _lenguaje_dominante(repo_dir: Path) -> str | None:
    conteo: dict[str, int] = {}
    try:
        for f in repo_dir.rglob("*"):
            if not f.is_file() or DIRS_IGNORADAS_REPO & set(f.relative_to(repo_dir).parts):
                continue
            lang = EXTENSION_LENGUAJE.get(f.suffix.lower())
            if lang:
                conteo[lang] = conteo.get(lang, 0) + 1
    except OSError:
        return None
    if not conteo:
        return None
    return max(conteo.items(), key=lambda kv: kv[1])[0]


def _primera_linea_readme(repo_dir: Path) -> str | None:
    for nombre in ("README.md", "README.rst", "README.txt", "README", "readme.md"):
        ruta = repo_dir / nombre
        if ruta.is_file():
            try:
                for linea in ruta.read_text(encoding="utf-8", errors="replace").splitlines():
                    limpia = linea.strip().lstrip("#").strip()
                    if limpia:
                        return _redactar(limpia[:200])
            except OSError:
                return None
    return None


def _analizar_repo(repo_dir: Path) -> dict:
    remoto = _git(repo_dir, "remote", "get-url", "origin") or None
    email_usuario = _git(repo_dir, "config", "user.email") or None
    commits_usuario = 0
    if email_usuario:
        log = _git(repo_dir, "log", f"--author={email_usuario}", "--oneline")
        commits_usuario = len([l for l in log.splitlines() if l.strip()])
    return {
        "nombre": repo_dir.name,
        "remoto": remoto,
        "lenguaje_principal": _lenguaje_dominante(repo_dir),
        "commits_usuario": commits_usuario,
        "primera_linea_readme": _primera_linea_readme(repo_dir),
    }


# Claves de texto libre de una entrada de repo de --fuente: se validan y se pasan por
# _redactar igual que cualquier otro texto que entra en el payload desde fuera. La única
# clave adicional que se acepta es "commits_usuario" (entero); cualquier otra clave de la
# entrada original se descarta en vez de copiarse tal cual.
CAMPOS_REPO_TEXTO = ("nombre", "remoto", "lenguaje_principal", "primera_linea_readme")


def _normalizar_repo_de_fuente(r: dict) -> dict:
    """Valida y redacta una entrada de `repos` de --fuente (modo simulado).

    No se copia nada tal cual: solo las claves conocidas, con los tipos esperados, y
    todo texto libre pasado por `_redactar` antes de entrar en el payload — el mismo
    tratamiento que recibe un asunto de correo o una carpeta de Drive. Sin esto, una
    credencial puesta por error en un repo simulado habría salido byte a byte.
    """
    salida: dict = {}
    for campo in CAMPOS_REPO_TEXTO:
        valor = r.get(campo)
        salida[campo] = _redactar(valor) if isinstance(valor, str) and valor else None
    commits = r.get("commits_usuario")
    salida["commits_usuario"] = commits if isinstance(commits, int) else 0
    return salida


def _barrer_repos(ruta_repos: str | None, repos_de_fuente: list, avisos: list[str]) -> dict:
    if ruta_repos:
        raiz = Path(ruta_repos)
        if not raiz.is_dir():
            avisos.append(f"Repos: --repos {ruta_repos} no es una carpeta; repos vacio.")
            return {"repositorios": []}
        repos_dirs = _buscar_repos_git(raiz, max_nivel=3)
        resultados = []
        for repo_dir in repos_dirs:
            try:
                resultados.append(_analizar_repo(repo_dir))
            except Exception as e:
                avisos.append(f"Repos: no se pudo leer {repo_dir.name} ({e}).")
        if not resultados:
            avisos.append(f"Repos: no se encontro ningun repositorio git bajo {ruta_repos}.")
        return {"repositorios": resultados}

    if repos_de_fuente:
        # --fuente trae entradas ya calculadas (modo simulado): se validan y se redactan,
        # nunca se copian tal cual (no se toca git ni disco en este camino).
        resultados = []
        ilegibles = 0
        for r in repos_de_fuente:
            if isinstance(r, dict):
                resultados.append(_normalizar_repo_de_fuente(r))
            else:
                ilegibles += 1
        if ilegibles:
            avisos.append(f"Repos: {ilegibles} entrada(s) de --fuente ilegible(s) "
                           "omitida(s) (no son objetos validos).")
        return {"repositorios": resultados}

    return {"repositorios": []}


# --------------------------------------------------------------------------- escritura


def _barrer_escritura(mensajes: list, avisos: list[str]) -> dict:
    enviados_utiles = []
    for m in mensajes:
        if not isinstance(m, dict) or not m.get("enviado"):
            continue
        descartar, _ = ruido.es_ruido(m)
        if descartar:
            continue
        cuerpo = m.get("cuerpo")
        if isinstance(cuerpo, str) and cuerpo.strip():
            enviados_utiles.append(cuerpo)

    if len(enviados_utiles) < ENVIADOS_MINIMOS_PARA_ESTILO:
        avisos.append(
            f"Escritura: solo {len(enviados_utiles)} enviado(s) util(es) con cuerpo; con "
            f"menos de {ENVIADOS_MINIMOS_PARA_ESTILO} no hay perfil de escritura (una "
            "muestra de uno no es un estilo).")
        return {}

    saludos: dict[str, int] = {}
    cierres: dict[str, int] = {}
    tuteos = ustedes = 0
    longitudes = []

    for cuerpo in enviados_utiles:
        longitudes.append(len(cuerpo))
        primera = next((l for l in cuerpo.splitlines() if l.strip()), "")
        m_saludo = SALUDOS.match(primera.strip())
        if m_saludo:
            saludos[m_saludo.group(1).lower()] = saludos.get(m_saludo.group(1).lower(), 0) + 1
        ultima = next((l for l in reversed(cuerpo.splitlines()) if l.strip()), "")
        m_cierre = CIERRES.search(ultima.strip())
        if m_cierre:
            cierres[m_cierre.group(1).lower()] = cierres.get(m_cierre.group(1).lower(), 0) + 1
        tuteos += len(PRON_TUTEO.findall(cuerpo))
        ustedes += len(PRON_USTED.findall(cuerpo))

    if tuteos > ustedes:
        estilo = "tu"
    elif ustedes > tuteos:
        estilo = "usted"
    else:
        estilo = "indeterminado"

    # Hasta tres muestras, repartidas por la lista, recortadas y redactadas: nunca el
    # cuerpo entero, nunca sin pasar por redact.redactar.
    paso = max(1, len(enviados_utiles) // MUESTRAS_MAXIMAS)
    elegidas = enviados_utiles[::paso][:MUESTRAS_MAXIMAS]
    muestras = [_redactar(c[:MUESTRA_MAX_CHARS]) for c in elegidas]

    return {
        "enviados_utiles": len(enviados_utiles),
        "longitud_media": round(sum(longitudes) / len(longitudes)),
        "saludo_habitual": max(saludos, key=saludos.get) if saludos else None,
        "cierre_habitual": max(cierres, key=cierres.get) if cierres else None,
        "estilo": estilo,
        "muestras": muestras,
    }


# ----------------------------------------------------------------------- fuentes/google


def _modulo_google_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent / "modulos" / "google"


def _importar_google_api():
    """Carga `modulos/google/gmail_api.py` si el módulo ya existe (Tarea 12).

    Devuelve `None` si la carpeta, el fichero o la importación fallan por cualquier
    motivo: nunca deja escapar la excepción, porque para este script la ausencia del
    módulo es un caso normal, no un error.
    """
    ruta = _modulo_google_dir() / "gmail_api.py"
    if not ruta.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("gmail_api_arranque", ruta)
        if spec is None or spec.loader is None:
            return None
        modulo = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(modulo)
        return modulo
    except Exception:
        return None


def _leer_fuentes(fuente: str | None, meses: int, avisos: list[str]):
    """Devuelve (mensajes, eventos, drive, repos). Nunca lanza."""
    if fuente:
        try:
            datos = json.loads(Path(fuente).read_text(encoding="utf-8"))
        except Exception as e:
            avisos.append(f"No se pudo leer --fuente {fuente} ({e}); correo, calendario, "
                           "drive y repos quedan vacios.")
            return [], [], [], []
        if not isinstance(datos, dict):
            avisos.append(f"--fuente {fuente} no contiene un objeto JSON; se ignora.")
            return [], [], [], []
        mensajes = datos.get("mensajes") if isinstance(datos.get("mensajes"), list) else []
        eventos = datos.get("eventos") if isinstance(datos.get("eventos"), list) else []
        drive = datos.get("drive") if isinstance(datos.get("drive"), list) else []
        repos = datos.get("repos") if isinstance(datos.get("repos"), list) else []
        return mensajes, eventos, drive, repos

    modulo = _importar_google_api()
    if modulo is None:
        avisos.append("Modulo google no disponible (no existe todavia, o no carga): correo, "
                       "calendario y drive quedan vacios. Repos no depende de el.")
        return [], [], [], []

    mensajes, eventos, drive = [], [], []
    try:
        mensajes = modulo.listar_mensajes(meses=meses)
    except Exception as e:
        avisos.append(f"Correo en vivo fallo ({e}); correo queda vacio.")
    try:
        eventos = modulo.listar_eventos(meses=meses)
    except Exception as e:
        avisos.append(f"Calendario en vivo fallo ({e}); calendario queda vacio.")
    try:
        drive = modulo.listar_drive()
    except Exception as e:
        avisos.append(f"Drive en vivo fallo ({e}); drive queda vacio.")
    return mensajes, eventos, drive, []


# ---------------------------------------------------------------------------- recorte


def _serializar(payload: dict) -> str:
    """Forma canonica de serializar la salida.

    Es, a propósito, la MISMA cadena que `_tamano_bytes` mide y la que `main()` escribe
    a disco. Medir con una forma (p.ej. sin `indent`) y escribir con otra (con `indent=2`)
    deja que el recorte decida "cabe" sobre un tamaño que no es el que termina en el
    fichero — el hallazgo que motivo este cambio: un sweep de 1000 mensajes vio 49 966
    bytes en la medicion y escribio 75 098 en disco, un 15% por encima del tope de 64 KB,
    reportando exito. Sin `indent`: es un fichero para que lo lea una maquina, no a mano.
    """
    return json.dumps(payload, ensure_ascii=False)


def _tamano_bytes(payload: dict) -> int:
    return len(_serializar(payload).encode("utf-8"))


def _recortar_hasta_caber(payload: dict, limite: int = TOPE_SALIDA_BYTES) -> bool:
    """Si la salida se acerca al tope, recorta listas enteras (nunca a media estructura)
    hasta caber. Devuelve True si tuvo que recortar algo."""
    recortado = False
    for _ in range(50):
        if _tamano_bytes(payload) <= limite:
            break
        progreso = False
        for clave, subclave in LISTAS_RECORTABLES:
            bloque = payload.get(clave)
            if not isinstance(bloque, dict):
                continue
            items = bloque.get(subclave)
            if isinstance(items, list) and items:
                nuevo_len = len(items) - max(1, len(items) // 4)
                bloque[subclave] = items[:max(0, nuevo_len)]
                progreso = True
                recortado = True
        if not progreso:
            break
    return recortado


# --------------------------------------------------------------------------------- main


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Barrido de arranque: metricas agregadas de correo, calendario, "
                     "Drive y repos. Nunca material en bruto.")
    ap.add_argument("--salida", required=True, help="Fichero JSON de salida.")
    ap.add_argument("--meses", type=int, default=12,
                     help="Meses hacia atras a pedir a las fuentes en vivo (ignorado con "
                          "--fuente, que ya trae lo que trae).")
    ap.add_argument("--repos", help="Carpeta donde buscar repositorios git (hasta 3 niveles).")
    ap.add_argument("--fuente", help="JSON con mensajes/eventos/drive/repos, en vez de red.")
    args = ap.parse_args()

    avisos: list[str] = []

    mensajes, eventos, drive_items, repos_fuente = _leer_fuentes(args.fuente, args.meses, avisos)

    correo = _barrer_correo(mensajes, avisos)
    calendario = _barrer_calendario(eventos, avisos)
    drive = _barrer_drive(drive_items, avisos)
    repos = _barrer_repos(args.repos, repos_fuente, avisos)
    escritura = _barrer_escritura(mensajes, avisos)

    payload = {
        "correo": correo,
        "calendario": calendario,
        "drive": drive,
        "repos": repos,
        "escritura": escritura,
        "avisos": avisos,
    }

    if _recortar_hasta_caber(payload):
        avisos.append("La salida se recorto (listas, nunca a media estructura) para no "
                       "superar el tope de 64 KB.")

    salida_path = Path(args.salida)
    salida_path.parent.mkdir(parents=True, exist_ok=True)
    salida_path.write_text(_serializar(payload), encoding="utf-8")

    print(f"Barrido escrito en {salida_path} ({_tamano_bytes(payload)} bytes).")
    for aviso in avisos:
        print(f"[aviso] {aviso}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
