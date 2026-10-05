# GLaDOS Starter — Generador de bóvedas de conocimiento

GLaDOS Starter es un plugin de Claude Code que te entrevista, analiza tu trabajo real y genera una bóveda de markdown con personalidad propia: hooks automáticos, búsqueda semántica, respaldos incrementales y un dashboard que refleja cómo trabajas.

## Instalación

### Vía plugin marketplace (recomendado)

```bash
/plugin marketplace add Fsegura-nter/nter-fran
/plugin install glados-starter@nterfran
/ecosistema
```

### Alternativa: Clonar el repositorio

```bash
git clone https://github.com/Fsegura-nter/glados-starter.git
cd glados-starter
./install.ps1
```

> **Advertencia:** PowerShell puede bloquear la ejecución de scripts descargados de Internet. Si ves un error `UnauthorizedAccess`, desbloquea el archivo:
> ```powershell
> Unblock-File -Path .\install.ps1
> ```
> O establece temporalmente la política de ejecución:
> ```powershell
> Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
> ```
> Por este motivo, **la instalación vía plugin marketplace es el camino recomendado**.

## Requisitos

- **Windows 10 o superior** (el kit es solo Windows)
- **Claude Code** (versión 2.1 o superior)
- **Git** (para versionado)
- **Python 3.12+** (para los scripts)
- **Node 20+** (para procesamiento)

## Qué genera

- Una bóveda de Obsidian con su propio repositorio git
- Paneles organizados por área de trabajo
- Índice léxico y búsqueda semántica
- Hooks de sesión para snapshot automático y commit
- Respaldos incrementales a Google Drive (opcional)
- Credential helper para tokens seguros
