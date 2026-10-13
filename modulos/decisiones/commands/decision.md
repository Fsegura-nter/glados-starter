# /decision — Registra una decisión donde corresponde

El activo de un responsable técnico no son las notas, son las **decisiones**. Un vault que
nunca registra ninguna lo arregla este comando, en diez segundos.

Una decisión que solo existe en una conversación **no existe**: cuando dentro de tres meses
alguien pregunte por qué se hizo así, la conversación ya no está.

## Entrada

`$ARGUMENTS` es lo que se decidió, en las palabras de quien lo pide. Puede venir vacío:
entonces se deduce de la conversación en curso y **se confirma antes de escribir nada**.

| Lo que se escribe | Qué se registra |
|---|---|
| `/decision el forecast genera peticiones el día 10, no el 1` | esa decisión, en el proyecto |
| `/decision con <cliente>: los becarios entran en V2` | acuerdo con cliente |
| `/decision` | la última decisión de la conversación, tras confirmarla |

---

## Fase 1 — Aislar la decisión

Una decisión, una invocación. Si en la conversación hay varias, tratarlas **de una en una**:
mezclarlas en una línea las hace imposibles de buscar después.

Lo que se registra tiene que ser **concreto y verificable**. «Mejorar el rendimiento» no es una
decisión; «paginación server-side en el listado de becarios, 50 por página» sí lo es.

Si lo que hay es una intención y no una decisión, decirlo y no escribir nada. Un registro de
decisiones lleno de intenciones deja de servir para nada.

---

## Fase 2 — Decidir dónde va

Tres destinos, y son excluyentes. Las carpetas de clientes y proyectos son las que declare
`.glados/settings.json` → `carpetas`; si no se han declarado, preguntar antes de escribir.

| Tipo | Dónde | Formato |
|---|---|---|
| **Acuerdo con el cliente** — alcance, plazos, prioridades, lo que se compromete | `<carpeta-clientes>/<Cliente>.md` → `## Acuerdos y decisiones` | `- **YYYY-MM-DD** — <decisión> — <quién>` |
| **Decisión técnica** — arquitectura, stack, contratos, patrones | `<carpeta-proyectos>/<Proyecto>.md` → `## Decisiones` | `- **YYYY-MM-DD** — <decisión> — <motivo>` |
| **Principio generalizable** — aplica más allá de este proyecto | `<carpeta-core>/principios.md` | como el resto de esa nota |

Si duda entre cliente y proyecto: **¿lo sabe el cliente?** Si el cliente lo ha aceptado o le
afecta, es acuerdo. Si es cómo lo construimos por dentro, es técnica.

**La entidad no se inventa.** Si no está claro a qué cliente o proyecto pertenece, preguntar y
enseñar las opciones.

Si la nota no tiene la sección, se crea en su sitio, respetando el orden de secciones de la
plantilla de ese tipo de nota.

---

## Fase 3 — Enseñar antes de escribir

Siempre, sin excepción:

```
→ <carpeta-proyectos>/<proyecto>.md · ## Decisiones

- **2026-09-29** — El Forecast genera las peticiones el día 10 del mes previo al Q — lo fija
  el KPI 1 del funcional, y el día 1 no da margen a revisarlas
```

Y esperar. Si se corrige la redacción, se reescribe; si se dice que va en otro sitio, se mueve.

**El «quién» y el «motivo» no se rellenan a ojo.** Si no se ha dicho quién lo decidió, se deja
el campo fuera antes que inventarlo. Un registro con datos inventados es peor que uno
incompleto: el incompleto se nota, el inventado no.

---

## Fase 4 — Escribir

Se añade **al final** de la sección, no al principio: se lee en orden cronológico.

Después, en una línea: dónde quedó y qué queda pendiente, si algo. Si la decisión afecta a un
proyecto con nota de estado desactualizada, proponer actualizar `## Estado actual` — proponer,
no hacerlo por cuenta propia.

---

## Reglas

- **Una decisión por invocación.**
- **No inventar** fecha distinta de hoy, quién, ni motivo. Lo que no se sabe, no se escribe.
- **No registrar intenciones** ni cosas que aún se están discutiendo. Si no está decidido, va
  al laboratorio de ideas, no aquí.
- Si la decisión **contradice** una ya registrada, decirlo y enseñar la anterior. No se borra la
  vieja: se añade la nueva y se anota que sustituye a la del `<fecha>`. El historial de por qué
  se cambió de opinión vale tanto como la decisión.
- Si la decisión es generalizable más allá del proyecto, después de registrarla proponer también
  la línea para el fichero de principios.
