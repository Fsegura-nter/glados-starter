# /responde — Contesta un correo en nombre de quien usa el vault

Un correo concreto, cuando la persona lo decide. Lee el hilo, redacta como escribe ella y
deja el borrador en Gmail.

**No es** `/correos`. Ese vacía la bandeja de un periodo y clasifica; este contesta **uno**.
Si hace falta revisar todo lo pendiente, ese es el otro.

`PY` = el Python del entorno del kit (`%LOCALAPPDATA%\<nombre>\venv\Scripts\python.exe`, donde
`<nombre>` es el que fije `.glados/settings.json`), ejecutado desde la raíz del vault. Los
scripts citados abajo viven en la carpeta `.glados` del vault, una vez instalado el módulo.

## Entrada

`$ARGUMENTS` es texto libre, y trae dos cosas mezcladas que hay que separar:

1. **A qué correo** — un remitente, un asunto, un trozo de frase, o nada.
2. **Qué contestar** — opcional. La intención de quien pide la respuesta, en sus palabras.

Ejemplos de lo que se puede recibir:

| Lo que se escribe | A qué correo | Qué contestar |
|---|---|---|
| `/responde a <nombre> lo del sprint 7` | `from:<nombre> sprint 7` | sin indicación: deducir del hilo |
| `/responde a <nombre> que lo revisamos el lunes` | `from:<nombre>` | «lo revisamos el lunes» |
| `/responde al último de <nombre> diciéndole que sí` | `from:<nombre>`, el más reciente | conformidad |
| `/responde` | el último recibido | deducir del hilo |

**Si no hay indicación de qué decir, no inventar una postura.** Redactar lo que el hilo pide de
forma neutra y dejar `[entre corchetes]` cualquier compromiso, fecha o cifra que no se haya
dado explícitamente. Un borrador que promete algo que nadie prometió es peor que no tener
borrador.

---

## Fase 1 — Cargar el perfil

Leer el perfil de escritura (`perfil_escritura.md`, en la carpeta `core` del vault — la que
declare `.glados/settings.json` → `carpetas.core`, o `core` si no se ha declarado ninguna).
**Es la única fuente de su estilo.** Trae longitud típica, saludos y cierres con su
frecuencia, tratamiento y tics; y señala cuál es su marca más reconocible, que no es opcional.

Un matiz que el perfil da en números y hay que convertir en decisión: puede tener **dos
cierres casi empatados**, uno neutro y otro cercano. Se elige por interlocutor — cliente y
externos el neutro, equipo de confianza el cercano —, nunca al azar.

Si el fichero no existe, decirlo y parar. Lo genera
`PY .glados/gmail_perfil.py --n 500 --auditar` (varios minutos; lo lanza la persona, no el
asistente, sin supervisión).

---

## Fase 2 — Encontrar el correo

Convertir la parte identificadora en una consulta de Gmail. Los operadores que sirven:
`from:`, `subject:`, `to:`, `newer_than:`, `is:unread`, `has:attachment`, o texto suelto.

```
PY .glados/gmail_bandeja.py --consulta "<q>"
```

Con nombres propios, buscar por el nombre suelto, no por el correo completo. Si la búsqueda
con acento no devuelve nada, repetir sin él. Si sigue vacía, ampliar: quitar `newer_than`,
dejar solo el remitente.

- **Un resultado** → seguir.
- **Varios** → enseñar la lista corta (remitente, asunto, fecha) y **preguntar cuál**. No
  elegir por cuenta propia: contestar al hilo equivocado se envía igual de bien que al
  correcto.
- **Ninguno** → decirlo, enseñar la consulta usada, y preguntar. No fabricar un destinatario.

Si no se identificó ningún correo, coger el último recibido
(`--consulta "in:inbox newer_than:7d"`) y **confirmar cuál es antes de redactar**.

---

## Fase 3 — Leer la conversación entera

```
PY .glados/gmail_bandeja.py --hilo <id>
```

El hilo completo, del mensaje más viejo al más nuevo. **Siempre este modo, no `--leer`:** ese
da solo el último mensaje, y la mitad de las conversaciones se entienden al revés sin lo
anterior. Aquí se ve además qué se ha dicho ya en el hilo, para no contradecirse ni repetirse.

Fijarse en tres cosas antes de escribir:

- **Qué se pregunta exactamente**, que no siempre es lo que ocupa más líneas.
- **Si ya se respondió algo** en el hilo. El borrador continúa esa postura, no la reabre.
- **Quién está en el hilo.** Determina el registro y el cierre. Si hay externos o cliente, no
  se usa el tono de equipo.

---

## Fase 4 — Redactar

- **Corto.** El perfil da la mediana; quedarse por debajo si se puede.
- Saludo y cierre propios del perfil, con el cierre elegido por interlocutor.
- Tutea. En español, salvo que el hilo venga en inglés.
- Texto plano. Sin markdown, sin viñetas decorativas, sin negritas.
- **Un párrafo, una línea. Nunca cortar a mano a 80 columnas.** Gmail envía el texto plano
  respetando los saltos que lleve dentro, así que un cuerpo maquetado como se maqueta un
  fichero sale en una columna estrecha y rota en cualquier ventana ancha. El salto de línea
  solo separa párrafos o entradas de una lista; dentro de cada uno, la línea corre lo que
  haga falta y que ajuste el cliente de correo. Lo mismo con la sangría: al ajustarse, la
  continuación vuelve a la columna cero y queda peor que sin ella — numerar (`3.1.`) en vez
  de indentar.
- Responde a lo que se pregunta, en el primer párrafo. Sin preámbulo.
- `[entre corchetes]` todo dato que no se haya dado explícitamente. Nunca inventar fechas ni
  compromisos.
- Si el hilo pide una decisión técnica y hay contexto en el vault (las carpetas de proyectos
  y clientes), leerlo antes. Un borrador que ignora lo que ya se sabe se nota.

Enseñar el borrador en la terminal **antes** de crearlo:

```
Para: Nombre <correo>        (cc: ... si lo hay)
Asunto: Re: ...
─────────────────────────────────────────────
[el texto tal cual]
─────────────────────────────────────────────
```

Y decir en una línea qué decisión se ha tomado al redactar, si hubo alguna: qué cierre y por
qué, o qué se ha dejado en corchetes y a la espera de qué.

---

## Fase 5 — Dejarlo en Gmail

Si no se piden cambios, escribir el JSON en el directorio temporal de la sesión:

```json
[{"id": "<id del ÚLTIMO mensaje del hilo>", "cuerpo": "<texto>"}]
```

```
PY .glados/gmail_bandeja.py --borrador <ruta del json>
```

El id tiene que ser el del **último** mensaje del hilo: así el borrador queda colgando de la
conversación y responde a quien escribió el último, no a quien la empezó. `--hilo` lo dice al
final de su salida.

Devolver el enlace del borrador. **Nada se envía**: no hay código de envío en el repo, y el
envío es siempre decisión de la persona, desde Gmail.

---

## Reglas

- **Nunca enviar.** Ni pedir permiso para enviar: no existe la capacidad.
- Ante duda de a qué correo se refiere, **preguntar**. Es una pregunta; equivocarse de hilo es
  un correo mal contestado.
- No inventar datos. Corchetes.
- No añadir información que no se pidió incluir. Contestar lo preguntado, no lucirse.
- Si el correo original pide algo que no se puede o no se debe conceder por cuenta propia,
  decirlo en la terminal en una línea antes del borrador, y redactar la respuesta neutra.
- Si el hilo trae datos de cliente, se queda en Gmail y en la terminal: **no se copia al vault**
  salvo que se pida explícitamente.
