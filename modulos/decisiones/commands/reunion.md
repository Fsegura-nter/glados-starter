# /reunion — Deja una reunión escrita en sesenta segundos

Las reuniones suelen quedar sin rastro. No porque no importen, sino porque escribirlas a
mano cuesta más de lo que parece y siempre hay algo después.

Esto es el puente hasta que la transcripción automática lo haga sola: **preguntar poco,
escribir bien, y salir**.

## Entrada

`$ARGUMENTS` es el título, opcional. También vale pegar notas crudas después del título: si
vienen, se parsean en vez de preguntar.

| Lo que se escribe | Qué pasa |
|---|---|
| `/reunion seguimiento forecast` | pregunta lo mínimo y escribe |
| `/reunion` | pregunta también el título |
| `/reunion daily <proyecto>` + notas pegadas | parsea las notas, solo pregunta lo que falte |

---

## Fase 1 — Preguntar todo de golpe

**Una sola tanda de preguntas, no un interrogatorio.** Lo que hace falta:

1. **Con quién** — asistentes. Nombres sueltos valen.
2. **De qué cliente o proyecto** — determina `area`, `cliente` y `proyecto`.
3. **Qué se habló** — dos o tres líneas.
4. **Qué se decidió** — si se decidió algo.
5. **Qué hay que hacer** — acciones, con responsable si lo hay.

Lo que se pueda deducir del contexto de la sesión, **se deduce y se confirma**, no se pregunta.
Si se menciona un cliente cuyo alias no está en su ficha, añadirlo a `aliases`: es lo que
alimenta el hook de contexto.

---

## Fase 2 — Escribir la nota

Ruta: `<carpeta-reuniones>/YYYY-MM-DD <título>.md` (la carpeta es la que declare
`.glados/settings.json` → `carpetas.reuniones`). Plana, sin subcarpetas.

```markdown
---
tipo: reunion
area: <uno de los valores declarados en .glados/settings.json → areas>
cliente: "[[<Cliente>]]"
proyecto: "[[<Proyecto>]]"
fecha: YYYY-MM-DD
tags: [reunion]
---

# <Título>

**Asistentes:** <nombres>

## Temas
- <lo que se trató, una línea por tema>

## Decisiones
- <lo que se decidió>

## Acciones
- [ ] <qué> — <quién>
```

**`area` es obligatorio.** Sin él la reunión no aparece en el panel de su bloque, que es donde
se va a buscar. `cliente` y `proyecto` se dejan fuera si no aplican, vacíos antes que
inventados.

Las secciones sin contenido **se quitan**, no se dejan con un «_(nada)_» dentro. Una nota de
reunión con tres secciones vacías es ruido en el vault y en el índice.

---

## Fase 3 — Cerrar el círculo

Tres cosas después de escribir, en una sola línea cada una:

- **Decisiones:** ofrecer pasarlas por `/decision`, una a una, para que queden también en la
  ficha del cliente o del proyecto. La nota de reunión es el acta; la ficha es el estado.
- **Acciones:** recordar que los checkboxes salen solos en el panel de tareas. No hay que
  copiarlos.
- **Transcripción**, si la hay: va a la carpeta de fuentes del cliente, **nunca al cuerpo de
  la nota**, y después se reindexa para que la búsqueda la vea. Una transcripción entera
  dentro de un `.md` es justo lo que puede tumbar el visor de notas si supera el límite de
  tamaño por nota.

---

## Reglas

- **La nota es corta.** Es un acta, no una transcripción. Si hace falta el literal, está en
  la carpeta de fuentes.
- **No inventar asistentes, decisiones ni acciones.** Si no se dijo, no estuvo.
- **No atribuir una acción a alguien** que no se haya nombrado como responsable.
- Si la reunión tiene datos sensibles del cliente, se queda en el vault y nunca sale de él.
- Si ya existe una nota para esa fecha y ese título, **no se sobreescribe**: se pregunta si es
  continuación o una reunión distinta.
