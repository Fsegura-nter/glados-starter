#!/usr/bin/env python3
"""
inventario_repos.py — Versiones reales de los repos de un workspace de Bitbucket.

Responde con datos la pregunta que a menudo se contesta por intuición: **qué deuda técnica
hay y dónde**. Lee el `package.json` y el `pom.xml` de cada repo y saca las versiones de
Angular, Spring Boot, Java y Node.

Por defecto imprime **solo el agregado** —cuántos repos en cada versión y cuáles son los más
atrasados—, que es lo que el modelo necesita leer. Las filas una a una solo con `--detalle`,
y el CSV completo se guarda siempre fuera del vault, en el directorio de datos del ecosistema
(`config.data_dir()`).

Credenciales: `bitbucket.email`, `bitbucket.token` y `bitbucket.workspace` del almacén.
El token necesita `read:repository`.

Uso:
  python inventario_repos.py [--detalle] [--hilos 8] [--limite 0]
"""
import argparse
import base64
import csv
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

config.force_utf8()
import credentials

API = "https://api.bitbucket.org/2.0"
TIMEOUT = 30


def auth() -> tuple[str, str]:
    email = credentials.get("bitbucket.email")
    token = credentials.get("bitbucket.token")
    ws = credentials.get("bitbucket.workspace")
    if not (email and token and ws):
        print("Faltan bitbucket.email, bitbucket.token o bitbucket.workspace en el almacen.")
        print("Comprobar con: python credentials.py list")
        raise SystemExit(1)
    cabecera = base64.b64encode(f"{email}:{token}".encode()).decode()
    return f"Basic {cabecera}", ws


def get(url: str, cabecera: str, crudo: bool = False):
    req = urllib.request.Request(url, headers={"Authorization": cabecera})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            datos = r.read()
        return datos.decode("utf-8", "replace") if crudo else json.loads(datos)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None                      # el repo no tiene ese fichero: es lo normal
        raise
    except Exception:
        return None


def listar_repos(cabecera: str, ws: str, limite: int) -> list[dict]:
    repos, url = [], (f"{API}/repositories/{ws}?pagelen=100"
                      f"&fields=next,values.slug,values.mainbranch.name,values.updated_on")
    while url:
        datos = get(url, cabecera)
        if not datos:
            break
        for r in datos.get("values", []):
            repos.append({
                "slug": r["slug"],
                "rama": (r.get("mainbranch") or {}).get("name") or "master",
                "actualizado": (r.get("updated_on") or "")[:10],
            })
        url = datos.get("next")
        if limite and len(repos) >= limite:
            return repos[:limite]
    return repos


def analizar(repo: dict, cabecera: str, ws: str) -> dict:
    base = f"{API}/repositories/{ws}/{repo['slug']}/src/{urllib.parse.quote(repo['rama'])}"
    fila = {**repo, "angular": "", "node": "", "spring": "", "java": "", "tipo": "",
            "parent": "", "parent_ver": "", "ficheros_raiz": 0}

    pkg = get(f"{base}/package.json", cabecera, crudo=True)
    if pkg:
        try:
            d = json.loads(pkg)
            deps = {**d.get("dependencies", {}), **d.get("devDependencies", {})}
            fila["angular"] = re.sub(r"^[\^~>=<\s]+", "", deps.get("@angular/core", ""))
            fila["node"] = (d.get("engines") or {}).get("node", "")
            fila["tipo"] = "front"
        except json.JSONDecodeError:
            fila["angular"] = "package.json ilegible"

    pom = get(f"{base}/pom.xml", cabecera, crudo=True)
    if not pkg and not pom:
        # En un workspace grande, buena parte de los repos sin manifiesto estan vacios o
        # son de otra tecnologia, y el numero crudo de "sin manifiesto" engana si no se
        # desglosa. Se clasifica mirando la raiz, porque un repo muerto se puede archivar
        # y uno de otra tecnologia no es deuda de Angular ni de Spring.
        raiz = get(f"{base}/?pagelen=40&fields=values.path", cabecera)
        nombres = [v.get("path", "") for v in (raiz or {}).get("values", [])]
        fila["ficheros_raiz"] = len(nombres)
        if len(nombres) <= 1:
            fila["tipo"] = "vacio"
        else:
            otras = {"composer.json": "php", "go.mod": "go", "requirements.txt": "python",
                     "pyproject.toml": "python", "Gemfile": "ruby", "build.gradle": "gradle",
                     "package-lock.json": "node", "Chart.yaml": "helm",
                     "main.tf": "terraform", "Dockerfile": "docker"}
            fila["tipo"] = next((v for k, v in otras.items() if k in nombres), "otro")
    if pom:
        # OJO: en algunos workspaces los micros no heredan de spring-boot-starter-parent,
        # sino de un framework propio de la organizacion que es quien fija la version de
        # Spring. Por eso se captura el parent sea cual sea: ahi puede estar la deuda
        # tecnica de back, no necesariamente en una version de Spring que el repo declare
        # directamente.
        p = re.search(r"<parent>(.*?)</parent>", pom, re.DOTALL)
        if p:
            bloque = p.group(1)
            art = re.search(r"<artifactId>([^<]+)</artifactId>", bloque)
            ver = re.search(r"<version>([^<]+)</version>", bloque)
            fila["parent"] = art.group(1).strip() if art else ""
            fila["parent_ver"] = ver.group(1).strip() if ver else ""
            if fila["parent"] == "spring-boot-starter-parent":
                fila["spring"] = fila["parent_ver"]
        if not fila["spring"]:
            m = re.search(r"<spring-boot\.version>([^<]+)</spring-boot\.version>", pom)
            fila["spring"] = m.group(1).strip() if m else ""
        j = (re.search(r"<java\.version>([^<]+)</java\.version>", pom)
             or re.search(r"<maven\.compiler\.source>([^<]+)</maven\.compiler\.source>", pom)
             or re.search(r"<release>([^<]+)</release>", pom))
        fila["java"] = j.group(1).strip() if j else ""
        fila["tipo"] = "full" if fila["tipo"] == "front" else "back"
    return fila


def mayor(version: str) -> str:
    m = re.match(r"(\d+)", version or "")
    return m.group(1) if m else "?"


def resumen(campo: str, filas: list[dict]) -> str:
    c = Counter(mayor(f[campo]) for f in filas if f[campo])
    if not c:
        return "sin datos"
    return " · ".join(f"v{k}: {n}" for k, n in sorted(c.items(), key=lambda kv: -kv[1]))


def main() -> int:
    ap = argparse.ArgumentParser(description="Versiones reales de los repos de Bitbucket.")
    ap.add_argument("--detalle", action="store_true", help="Imprime las filas una a una")
    ap.add_argument("--hilos", type=int, default=8)
    ap.add_argument("--limite", type=int, default=0, help="Solo los N primeros (pruebas)")
    args = ap.parse_args()

    cabecera, ws = auth()
    print(f"Workspace {ws}: listando repos...", flush=True)
    repos = listar_repos(cabecera, ws, args.limite)
    print(f"{len(repos)} repos. Leyendo package.json y pom.xml de cada uno "
          f"({args.hilos} en paralelo)...", flush=True)

    with ThreadPoolExecutor(max_workers=args.hilos) as pool:
        filas = list(pool.map(lambda r: analizar(r, cabecera, ws), repos))

    salida = config.data_dir() / "inventario_repos.csv"
    salida.parent.mkdir(parents=True, exist_ok=True)
    with salida.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["slug", "tipo", "rama", "actualizado",
                                           "angular", "node", "spring", "java",
                                           "parent", "parent_ver", "ficheros_raiz"])
        w.writeheader()
        w.writerows(filas)

    con_datos = [f for f in filas if f["angular"] or f["parent"]]
    print(f"\n{'=' * 70}\nRESUMEN — {len(filas)} repos, {len(con_datos)} con manifiesto legible")
    print("=" * 70)
    print(f"  Angular     {resumen('angular', filas)}")
    print(f"  Spring Boot {resumen('spring', filas)}")
    print(f"  Java        {resumen('java', filas)}")
    parents = Counter(f"{f['parent']} {f['parent_ver']}" for f in filas if f["parent"])
    if parents:
        print("\n  Parent de Maven (es quien fija la version de Spring en este workspace):")
        for nombre, n in parents.most_common(8):
            print(f"    {nombre:<52} {n} repos")

    print("\nLOS MAS ATRASADOS")
    for campo, etiqueta in (("angular", "Angular"), ("parent_ver", "Parent corporativo")):
        candidatos = sorted((f for f in filas if f[campo] and mayor(f[campo]) != "?"),
                            key=lambda f: int(mayor(f[campo])))[:6]
        if candidatos:
            print(f"  {etiqueta}:")
            for f in candidatos:
                print(f"    {f['slug'][:42]:<44} {f[campo]:<12} (últ. cambio {f['actualizado']})")

    sin_nada = [f for f in filas if not f["angular"] and not f["parent"]]
    print(f"\nSIN package.json NI pom.xml: {len(sin_nada)} — desglosados, no todos son iguales")
    for tipo, n in Counter(f["tipo"] for f in sin_nada).most_common():
        etiqueta = {"vacio": "vacios (archivables)"}.get(tipo, tipo)
        print(f"    {etiqueta:<24} {n} repos")
    if args.detalle:
        print(f"\n{'REPO':<44} {'TIPO':<6} {'ANGULAR':<12} {'SPRING':<10} JAVA")
        for f in sorted(filas, key=lambda f: f["slug"]):
            print(f"  {f['slug'][:42]:<44} {f['tipo']:<6} {f['angular']:<12} "
                  f"{f['parent_ver']:<10} {f['java']}")
    print(f"\nCSV completo: {salida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
