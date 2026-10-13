param(
    [Parameter(Mandatory = $true)][string]$Base,          # https://gitlab.host
    [Parameter(Mandatory = $true)][string]$ProjectPath,   # group/sub/repo (not encoded)
    [Parameter(Mandatory = $true)][string]$Ref,           # target branch or SHA
    [Parameter(Mandatory = $true)][string]$ChangesJson,   # $DIR\changes.json
    [string]$OutDir                                       # optional: writes routing.txt
)

# Detects the stack(s) of an MR and routes every changed file to a layer
# (back / front / other) using the NEAREST manifest, not the file extension.
# The token is resolved from the config here (see get-token.ps1) so it never
# travels as a parameter.
#
# Output (stdout, small enough for the conversation):
#   STACK back|front  <stack> <version> <manifest path>
#   ROUTE back|front|other  <count> files
#   UNROUTED <count>
# and, if -OutDir is given, one "layer:path" line per file in routing.txt

$ErrorActionPreference = 'Stop'

$token = & "$PSScriptRoot\get-token.ps1" $ProjectPath
if (-not $token) { Write-Output "ERROR: no token for $ProjectPath"; exit 1 }

$enc = [uri]::EscapeDataString($ProjectPath)
$api = "$Base/api/v4/projects/$enc"

function Get-Raw([string]$path) {
    $p = [uri]::EscapeDataString($path)
    $out = curl.exe -s --header "PRIVATE-TOKEN: $token" "$api/repository/files/$p/raw?ref=$Ref" 2>$null
    if ($LASTEXITCODE -ne 0) { return $null }
    $joined = $out -join "`n"
    if (-not $joined -or $joined -match '^\s*\{"message"') { return $null }
    return $joined
}

function Get-Tree([string]$dir) {
    $q = "$api/repository/tree?ref=$Ref&per_page=100"
    if ($dir) { $q += "&path=$([uri]::EscapeDataString($dir))" }
    $out = (curl.exe -s --header "PRIVATE-TOKEN: $token" $q 2>$null) -join "`n"
    if (-not $out -or $out -match '^\s*\{"message"') { return @() }
    try { return (ConvertFrom-Json $out) | Where-Object { $_.type -eq 'blob' } | ForEach-Object { $_.name } }
    catch { return @() }
}

# --- changed files -----------------------------------------------------------
$changes = (Get-Content $ChangesJson -Raw | ConvertFrom-Json).changes
$files = @($changes | Where-Object { -not $_.deleted_file } | ForEach-Object { $_.new_path })
if ($files.Count -eq 0) { Write-Output "ERROR: no files in diff"; exit 1 }

# candidate manifest directories: every ancestor of every changed file, shallowest first
$dirs = New-Object System.Collections.Generic.HashSet[string]
[void]$dirs.Add('')
foreach ($f in $files) {
    $parts = $f -split '/'
    for ($i = 0; $i -lt $parts.Count - 1; $i++) {
        [void]$dirs.Add(($parts[0..$i] -join '/'))
    }
}
$ordered = @($dirs) | Sort-Object { ($_ -split '/').Count }, { $_ } | Select-Object -First 12

$manifestNames = @('pom.xml', 'build.gradle', 'build.gradle.kts', 'package.json', 'go.mod',
    'pyproject.toml', 'requirements.txt', 'composer.json', 'Gemfile', 'Cargo.toml')

# --- probe each candidate dir for manifests ----------------------------------
$found = @()   # @{ dir; name }
foreach ($d in $ordered) {
    foreach ($n in (Get-Tree $d)) {
        if ($manifestNames -contains $n -or $n -like '*.csproj') {
            $found += [pscustomobject]@{ Dir = $d; Name = $n }
        }
    }
}

# --- classify each manifest into layer + stack + version ---------------------
function Resolve-Manifest($dir, $name) {
    $path = if ($dir) { "$dir/$name" } else { $name }
    $c = Get-Raw $path
    if ($null -eq $c) { return $null }

    switch -Wildcard ($name) {
        'pom.xml' {
            $v = if ($c -match '(?s)spring-boot-starter-parent.*?<version>([^<]+)</version>') { $Matches[1] }
                 elseif ($c -match '<spring-boot\.version>([^<]+)</spring-boot\.version>') { $Matches[1] } else { '' }
            $stack = if ($v -or $c -match 'org\.springframework\.boot') { 'spring-boot' } else { 'java' }
            if (-not $v -and $c -match '<(?:java\.version|maven\.compiler\.release)>([^<]+)<') { $v = "java $($Matches[1])" }
            return @{ Layer = 'back'; Stack = $stack; Version = $v; Path = $path }
        }
        'build.gradle*' {
            $v = if ($c -match "org\.springframework\.boot['`"]?\s*\)?\s*version\s*['`"]([^'`"]+)") { $Matches[1] } else { '' }
            $stack = if ($v -or $c -match 'org\.springframework\.boot') { 'spring-boot' } else { 'java' }
            return @{ Layer = 'back'; Stack = $stack; Version = $v; Path = $path }
        }
        'package.json' {
            try { $j = ConvertFrom-Json $c } catch { return $null }
            $deps = @{}
            foreach ($sec in @('dependencies', 'devDependencies', 'peerDependencies')) {
                if ($j.$sec) { $j.$sec.PSObject.Properties | ForEach-Object { $deps[$_.Name] = $_.Value } }
            }
            # "^18.2.13" / "~5.4.4" / ">=18.0.0 <19" -> "18.2.13" / "5.4.4" / "18.0.0".
            # Strip the range operators FIRST: leading '^' is a non-digit, so cutting at
            # the first non-digit before stripping would eat the whole version.
            $clean = {
                param($s)
                if (-not $s) { return '' }
                ($s -replace '^[\s~^>=<v]*', '') -replace '[^0-9.].*$', ''
            }
            # backend-first: a NestJS/Express package.json is not a frontend
            if ($deps.ContainsKey('@nestjs/core')) { return @{ Layer = 'back'; Stack = 'nestjs'; Version = (& $clean $deps['@nestjs/core']); Path = $path } }
            if ($deps.ContainsKey('next'))         { return @{ Layer = 'front'; Stack = 'nextjs'; Version = (& $clean $deps['next']); Path = $path } }
            if ($deps.ContainsKey('@angular/core')){ return @{ Layer = 'front'; Stack = 'angular'; Version = (& $clean $deps['@angular/core']); Path = $path } }
            if ($deps.ContainsKey('vue'))          { return @{ Layer = 'front'; Stack = 'vue'; Version = (& $clean $deps['vue']); Path = $path } }
            if ($deps.ContainsKey('svelte'))       { return @{ Layer = 'front'; Stack = 'svelte'; Version = (& $clean $deps['svelte']); Path = $path } }
            if ($deps.ContainsKey('react'))        { return @{ Layer = 'front'; Stack = 'react'; Version = (& $clean $deps['react']); Path = $path } }
            if ($deps.ContainsKey('express') -or $deps.ContainsKey('fastify')) { return @{ Layer = 'back'; Stack = 'node'; Version = ''; Path = $path } }
            return @{ Layer = 'front'; Stack = 'node'; Version = ''; Path = $path }
        }
        'go.mod' {
            $v = if ($c -match '(?m)^go\s+([0-9.]+)') { $Matches[1] } else { '' }
            return @{ Layer = 'back'; Stack = 'go'; Version = $v; Path = $path }
        }
        'pyproject.toml' {
            $stack = if ($c -match 'fastapi') { 'fastapi' } elseif ($c -match '\bdjango\b') { 'django' } elseif ($c -match '\bflask\b') { 'flask' } else { 'python' }
            return @{ Layer = 'back'; Stack = $stack; Version = ''; Path = $path }
        }
        'requirements.txt' {
            $stack = if ($c -match '(?im)^fastapi') { 'fastapi' } elseif ($c -match '(?im)^django') { 'django' } elseif ($c -match '(?im)^flask') { 'flask' } else { 'python' }
            $v = if ($c -match "(?im)^(?:fastapi|django|flask)[=><~]+([0-9.]+)") { $Matches[1] } else { '' }
            return @{ Layer = 'back'; Stack = $stack; Version = $v; Path = $path }
        }
        'composer.json' {
            $stack = if ($c -match 'laravel/framework') { 'laravel' } elseif ($c -match 'symfony/') { 'symfony' } else { 'php' }
            return @{ Layer = 'back'; Stack = $stack; Version = ''; Path = $path }
        }
        'Gemfile'     { return @{ Layer = 'back'; Stack = 'rails'; Version = ''; Path = $path } }
        'Cargo.toml'  { return @{ Layer = 'back'; Stack = 'rust'; Version = ''; Path = $path } }
        '*.csproj' {
            $v = if ($c -match '<TargetFramework[^>]*>([^<]+)<') { $Matches[1] } else { '' }
            return @{ Layer = 'back'; Stack = 'dotnet'; Version = $v; Path = $path }
        }
    }
    return $null
}

$manifests = @()
foreach ($m in $found) {
    $r = Resolve-Manifest $m.Dir $m.Name
    if ($r) { $r['Dir'] = $m.Dir; $manifests += $r }
}

# --- route every changed file to its nearest manifest ------------------------
# Deeper manifest wins. A file with no manifest above it falls back to extension.
$frontExt = @('.ts', '.tsx', '.js', '.jsx', '.mjs', '.html', '.scss', '.css', '.less', '.vue', '.svelte')
$backExt  = @('.java', '.kt', '.go', '.py', '.rb', '.php', '.cs', '.sql', '.gradle')

$routes = @()
foreach ($f in $files) {
    $own = $manifests |
        Where-Object { $_.Dir -eq '' -or $f.StartsWith("$($_.Dir)/") } |
        Sort-Object { $_.Dir.Length } -Descending |
        Select-Object -First 1
    $layer = if ($own) { $own.Layer } else {
        $e = [System.IO.Path]::GetExtension($f).ToLower()
        if ($frontExt -contains $e) { 'front' } elseif ($backExt -contains $e) { 'back' } else { 'other' }
    }
    # a manifest tells us the project, the extension still tells us the file's nature:
    # .html/.scss inside a NestJS repo, or .sql inside an Angular repo, are edge cases
    # we deliberately keep on the manifest's layer so the reviewer sees the whole change.
    $routes += "$layer`:$f"
}

# --- report ------------------------------------------------------------------
foreach ($layer in @('back', 'front')) {
    $m = $manifests | Where-Object { $_.Layer -eq $layer } | Sort-Object { $_.Dir.Length } | Select-Object -First 1
    if ($m) { Write-Output "STACK $layer $($m.Stack) $(if ($m.Version) { $m.Version } else { '(version unknown)' }) $($m.Path)" }
}
foreach ($layer in @('back', 'front', 'other')) {
    $n = @($routes | Where-Object { $_ -like "$layer`:*" }).Count
    if ($n -gt 0) { Write-Output "ROUTE $layer $n" }
}
if ($manifests.Count -eq 0) { Write-Output "STACK none - no manifest found, extension routing only" }

if ($OutDir) {
    if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }
    $routes -join "`n" | Out-File "$OutDir\routing.txt" -Encoding ascii
    Write-Output "WROTE $OutDir\routing.txt"
}
