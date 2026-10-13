param(
    [Parameter(Mandatory = $true, Position = 0)][string]$ProjectPath,
    [string]$ConfigPath = "$env:USERPROFILE\.claude\mr-review\config.json"
)

# Resolves the GitLab token of ONE project and writes it to stdout, nothing else,
# so a caller can do:  $TOKEN = & "<scripts>\get-token.ps1" 'group/repo'
#
# Two ways for a project to declare its token in config.json:
#
#   "token": "glpat-xxxx"                        the token itself, inline
#
#   "tokenFrom": {                               an indirection to another JSON
#       "file": "%LOCALAPPDATA%\store.json",    file; %VARS% are expanded
#       "path": "a.b.c"                          dotted key path to the value
#   }
#
# tokenFrom exists for setups whose policy forbids credentials under ~/.claude.
# The skill stays portable either way: no credential store is named in any
# script, only in the user's own config.
#
# A key segment may itself contain dots - a GitLab path used as a key, say - so
# the path is resolved greedily: at each step the LONGEST prefix of the
# remaining segments that matches a property wins.

function Fail([string]$m) { [Console]::Error.WriteLine("get-token: $m"); exit 1 }

if (-not (Test-Path $ConfigPath)) { Fail "config not found: $ConfigPath" }
$cfg = Get-Content $ConfigPath -Raw | ConvertFrom-Json
$p = $cfg.projects.$ProjectPath
if (-not $p) { Fail "no project '$ProjectPath' in $ConfigPath" }

if ($p.token) { Write-Output $p.token; exit 0 }
if (-not $p.tokenFrom) { Fail "project '$ProjectPath' declares neither 'token' nor 'tokenFrom'" }

$file = [Environment]::ExpandEnvironmentVariables($p.tokenFrom.file)
if (-not (Test-Path $file)) { Fail "tokenFrom.file not found: $file" }
$node = Get-Content $file -Raw | ConvertFrom-Json

$segs = @($p.tokenFrom.path -split '\.')
$i = 0
while ($i -lt $segs.Count) {
    $matched = $false
    for ($take = $segs.Count - $i; $take -ge 1; $take--) {
        $name = ($segs[$i..($i + $take - 1)]) -join '.'
        $prop = if ($node -is [psobject]) { $node.PSObject.Properties[$name] } else { $null }
        if ($prop) { $node = $prop.Value; $i += $take; $matched = $true; break }
    }
    if (-not $matched) { Fail "tokenFrom.path: no key matches at '$($segs[$i])' in $file" }
}

if ($node -isnot [string] -or -not $node) { Fail "tokenFrom.path did not resolve to a non-empty string in $file" }
Write-Output $node
