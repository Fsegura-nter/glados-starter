# Google · de cero a leer un correo

**Aquí está el 90% del riesgo de abandono de todo el proceso.** No es difícil: es largo,
tiene pantallas que cambian de sitio y está lleno de nombres que no significan nada la
primera vez. Así que se guía con instrucciones literales y se demuestra el resultado
antes de seguir.

**Esta fase se puede saltar.** Si se salta, queda escrita en la lista de pendientes del
`CLAUDE.md` generado, para que el asistente sepa que no puede leer correo y lo diga en
vez de fingir. Un ecosistema degradado que no sabe que lo está es peor que uno roto.

---

## 1 · Proyecto en Google Cloud

1. Entrar en <https://console.cloud.google.com> con la cuenta de trabajo.
2. Selector de proyecto, arriba a la izquierda → **Proyecto nuevo**.
3. Nombre: cualquiera reconocible (`boveda-personal` sirve). **Crear**.
4. Comprobar que el selector de arriba muestra **ese** proyecto y no otro. Es el error
   más común de todo el proceso: activar las APIs en el proyecto equivocado y pasar
   media hora buscando por qué no funciona nada.

## 2 · Activar las tres APIs

En **APIs y servicios → Biblioteca**, buscar y pulsar **Habilitar** en cada una:

- **Gmail API**
- **Google Drive API**
- **Google Calendar API**

Las tres, una a una. Si alguna da error de permisos, **no se bloquea el proceso**: se
anota y se sigue con las otras dos. La prueba de vida del paso 7 está partida por
servicio precisamente para eso.

## 3 · Pantalla de consentimiento

**APIs y servicios → Pantalla de consentimiento de OAuth**:

- Tipo de usuario: **Interno**, si la organización lo permite. Si solo deja **Externo**,
  vale igual, pero hay que **añadirse como usuario de prueba** o el login fallará con
  `access_denied`.
- Nombre de la aplicación: el que sea. Correo de soporte: el propio.
- Guardar y continuar hasta el final. **No hace falta tocar los ámbitos aquí:** los pide
  la aplicación en el momento del login.

## 4 · Credencial de tipo escritorio

**APIs y servicios → Credenciales → Crear credenciales → ID de cliente de OAuth**:

- Tipo de aplicación: **Aplicación de escritorio**. No «Aplicación web»: una credencial
  web exige una URI de redirección registrada, y el login local no la tiene.
- Crear. Google muestra un **ID de cliente** y un **secreto de cliente**.

Dejar esa ventana abierta: los dos valores van al paso siguiente.

## 5 · Pegar las dos claves — y cómo NO hacerlo

Las dos claves van al almacén de credenciales, que vive **fuera de la bóveda y fuera de
cualquier repositorio**, en este fichero:

```
%LOCALAPPDATA%\<nombre-del-ecosistema>\secrets.json
```

Se abre ese fichero en el editor y se añaden estas dos claves, con los valores que
muestra Google:

```json
{
  "google.client_id": "....apps.googleusercontent.com",
  "google.client_secret": "...."
}
```

> **Se pegan en el fichero, nunca en un comando.** Un secreto escrito en la terminal
> queda en el historial de PowerShell para siempre, y ahí no lo busca nadie el día que
> haya que rotarlo. El almacén tiene una orden para escribir claves y **aquí no se usa**:
> existe para valores que no son secretos y para scripts.
>
> Quien guía esta fase **no pide los valores por el chat**, no los repite y no los
> escribe en ningún sitio. Se dan la ruta y los nombres de clave exactos, y el resto se
> hace en el editor.

Para comprobar que quedaron guardadas, sin ver los valores:

```
python .glados/credentials.py list
```

Enmascara por diseño: dice qué claves hay, nunca su contenido.

## 6 · El login

```
python .glados/google_auth.py login
```

Abre el navegador, pide consentimiento y guarda un `refresh_token` en el almacén. A
partir de ahí no vuelve a hacer falta el navegador.

Ámbitos que pide, y ni uno más:

| Ámbito | Para qué |
|---|---|
| `gmail.readonly` | leer correo |
| `gmail.compose` | **crear borradores** |
| `drive.readonly` | listar carpetas y nombres de fichero |
| `calendar.readonly` | leer eventos |

> **Lo incómodo, dicho en voz alta porque es verdad:** `gmail.compose` **puede enviar
> correo**. Su descripción oficial es «Manage drafts and send emails», y no existe un
> ámbito de Gmail para borradores sin envío: ese es el mínimo disponible. Lo que
> garantiza que no se envíe nada no es el ámbito, es que en todo el código no hay ni una
> llamada a `messages/send` ni a `drafts/send`. Eso queda escrito también en el
> `CLAUDE.md` de la bóveda generada, no solo aquí.

Si el login falla:

| Error | Causa casi siempre |
|---|---|
| `access_denied` | consentimiento **Externo** sin añadirse como usuario de prueba |
| `invalid_client` | el ID o el secreto se pegaron con un espacio o un salto de línea de más |
| `redirect_uri_mismatch` | la credencial se creó como **web** en vez de **escritorio** |
| el navegador no vuelve | otro proceso ocupa el puerto local; cerrar y repetir |

## 7 · Prueba de vida — tres, por separado

**Ninguna fase avanza con una prueba de vida fallida.** Y se hacen las tres **por
separado**, porque un servicio capado por el departamento de sistemas no debe tumbar los
otros dos:

1. **Un correo.** Leer uno y mostrar remitente y asunto. Nada más: el cuerpo no se
   vuelca.
2. **Un evento.** Leer el calendario y mostrar el título y la hora de uno.
3. **Un nombre de fichero de Drive.** Solo el nombre de uno, no su contenido.

Resultado posible y perfectamente válido: **dos de tres**. Entonces el módulo `google`
sigue activo, el servicio que falló se marca `fallo` en `.glados/estado_modulos.json`
—una entrada **por servicio**, no un interruptor por módulo— y el motivo entra en la
lista de pendientes del `CLAUDE.md` con una frase que se entienda dentro de tres meses:

> `google/drive: la API de Drive devuelve 403 en esta organización. Gmail y Calendar sí.
> Sin búsqueda en Drive.`

El diagnóstico lee ese fichero en su último chequeo, así que un servicio caído se sigue
viendo medio año después sin tener que acordarse de nada.
