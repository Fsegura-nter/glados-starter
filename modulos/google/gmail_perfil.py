#!/usr/bin/env python3
"""
gmail_perfil.py — Destila el estilo de escritura de quien usa el vault a partir de sus
correos enviados.

Por qué es un script y no una conversación: leer 500 correos con el modelo costaría una
fortuna en contexto, no sería repetible y no dejaría herramienta. Aquí el script lee los
500; el modelo lee la ficha de una página que produce.

Qué descarta, y por qué (lecciones aprendidas a golpes, con el perfil real):
  · **Respuestas a invitaciones de Calendar.** Gmail las guarda en Enviados y contaminan el
    perfil: una frase de tipo «<Nombre> ha rechazado esta invitación» puede salir decenas de
    veces como si fuera un saludo habitual. Se filtran por la consulta, por estructura y por
    contenido.
  · **La firma corporativa.** El logo, el cargo y la dirección inflan la mediana de palabras
    y líneas: medían la firma, no la escritura.
  · **La parte citada** de cada respuesta: solo interesa lo que escribió la propia persona.

Y tres defensas que faltaban en una primera versión:
  · **Reintento con retroceso**: una corrida sin reintento perdió la mitad de los correos
    por cuota.
  · **Caché versionada**: una caché de formato anterior se rechaza en vez de usarse a medias.
    Pasó: produjo un perfil con pinta de nuevo y la sección «Con quién» vacía.
  · **Ctrl+C dentro del bucle**: lo descargado se conserva de verdad.

Uso:
    python gmail_perfil.py --estimar          # cuántos hay y cuánto tarda. No descarga
    python gmail_perfil.py --n 500 --auditar  # descarga, destila y registra descartes
    python gmail_perfil.py --solo-cache       # recalcula sin tocar la red
"""
import argparse
import json
import re
import sys
import time
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config
from google_auth import access_token
from gmail_api import (PAUSA, REINTENTOS, CORTE_CITA, CORTE_FIRMA, ES_CALENDAR,
                       ES_AUTOMATICO, api_get_reintento, cuerpo_de,
                       tiene_calendario, cabecera, limpiar)
from redact import redactar

config.force_utf8()

# Si cambia lo que se guarda por correo, sube el número: una caché del formato anterior se
# rechaza en vez de usarse a medias.
ESQUEMA_CACHE = 2

API = "https://gmail.googleapis.com/gmail/v1/users/me"
CACHE = config.data_dir() / "gmail_cache" / "enviados.jsonl"
AUDITORIA = config.data_dir() / "gmail_cache" / "descartados.jsonl"
# "core" es un rol de carpeta como "clientes" o "proyectos": si `.glados/settings.json`
# no le da nombre, se usa "core" tal cual, sin ningún prefijo numérico de una convención
# personal.
NOMBRE_CORE = config.carpetas().get("core") or "core"
SALIDA = config.vault_path() / NOMBRE_CORE / "perfil_escritura.md"

# La consulta ya descarta lo que no queremos, para no gastar llamadas en bajarlo:
#   -filename:invite.ics  → respuestas a invitaciones de Calendar
#   -in:chats             → mensajes de chat
CONSULTA = "in:sent -filename:invite.ics -in:chats"

ES = {"que", "los", "las", "del", "para", "con", "una", "por", "más", "pero", "esta", "como"}
EN = {"the", "and", "for", "with", "this", "that", "from", "have", "will", "your", "about"}
EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
CIERRE = re.compile(r"(?i)^(un saludo|saludos|muchas gracias|mil gracias|gracias|"
                    r"best|best regards|regards|thanks|thank you|cheers|atentamente|"
                    r"un abrazo|abrazo)[\s,.!;:]*$")


def registro_de(msg: dict, cuerpo: str) -> dict:
    lineas = [l.strip() for l in cuerpo.splitlines() if l.strip()]
    try:
        fecha = parsedate_to_datetime(cabecera(msg, "Date"))
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=timezone.utc)
    except Exception:
        fecha = datetime.fromtimestamp(int(msg.get("internalDate", 0)) / 1000, timezone.utc)
    para = cabecera(msg, "To") or ""
    return {
        "_v": ESQUEMA_CACHE,
        "fecha": fecha.isoformat(),
        "hora": fecha.hour,
        "dia_semana": fecha.weekday(),
        "destinatarios": para.count("@"),
        "dominios": sorted({d.lower() for d in re.findall(r"[\w.\-+]+@([\w.\-]+)", para)}),
        "asunto_len": len(cabecera(msg, "Subject").split()),
        "palabras": len(cuerpo.split()),
        "lineas": len(lineas),
        "primera": lineas[0][:120] if lineas else "",
        "ultimas": [l[:80] for l in lineas[-4:]],
        "emojis": len(EMOJI.findall(cuerpo)),
        "preguntas": cuerpo.count("?"),
        "exclamaciones": cuerpo.count("!"),
        "tu": len(re.findall(r"\b(tú|te|ti|tuyo|puedes|tienes|dime)\b", cuerpo, re.I)),
        # Solo los pronombres inequívocos: `puede` y `tiene` son tercera persona de uso
        # corriente («esto puede fallar»), y contarlas inflaba el usted hasta casi empatar.
        "usted": len(re.findall(r"\b(usted|ustedes)\b", cuerpo, re.I)),
        "es": sum(1 for w in cuerpo.lower().split() if w.strip(".,;:") in ES),
        "en": sum(1 for w in cuerpo.lower().split() if w.strip(".,;:") in EN),
        "espacio_antes_signo": len(re.findall(r"\s[!?]", cuerpo)),
        "menciones": len(re.findall(r"@[A-ZÁÉÍÓÚÑ]\w+", cuerpo)),
        "muestra": cuerpo[:400],
    }


def listar_ids(n: int, token: str) -> list[str]:
    ids, pagina = [], None
    while len(ids) < n:
        params = {"q": CONSULTA, "maxResults": min(100, n - len(ids))}
        if pagina:
            params["pageToken"] = pagina
        datos = api_get_reintento(f"{API}/messages", token, params)
        if not datos:
            break
        ids += [m["id"] for m in datos.get("messages", [])]
        pagina = datos.get("nextPageToken")
        if not pagina:
            break
    return ids


def descargar(n: int, auditar: bool) -> list[dict]:
    token = access_token()
    ids = listar_ids(n, token)
    print(f"  {len(ids)} candidatos tras filtrar invitaciones y chats.", flush=True)

    registros: list[dict] = []
    descartados: list[dict] = []
    inicio = time.time()
    try:
        for i, mid in enumerate(ids, 1):
            if i % 25 == 0:
                pasado = time.time() - inicio
                queda = int((pasado / i) * (len(ids) - i))
                print(f"    {i}/{len(ids)} · {int(pasado)}s · quedan ~{queda // 60}m{queda % 60:02d}s"
                      f" · válidos {len(registros)} · descartados {len(descartados)}", flush=True)
            time.sleep(PAUSA)
            msg = api_get_reintento(f"{API}/messages/{mid}", token, {"format": "full"})
            if not msg:
                descartados.append({"id": mid, "motivo": "no se pudo descargar"})
                continue
            payload = msg.get("payload", {})
            if tiene_calendario(payload):
                descartados.append({"id": mid, "motivo": "parte text/calendar"})
                continue
            bruto = cuerpo_de(payload)
            if ES_CALENDAR.search(bruto[:600]):
                descartados.append({"id": mid, "motivo": "texto de notificación de Calendar"})
                continue
            if ES_AUTOMATICO.search(bruto[:300]):
                descartados.append({"id": mid, "motivo": "notificación automática de Drive"})
                continue
            cuerpo = limpiar(bruto)
            if len(cuerpo.split()) < 3:
                descartados.append({"id": mid, "motivo": "vacío tras quitar cita y firma"})
                continue
            registros.append(registro_de(msg, cuerpo))
    except KeyboardInterrupt:
        # Se captura DENTRO de la función: así los registros ya obtenidos no se tiran.
        print(f"\n  Cortado a mano. Se conservan los {len(registros)} correos ya descargados.",
              flush=True)

    print(f"\n  Válidos: {len(registros)} · descartados: {len(descartados)}", flush=True)
    for motivo, cuantos in Counter(d["motivo"] for d in descartados).most_common():
        print(f"    {cuantos:>4}  {motivo}", flush=True)
    if auditar and descartados:
        AUDITORIA.parent.mkdir(parents=True, exist_ok=True)
        with AUDITORIA.open("w", encoding="utf-8") as f:
            for d in descartados:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"  Auditoría de descartes: {AUDITORIA}", flush=True)
    return registros


# ─── caché ────────────────────────────────────────────────────────────────────

def guardar_cache(registros: list[dict]) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    with CACHE.open("w", encoding="utf-8") as f:
        for r in registros:
            f.write(json.dumps({**r, "_v": ESQUEMA_CACHE}, ensure_ascii=False) + "\n")


def fecha_cache() -> str:
    try:
        return datetime.fromtimestamp(CACHE.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "?"


def leer_cache() -> list[dict]:
    """Devuelve la caché solo si es del formato actual. Si es antigua lo dice y devuelve
    vacío: mejor ningún perfil que uno que parece bueno y no lo es."""
    if not CACHE.exists():
        return []
    with CACHE.open(encoding="utf-8") as f:
        registros = [json.loads(l) for l in f if l.strip()]
    if not registros:
        return []
    if registros[0].get("_v") != ESQUEMA_CACHE:
        print(f"  La caché ({len(registros)} correos, {fecha_cache()}) es de un formato anterior "
              f"al actual (v{ESQUEMA_CACHE}): NO se usa.", flush=True)
        print("  Hay que descargar de nuevo: python gmail_perfil.py --n 500", flush=True)
        return []
    return registros


# ─── análisis ─────────────────────────────────────────────────────────────────

def normaliza_saludo(linea: str) -> str:
    l = re.sub(r"[^\wáéíóúñü\s]", "", linea.lower()).strip()
    return " ".join(re.sub(r"\s+", " ", l).split()[:3])


def analiza(registros: list[dict]) -> dict:
    # Segunda pasada del filtro de automáticos: así una caché ya descargada se limpia sin
    # volver a pedir todos los correos a Gmail.
    antes = len(registros)
    registros = [r for r in registros
                 if not ES_AUTOMATICO.search((r.get("primera", "") + " " + r.get("muestra", ""))[:300])]
    if len(registros) != antes:
        print(f"  Descartados al analizar: {antes - len(registros)} automáticos de Drive.", flush=True)
    if not registros:
        return {}
    pal = sorted(r["palabras"] for r in registros)
    saludos = Counter(normaliza_saludo(r["primera"]) for r in registros if r["primera"])
    cierres: Counter = Counter()
    for r in registros:
        for l in r["ultimas"]:
            if CIERRE.match(l.strip()):
                cierres[l.strip().lower().rstrip(",.!;: ")] += 1
    dominios: Counter = Counter()
    for r in registros:
        for d in r.get("dominios", []):
            dominios[d] += 1
    fechas = sorted(r["fecha"][:10] for r in registros)
    return {
        "n": len(registros),
        "rango": (fechas[0], fechas[-1]),
        "mediana_palabras": pal[len(pal) // 2],
        "media_palabras": round(sum(pal) / len(pal)),
        "p90_palabras": pal[int(len(pal) * 0.9)],
        "cortos_pct": round(100 * sum(1 for p in pal if p <= 40) / len(pal)),
        "mediana_lineas": sorted(r["lineas"] for r in registros)[len(registros) // 2],
        "saludos": [(s, n) for s, n in saludos.most_common(12) if s],
        "cierres": cierres.most_common(6),
        "dominios": dominios.most_common(8),
        "horas": Counter(r["hora"] for r in registros).most_common(5),
        "dias": Counter(r["dia_semana"] for r in registros),
        "ingles_pct": round(100 * sum(1 for r in registros if r["en"] > r["es"]) / len(registros)),
        "emojis_pct": round(100 * sum(1 for r in registros if r["emojis"]) / len(registros)),
        "preguntas_media": round(sum(r["preguntas"] for r in registros) / len(registros), 1),
        "excl_media": round(sum(r["exclamaciones"] for r in registros) / len(registros), 1),
        "tu_vs_usted": (sum(r["tu"] for r in registros), sum(r["usted"] for r in registros)),
        "varios_dest_pct": round(100 * sum(1 for r in registros
                                           if r.get("destinatarios", 1) > 1) / len(registros)),
        # None, no 0, cuando la caché es de antes de medir esto: un 0% sería mentira.
        "espacio_signo_pct": (round(100 * sum(1 for r in registros
                                              if r.get("espacio_antes_signo", 0)) / len(registros))
                              if any("espacio_antes_signo" in r for r in registros) else None),
        "menciones_pct": (round(100 * sum(1 for r in registros
                                          if r.get("menciones", 0)) / len(registros))
                          if any("menciones" in r for r in registros) else None),
        "usted_fiable": all("espacio_antes_signo" in r for r in registros),
        "muestras": [r["muestra"] for r in registros[:3]],
    }


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]


def escribir(p: dict, origen: str) -> None:
    if not p:
        print("Sin datos que escribir.")
        return
    tu, usted = p["tu_vs_usted"]
    l = [
        "---", "tags: [core, perfil, correo]", f"fecha: {datetime.now():%Y-%m-%d}", "---", "",
        "# Perfil de escritura", "",
        f"Destilado de **{p['n']} correos enviados** ({p['rango'][0]} … {p['rango'][1]}), sin "
        "invitaciones de Calendar, sin la parte citada y sin la firma corporativa.",
        "",
        f"**Origen de los datos:** {origen}.",
        "**Generado, no editar a mano**: se regenera con `python gmail_perfil.py --n 500`.",
        "", "Al redactar en su nombre, esto es lo que hay que respetar.", "",
        "## Longitud", "",
        "| Mediana | Media | Percentil 90 | Cortos (≤40 palabras) | Líneas (mediana) |",
        "|---|---|---|---|---|",
        f"| **{p['mediana_palabras']}** palabras | {p['media_palabras']} | {p['p90_palabras']} | "
        f"**{p['cortos_pct']}%** | {p['mediana_lineas']} |", "",
        "## Saludos", "",
    ]
    for texto, n in p["saludos"]:
        l.append(f"- `{texto}` — {n} veces")
    l += ["", "## Cierres", ""]
    if p["cierres"]:
        for texto, n in p["cierres"]:
            l.append(f"- `{texto}` — {n} veces")
    else:
        l.append("- _Ninguno recurrente: suele acabar sin despedida explícita._")
    l += [
        "", "## Tono y forma", "",
        f"- **Idioma:** {100 - p['ingles_pct']}% en español, {p['ingles_pct']}% en inglés.",
        f"- **Tratamiento:** {tu} marcas de *tú* frente a {usted} de *usted* → "
        + ("tutea por defecto." if tu > usted else "trata de usted por defecto."),
        f"- **Emojis:** en el {p['emojis_pct']}% de los correos."
        + (" Prácticamente nunca." if p["emojis_pct"] < 10 else ""),
        f"- **Preguntas:** {p['preguntas_media']} por correo · **exclamaciones:** {p['excl_media']}.",
        f"- **Varios destinatarios:** {p['varios_dest_pct']}% de los correos.",
        "",
        "### Tics propios — lo que delata quién lo escribió",
        "",
    ]
    if p["espacio_signo_pct"] is None:
        l += ["- _Sin medir: la caché es anterior a estas métricas. Regenerar con "
              "`--n 500` para obtenerlas._"]
    else:
        l += [
            f"- **Espacio antes del signo de exclamación** («Buenos días !»): en el "
            f"{p['espacio_signo_pct']}% de los correos.",
            f"- **Menciona con `@Nombre`** en el cuerpo: {p['menciones_pct']}% de los correos.",
        ]
    if not p["usted_fiable"]:
        l += ["- _El recuento de «usted» viene de una medición anterior que contaba `puede` y "
              "`tiene`, así que está inflado. La conclusión (tutea) sí es válida._"]
    l += [
        "", "## Cuándo escribe", "",
        "- Horas: " + ", ".join(f"**{h}:00** ({n})" for h, n in p["horas"]),
        "- Días: " + ", ".join(f"{DIAS[d]} {n}" for d, n in sorted(p["dias"].items())),
        "", "## Con quién", "",
    ]
    if p["dominios"]:
        for dominio, n in p["dominios"]:
            l.append(f"- `{dominio}` — {n} correos")
    else:
        l.append("- _Sin datos de destinatarios en esta corrida._")
    l += ["", "## Muestras literales", "",
          "_Principio de tres correos reales, ya limpios, para calibrar el registro:_", ""]
    for m in p["muestras"]:
        l += ["```", m.strip()[:320], "```", ""]

    contenido, hallados = redactar("\n".join(l))
    if hallados:
        contenido += f"\n> [!warning] Se redactaron credenciales: {', '.join(hallados)}\n"
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(contenido, encoding="utf-8")
    print(f"\nPerfil escrito en {SALIDA.relative_to(config.vault_path())} · origen: {origen}")
    if hallados:
        print(f"  Venían credenciales en los correos y se redactaron: {hallados}")


def estimar(n: int) -> int:
    token = access_token()
    ids = listar_ids(n, token)
    muestra = time.time()
    api_get_reintento(f"{API}/profile", token)
    ida_vuelta = max(0.15, time.time() - muestra)
    segundos = int(len(ids) * (ida_vuelta + PAUSA))
    print(f"\n  Consulta   : {CONSULTA}")
    print(f"  Candidatos : {len(ids)} correos")
    print(f"  Ida y vuelta medida: {ida_vuelta:.2f} s · pausa {PAUSA} s")
    print(f"  Estimación : ~{segundos // 60} min {segundos % 60:02d} s")
    print(f"\n  Caché actual: {'ninguna' if not CACHE.exists() else fecha_cache()}")
    print("  Se puede cortar con Ctrl+C: lo descargado se conserva y se destila.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--solo-cache", action="store_true")
    ap.add_argument("--estimar", action="store_true")
    ap.add_argument("--auditar", action="store_true")
    args = ap.parse_args()

    if args.estimar:
        return estimar(args.n)

    if args.solo_cache:
        registros = leer_cache()
        if not registros:
            return 1
        origen = f"caché del {fecha_cache()} ({len(registros)} correos), sin descargar"
        print(f"Caché: {len(registros)} correos del {fecha_cache()}.")
    else:
        registros = descargar(args.n, args.auditar)
        if registros:
            guardar_cache(registros)
            origen = f"descarga en vivo del {datetime.now():%Y-%m-%d %H:%M}"
            print(f"  Caché: {CACHE}")
        else:
            # Sin descarga no se inventa un perfil: se dice y se sale. Antes caía a la caché
            # en silencio y producía un perfil viejo con pinta de nuevo.
            print("\nNo se descargó ningún correo.")
            print("  ¿Autorizado? python google_auth.py check")
            print("  Para recalcular con la caché, si la hay: --solo-cache")
            return 1
    escribir(analiza(registros), origen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
