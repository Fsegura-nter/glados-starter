# /correos — Triage de bandeja de entrada

Procesa la bandeja de quien usa el vault, clasifica, prioriza y deja **borradores en Gmail**
que suenen a ella.

## Por qué está partido en capas

Leer cada hilo con el MCP de Gmail son decenas de miles de tokens **cada vez**, y buena parte
se descarta como ruido. Por eso:

1. **El estilo se lee de un perfil ya destilado** (`gmail_perfil.py`), no se reconstruye en
   cada ejecución a partir de los últimos enviados: más barato y con muchísima más muestra.
2. **Los hilos no se leen uno a uno con el MCP.** Un script devuelve una tabla compacta, y
   solo se piden completos los pocos que hay que contestar.

Y los borradores **se crean en Gmail**, no se quedan en la conversación para copiarlos a mano.

`PY` en los comandos de abajo es el Python del entorno del kit
(`%LOCALAPPDATA%\<nombre>\venv\Scripts\python.exe`), ejecutado desde la raíz del vault. Los
scripts citados viven en `.glados`, una vez instalado el módulo.

## Parámetro de entrada

`$ARGUMENTS` es el periodo: nada o `1d` (24 h), `3d`, `1w`, `2w`. Si no se reconoce, preguntar
antes de seguir.

---

## Fase 1 — Cargar el perfil de escritura

Leer `perfil_escritura.md` (carpeta `core` del vault). **Es la única fuente de su estilo**: no
deducirlo de los correos, no mezclarlo con impresiones propias, no repetir aquí sus cifras (si
se duplican, un día dejan de coincidir).

Ese fichero trae la longitud típica, los saludos y cierres con su frecuencia, el tratamiento,
los tics y con quién habla. Marca cuál es su tic más reconocible; respetarlo no es opcional:
es lo que distingue un borrador suyo de uno genérico.

Un matiz que el perfil da en números y que hay que convertir en decisión: puede tener **dos
cierres casi empatados**, uno neutro y otro cercano. Elegir por interlocutor, no al azar —
cliente y externos el neutro; equipo de confianza el cercano. Acertar la mitad de las veces se
nota.

Si el fichero no existe, decirlo y parar:
`PY .glados/gmail_perfil.py --n 500 --auditar` lo genera (varios minutos; lo lanza la persona).

---

## Fase 2 — Tabla de no leídos

```
PY .glados/gmail_bandeja.py --listar <periodo>
```

Devuelve una fila por correo: id, fecha, remitente, asunto y 160 caracteres de cuerpo ya
limpio, sin firma ni hilo citado.

- **`[AUTO:motivo]` es ruido comprobado**, no una sospecha: sale de `List-Unsubscribe`,
  `Precedence: bulk`, remitente `noreply` o `Auto-Submitted` (filtro compartido con el resto
  del ecosistema). Va directo a RUIDO sin gastar razonamiento en ello. Solo rescatarlo si el
  asunto delata algo que de verdad requiere acción.
- **`[adj:n]`** avisa de adjuntos, que suelen indicar petición real.
- Si el script avisa de correos que no pudo leer, **decirlo**: no están en la tabla y no se
  puede concluir que no existan.

---

## Fase 3 — Clasificar desde la tabla

Cuatro categorías, decididas con lo que hay en la tabla. No hace falta abrir nada todavía.

**ACCIÓN INMEDIATA** — respuesta o decisión en 24-48 h con impacto real: decisiones de negocio,
peticiones de cliente o de superiores, fechas límite, aprobaciones, bloqueos. No responder
tiene consecuencias visibles.

**SEGUIMIENTO** — hay que responder, pero aguanta 2-5 días sin daño.

**INFORMATIVO** — solo leer. Informes, FYI, confirmaciones de algo que ya se sabe.

**RUIDO** — newsletters, marketing, notificaciones de sistemas, alertas. Todo lo marcado
`[AUTO:*]` empieza aquí.

Para ACCIÓN INMEDIATA, anotar además quién escribe (cliente, superior, equipo, externo), qué
pide exactamente y la fecha límite, explícita o implícita.

---

## Fase 4 — Leer solo lo que se va a contestar

```
PY .glados/gmail_bandeja.py --leer <id> <id> ...
```

Solo los de ACCIÓN INMEDIATA. Devuelve el cuerpo limpio, el destinatario, el cc y el id de
hilo. Avisa de cuántos caracteres de hilo previo recortó: si la petición no se entiende sin
ese contexto, hay que pedirlo antes de redactar, no adivinar.

---

## Fase 5 — Redactar y crear los borradores en Gmail

Redactar cada respuesta respetando el perfil de la Fase 1:

- **Corto.** El perfil da la mediana; quedarse por debajo si se puede. Va al grano.
- Saludo y cierre de los que usa, con el cierre elegido por interlocutor.
- Tutea. En español salvo que el original venga en inglés, y entonces todo en inglés.
- Texto plano, sin markdown, sin viñetas decorativas.
- `[entre corchetes]` donde no se pueda saber un dato concreto: fecha, nombre, cifra. **Nunca
  inventarlo.** Un corchete es honesto; un dato falso en un correo a un cliente, no.
- No suena a IA. Suena a quien lo firma, que escribe afirmando y sin florituras.

Escribir un JSON en el directorio temporal de la sesión con una entrada por respuesta:

```json
[
  {"id": "<id del correo original>", "cuerpo": "<texto del borrador>"},
  {"id": "...", "cuerpo": "...", "cc": "opcional@ejemplo.com"}
]
```

Y crearlos:

```
PY .glados/gmail_bandeja.py --borrador <ruta del json>
```

El script saca de la fuente el destinatario, el asunto y las cabeceras de hilo, así que el
borrador aparece **dentro de su conversación** en Gmail. Devuelve un enlace por borrador.

**No se envía nada.** El repo no tiene código de envío, a propósito: el permiso de Google sí
lo permitiría, así que la garantía es esa ausencia. Enviar es siempre decisión de la persona,
desde Gmail.

---

## Fase 6 — Salida en terminal

```
╔══════════════════════════════════════════════════════════════╗
║  CORREOS · [periodo]  ·  [fecha de hoy]                      ║
╚══════════════════════════════════════════════════════════════╝

  No leídos procesados: X   ·   Borradores creados: N

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  ACCIÓN INMEDIATA (N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[1] De: Nombre Apellido <email@dominio.com>
    Asunto: "Asunto del correo"
    Pide: [qué pide exactamente y para cuándo]

    Borrador en Gmail → [enlace que devolvió el script]
    ┌──────────────────────────────────────────────────────────
    │ [el texto tal cual se creó]
    └──────────────────────────────────────────────────────────

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  SEGUIMIENTO (N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[N] De: Nombre · Asunto: "..." · [1 línea de contexto]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  INFORMATIVO (N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[N] De: Nombre · Asunto: "..."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  RUIDO (N)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  → N correos automáticos. Sin acción.
```

Omitir las secciones vacías. Si no hay nada nuevo: `Sin correos no leídos en [periodo].`

---

## Reglas

- **Los borradores van a Gmail.** Enseñar también el texto en terminal, para que se pueda
  descartar de un vistazo sin abrir el navegador.
- **Nada se envía.** Ni con confirmación: no hay código para ello.
- No inventar información que no esté en el correo. Corchetes.
- Prioridad dentro de ACCIÓN INMEDIATA: clientes, después superiores, después equipo.
- Los borradores son puntos de partida, no obras terminadas. No sobreexplicarlos.
- Si un correo trae hilo y la petición no se entiende sin él, leer el contexto antes de
  redactar. Un borrador que responde a lo que no se preguntó es peor que ninguno.
