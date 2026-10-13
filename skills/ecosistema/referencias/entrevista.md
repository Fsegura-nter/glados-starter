# Fase 1 · La entrevista

Ocho preguntas abiertas. **No es un formulario:** se hacen en una sola tanda, se deja
contestar en prosa, y lo que quede a medias se completa con la fase 2 en vez de
repreguntar. Alguien que acaba de instalar un plugin no quiere un interrogatorio.

Regla por encima de las ocho: **si la respuesta a una pregunta ya está en otra, no se
vuelve a preguntar.** Y si se contesta «lo que tú veas» a todo, se sigue adelante: la
fase 2 lee el material real y la fase 3 propone. No se escribe nada hasta la 4, así que
una entrevista pobre encarece la propuesta, no la arruina.

---

## Las ocho

**1. ¿Cuál es tu rol y en qué equipo?**
→ Fija el vocabulario del `CLAUDE.md` generado y la densidad técnica del asistente. Un
perfil de gestión y uno de desarrollo no reciben el mismo tono aunque elijan el mismo
arquetipo.

**2. ¿Con quién tratas cada semana, dentro y fuera de casa?**
→ Se cruza con los interlocutores reales de la fase 2. Lo que se nombra de memoria y el
correo confirma es el núcleo; lo que el correo muestra y no se nombró merece una pregunta
en la fase 3, porque suele ser una relación que se ha vuelto invisible.

**3. ¿Qué parte de tu trabajo repites siempre igual?**
→ Es la pregunta que decide los **módulos** y los comandos. «Contesto los mismos correos»
→ `google`. «Reviso merge requests» → `gitlab`. «Decido cosas en reuniones y se me
olvidan» → `decisiones`.

**4. ¿Llevas clientes, repositorios, los dos o ninguno?**
→ Decide el **árbol de carpetas**, y es la razón de que este kit no reparta una plantilla
fija. Sin clientes no hay `01_CLIENTES`. Sin repos no hay carpeta de repos. Preguntarlo
explícitamente ahorra una carpeta vacía que nadie borra nunca.

**5. ¿Cómo agrupas tu trabajo en tu cabeza: por cliente, por producto, por tipo de
tarea?**
→ De aquí sale el vocabulario de **áreas**, que es el agrupador de todas las vistas. La
fase 2 lo contrasta con las series del calendario, que suelen ser mejor señal que la
memoria: mucha gente cree agrupar por cliente y su calendario dice que agrupa por
cadencia.

**6. ¿Qué te gustaría que tu asistente hiciera sin que se lo pidas?**
→ Decide los **hooks**, y es la pregunta que más da por palabra. «Que no me deje cerrar
sin anotar lo decidido» → el hook de cierre del módulo `decisiones`. «Que me recuerde
dónde iba» → `SessionStart`. «Que no me haga repetir el contexto cada vez» →
`UserPromptSubmit`.

**7. Si usas GitLab, ¿cuál es el host?**
→ Solo si la 3 o la 4 mencionaron repos. El host **nunca** se escribe como literal en
ningún script: va a `.glados/settings.json`, clave `gitlab_host`. Ver
[`gitlab.md`](gitlab.md).

**8. ¿En qué idioma quieres que te hable?**
→ Va al plan y al `CLAUDE.md`. Importa más de lo que parece: el asistente también redacta
textos para reenviar a otras personas, y ahí un registro equivocado lo firma quien lo
manda, no quien lo escribió.

---

## Las tres mecánicas, antes de las ocho

Se preguntan primero porque `bootstrap.ps1` las necesita y no dependen de nada más:

1. **Nombre de la bóveda** — nombra la carpeta y el directorio de datos.
2. **Dónde va** — por defecto `Escritorio\<nombre>`. **Sin espacios en la ruta:** los
   comandos de los hooks van sin comillas a propósito y un espacio los parte.
   `bootstrap.ps1` la rechaza, pero avisar antes ahorra el rechazo.
3. **¿Línea de estado?** — cosmético, y se puede decir no.

---

## Qué hacer con una respuesta incómoda

| Respuesta | Qué hacer |
|---|---|
| «No sé, lo que tú veas» | Seguir. La fase 2 decide y la 3 lo enseña para corregir |
| «Todo es importante» | No insistir. El calendario y el correo dirán qué pesa de verdad |
| «No quiero que lea mi correo» | Saltar el módulo `google` entero. Queda en los pendientes del `CLAUDE.md`, y el resto del ecosistema funciona igual |
| Una respuesta que contradice sus datos | **No se corrige en la entrevista.** Se anota y se saca en la fase 3, con el dato delante. Discutir con alguien sobre su propio trabajo en la primera pregunta no acaba bien |

---

## Qué NO se pregunta

- **Nada que el material vaya a contestar mejor.** No se pregunta cuántos clientes hay ni
  cómo se escribe: eso lo mide la fase 2. Preguntarlo gasta paciencia y además se
  contesta mal, porque nadie recuerda su propio estilo.
- **Nada sobre credenciales.** Los tokens llegan en su fase, con la ruta del fichero
  delante. Preguntar por un secreto de cliente en medio de una entrevista es
  exactamente donde se pierde a la gente.
- **Nada que no cambie el resultado.** Si una respuesta no mueve el árbol, ni los
  módulos, ni el tono, ni los hooks, esa pregunta no existe.
