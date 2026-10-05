<#
.SYNOPSIS
    Mitad mecanica de la instalacion de GLaDOS Starter: comprueba prerrequisitos,
    valida la ruta elegida, crea el entorno virtual, instala una Nerd Font, copia el
    nucleo en una boveda nueva, resuelve las plantillas de configuracion y hace el
    `git init`. Nada de juicio aqui: lo que requiere decidir (estructura de carpetas,
    vocabulario, entrevista) lo hace la skill despues.

.PARAMETER Vault
    Ruta absoluta donde nace la boveda. Sin espacios ni caracteres fuera de
    letras-sin-tilde/numeros/guion/punto/barra: los comandos de hook van sin comillas
    a proposito (ver nucleo/.claude/settings.json.tmpl), y un espacio parte el comando.

.PARAMETER Nombre
    Nombre del ecosistema. Nombra la carpeta de datos fuera de la boveda
    (%LOCALAPPDATA%\<Nombre>) y se escribe en .glados/settings.json.

.PARAMETER ConStatusline
    Instala tambien la configuracion de ccstatusline. No implementado todavia en este
    kit: se imprime un aviso informativo y se continua.

.PARAMETER DryRun
    Solo valida la ruta y comprueba los prerrequisitos. No toca el disco.

.PARAMETER SinDependencias
    Crea el entorno virtual pero omite `pip install -r requirements.txt` (chromadb y
    sentence-transformers arrastran varios GB de torch). Pensado para pruebas
    automaticas; un usuario real no deberia pasarlo.
#>
param(
    [Parameter(Mandatory = $true)] [string]$Vault,
    [Parameter(Mandatory = $true)] [string]$Nombre,
    [switch]$ConStatusline,
    [switch]$DryRun,
    [switch]$SinDependencias
)

$ErrorActionPreference = "Stop"

function Ok($msg) { Write-Host "OK     $msg" }
function Aviso($msg) { Write-Host "AVISO  $msg" -ForegroundColor Yellow }
function Fallo($msg) { Write-Host "FALLO  $msg" -ForegroundColor Red }

# PowerShell 5.1 escribe BOM con `Set-Content -Encoding UTF8` o con
# `[System.Text.Encoding]::UTF8`. Un BOM al principio de un settings.json rompe
# `json.loads` / `config.py` (que leen con `encoding="utf-8"`, sin `-sig`), asi que
# todo fichero de configuracion se escribe con esta codificacion explicita sin BOM.
$Utf8SinBom = New-Object System.Text.UTF8Encoding($false)
function Escribir-Utf8SinBom([string]$Path, [string]$Texto) {
    [System.IO.File]::WriteAllText($Path, $Texto, $Utf8SinBom)
}

# ---------------------------------------------------------------------------
# Paso 1: validar la ruta. Antes de crear nada.
# ---------------------------------------------------------------------------
if ($Vault -match '\s') {
    Fallo "La ruta del vault no puede llevar espacios: $Vault"
    Write-Host "       Los comandos de hook van sin comillas (si no, PowerShell los lee como"
    Write-Host "       texto y los hooks de cierre fallan en silencio). Sin comillas, un"
    Write-Host "       espacio parte el comando. Elija una ruta sin espacios."
    exit 1
}
if ($Vault -notmatch '^[A-Za-z]:[\\A-Za-z0-9_\-.\\]+$') {
    Fallo "La ruta solo admite letras sin tilde, numeros, guion, punto y barra: $Vault"
    exit 1
}
Ok "Ruta del vault valida: $Vault"

# ---------------------------------------------------------------------------
# Paso 2: comprobar prerrequisitos.
# ---------------------------------------------------------------------------
function Comprobar-Herramienta([string]$Nombre) {
    try {
        $null = & $Nombre --version 2>&1
        return $true
    } catch {
        return $false
    }
}

$faltan = @()
foreach ($h in @("git", "python", "node", "claude")) {
    if (-not (Comprobar-Herramienta $h)) { $faltan += $h }
}
if ($faltan.Count -gt 0) {
    Fallo "Falta en el PATH: $($faltan -join ', '). Instalelo antes de continuar."
    exit 1
}
Ok "Prerrequisitos presentes: git, python, node, claude"

if ($DryRun) {
    Ok "DryRun: ruta y prerrequisitos validados, no se ha tocado el disco."
    exit 0
}

# ---------------------------------------------------------------------------
# Paso 3: entorno virtual en %LOCALAPPDATA%\<Nombre>\venv.
# ---------------------------------------------------------------------------
$datosDir = Join-Path $env:LOCALAPPDATA $Nombre
$venvDir = Join-Path $datosDir "venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if ($venvPython -match '\s') {
    Fallo "La ruta del entorno virtual no puede llevar espacios: $venvPython"
    Write-Host "       {{PYTHON}} se vuelca sin comillas en los comandos de hook, igual que"
    Write-Host "       {{VAULT}}. Revise por que %LOCALAPPDATA% o -Nombre llevan un espacio."
    exit 1
}

# El directorio de datos (%LOCALAPPDATA%\<Nombre>) no tiene dueño por si solo: dos
# bovedas con el mismo -Nombre compartirian venv, indice y respaldo sin darse cuenta.
# Un marcador con la ruta de la boveda que lo creo detecta el choque antes de tocar
# nada. Si el marcador falta (directorio de una ejecucion anterior a este arreglo),
# se adopta sin preguntar. Si coincide, seguir en silencio: relanzar la misma boveda
# tiene que seguir siendo idempotente.
$markerPath = Join-Path $datosDir "vault.txt"
if (Test-Path $markerPath) {
    $marcado = (Get-Content -Raw -Encoding UTF8 -Path $markerPath).Trim()
    if ($marcado -and $marcado -ne $Vault) {
        Fallo "El nombre '$Nombre' ya esta en uso por otra boveda: $marcado. Elija otro -Nombre para esta."
        exit 1
    }
} else {
    New-Item -ItemType Directory -Force -Path $datosDir | Out-Null
    Escribir-Utf8SinBom -Path $markerPath -Texto $Vault
}

if (Test-Path $venvPython) {
    Ok "El entorno virtual ya existe, se omite: $venvDir"
} else {
    python -m venv $venvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $venvPython)) {
        Fallo "No se ha podido crear el entorno virtual en $venvDir"
        exit 1
    }
    Ok "Entorno virtual creado: $venvDir"
}

# ---------------------------------------------------------------------------
# Paso 4: Nerd Font (simbolos de powerline/box-drawing), sin administrador.
# Fallar aqui es un AVISO, nunca un FALLO: sin fuente se vive, solo se ven cajas
# vacias en los separadores de la linea de estado.
# ---------------------------------------------------------------------------
function Instalar-NerdFont {
    $fontsDir = Join-Path $env:LOCALAPPDATA "Microsoft\Windows\Fonts"
    $nombreFichero = "SymbolsNerdFontMono-Regular.ttf"
    $nombreFuente = "Symbols Nerd Font Mono"
    $destinoFont = Join-Path $fontsDir $nombreFichero
    $regPath = "HKCU:\Software\Microsoft\Windows NT\CurrentVersion\Fonts"

    if (Test-Path $destinoFont) {
        Ok "Nerd Font ya instalada, se omite: $nombreFuente"
        return
    }
    $existente = Get-ItemProperty -Path $regPath -ErrorAction SilentlyContinue
    if ($existente -and ($existente.PSObject.Properties.Name -like "$nombreFuente*")) {
        Ok "Nerd Font ya registrada, se omite: $nombreFuente"
        return
    }

    try {
        New-Item -ItemType Directory -Force -Path $fontsDir | Out-Null
        $zipPath = Join-Path ([System.IO.Path]::GetTempPath()) "glados-nerdfont-symbols.zip"
        $url = "https://github.com/ryanoasis/nerd-fonts/releases/latest/download/NerdFontsSymbolsOnly.zip"
        Invoke-WebRequest -Uri $url -OutFile $zipPath -TimeoutSec 60 -UseBasicParsing

        Add-Type -AssemblyName System.IO.Compression.FileSystem
        $zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
        try {
            $entrada = $zip.Entries | Where-Object { $_.Name -eq $nombreFichero }
            if (-not $entrada) { throw "El zip descargado no contiene $nombreFichero" }
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entrada, $destinoFont, $true)
        } finally {
            $zip.Dispose()
        }
        Remove-Item $zipPath -ErrorAction SilentlyContinue

        New-Item -ItemType Directory -Force -Path $regPath | Out-Null
        New-ItemProperty -Path $regPath -Name "$nombreFuente (TrueType)" -Value $nombreFichero `
            -PropertyType String -Force | Out-Null

        Ok "Nerd Font instalada para el usuario: $nombreFuente"
    } catch {
        Aviso "No se ha podido instalar la Nerd Font ($($_.Exception.Message)). Sin ella, algunos separadores de la linea de estado saldran como cajas vacias."
    }
}

Instalar-NerdFont

# ---------------------------------------------------------------------------
# Paso 5: copiar el nucleo en la boveda, sin pisar ficheros que el usuario
# pueda haber editado.
#
# Los scripts mecanicos (.py y requirements.txt) se refrescan siempre: son
# codigo del kit, no contenido del usuario, y una boveda que nunca recibe
# arreglos del kit es su propia trampa. Los `settings.json` resueltos (paso 6)
# son la excepcion: se escriben una vez y nunca se vuelven a tocar, porque ahi
# es donde vive la personalizacion real (vocabulario, carpetas, respaldo...).
# Cualquier nota del usuario vive fuera de .glados/.claude y este paso no la
# toca en absoluto.
# ---------------------------------------------------------------------------
$raiz = Split-Path -Parent $MyInvocation.MyCommand.Path
$nucleoGlados = Join-Path $raiz "nucleo\.glados"
$nucleoClaude = Join-Path $raiz "nucleo\.claude"

$vaultGlados = Join-Path $Vault ".glados"
$vaultClaude = Join-Path $Vault ".claude"

New-Item -ItemType Directory -Force -Path $Vault | Out-Null
New-Item -ItemType Directory -Force -Path $vaultGlados | Out-Null
New-Item -ItemType Directory -Force -Path $vaultClaude | Out-Null

$scriptsNucleo = @(
    "config.py", "credentials.py", "redact.py", "session_start.py",
    "precompact_snapshot.py", "commit_vault.py", "respaldo_drive.py",
    "context_injector.py", "lexical.py", "index_docs.py", "query_docs.py",
    "requirements.txt"
)
foreach ($f in $scriptsNucleo) {
    $origen = Join-Path $nucleoGlados $f
    $destinoF = Join-Path $vaultGlados $f
    if (Test-Path $destinoF) {
        # Get-FileHash no esta disponible en todas las maquinas corporativas
        # bloqueadas (confirmado en la de desarrollo: el modulo que lo trae no lo
        # incluye aqui), asi que la comparacion es texto crudo con lo unico que
        # esta garantizado: Get-Content.
        $textoOrigen = Get-Content -Raw -Encoding UTF8 -Path $origen
        $textoDestino = Get-Content -Raw -Encoding UTF8 -Path $destinoF
        if ($textoOrigen -ne $textoDestino) {
            Aviso "$f tenia cambios locales, sobrescrito"
        }
    }
    Copy-Item -Path $origen -Destination $destinoF -Force
}
Ok "Nucleo (.glados) copiado/actualizado en $vaultGlados"

# ---------------------------------------------------------------------------
# Paso 6: resolver las plantillas de configuracion.
#
# Ambas: la de hooks (nucleo/.claude/settings.json.tmpl) y la del ecosistema
# (nucleo/.glados/settings.json.tmpl), que config.py necesita para el nombre,
# las colecciones, el vocabulario, el mapa de carpetas, la ruta de respaldo y
# el modelo de embeddings. Sin ella el nucleo arranca desconfigurado.
#
# Los `{{PYTHON}}` / `{{VAULT}}` se sustituyen como texto plano sobre el JSON
# crudo (sin parsear-reserializar), doblando las barras invertidas de la ruta
# sustituida para que el JSON siga siendo valido: la plantilla ya trae sus
# propias barras invertidas escapadas (`\\.glados\\...`), y el resultado final
# debe seguir sin comillas simples ni `&`, que es justo lo que valida la
# prueba de comportamiento.
# ---------------------------------------------------------------------------
function Resolver-Plantilla([string]$TmplPath, [string]$DestPath, [string]$PythonPath, [string]$VaultPath) {
    $texto = Get-Content -Raw -Encoding UTF8 -Path $TmplPath
    $pythonJson = $PythonPath.Replace('\', '\\')
    $vaultJson = $VaultPath.Replace('\', '\\')
    $texto = $texto.Replace('{{PYTHON}}', $pythonJson).Replace('{{VAULT}}', $vaultJson)
    Escribir-Utf8SinBom -Path $DestPath -Texto $texto
}

$destClaudeSettings = Join-Path $vaultClaude "settings.json"
if (Test-Path $destClaudeSettings) {
    Ok "settings.json de hooks ya existe, se conserva: $destClaudeSettings"
} else {
    Resolver-Plantilla -TmplPath (Join-Path $nucleoClaude "settings.json.tmpl") `
        -DestPath $destClaudeSettings -PythonPath $venvPython -VaultPath $Vault
    Ok "Hooks resueltos en $destClaudeSettings"
}

$destGladosSettings = Join-Path $vaultGlados "settings.json"
if (Test-Path $destGladosSettings) {
    Ok "settings.json del ecosistema ya existe, se conserva: $destGladosSettings"
} else {
    $tmplGlados = Get-Content -Raw -Encoding UTF8 -Path (Join-Path $nucleoGlados "settings.json.tmpl")
    $datos = $tmplGlados | ConvertFrom-Json
    $datos.nombre = $Nombre
    Escribir-Utf8SinBom -Path $destGladosSettings -Texto ($datos | ConvertTo-Json -Depth 10)
    Ok "settings.json del ecosistema creado en $destGladosSettings (nombre: $Nombre)"
}

# ---------------------------------------------------------------------------
# Paso 7: git init, .gitignore y commit inicial. Nunca un remoto.
# ---------------------------------------------------------------------------
$gitDir = Join-Path $Vault ".git"
if (Test-Path $gitDir) {
    Ok "La boveda ya tiene git inicializado, se omite"
} else {
    Push-Location $Vault
    try {
        git init | Out-Null

        $gitignore = @(
            "__pycache__/",
            "*.pyc",
            ".glados/last_session.md"
        ) -join "`n"
        Escribir-Utf8SinBom -Path (Join-Path $Vault ".gitignore") -Texto $gitignore

        if (-not (git config user.email)) {
            git config user.email "glados@localhost" | Out-Null
            git config user.name "GLaDOS Starter" | Out-Null
        }

        git add -A | Out-Null
        git commit -m "chore: inicializa la boveda" | Out-Null
        if ($LASTEXITCODE -ne 0) {
            Fallo "No se ha podido crear el commit inicial"
            Pop-Location
            exit 1
        }
        Ok "git init y commit inicial hechos, sin remoto"
    } finally {
        Pop-Location
    }
}

# ---------------------------------------------------------------------------
# Paso 8: resumen y, si se pide, ccstatusline.
# ---------------------------------------------------------------------------
if ($ConStatusline) {
    Aviso "-ConStatusline todavia no esta implementado en este kit: se omite."
}

Ok "Boveda lista en $Vault"

# ---------------------------------------------------------------------------
# Ultimo paso: dependencias pesadas (chromadb, sentence-transformers -> torch).
# Siempre al final, para que una descarga fallida nunca deje una boveda a medias.
# ---------------------------------------------------------------------------
if ($SinDependencias) {
    Ok "Dependencias omitidas (-SinDependencias)"
} else {
    & $venvPython -m pip install --quiet --disable-pip-version-check -r (Join-Path $vaultGlados "requirements.txt")
    if ($LASTEXITCODE -eq 0) {
        Ok "Dependencias instaladas en el entorno virtual"
    } else {
        Aviso "No se han podido instalar todas las dependencias. La busqueda lexica y los hooks funcionan igual; la busqueda semantica no."
    }
}

exit 0
