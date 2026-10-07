#!/usr/bin/env python3
"""
doctor.py — Diagnóstico de la bóveda: diez chequeos, en un orden que no es casual.

Este kit no tiene soporte: quien lo use está solo si algo se rompe, y este script es
lo único que le dirá qué. Por eso **nunca lanza**: una bóveda rota es justo el momento
en que esto corre, y un doctor que se cae con el paciente enfermo no sirve para nada.
Cada chequeo atrapa sus propios fallos y los convierte en un `Chequeo` en estado
`"fallo"` con el motivo, nunca en una traza sin capturar.

Tampoco arregla nada: decidir si una desviación de vocabulario es deriva o una
categoría nueva, o si una credencial que falta hay que rellenarla ya, es cosa de quien
lee el informe.

Los chequeos 4, 6, 7, 8 y 9 inspeccionan el entorno de LA BÓVEDA QUE SE DIAGNOSTICA, no
el de este propio fichero: cargan `config.py`, `credentials.py`, `lexical.py` y
`respaldo_drive.py` desde `<vault>/.glados/`, nunca desde la copia que viaja junto a
`doctor.py` (ver `_cargar_glados`). Así, si esos scripts están rotos o ausentes en la
bóveda diagnosticada —que es justo lo que este doctor existe para encontrar—, el
diagnóstico lo refleja en vez de comprobarse a sí mismo por error.

Uso:
    python doctor.py [--vault RUTA] [--json]

Salida: tabla con `v` (ok), `!` (aviso) y `x` (fallo). Código de salida 1 si algún
chequeo queda en `fallo`.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from collections import namedtuple
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()

Chequeo = namedtuple("Chequeo", "nombre estado detalle")

LIMITE_NOTA_BYTES = 250 * 1024
DIRS_IGNORADAS = {".git", ".glados", ".claude", ".obsidian", "__pycache__",
                   "node_modules", ".venv", "venv", ".pytest_cache", ".trash"}

# Scripts que todo hook de sesión debería tener registrado (chequeo 2). Si falta uno,
# la función que cubre ya no corre nunca, y en silencio: nadie ve un hook que no está.
HOOKS_ESPERADOS = ("session_start.py", "context_injector.py", "precompact_snapshot.py",
                    "commit_vault.py", "respaldo_drive.py")

# Nombre de import cuando difiere del nombre de paquete en requirements.txt.
NOMBRE_IMPORT = {"python-docx": "docx", "sentence-transformers": "sentence_transformers"}

# Módulos de `.glados` que este doctor reutiliza, cargados siempre desde la bóveda que
# se diagnostica (ver `_cargar_glados`). Orden importante: `config` primero, porque los
# demás lo importan a su vez y deben encontrar YA en `sys.modules` la copia correcta.
MODULOS_REUTILIZADOS = ("config", "credentials", "lexical", "respaldo_drive")


# --------------------------------------------------------------------------- utilidad

def _seguro(nombre: str, fn) -> Chequeo:
    """Ejecuta un chequeo y nunca deja escapar una excepción: la convierte en un
    `Chequeo` en `fallo`. Es la póliza de la regla "un diagnóstico nunca lanza"."""
    try:
        return fn()
    except Exception as e:
        return Chequeo(nombre, "fallo", f"el chequeo falló por una excepción interna: {e}")


def _cargar_glados(vault: Path) -> dict:
    """Carga `config`, `credentials`, `lexical` y `respaldo_drive` desde
    `<vault>/.glados/`, no desde la carpeta de este fichero.

    Fuerza una recarga (`sys.modules.pop`) antes de importar: si una llamada anterior a
    `diagnosticar()` en el mismo proceso —justo lo que hace esta batería de pruebas, que
    diagnostica varias bóvedas temporales una tras otra— dejó cacheado el `config` de
    OTRA bóveda, una nueva debe leer el suyo, nunca el de la anterior.

    Nunca lanza: un módulo ausente o roto en la bóveda queda en `None` para quien lo
    consuma, que lo trata como "no disponible" — es justo lo que varios chequeos deben
    poder reportar, no un fallo propio del doctor.
    """
    carpeta = vault / ".glados"
    carpeta_str = str(carpeta.resolve()) if carpeta.is_dir() else None

    for nombre in MODULOS_REUTILIZADOS:
        sys.modules.pop(nombre, None)

    insertado = False
    if carpeta_str and carpeta_str not in sys.path:
        sys.path.insert(0, carpeta_str)
        insertado = True

    modulos: dict = {}
    try:
        for nombre in MODULOS_REUTILIZADOS:
            ruta = carpeta / f"{nombre}.py"
            if not carpeta_str or not ruta.is_file():
                modulos[nombre] = None
                continue
            try:
                spec = importlib.util.spec_from_file_location(nombre, ruta)
                m = importlib.util.module_from_spec(spec)
                sys.modules[nombre] = m
                spec.loader.exec_module(m)
                modulos[nombre] = m
            except Exception:
                sys.modules.pop(nombre, None)
                modulos[nombre] = None
    finally:
        if insertado:
            try:
                sys.path.remove(carpeta_str)
            except ValueError:
                pass
    return modulos


def _notas(vault: Path):
    """Ficheros `.md` de la bóveda, fuera de `.git`, `.glados`, `.claude`, etc."""
    for ruta in vault.rglob("*.md"):
        if not ruta.is_file():
            continue
        partes = ruta.relative_to(vault).parts[:-1]
        if DIRS_IGNORADAS & set(partes):
            continue
        yield ruta


def _settings_claude(vault: Path) -> tuple[dict | None, str | None]:
    """(datos, None) si `.claude/settings.json` es un objeto JSON válido.
    (None, motivo_en_castellano) en cualquier otro caso — ausente, ilegible, JSON roto,
    o JSON válido que no es un objeto (una lista, por ejemplo, que es justo el caso
    que antes hacía que `datos.get("hooks")` lanzara `AttributeError` sin capturar).
    Nunca lanza.
    """
    ruta = vault / ".claude" / "settings.json"
    if not ruta.is_file():
        return None, f"no existe {ruta}"
    try:
        texto = ruta.read_text(encoding="utf-8")
    except OSError:
        return None, f"no se pudo leer {ruta}"
    try:
        datos = json.loads(texto)
    except json.JSONDecodeError as e:
        return None, (f"{ruta} no es JSON válido (línea {e.lineno}, "
                       f"columna {e.colno})")
    if not isinstance(datos, dict):
        return None, (f"{ruta} no contiene un objeto JSON en la raíz "
                       "(es una lista u otro valor), así que los hooks no se "
                       "pueden leer")
    return datos, None


def _comandos_hooks(vault: Path) -> list[tuple[str, str]]:
    """[(evento, comando), ...] de `.claude/settings.json`. `[]` si no existe, no es
    JSON válido, o su forma no es la esperada — nunca lanza."""
    datos, motivo = _settings_claude(vault)
    if datos is None:
        return []
    hooks = datos.get("hooks")
    if not isinstance(hooks, dict):
        return []
    salida = []
    for evento, entradas in hooks.items():
        if not isinstance(entradas, list):
            continue
        for entrada in entradas:
            if not isinstance(entrada, dict):
                continue
            for orden in entrada.get("hooks", []):
                if isinstance(orden, dict) and isinstance(orden.get("command"), str):
                    salida.append((evento, orden["command"]))
    return salida


def _python_de_hooks(vault: Path) -> Path | None:
    """El ejecutable de Python que usan los comandos de hook (primer token de
    cualquiera de ellos; todos usan el mismo). `None` si no hay ninguno."""
    for _evento, comando in _comandos_hooks(vault):
        partes = comando.split(" ")
        if partes:
            return Path(partes[0])
    return None


def _frontmatter(ruta: Path) -> dict:
    """Frontmatter mínimo: escalares `clave: valor` y listas `clave:` + `  - valor`.

    No es un parser YAML general — a propósito, el mismo criterio que
    `generar_vault._frontmatter_yaml`, que es quien escribe lo que esto lee. Nunca
    lanza: un fichero que no se puede leer o sin frontmatter devuelve `{}`.
    """
    try:
        texto = ruta.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not texto.startswith("---"):
        return {}
    resto = texto[3:]
    fin = resto.find("\n---")
    if fin == -1:
        return {}
    bloque = resto[:fin]

    datos: dict = {}
    clave_actual = None
    for linea in bloque.splitlines():
        if not linea.strip():
            continue
        if linea[0] in (" ", "\t"):
            valor = linea.strip()
            if valor.startswith("- ") and clave_actual is not None:
                datos.setdefault(clave_actual, [])
                if isinstance(datos[clave_actual], list):
                    datos[clave_actual].append(valor[2:].strip().strip('"'))
            continue
        if ":" not in linea:
            continue
        clave, _, valor = linea.partition(":")
        clave = clave.strip()
        valor = valor.strip().strip('"')
        clave_actual = clave
        datos[clave] = valor if valor else []
    return datos


# -------------------------------------------------------------------- chequeo 1: remoto

def chequeo_remoto(vault: Path) -> Chequeo:
    """Única barrera entre una bóveda con datos de cliente y un host público: va
    primero a propósito.

    Antes de fiarse de un `stdout` vacío, comprueba que esto es de verdad un
    repositorio git: `git remote -v` también sale vacío (por `stdout`) cuando la
    carpeta nunca tuvo `git init`, y en ese caso `stdout` vacío NO significa "sin
    remoto, bien" — significa que no hay ni historial ni forma de deshacer un
    borrado, que es peor que tener un remoto y mucho peor que lo que este chequeo
    estaba diciendo antes de este arreglo.
    """
    r = subprocess.run(["git", "remote", "-v"], cwd=vault,
                        capture_output=True, text=True, encoding="utf-8")
    if r.returncode != 0 or not (vault / ".git").is_dir():
        return Chequeo("remoto git", "fallo",
                        "esta carpeta no es un repositorio git (o su .git ha "
                        "desaparecido): sin historial, sin forma de deshacer un "
                        "borrado, y sin ninguna de las protecciones que el resto de "
                        "este diseño asume. Arréglelo con: git init")
    remotos = [l for l in r.stdout.splitlines() if l.strip()]
    if remotos:
        return Chequeo("remoto git", "fallo",
                        "el vault tiene remoto y puede acabar publicado: "
                        + "; ".join(remotos)
                        + ". Quítelo con: git remote remove <nombre>")
    return Chequeo("remoto git", "ok", "sin remoto, como debe ser")


# --------------------------------------------------------------------- chequeo 2: hooks

def chequeo_hooks(vault: Path) -> Chequeo:
    datos, motivo = _settings_claude(vault)
    if datos is None:
        return Chequeo("hooks", "fallo", motivo)

    hooks = datos.get("hooks")
    if not isinstance(hooks, dict):
        return Chequeo("hooks", "fallo",
                        ".claude/settings.json no declara la clave 'hooks' como un "
                        "objeto; no hay hooks que leer")

    comandos = _comandos_hooks(vault)
    if not comandos:
        return Chequeo("hooks", "fallo", ".claude/settings.json no declara ningún hook")

    problemas = []
    vistos = set()
    for evento, comando in comandos:
        if "'" in comando:
            problemas.append(f"{evento}: lleva comillas simples ({comando!r})")
        if "&" in comando:
            problemas.append(f"{evento}: lleva & ({comando!r})")

        partes = comando.split(" ")
        script = Path(partes[-1]) if partes else None
        if script is None:
            continue
        vistos.add(script.name)
        if not script.is_file():
            problemas.append(f"{evento}: no existe el script {script}")
            continue
        try:
            texto = script.read_text(encoding="utf-8")
            compile(texto, str(script), "exec")
        except SyntaxError as e:
            problemas.append(f"{evento}: {script.name} no compila "
                              f"(error de sintaxis en la línea {e.lineno})")
        except Exception:
            problemas.append(f"{evento}: no se pudo leer o decodificar "
                              f"{script.name} (compruebe que está en UTF-8)")

    faltan = [h for h in HOOKS_ESPERADOS if h not in vistos]
    if faltan:
        problemas.append("no registrados en settings.json: " + ", ".join(faltan))

    if problemas:
        return Chequeo("hooks", "fallo", "; ".join(problemas))
    return Chequeo("hooks", "ok",
                    f"{len(comandos)} hook(s) registrados, compilan, sin comillas ni &")


# -------------------------------------------------------------------- chequeo 3: notas

def chequeo_notas_grandes(vault: Path) -> Chequeo:
    grandes = []
    for ruta in _notas(vault):
        try:
            tam = ruta.stat().st_size
        except OSError:
            continue
        if tam > LIMITE_NOTA_BYTES:
            grandes.append(f"{ruta.relative_to(vault)} ({tam // 1024} KB)")
    if grandes:
        return Chequeo("notas", "fallo",
                        f"{len(grandes)} nota(s) superan los 250 KB: " + "; ".join(grandes))
    return Chequeo("notas", "ok", "ninguna nota supera los 250 KB")


# --------------------------------------------------------------- chequeo 4: entorno virtual

def _paquetes_declarados(vault: Path) -> list[str] | None:
    ruta = vault / ".glados" / "requirements.txt"
    if not ruta.is_file():
        return None
    paquetes = []
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        nombre = re.split(r"[<>=!~\[;#]", linea.strip(), maxsplit=1)[0].strip()
        if nombre:
            paquetes.append(nombre)
    return paquetes


def chequeo_venv(vault: Path) -> Chequeo:
    python_path = _python_de_hooks(vault)
    if not python_path or not python_path.is_file():
        extra = f" ({python_path})" if python_path else ""
        return Chequeo("entorno virtual", "fallo",
                        f"no se encuentra el Python del entorno virtual{extra}; "
                        "ningún hook puede ejecutarse.")

    paquetes = _paquetes_declarados(vault)
    if paquetes is None:
        return Chequeo("entorno virtual", "aviso",
                        f"el venv existe ({python_path}) pero no hay requirements.txt "
                        "para saber qué dependencias declara.")

    fallidos = []
    for paquete in paquetes:
        modulo = NOMBRE_IMPORT.get(paquete, paquete.replace("-", "_"))
        try:
            r = subprocess.run([str(python_path), "-c", f"import {modulo}"],
                                capture_output=True, text=True, encoding="utf-8",
                                timeout=60)
            if r.returncode != 0:
                fallidos.append(paquete)
        except Exception:
            fallidos.append(paquete)

    if fallidos:
        return Chequeo("entorno virtual", "aviso",
                        f"venv en {python_path}; no importan (búsqueda semántica no "
                        f"disponible, el resto del kit funciona igual): "
                        + ", ".join(fallidos))
    return Chequeo("entorno virtual", "ok",
                    f"venv en {python_path}; {len(paquetes)} dependencia(s) declarada(s) "
                    "importan sin problema")


# ------------------------------------------------------------------- chequeo 5: enlaces

def chequeo_enlaces(vault: Path) -> Chequeo:
    """Las rutas absolutas que `bootstrap.ps1` grabó en los comandos de hook —el
    Python del venv y el script dentro de `.glados`— siguen apuntando a algo que
    existe. Si alguien mueve la bóveda o borra el venv, estas rutas quedan huérfanas y
    cada hook falla en silencio; esto es lo que lo detecta."""
    comandos = _comandos_hooks(vault)
    if not comandos:
        return Chequeo("enlaces", "fallo",
                        "no hay comandos de hook que comprobar "
                        "(.claude/settings.json ausente o sin hooks)")

    rotos = []
    for evento, comando in comandos:
        partes = comando.split(" ")
        if len(partes) != 2:
            rotos.append(f"{evento}: comando con forma inesperada ({comando!r})")
            continue
        py, script = partes
        if not Path(py).is_file():
            rotos.append(f"{evento}: no existe el Python {py}")
        if not Path(script).is_file():
            rotos.append(f"{evento}: no existe el script {script}")

    if rotos:
        return Chequeo("enlaces", "fallo",
                        "rutas de hook que ya no existen (bóveda movida o venv "
                        "borrado): " + "; ".join(rotos))
    return Chequeo("enlaces", "ok",
                    f"las {len(comandos)} rutas de hook (Python + script) apuntan "
                    "donde deben")


# --------------------------------------------------------------- chequeo 6: credenciales

def chequeo_credenciales(modulos: dict) -> Chequeo:
    mod = modulos.get("credentials")
    if mod is None:
        return Chequeo("credenciales", "fallo", "no se pudo cargar .glados/credentials.py")

    faltan = []
    for servicio, campos in mod.ENV_MAP.items():
        for campo in campos:
            clave = f"{servicio}.{campo}"
            if not mod.get(clave):
                faltan.append(clave)

    huerfanas = mod.huerfanas()

    if huerfanas:
        detalle = "claves guardadas que ningún consumidor sabe leer: " + ", ".join(huerfanas)
        if faltan:
            detalle += ". También faltan por configurar: " + ", ".join(faltan)
        return Chequeo("credenciales", "fallo", detalle)

    if faltan:
        return Chequeo("credenciales", "aviso",
                        "faltan por configurar: " + ", ".join(faltan))

    return Chequeo("credenciales", "ok",
                    "todas las claves conocidas están puestas, sin huérfanas")


# ------------------------------------------------------------------- chequeo 7: respaldo

def chequeo_respaldo(modulos: dict) -> Chequeo:
    mod = modulos.get("respaldo_drive")
    if mod is None:
        return Chequeo("respaldo", "fallo", "no se pudo cargar .glados/respaldo_drive.py")

    carpeta, explicacion = mod.destino()
    if not carpeta:
        return Chequeo("respaldo", "aviso", f"sin destino de respaldo: {explicacion}")

    previo = mod.ultimo(carpeta)
    if not previo:
        return Chequeo("respaldo", "aviso", f"no hay ningún respaldo todavía en {carpeta}")

    dias = (datetime.now() - datetime.fromtimestamp(previo.stat().st_mtime)).total_seconds() / 86400
    estado = "aviso" if dias >= 3 else "ok"
    return Chequeo("respaldo", estado, f"último respaldo de hace {dias:.1f} día(s) ({previo.name})")


# -------------------------------------------------------------------- chequeo 8: índices

def chequeo_indices(modulos: dict) -> Chequeo:
    mod = modulos.get("lexical")
    if mod is None:
        return Chequeo("índices", "fallo", "no se pudo cargar .glados/lexical.py")

    if not mod.is_populated():
        return Chequeo("índices", "aviso",
                        "no hay nada indexado todavía (normal en una bóveda recién "
                        "creada); ejecuta index_docs.py cuando haya material")

    filas = mod.stats()
    resultados = mod.search("prueba de diagnostico del doctor")
    total_docs = sum(nf for _, nf, _ in filas)
    total_frag = sum(nc for _, _, nc in filas)
    return Chequeo("índices", "ok",
                    f"{total_docs} documento(s), {total_frag} fragmento(s) en "
                    f"{len(filas)} colección(es); la consulta de prueba devolvió "
                    f"{len(resultados)} resultado(s)")


# ---------------------------------------------------------------- chequeo 9: frontmatter

def chequeo_frontmatter(vault: Path, modulos: dict) -> Chequeo:
    mod = modulos.get("config")
    vocabulario = mod.vocabulario() if mod else {}
    if not vocabulario:
        return Chequeo("frontmatter", "ok",
                        "sin vocabulario declarado en settings.json; nada que comprobar")

    desviaciones = []
    for ruta in _notas(vault):
        fm = _frontmatter(ruta)
        for clave, permitidos in vocabulario.items():
            if clave not in fm or not isinstance(permitidos, list) or not permitidos:
                continue
            valor = fm[clave]
            valores = valor if isinstance(valor, list) else [valor]
            for v in valores:
                if v and v not in permitidos:
                    desviaciones.append(
                        f"{ruta.relative_to(vault)}: {clave}={v!r} no está en {permitidos}")

    if desviaciones:
        return Chequeo("frontmatter", "aviso",
                        f"{len(desviaciones)} desviación(es) del vocabulario declarado "
                        "(deriva o vocabulario nuevo, a decidir): "
                        + "; ".join(desviaciones[:10]))
    return Chequeo("frontmatter", "ok", "el frontmatter respeta el vocabulario declarado")


# -------------------------------------------------------------------- chequeo 10: módulos

def chequeo_modulos(vault: Path) -> Chequeo:
    ruta = vault / ".glados" / "estado_modulos.json"
    if not ruta.is_file():
        return Chequeo("módulos", "ok",
                        "sin módulos activos todavía (no existe estado_modulos.json)")

    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return Chequeo("módulos", "fallo",
                        f"estado_modulos.json no es JSON válido (línea {e.lineno}, "
                        f"columna {e.colno})")
    except Exception:
        return Chequeo("módulos", "fallo", "no se pudo leer estado_modulos.json")
    if not isinstance(datos, dict):
        return Chequeo("módulos", "fallo", "estado_modulos.json no contiene un objeto")

    fallidos = []
    nunca_probados = []
    for modulo, servicios in datos.items():
        if not isinstance(servicios, dict):
            continue
        for servicio, estado in servicios.items():
            etiqueta = f"{modulo}/{servicio}"
            if estado == "fallo":
                fallidos.append(f"{etiqueta}: fallo")
            elif estado != "ok":
                nunca_probados.append(f"{etiqueta}: {estado}")

    if fallidos:
        detalle = "la prueba de vida falló en: " + "; ".join(fallidos)
        if nunca_probados:
            detalle += "; nunca probados: " + "; ".join(nunca_probados)
        return Chequeo("módulos", "fallo", detalle)

    if nunca_probados:
        return Chequeo("módulos", "aviso",
                        "nunca se ha probado: " + "; ".join(nunca_probados))

    return Chequeo("módulos", "ok", "todos los módulos activos pasaron su prueba de vida")


# ------------------------------------------------------------------------- orquestación

def diagnosticar(vault: Path) -> list[Chequeo]:
    """Los diez chequeos, en este orden. Nunca lanza."""
    vault = Path(vault)
    try:
        modulos = _cargar_glados(vault)
    except Exception:
        modulos = {nombre: None for nombre in MODULOS_REUTILIZADOS}

    return [
        _seguro("remoto git", lambda: chequeo_remoto(vault)),
        _seguro("hooks", lambda: chequeo_hooks(vault)),
        _seguro("notas", lambda: chequeo_notas_grandes(vault)),
        _seguro("entorno virtual", lambda: chequeo_venv(vault)),
        _seguro("enlaces", lambda: chequeo_enlaces(vault)),
        _seguro("credenciales", lambda: chequeo_credenciales(modulos)),
        _seguro("respaldo", lambda: chequeo_respaldo(modulos)),
        _seguro("índices", lambda: chequeo_indices(modulos)),
        _seguro("frontmatter", lambda: chequeo_frontmatter(vault, modulos)),
        _seguro("módulos", lambda: chequeo_modulos(vault)),
    ]


# -------------------------------------------------------------------------------- CLI

SIMBOLO = {"ok": "v", "aviso": "!", "fallo": "x"}


def _tabla(chequeos: list[Chequeo]) -> str:
    ancho = max((len(c.nombre) for c in chequeos), default=0)
    return "\n".join(
        f"{SIMBOLO.get(c.estado, '?')}  {c.nombre:<{ancho}}  {c.detalle}"
        for c in chequeos
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Diagnóstico de la bóveda. Diez chequeos; no arregla nada.")
    ap.add_argument("--vault", help="Raíz de la bóveda a diagnosticar. Por defecto, la "
                     "que contiene este propio .glados.")
    ap.add_argument("--json", action="store_true",
                     help="Salida en JSON, para que la consuma la skill.")
    args = ap.parse_args()

    vault = Path(args.vault) if args.vault else Path(__file__).resolve().parent.parent
    chequeos = diagnosticar(vault)

    if args.json:
        print(json.dumps([c._asdict() for c in chequeos], ensure_ascii=False, indent=2))
    else:
        print(_tabla(chequeos))

    return 1 if any(c.estado == "fallo" for c in chequeos) else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"[doctor] fallo interno: {e}", file=sys.stderr)
        sys.exit(1)
