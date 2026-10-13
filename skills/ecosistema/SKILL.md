---
name: ecosistema
description: Levanta un ecosistema de trabajo completo — una bóveda de markdown que se trabaja desde consola, con personalidad propia, conectada al correo, Drive, calendario y repositorios, con hooks de sesión, búsqueda en dos capas y respaldo automático. Entrevista a la persona, lee su material real con un script, propone una estructura deducida de sus datos y la genera. Úsala cuando alguien escriba "/ecosistema" o pida montar su propia bóveda o su segundo cerebro. Acepta "--simulado" para recorrer las cinco fases con datos ficticios, sin tocar ninguna cuenta.
---

# /ecosistema — cinco fases con puerta

Levantas una bóveda de trabajo para la persona que tienes delante. No reparte una
plantilla: la entrevistas, lees su material real y **propones** una estructura que sale
de sus datos.

Argumento opcional: `--simulado`, que recorre las cinco fases con la persona ficticia de
`referencias/simulacion/` y sin tocar una sola cuenta. Úsalo para probar cambios en esta
skill.

## Las dos reglas que están por encima de todo

**1. Ninguna fase avanza con una prueba de vida fallida.** Cada fase demuestra algo
mínimo, real y visible antes de continuar. Cuando una falla: te paras, enseñas **el error
exacto** —no un resumen tranquilizador—, y ofreces seguir sin ese módulo. Si se salta,
lo escribes en `plan["pendientes_manuales"]` y en `plan["estado_modulos"]`. Nadie debe
llegar al minuto veinticinco para descubrir que el minuto cuatro estaba roto.

**2. Nada se escribe en disco antes de la fase 4.** Las fases 1 a 3 preguntan, miden y
proponen. La propuesta se enseña entera y se corrige hasta que haya un sí explícito.

Y una regla de material: **nunca pides un secreto por el chat, ni lo repites, ni lo
escribes.** Das la ruta del fichero y el nombre exacto de la clave. Ver
[`referencias/google-cloud.md`](referencias/google-cloud.md).

---

## Fase 0 · La parte mecánica

Tres preguntas, y las tres las necesita `bootstrap.ps1`:

1. **Nombre** de la bóveda.
2. **Dónde va** (por defecto `Escritorio\<nombre>`). **Sin espacios en la ruta.**
3. **¿Línea de estado?**

Después, desde la raíz del plugin:

```
powershell -NoProfile -ExecutionPolicy Bypass -File "${CLAUDE_PLUGIN_ROOT}/bootstrap.ps1" -Vault "<ruta>" -Nombre "<nombre>"
```

Añade `-ConStatusline` si dijeron que sí. Usa `-DryRun` antes si quieres comprobar
prerrequisitos sin tocar nada.

Comprueba prerrequisitos, valida la ruta, crea el entorno virtual, instala la fuente en
el registro del usuario, copia el núcleo, resuelve las plantillas de configuración e
inicializa el repositorio **sin remoto**.

> **Prueba de vida:** `git`, `python`, `node` y `claude` responden a `--version`; el
> entorno virtual importa sus dependencias; la fuente está registrada. Si la ruta se
> rechaza por tener espacios, **no la rodees con comillas ni busques un atajo**: pide
> otra ruta. Los comandos de los hooks van sin comillas a propósito, y un espacio los
> parte en silencio en las sesiones no interactivas.

---

## Fase 1 · Entrevista

Las ocho preguntas de [`referencias/entrevista.md`](referencias/entrevista.md), **en una
sola tanda**, en prosa, sin repreguntar lo que la fase 2 va a contestar mejor.

Con `--simulado`: lee las respuestas de `referencias/simulacion/persona.json` y no
preguntes nada.

---

## Fase 2 · Lectura

**La lectura la hace un script, no tú.** Tú lees métricas agregadas; el material entero
no entra en el contexto. Meter quinientos correos en una conversación cuesta una fortuna,
no es reproducible y no deja herramienta.

```
python <vault>/.glados/arranque_lectura.py --salida <tmp>/metricas.json --meses 12 [--repos "<ruta>"]
```

Con `--simulado`, o para probar sin cuentas:

```
python <vault>/.glados/arranque_lectura.py --fuente "${CLAUDE_PLUGIN_ROOT}/skills/ecosistema/referencias/simulacion/fuente.json" --salida <tmp>/metricas.json
```

Antes de esto, si el módulo `google` entra: la guía de
[`referencias/google-cloud.md`](referencias/google-cloud.md). Si entra `gitlab`:
[`referencias/gitlab.md`](referencias/gitlab.md).

Lo que devuelve, y de dónde sacar cada decisión:

| Métrica | Qué decide |
|---|---|
| `correo.interlocutores` | quiénes son sus clientes y cuáles son reales |
| `correo.asuntos_repetidos` | qué proyectos existen |
| `calendario.series` | **las áreas de trabajo** — mejor señal que la memoria |
| `drive.carpetas_con_actividad` | qué carpetas del árbol tienen sentido |
| `repos` | si hace falta carpeta de repositorios, y si no, no se crea |
| `escritura` | tuteo, longitud, saludo y cierre: afina el arquetipo |
| `avisos` | **léelos en voz alta.** Un buzón sin material útil no se disimula |

Los cuerpos de los correos no entran en la bóveda. Solo métricas y tres muestras cortas,
ya redactadas por el script.

> **Prueba de vida (Google):** un correo leído · un evento · un nombre de fichero de
> Drive, **los tres por separado**. Dos de tres es un resultado válido: el servicio que
> falle se marca y se anota, y los otros dos siguen.
>
> **Prueba de vida (repos):** un remoto resuelto · un `README` leído.

---

## Fase 3 · Propuesta

Se enseña, se corrige, y **no se escribe nada** hasta que haya un sí. Cuatro cosas, en
este orden:

1. **El árbol de carpetas**, con **una línea por carpeta diciendo de qué dato sale.** Si
   no puedes justificar una carpeta con una métrica, esa carpeta no va. Quien no tiene
   clientes no recibe `01_CLIENTES`; quien no tiene repos no recibe carpeta de repos.
2. **El vocabulario de áreas**, derivado de las series del calendario y de los
   interlocutores. Cerrado y corto: cada área que sobra es una vista que no agrupa nada.
3. **Los módulos** que se activarían, **y por qué cada uno**. Los que no, también: «no
   activo `gitlab` porque dijiste que no lo usas» es información.
4. **Tres personalidades candidatas** de
   [`referencias/arquetipos.md`](referencias/arquetipos.md), elegidas según el perfil de
   escritura, y **presentadas respondiendo a algo real suyo** —un correo suyo, una
   incidencia suya, una reunión de su calendario—, un párrafo cada una. Se eligen
   oyéndolas, no leyendo su descripción. Pueden mezclar dos o rechazar las tres.

Si una métrica contradice lo que dijeron en la entrevista, **sácalo aquí**, con el dato
delante y sin discutir: «dijiste que agrupas por cliente, y tu calendario tiene tres
series que no son de cliente. ¿Lo dejamos por cliente o por cadencia?».

---

## Fase 4 · Generación

Escribes un **plan en JSON**; `generar_vault.py` lo ejecuta. Separar decidir de escribir
es lo que hace esta fase relanzable: si falla a medias, se corrige el JSON y se vuelve a
lanzar, en vez de confiar en que repitas tus propias decisiones.

Claves que **lee el ejecutor**, y ninguna más:

| Clave | Obligatoria | Qué es |
|---|---|---|
| `asistente.nombre` | **sí** | nombra el fichero de estilo y el `CLAUDE.md` |
| `asistente.arquetipo` | no | se escribe en el `CLAUDE.md` |
| `areas` | **sí** (lista) | vocabulario cerrado. Toda `area` usada tiene que estar aquí |
| `carpetas` | **sí** (lista) | cada entrada necesita `ruta` |
| `notas` | **sí** (lista) | cada entrada necesita `ruta`; `frontmatter` objeto, `cuerpo` texto |
| `modulos` | no | se validan contra las carpetas de `modulos/` |
| `estado_modulos` | no | **una entrada por SERVICIO**, no por módulo. Lo que falte nace `sin_probar` |
| `pendientes_manuales` | no | lista de frases; van al `CLAUDE.md` generado |
| `vault` | no | procedencia: nombre e idioma. El ejecutor no lo usa |

**Los hooks no van en el plan.** Los escribe `bootstrap.ps1` al resolver
`.claude/settings.json` en la fase 0. Si la entrevista pidió un comportamiento que
depende de un módulo, lo que entra es el módulo, no un hook suelto.

Validar primero, siempre:

```
python <vault>/.glados/generar_vault.py <tmp>/plan.json --raiz "<vault>" --dry-run
python <vault>/.glados/generar_vault.py <tmp>/plan.json --raiz "<vault>"
```

El ejecutor valida el plan **entero** antes de tocar el disco, **nunca pisa un fichero
que ya exista**, y si falla a mitad de la escritura deshace lo que esa llamada había
creado. Media bóveda es peor que ninguna.

> **Prueba de vida:** el frontmatter cumple su propio vocabulario · ninguna nota pasa de
> 250 KB · los hooks compilan · `git log` tiene un commit · el índice tiene documentos y
> una consulta léxica devuelve resultado:
>
> ```
> python <vault>/.glados/index_docs.py --solo-lexico
> python <vault>/.glados/lexical.py "<una palabra de su material>"
> ```

### Instalar los módulos aprobados

**No copies ficheros a mano.** Hay un script, y existe porque esto ya salió mal una vez:

```
python "${CLAUDE_PLUGIN_ROOT}/herramientas/instalar_modulos.py" --vault "<vault>" --modulos google decisiones --dry-run --json
python "${CLAUDE_PLUGIN_ROOT}/herramientas/instalar_modulos.py" --vault "<vault>" --modulos google decisiones
```

Valida los manifiestos **enteros** antes de copiar nada, honra el `destino` de cada
módulo y su mapa `destinos`, **nunca pisa un fichero que ya exista** —relanzarlo completa
lo que falte y deja intacto lo que se haya tocado a mano— y **se para** si un fichero
descubrible fuera a aterrizar donde no se descubre.

Eso último no es fontanería. Los comandos, las skills y los agentes solo se descubren en
rutas fijas bajo `.claude`: `commands/`, `skills/<nombre>/SKILL.md` y `agents/`. Un
comando copiado a `.glados/` existe en el disco y **no existe para quien lo instaló**, y
nada se queja. El 2026-10-07, cuatro de los cinco módulos lo hacían así: once ficheros
—`/responde`, `/correos`, `/decision`, `/reunion`, `/consolidar` y la skill `/mr` con sus
dos agentes— se habrían instalado invisibles.

El informe en `--json` trae, por módulo, lo copiado, lo que ya estaba, las credenciales
que necesita y su **prueba de vida**. Córrela: la que pase marca `ok`; la que falle marca
`fallo` y su motivo entra en `pendientes_manuales`. En una pasada simulada **ninguna
prueba de vida real pasa**: los servicios se quedan `sin_probar`, y eso se dice en voz
alta en vez de disimularlo.

---

## Fase 5 · Verificación y cierre

```
python <vault>/.glados/doctor.py --vault "<vault>"
```

Diez chequeos. Enseña **su salida entera**, no un resumen. Avisos se toleran; un solo
`fallo` significa que esto no está terminado, y se dice así.

El primero de los diez es el que importa para la privacidad: **la bóveda no tiene remoto
git**. Nace sin él a propósito y el diagnóstico lo vigila para siempre.

Para cerrar, en este orden:

1. **La lista de lo que queda a mano**, leída en voz alta desde `pendientes_manuales`. Si
   está vacía, dilo también.
2. **El comando para abrir la sesión definitiva**, al portapapeles:
   ```
   cd "<vault>" ; claude
   ```
   Los hooks se leen al arrancar la sesión, así que los que acabas de escribir **no están
   vivos todavía**. Ese salto es inevitable —ningún diseño activa un hook en la misma
   sesión que lo escribe—, así que va **al final y una sola vez**, donde es un cierre y
   no una interrupción. La siguiente sesión es la primera en que su asistente le saluda
   por su nombre.
3. **La oferta de desinstalar el kit:** `/plugin uninstall glados-starter@nterfran`. Se
   ofrece, no se impone: quien quiera conservar el diagnóstico para dentro de tres meses
   puede decir que no. Y se ofrece **al final**, nunca antes de comprobar el resultado.

---

## Lo que esta skill no hace

- **No promete soporte.** El kit no se mantiene: cada bóveda divierte por su cuenta desde
  el minuto uno. Por eso existe el diagnóstico, y por eso todo lo que falte queda
  escrito en el `CLAUDE.md` en vez de en la memoria de nadie.
- **No migra una bóveda existente.** Genera una nueva.
- **No envía correo.** Crea borradores. No hay en todo el código una llamada al envío.
- **No toca nada fuera de la bóveda y del directorio de datos**, salvo las dos líneas de
  configuración de `git` del módulo `gitlab`, que se enseñan antes de ejecutarlas.
- **No sale a la red en modo simulado.** Si una pasada simulada necesita una cuenta, es
  un defecto de esta skill, no un límite de la simulación.
