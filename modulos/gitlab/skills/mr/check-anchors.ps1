param(
    [Parameter(Mandatory = $true)][string]$AnchorsFile,   # one "index|path|line" per proposed inline comment
    [Parameter(Mandatory = $true)][string]$OutDir,        # must contain linemap.txt; existing.json optional
    [switch]$SkipDedupe
)

# Validates every proposed inline anchor BEFORE anything is posted.
#   OK          -> the line exists on the new side of the diff, post as inline
#   DEGRADE     -> line not anchorable (outside the diff / wrong path), post as general
#   DUPLICATE   -> this file+line already has a discussion on the MR, drop it
#
# This removes the two failure modes that only show up at POST time: a 400 from
# GitLab for an unanchorable line, and a re-run of the skill republishing the
# same comments after a new push.

$ErrorActionPreference = 'Stop'

$mapPath = Join-Path $OutDir 'linemap.txt'
if (-not (Test-Path $mapPath)) { Write-Output "ERROR: linemap.txt not found in $OutDir"; exit 1 }

$map = New-Object System.Collections.Generic.HashSet[string]
Get-Content $mapPath | ForEach-Object { if ($_) { [void]$map.Add($_.Trim()) } }

# Files present in the diff, to tell "wrong line" from "wrong file"
$paths = New-Object System.Collections.Generic.HashSet[string]
foreach ($k in $map) { [void]$paths.Add(($k -replace ':\d+$', '')) }

# Existing discussion anchors on the MR (dedupe)
$existing = New-Object System.Collections.Generic.HashSet[string]
$exPath = Join-Path $OutDir 'existing.json'
if (-not $SkipDedupe -and (Test-Path $exPath)) {
    try {
        $disc = Get-Content $exPath -Raw | ConvertFrom-Json
        foreach ($d in $disc) {
            foreach ($n in $d.notes) {
                if ($n.position -and $n.position.new_path -and $n.position.new_line) {
                    [void]$existing.Add("$($n.position.new_path):$($n.position.new_line)")
                }
            }
        }
    } catch { }
}

foreach ($raw in (Get-Content $AnchorsFile)) {
    if (-not $raw.Trim()) { continue }
    $parts = $raw -split '\|'
    if ($parts.Count -lt 3) { Write-Output "$raw|DEGRADE:malformed"; continue }
    $idx  = $parts[0].Trim()
    $path = $parts[1].Trim()
    $line = $parts[2].Trim()
    $key  = "$path`:$line"

    if ($existing.Contains($key))   { Write-Output "$idx|DUPLICATE|$key"; continue }
    if ($map.Contains($key))        { Write-Output "$idx|OK|$key"; continue }
    if (-not $paths.Contains($path)){ Write-Output "$idx|DEGRADE:file-not-in-diff|$key"; continue }
    Write-Output "$idx|DEGRADE:line-not-in-diff|$key"
}

Write-Output "---"
Write-Output "EXISTING ANCHORS ON MR: $($existing.Count)"
