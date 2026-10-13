# GLaDOS Starter

Un plugin de Claude Code que **te entrevista, lee tu trabajo real y genera tu propia
bóveda** de markdown: una carpeta de notas que se trabaja desde la consola, con un
asistente de personalidad propia, conectada a tu correo, tu Drive, tu calendario y tus
repositorios, con hooks de sesión, búsqueda en dos capas y respaldo automático.

**No reparte una plantilla.** Los proyectos equivalentes te dan la misma estructura que a
todo el mundo. Este pregunta primero, mide tu material con un script y **propone** un
árbol que sale de tus datos: quien no tiene clientes no recibe una carpeta de clientes;
quien no tiene repositorios no recibe una de repositorios.

---

## Instalación

Tres líneas dentro de Claude Code, desde cualquier carpeta:

```
/plugin marketplace add Fsegura-nter/nter-fran
/plugin install glados-starter@nterfran
/ecosistema
```

A partir de la tercera línea te lleva de la mano. **No hay nada que descargar y ejecutar
a mano**, y es a propósito: en un Windows corporativo, un `.ps1` bajado de internet
choca con `ExecutionPolicy` y con la marca de Zona de Internet, y el primer paso se
convierte en «ejecuta esto para poder ejecutar lo otro».

### Qué tiene que haber antes

| | |
|---|---|
| Windows 10 o superior | **El kit es solo Windows.** No hay camino para macOS ni Linux |
| Claude Code | la sesión desde la que se lanza todo |
| `git`, `python` 3.12+, `node` | se comprueban los cuatro antes de tocar nada |

Sin privilegios de administrador en ningún paso.

### Probarlo sin tocar ninguna cuenta

```
/ecosistema --simulado
```

Recorre las cinco fases con una persona ficticia y un paquete de datos falsos. Tarda unos
veinte segundos y no habla con Google ni con GitLab. Sirve para ver la forma de la cosa
antes de darle tus credenciales.

---

## Qué pasa cuando lo lanzas

Cinco fases, y **ninguna avanza con una prueba de vida fallida**: cada paso demuestra
algo mínimo y visible antes de seguir. Nadie debería llegar al minuto veinticinco para
descubrir que el minuto cuatro estaba roto.

| Fase | Qué hace | Prueba de vida |
|---|---|---|
| **0 · Mecánica** | Comprueba prerrequisitos, crea el entorno virtual, copia el núcleo, inicializa git **sin remoto** | los cuatro programas responden; el entorno importa sus dependencias |
| **1 · Entrevista** | Ocho preguntas abiertas, en una tanda | — |
| **2 · Lectura** | Un **script** barre tu correo, calendario, Drive y repositorios de un año y devuelve **métricas agregadas** | un correo leído · un evento · un fichero de Drive, **por separado** |
| **3 · Propuesta** | Te enseña el árbol, las áreas, los módulos y **tres personalidades candidatas**, cada una respondiendo a algo real tuyo | nada se escribe hasta que digas sí |
| **4 · Generación** | Escribe un plan en JSON y lo ejecuta | el frontmatter cuadra · ninguna nota pasa de 250 KB · los hooks compilan · una búsqueda devuelve resultado |
| **5 · Verificación** | Diez chequeos, la lista de lo que queda a mano, y el comando para abrir tu primera sesión de verdad | el diagnóstico completo, con su código de salida |

Entre media hora y una hora la primera vez, casi toda en la fase 2 si enganchas Google.

---

## Lo que no sale de tu máquina

Esto es lo que más preguntan, así que va aquí arriba:

- **La bóveda nace sin remoto git**, a propósito, y el diagnóstico avisa para siempre si
  algún día aparece uno. Nada se sube a ningún sitio porque no hay dónde.
- **Las credenciales viven fuera de la bóveda y fuera de cualquier repositorio**, en
  `%LOCALAPPDATA%\<nombre>\secrets.json`. Nunca en una nota, nunca en una variable de
  entorno de usuario, nunca en el historial de la terminal: se pegan **en el fichero**, y
  la guía te da la ruta y el nombre exacto de cada clave.
- **El contenido de tus correos no entra en la bóveda.** La fase 2 guarda métricas
  —cuántos, con quién, cada cuánto— y tres muestras cortas de tu propia escritura, ya
  pasadas por un redactor que quita tokens, direcciones y números largos.
- **No envía correo.** Crea borradores. En todo el código no hay una sola llamada al
  endpoint de envío. El ámbito de Gmail que pide **sí podría** enviar —no existe uno para
  borradores sin envío—, y eso está escrito en el `CLAUDE.md` que se genera, no escondido
  en un README.
- **Nada se envía ni se borra sin que lo confirmes.**

---

## Lo que genera

- Una bóveda de markdown con su propio repositorio git local
- Un asistente con voz propia: su fichero de estilo y la sección de tono del `CLAUDE.md`
- Paneles por área de trabajo, con el vocabulario que acordaste
- Búsqueda en dos capas: léxica en milisegundos, semántica a demanda
- Hooks de sesión: te recuerda dónde ibas al abrir, y al cerrar hace snapshot, commit y
  respaldo
- Respaldo: un zip fechado en la carpeta que ya sincroniza tu cliente de nube. **No usa
  ninguna API**, así que no hay nada que autorizar y no existe forma de que borre algo
  remoto
- Los módulos que hayas aprobado, instalados **donde Claude Code los descubre**

### Los cinco módulos

Todos opcionales. Se eligen en la fase 3 y se pueden saltar.

| Módulo | Qué trae |
|---|---|
| `google` | OAuth propio, perfil de escritura, triaje de bandeja y borradores (`/responde`, `/correos`) |
| `gitlab` | Credential helper, MCP en solo lectura, inventario de repos y la skill `/mr` de revisión de merge requests |
| `decisiones` | La red de seguridad: detecta decisiones que no llegaron a una ficha (`/decision`, `/reunion`) |
| `paneles` | Navegación por áreas, auditoría del frontmatter, `/consolidar` |
| `statusline` | Indicador de límites de la suscripción para la línea de estado |

Un módulo saltado **queda escrito en el `CLAUDE.md`** de tu bóveda, para que tu asistente
sepa que le falta un brazo y lo diga en vez de fingir. Un ecosistema degradado que no
sabe que lo está es peor que uno roto.

---

## Sin soporte, y con un diagnóstico

**Esto no es un producto mantenido.** Cada bóveda es tuya desde el minuto uno: la
cambiarás, divergirá, y nadie va a venir a arreglarla. Por eso el kit trae su propio
médico:

```
python .glados/doctor.py
```

Diez chequeos: enlaces, entorno virtual y dependencias, credenciales que faltan **por
nombre y nunca por valor**, hooks registrados y compilables, repositorio git **sin
remoto**, antigüedad del último respaldo, documentos indexados, frontmatter contra tu
propio vocabulario, notas por encima de 250 KB, y módulos activos cuya prueba de vida
nunca pasó. Sale 1 si algo falla. **No arregla nada**: decidir si una desviación es deriva
o una categoría nueva es tuyo.

El empaquetado como plugin te regala `/plugin update`, así que si el kit mejora puedes
traerte la mejora. **Pero eso actualiza el kit, nunca tu bóveda:** lo que ya se generó es
tuyo y no se toca.

---

## Si algo se atasca

| Síntoma | Qué pasa |
|---|---|
| «La ruta solo admite letras sin tilde, numeros, guion, punto y barra» | Elige otra ruta. **No la rodees con comillas.** Los comandos de los hooks van sin comillas a propósito, y un espacio o una tilde los parte en silencio en las sesiones no interactivas. Esto incluye las rutas cortas con `~`, como la de `%TEMP%` |
| El login de Google dice `access_denied` | La pantalla de consentimiento es **Externa** y no te añadiste como usuario de prueba |
| El login dice `invalid_client` | El ID o el secreto se pegaron con un espacio o un salto de línea de más |
| El login dice `redirect_uri_mismatch` | La credencial se creó como **web** en vez de **aplicación de escritorio** |
| Un comando como `/responde` no aparece | Reinicia la sesión de Claude Code: los comandos se descubren al arrancar |
| Los hooks no hacen nada en la primera sesión | Normal. Se leen al arrancar la sesión, y los acaba de escribir **esta**. La fase 5 te da el comando para abrir la siguiente, que es donde empiezan a vivir |
| Un `git push` parece colgado | **Nunca pongas un token en la URL del remoto.** El Gestor de credenciales de Windows abre un diálogo que no se ve en una terminal integrada y el proceso espera para siempre. Usa el credential helper del módulo `gitlab` |

---

## Camino alternativo

Si no puedes usar marketplaces de plugins, el repositorio se clona y la parte mecánica se
lanza a mano:

```powershell
git clone https://github.com/Fsegura-nter/glados-starter.git
cd glados-starter
powershell -NoProfile -ExecutionPolicy Bypass -File .\bootstrap.ps1 -Vault "C:\Users\tu-usuario\Desktop\mi-boveda" -Nombre mi-boveda
```

Añade `-DryRun` para comprobar prerrequisitos sin tocar el disco, y `-SinDependencias`
para saltarte la descarga del modelo de embeddings (son dos o tres gigabytes; la búsqueda
semántica queda fuera, la léxica funciona).

**No es el camino recomendado ni el que se prueba primero**, y deja fuera la parte que de
verdad aporta: las cinco fases guiadas. Después de `bootstrap.ps1` tendrías una bóveda
vacía y te faltaría todo lo demás.

---

## Para quien quiera mirar por dentro

```
bootstrap.ps1              la parte mecánica, idempotente, sin privilegios
nucleo/.glados/            los 15 scripts que viven en la bóveda generada
nucleo/.claude/            plantilla de configuración y hooks
modulos/<nombre>/          los cinco módulos, cada uno con su modulo.json
skills/ecosistema/         la skill que conduce las cinco fases, y sus referencias
plantillas/                CLAUDE.md, estilo del asistente y plantillas de nota
herramientas/              limpieza.py (barrido de datos) e instalar_modulos.py
tests/                     la suite; se ejecuta con pytest
```

Decisiones de diseño que no son obvias y que conviene no deshacer sin leer el motivo:

- **Los comandos de los hooks van sin comillas y sin `&`.** Con comillas, PowerShell lee
  `'ruta' 'ruta'` como una cadena suelta y los hooks de cierre fallan con `ParserError`
  en modo no interactivo, **en silencio**, porque en una terminal normal funcionan. Con
  `&` se arregla PowerShell y se rompe bash.
- **Los datos pesados viven fuera de la bóveda**, en `%LOCALAPPDATA%\<nombre>\`: una base
  de datos dentro de una carpeta sincronizada se corrompe.
- **Ninguna nota pasa de 250 KB.** El visor parsea la bóveda entera al arrancar y muere
  por falta de memoria si el volumen es excesivo. Medido: 3,9 MB la mata.
- **El respaldo se nombra con el nombre del ecosistema.** Varias bóvedas de una misma
  máquina pueden compartir la carpeta de sincronización, y con un patrón global cada una
  veía los respaldos de las otras y podía borrarlos al podar.
- **La lectura la hace un script, no el modelo.** Meter quinientos correos en un contexto
  cuesta una fortuna, no es reproducible y no deja herramienta.

```
python -m pytest -q
cp .limpieza-patrones.example.json .limpieza-patrones.json   # y rellénalo
python herramientas/limpieza.py
```

Lo último es el barrido que impide que un dato privado acabe en un repositorio público:
dominios internos, correos corporativos, nombres de cliente y rutas personales. Sale **1**
si encuentra algo y **2** si le falta el fichero de patrones — nunca 0, porque un barrido
sin patrones certificaría que no hay fugas sin haber mirado.

**Los patrones viven en `.limpieza-patrones.json`, que está en `.gitignore` y no se
publica.** Nombran justo lo que no debe salir, así que publicarlos sería la fuga que la
herramienta existe para evitar. Esto se aprendió por las malas: hasta el 2026-10-13 los
patrones estaban escritos dentro del propio script, y el script estaba en la lista blanca
del barrido. El guardián era invisible a sí mismo.

---

MIT. Francisco Segura.
