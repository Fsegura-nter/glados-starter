# Diseño

Qué se construye y **por qué**. El `README` cuenta cómo se usa; esto cuenta las decisiones
y lo que costó aprenderlas. Si algo del código parece raro, probablemente esté explicado
aquí, y deshacerlo sin leer el motivo es cómo vuelven los fallos.

---

## 1 · Qué es

Un plugin de Claude Code que permite a una persona levantar en una tarde un ecosistema de
trabajo: una bóveda de markdown que se trabaja **desde la consola**, con un asistente de
personalidad propia, conectada a su correo, su Drive, su calendario y sus repositorios,
con hooks de sesión, búsqueda en dos capas y respaldo automático.

El usuario objetivo es un perfil técnico con Windows corporativo, Claude Code instalado, y
ninguna intención de leerse novecientas líneas de documentación.

El resultado medible: alguien escribe tres líneas y, menos de una hora después, tiene una
bóveda funcionando que sabe quiénes son sus clientes, le hace commit del trabajo al cerrar
la sesión y le habla con una voz que eligió.

## 2 · Qué no es

- **No es un fork de la bóveda de nadie.** Se copia la **maquinaria**, limpia de datos.
- **No es un producto mantenido.** Decisión explícita: cada bóveda diverge y mejora por su
  cuenta. **No hay soporte y no se promete nada.** Por eso el kit trae un diagnóstico: un
  ecosistema roto a los tres meses tiene que poder diagnosticarse solo.
  El empaquetado como plugin regala `/plugin update`, así que las mejoras del kit se pueden
  traer. Pero eso actualiza **el kit, nunca la bóveda**: lo generado es de quien lo generó
  y no se toca. El canal existe por el envoltorio, no por compromiso.
- **No migra una bóveda existente**, no instala Claude Code, y **no envía correo**.

## 3 · El hueco que llena

Hay varios proyectos públicos que generan una estructura de notas. Todos reparten **la
misma plantilla a todo el mundo**: carpetas fijas, vocabulario fijo, y el trabajo de
adaptarlo queda para después, que es cuando ya nadie lo hace.

Aquí la estructura **se propone** después de entrevistar a la persona y medir su material
real. Un perfil de QA sin clientes no recibe una carpeta de clientes. Un perfil de gestión
sin repositorios no recibe una de repositorios. Eso es la diferencia, y es casi todo el
valor.

## 4 · La frontera de privacidad

La decisión que condiciona el resto, y la que más preguntan:

- **Sin límites para leer en local. Cero datos hacia fuera.**
- La bóveda nace con `git init` **y sin remoto**, a propósito. El diagnóstico lo comprueba
  en su **primer** chequeo y avisa para siempre si algún día aparece uno. No hay dónde
  subir nada porque no se configura ningún sitio.
- **Las credenciales viven fuera de la bóveda y fuera de cualquier repositorio**, en
  `%LOCALAPPDATA%\<nombre>\secrets.json`. Nunca en una nota, nunca en una variable de
  entorno de usuario, nunca en el historial de la terminal: **se pegan en el fichero**, y
  la guía da la ruta y el nombre exacto de cada clave.
- **Los cuerpos de los correos no entran en la bóveda.** La fase de lectura guarda
  métricas y, como mucho, tres muestras de escritura de 300 caracteres, pasadas por un
  redactor que quita tokens, direcciones y números largos.
- El ámbito de Gmail que se pide **sí puede enviar** — no existe uno para borradores sin
  envío. Lo que garantiza que no se envíe nada es que **en todo el código no hay una
  llamada a `messages/send` ni a `drafts/send`**. Eso queda escrito en el `CLAUDE.md`
  generado, no escondido en un documento de diseño.

## 5 · Arquitectura

```
bootstrap.ps1          la parte mecánica: prerrequisitos, venv, fuente, núcleo, git init
nucleo/.glados/        los 15 scripts que viven DENTRO de la bóveda generada
nucleo/.claude/        plantilla de configuración y hooks
modulos/<nombre>/      cinco módulos opcionales, cada uno con su modulo.json
skills/ecosistema/     la skill que conduce las cinco fases, y sus cuatro guías
plantillas/            CLAUDE.md, estilo del asistente, plantillas de nota
herramientas/          utilidades del kit, que NO viajan a la bóveda
```

**Núcleo frente a módulos.** El núcleo es lo que toda bóveda necesita: configuración,
credenciales, redacción, hooks de sesión, búsqueda en dos capas, respaldo, el generador y
el diagnóstico. Un módulo es todo lo que depende de un servicio externo o de una forma de
trabajar concreta, y **se puede saltar sin romper nada**.

**La entrega es un plugin de marketplace, no un ZIP con un `.ps1`.** En un Windows
corporativo, `ExecutionPolicy` y la marca de Zona de Internet convierten el primer paso en
«ejecuta esto para poder ejecutar lo otro». `bootstrap.ps1` sigue existiendo, pero lo
invoca la skill desde una sesión que ya está corriendo.

## 6 · Las cinco fases

Con una regla por encima de todas: **ninguna fase avanza con una prueba de vida fallida.**

### Fase 1 · Entrevista

Ocho preguntas abiertas, en una sola tanda, no un formulario. Rol y equipo; con quién
trata cada semana; qué parte del trabajo repite siempre igual; si lleva clientes, repos o
ninguna de las dos cosas; cómo agrupa el trabajo en su cabeza; qué quiere que el asistente
haga sin que se lo pidan; host de GitLab si lo usa; idioma.

**No se pregunta nada que el material vaya a contestar mejor.** Nadie recuerda su propio
estilo de escritura, así que preguntarlo gasta paciencia y además se contesta mal.

### Fase 2 · Lectura

**La lee un script, no el modelo.** Devuelve **métricas agregadas**:

- **Correo** (un año, enviado y recibido, pasado por un filtro de ruido): interlocutores
  reales y frecuencia, dominios externos recurrentes, asuntos que se repiten, y el perfil
  de escritura — saludos, cierres, longitud media, tuteo o usted, tres muestras cortas.
- **Calendario** (un año): series recurrentes y su cadencia, con quién, duración. **De
  aquí salen las áreas de trabajo mejor que de ningún otro sitio.**
- **Drive**: carpetas con actividad propia, compartidas y con quién.
- **Repositorios** (hasta 3 niveles): remotos, lenguaje, commits propios, `README`.

El modelo lee ese resumen, nunca el material entero. Meter quinientos correos en un
contexto cuesta una fortuna, no es reproducible y no deja herramienta.

### Fase 3 · Propuesta

Se enseña, se corrige, y **no se escribe nada** hasta que haya un sí:

1. **El árbol de carpetas**, con una línea por carpeta diciendo **de qué dato sale**. Una
   carpeta que no se puede justificar con una métrica no entra.
2. **El vocabulario de áreas**, derivado de las series del calendario y los
   interlocutores.
3. **Los módulos** que se activarían, y por qué. Los que no, también.
4. **Tres personalidades candidatas**, presentadas **respondiendo a algo real** de la
   persona, un párrafo cada una. Se eligen oyéndolas, no leyendo su descripción.

Si una métrica contradice lo que se dijo en la entrevista, **se saca aquí**, con el dato
delante.

### Fase 4 · Generación

El modelo escribe un **plan en JSON**; un ejecutor lo aplica.

**Separar decidir de escribir es lo que hace esto relanzable.** Si la generación falla a
medias, se corrige el JSON y se vuelve a lanzar, en vez de confiar en que el modelo repita
sus propias decisiones. También es lo que permite probar la generación entera sin un
humano delante.

El ejecutor **valida el plan completo antes de tocar el disco**, **nunca pisa un fichero
que ya exista** —relanzar completa lo que falte y respeta lo que se haya editado a mano— y
si falla a mitad de la escritura **deshace lo que esa llamada había creado**. Media bóveda
es peor que ninguna: obliga a averiguar qué quedó a medias en vez de simplemente repetir.

El plan lo escribe un modelo de lenguaje, así que **cada ruta se trata como dato hostil**:
nada puede salirse de la bóveda, ni usar un nombre reservado de Windows, ni un componente
con punto o espacio final.

### Fase 5 · Verificación y cierre

El diagnóstico completo, su salida en pantalla, la lista de lo que queda a mano, el
comando para abrir la sesión definitiva, y la oferta de desinstalar el kit.

**El kit se desinstala al final y no antes**, porque borrar la herramienta antes de
comprobar el resultado es una decisión de humano con prisa. Y se ofrece, no se impone.

## 7 · La columna de pruebas de vida

Cada paso demuestra algo **mínimo, real y visible** antes de continuar. Nadie debería
llegar al minuto veinticinco para descubrir que el minuto cuatro estaba roto.

| Fase | Prueba de vida |
|---|---|
| Mecánica | `git`, `python`, `node` y `claude` responden; el venv importa sus dependencias; la fuente está registrada |
| Google | un correo leído · un evento · un nombre de fichero de Drive |
| Repos | un remoto resuelto · un `README` leído |
| Generación | el frontmatter cumple su vocabulario · ninguna nota pasa de 250 KB · los hooks compilan · hay un commit · una consulta léxica devuelve resultado |
| Cierre | el diagnóstico entero, con su código de salida |

**Las tres de Google se hacen por separado**, y eso no es un detalle: un servicio capado
por el departamento de sistemas no debe tumbar los otros dos. **Dos de tres es un
resultado válido.**

**Cuando una falla:** se para, se enseña el error exacto, y se ofrece seguir sin ese
módulo. Si se salta, **queda escrito en el `CLAUDE.md` de la bóveda generada** como
pendiente, para que el asistente sepa que le falta un brazo y lo diga en vez de fingir que
puede leer el correo.

> **Un ecosistema degradado que no sabe que lo está es peor que uno roto.**

El estado se guarda **por servicio, no por módulo**: un módulo no es un interruptor. Google
son tres cosas y una puede faltar sin tumbar las otras dos.

## 8 · La personalidad

Tres pasos:

1. **Seis arquetipos** de partida, descritos **por comportamiento** —registro, muletillas,
   prohibiciones—, nunca como «habla igual que tal personaje»: eso hereda un copyright y,
   peor, no dice nada útil sobre qué hace el asistente cuando algo falla.
2. **Afinado con el material real.** El perfil de escritura ajusta tuteo, longitud,
   formalidad y densidad técnica. Quien escribe correos de tres líneas no recibe un
   asistente que contesta en ensayos.
3. **Muestra, no descripción.** Cada candidata responde a algo real de la persona.

Sale en dos ficheros: el estilo de salida y la sección de tono del `CLAUDE.md`.

## 9 · Restricciones del entorno, y no son negociables

Tres cosas que parecen arbitrarias y no lo son:

- **Los comandos de los hooks van sin comillas y sin `&`.** Con comillas simples,
  PowerShell lee `'ruta' 'ruta'` como una cadena suelta y los hooks de cierre fallan con
  `ParserError` **en modo no interactivo** — y **en silencio**, porque en una terminal
  normal funcionan. Con `&` se arregla PowerShell y se rompe bash, donde manda el proceso
  a segundo plano.
- **Consecuencia: ni la bóveda ni el venv pueden vivir en una ruta con espacios.**
  `bootstrap.ps1` valida la ruta y la rechaza con el motivo escrito. Rechaza también
  tildes y `~`, lo que incluye las rutas cortas 8.3.
- **Ninguna nota pasa de 250 KB.** El visor parsea la bóveda entera al arrancar y el
  proceso de render muere por falta de memoria si el volumen es excesivo. Medido: una nota
  de 3,9 MB lo mata. Los datos pesados —venv, índice vectorial, base de datos— viven
  fuera, en `%LOCALAPPDATA%`: una base de datos dentro de una carpeta sincronizada se
  corrompe.

## 10 · Cómo se prueba sin gastar a una persona

- **`-DryRun`** — solo la comprobación previa, no toca nada.
- **`--simulado`** — la skill recorre las cinco fases con una persona ficticia y un
  paquete de datos falsos, **sin tocar ninguna cuenta real**. Es posible precisamente
  porque la generación está partida en plan JSON + ejecutor.
- **Piloto real** cuando la simulación pase limpia tres veces seguidas.

Medido: tres pasadas de unos 20 segundos, con salida idéntica y cero fallos en el
diagnóstico. La suite son 160 pruebas de comportamiento.

## 11 · Lo que salió mal, y lo que cambió por eso

Esta sección es la más útil del documento. Cada entrada costó encontrarla.

### Los ficheros descubribles tienen rutas fijas, y nada se queja si fallan

Claude Code descubre comandos, skills y agentes **solo** en `commands/`,
`skills/<nombre>/SKILL.md` y `agents/`, bajo `.claude`. Cuatro de los cinco módulos los
declaraban con destino a la carpeta de scripts, usando además nombres de carpeta que nadie
busca. **Once ficheros** se habrían copiado al disco y **no habrían existido** para quien
los instaló: cinco comandos, una skill y dos agentes.

Lo grave no es el fallo, es que **era silencioso**: el fichero está ahí, el instalador no
protesta, y el comando simplemente no aparece. Las pruebas de entonces solo comprobaban
que el fichero existiera en el repositorio.

Qué cambió: el manifiesto declara un destino por defecto y un mapa de excepciones por
prefijo; hay un **instalador** que lo honra —no prosa pidiéndole al modelo que copie
ficheros— y **se para** si un fichero descubrible fuera a aterrizar donde no se descubre;
y las pruebas comprueban la **ruta de instalación calculada**, no la existencia.

### El guardián de datos privados era invisible a sí mismo

El barrido que impide publicar datos privados llevaba sus patrones **escritos en su propio
código fuente** —un dominio interno, un dominio de correo corporativo y cuatro nombres de
cliente—, y la lista blanca del barrido **excluía ese mismo fichero**. Publicar el
repositorio habría publicado la lista de clientes de la empresa **dentro de la herramienta
cuyo único trabajo es impedirlo**, y la herramienta habría informado de cero hallazgos.

No lo encontró el barrido. Lo encontró un `grep` adversario sobre los ficheros
**rastreados por git**, hecho a propósito antes de crear el repositorio.

> **El barrido comprueba el disco; lo que se publica es el índice de git.** No son lo
> mismo, y esa diferencia es por donde se escapa una fuga.

Qué cambió: los patrones viven en un fichero local que está en `.gitignore`, con un
ejemplo publicado; **si falta, el script sale con código 2 y no barre nada**, porque un
barrido sin patrones que contesta «cero hallazgos» certifica un repositorio que nadie ha
mirado; la lista blanca está **vacía**, con el motivo escrito dentro para quien vaya a
añadirle una línea; y las pruebas que afirmaban una ausencia **nombrándola** ahora afirman
por forma.

Un fichero que necesita estar en una lista blanca es un fichero que nombra algo real, y
casi siempre se puede reescribir para que no lo nombre.

### Un respaldo global pisaba el de otra bóveda

El respaldo se llamaba `vault-<fecha>.zip`, un patrón global, y el destino es una carpeta
de sincronización que varias bóvedas de una misma máquina pueden compartir. Resultado: el
diagnóstico de una bóveda **recién creada** anunciaba un respaldo de hace una semana que
era de otra, y la poda podía borrar copias que no eran suyas.

Ahora el nombre lleva el del ecosistema, **y la fecha va anclada**: `<nombre>-*.zip`
seguiría casando con cualquier bóveda cuyo nombre empiece igual, así que una llamada
`boveda` se habría llevado los respaldos de `boveda-qa`.

### Un error de codificación escondido detrás de un aviso

`bootstrap.ps1` interpola rutas que vienen de fuera. PowerShell escribe en la página de
códigos del proceso, no en UTF-8, así que una ruta con un carácter fuera de ASCII volvía
en bytes crudos y hacía saltar un error de decodificación **en el hilo que lee la salida**
de cualquier llamante. En una terminal no se nota. La skill **sí captura** esa salida: allí
habría sido un valor vacío silencioso justo en la fase que guía a la persona.

Y una prueba llevaba días pasando a través de ese fallo, porque una excepción en un hilo
lector llega como **aviso**, no como error, y la prueba solo comprobaba el código de
salida.

Qué cambió: la salida se fuerza a UTF-8, la prueba exige **leer** el mensaje, y la
configuración de pruebas convierte esa clase de aviso en fallo. **El silencio era el
defecto, no el byte.**

### Un token en la URL del remoto no falla: cuelga

Con el token dentro de la URL, el Gestor de credenciales de Windows abre un diálogo
gráfico pidiendo confirmación. En una terminal integrada **ese diálogo no se ve**, y el
proceso espera para siempre una respuesta que nadie puede dar. No falla, así que no hay
mensaje de error que buscar.

Por eso la regla va en mayúsculas en la guía, y por eso existe el credential helper.

## 12 · Riesgos conocidos

| Riesgo | Mitigación |
|---|---|
| Datos privados en el repositorio público | Barrido con patrones fuera del repo, lista blanca vacía, y un `grep` sobre lo rastreado antes de publicar |
| El departamento de sistemas bloquea una instalación | Nada requiere administrador; la fuente va al registro del usuario; lo que no se pueda, se lista como pendiente |
| Una ruta con espacios rompe los hooks en silencio | Validación con rechazo y explicación |
| Abandono configurando el OAuth de Google | Guía literal, prueba de vida inmediata, y opción de saltar el módulo dejando rastro |
| Cuota de la API al barrer un año de correo | Lectura por lotes con reintentos; la ventana se puede reducir |
| El modelo inventa una estructura que no encaja | Nada se escribe antes de la fase 3; la propuesta se enseña entera y se corrige |
| Coste en tokens de la propuesta | La fase 2 entrega métricas agregadas, no material bruto |
| El marketplace queda desatendido | La entrada referencia el repositorio por nombre, no por URL de instancia; el `README` documenta la vía alternativa |

## 13 · Criterios de aceptación

1. Un Windows limpio con los cuatro prerrequisitos llega a bóveda funcionando **sin
   privilegios de administrador** y **sin ejecutar ningún `.ps1` a mano**.
2. `bootstrap.ps1` es idempotente: relanzarlo no rompe nada.
3. **Ninguna prueba de vida fallida deja avanzar en silencio.**
4. Un módulo saltado queda escrito en el `CLAUDE.md` de la bóveda generada.
5. La bóveda generada **no tiene remoto git**, y el diagnóstico lo verifica.
6. El modo simulado recorre las cinco fases **sin tocar una sola cuenta real**.
7. **El repositorio público no contiene ningún nombre de cliente, dominio interno, correo
   ni ruta personal.** Se verifica con un barrido antes de publicar.
8. Al reabrir la sesión, los hooks de la bóveda generada corren y el arranque saluda.

El criterio 7 es el que estuvo a punto de romperse, y lo cuenta la sección 11.

## 14 · Fuera de alcance

macOS y Linux · migración automática de una bóveda ya generada cuando el kit cambie ·
instalación de Claude Code · migración de una bóveda existente · integraciones fuera de
Google y GitLab · **cualquier automatización que envíe correo**.
