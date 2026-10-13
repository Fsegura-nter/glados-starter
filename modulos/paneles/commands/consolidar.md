# /consolidar — Pasa a la ficha lo que el vault ya sabe

El vault tiene dos capas y la de abajo suele saber más que la de arriba. La carpeta de
memoria y la de fuentes guardan lo que se trabajó; las fichas de clientes y proyectos
deberían guardar lo que es cierto **hoy**. Nadie hace nunca el viaje de vuelta por su
cuenta: es fácil acabar con una ficha de pocas líneas y «pendiente» al lado de carpetas que
ya guardan decenas de memorias y varios funcionales indexados.

Esto lo cierra. **Una entidad por invocación.**

`PY` = el Python del entorno del kit, ejecutado desde la raíz del vault.

## Entrada

`$ARGUMENTS` es el nombre o el alias de un cliente o un proyecto. Si viene vacío, preguntar
cuál — no elegir uno.

---

## Fase 1 — Que el script haga el trabajo mecánico

```
PY .glados/consolidar.py <entidad> [-n 4] [--seccion "Contexto"]
```

Devuelve los **huecos** de la ficha (secciones vacías o marcadas como pendientes) y, por hueco,
los fragmentos candidatos con su referencia y su fecha. **No leer las memorias enteras antes de
esto:** el script ya hace la búsqueda, el filtrado por entidad y el recorte. Leer el material
completo cuesta tokens en cada repetición y es justo lo que el principio de «scripts antes que
tokens» prohíbe.

Si un fragmento se queda corto y la sección lo merece, **entonces sí** leer ese fichero con
`Read`. Uno, el que haga falta, no la carpeta.

Si el script dice que no hay ficha, ofrecer `/new-client` o `/new-project` y parar.

---

## Fase 2 — Leer las evidencias con desconfianza

Tres filtros antes de proponer nada:

- **`[VERIFICAR: más de 90 días]`** — el script lo marca. Ese material describe lo que era
  cierto entonces. Se propone igual, pero **diciendo la fecha en la propia línea** y señalando
  que hay que confirmarlo: las memorias son historia, no estado.
- **Relevancia real.** La búsqueda es léxica: devuelve lo más cercano, no lo que contesta la
  pregunta. Si las evidencias de «Contactos» hablan de arquitectura, **la sección no tiene
  fuente**, por muchos fragmentos que salgan. Decirlo en vez de estirar el material.
- **Contradicciones.** Si dos memorias dicen cosas distintas, gana la más reciente y **se
  menciona la otra**. Que alguien cambiara de opinión es información.

---

## Fase 3 — Proponer todo, escribir solo lo aprobado

Las propuestas se enseñan **todas juntas**, separadas por sección y cada una con sus fuentes,
para que se lean de una vez y se contesten de una vez. Lo que no se hace nunca es **escribir**
sin respuesta: se escriben solo las secciones que se aprueban, y las que se corrijan se
reescriben antes.

Para cada sección:

```
## Contexto          (hoy: "sector y alcance (pendiente)")

Propuesta:
  <una o dos frases con lo que dicen las evidencias, sin inventar nada que no esté en ellas>

Fuentes:
  · memoria/<cliente>/modelo-operativo.md (2026-09-01)
  · fuentes/<Cliente>/Documento Funcional.md
```

Y esperar. Sí, no, o corrección, por sección. **Nunca escribir sin esa respuesta**, ni aunque
antes se haya dicho «hazlo todo»: eso llena el vault de cosas que nadie ha leído, y una ficha
en la que no se confía no se consulta. Aprobar el alcance no es aprobar el contenido.

Reglas de redacción:

- **Estado, no historia.** La memoria dice «el 2026-08-31 se crearon 42 tarjetas»; la ficha dice
  qué es el módulo y cómo está. Si el dato solo tiene sentido con su fecha, va con su fecha.
- **Corto.** Una ficha es un mapa. Lo largo ya está en la carpeta de fuentes y lo busca el RAG.
- **Nada sin fuente.** Si hace falta una deducción para que la frase funcione, no se escribe:
  se pregunta.
- Respetar el frontmatter y el orden de secciones de la plantilla de ese tipo de nota.

---

## Fase 4 — Cerrar

Al terminar, tres líneas:

1. **Qué secciones se rellenaron** y cuánto creció la ficha.
2. **Qué sigue sin fuente**, como preguntas concretas. Estas son el producto más valioso del
   comando: son exactamente lo que el vault no sabe de un cliente activo.
3. Si aparecieron decisiones o acuerdos, proponer pasarlos por `/decision` para que queden
   fechados donde toca, en vez de fundidos en un párrafo.

---

## Reglas

- **Una entidad por invocación.**
- **No inventar.** Ni contactos, ni fechas, ni alcances. El hueco sin fuente se queda hueco y se
  convierte en pregunta.
- **No borrar** lo que ya había escrito en la ficha: se completa, no se sustituye. Si algo que
  hay escrito contradice a la evidencia, decirlo y preguntar cuál vale.
- Si al consolidar aparece un alias por el que se llama a la entidad y no está en `aliases`,
  añadirlo: es lo que alimenta el hook de contexto.
- Aplica igual a clientes y a proyectos.
