# GitLab · host, tokens y la regla que se paga aprendiendo

Solo si la entrevista dijo que se usa GitLab. Es la integración corta: un host, un token
por repositorio y una regla que, si se incumple, cuelga la terminal sin explicar por qué.

---

## 1 · El host no es un literal

El host lo dice la entrevista, y va **a la configuración**, nunca escrito dentro de un
script:

```
.glados/settings.json  →  "gitlab_host": "https://gitlab.ejemplo.invalido"
```

Vale una instancia propia o `https://gitlab.com`. Ningún script del kit trae un host
dentro: una instancia hospedada por una empresa en el código de un repositorio público
es exactamente el tipo de dato que no debe viajar.

## 2 · Tokens: uno por repositorio

En GitLab, **Configuración del proyecto → Tokens de acceso** (no los de cuenta), con el
ámbito mínimo que haga falta: `read_repository` para leer, `read_api` si además se van a
consultar merge requests.

Cada token va al almacén con la ruta del repositorio en la clave:

```
%LOCALAPPDATA%\<nombre-del-ecosistema>\secrets.json
```

```json
{
  "gitlab.tokens.grupo/subgrupo/mi-repo": "...."
}
```

**Se pegan en el fichero, igual que los de Google.** Un token en la línea de comandos
queda en el historial de PowerShell, y de ahí no lo saca nadie el día que haya que
revocarlo.

Hay además una clave general, `gitlab.token`, para un token de cuenta que vea toda la
instancia. Es cómoda y es más poder del necesario: con tokens por repositorio, lo que se
filtre afecta a un repositorio. Quien quiera el inventario completo de la instancia la
necesita; quien solo trabaje en tres repos, no.

Para ver qué hay guardado, sin ver los valores:

```
python .glados/credentials.py list
```

## 3 · El credential helper

`git_credential.py` es un *credential helper*: cuando `git` pide usuario y contraseña, lo
lee del almacén. Se registra para el host con `useHttpPath` activado, que es lo que hace
que cada repositorio reciba **su** token y no el del vecino:

```
git config --global credential.https://gitlab.ejemplo.invalido.helper "<ruta>/.glados/git_credential.py"
git config --global credential.https://gitlab.ejemplo.invalido.useHttpPath true
```

## 4 · LA REGLA

> ## EL TOKEN NUNCA VA EN LA URL DEL REMOTO.

Ni `https://oauth2:TOKEN@host/grupo/repo.git`, ni ninguna variante. Nunca.

**Por qué, y no es higiene: es que cuelga.** Con el token en la URL, el Gestor de
credenciales de Windows abre un diálogo gráfico pidiendo confirmación. En una terminal
integrada —la de un editor, la de un agente, cualquier sesión no interactiva— **ese
diálogo no se ve**, y el proceso se queda esperando una respuesta que nadie puede dar.
No falla: se cuelga. Y como no falla, no hay mensaje de error que buscar.

Esta regla está escrita aquí porque se pagó aprendiéndola: la alternativa fue acabar con
el token incrustado en los remotos de cinco repositorios, que es una fuga esperando un
`git remote -v` delante de alguien.

El helper del paso 3 existe precisamente para no tener que hacer esto.

## 5 · El MCP, en solo lectura

`mcp_gitlab.py` lanza el servidor MCP de GitLab **forzado a solo lectura**, y el forzado
está en el lanzador, no en la confianza. Un asistente que puede cerrar issues o aprobar
merge requests por su cuenta es una decisión que se toma a propósito, no una que se
hereda de una plantilla.

Aviso heredado y verificado: un token **por repositorio** sirve para ese repositorio. El
MCP arrancado con uno de esos solo ve ese proyecto, y las llamadas que listan la
instancia devuelven vacío o 403. No está roto: está limitado, que es lo que se pidió.

## 6 · Prueba de vida — dos

1. **`git ls-remote`** contra un repositorio propio. Resuelve el remoto y demuestra que
   el helper entrega el token: es la prueba de que los pasos 2 y 3 están bien.
2. **La comprobación de salud del MCP.** Demuestra que el servidor arranca y responde.

Si la primera pasa y la segunda no, el módulo queda activo para `git` y marcado `fallo`
en la entrada del MCP de `.glados/estado_modulos.json`. Como con Google: **una entrada
por servicio**, porque media integración funcionando es mejor que ninguna, siempre que
esté escrito cuál es la mitad que falta.
