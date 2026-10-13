param(
    [Parameter(Mandatory = $true)][string]$ChangesJson,
    [Parameter(Mandatory = $true)][string]$OutDir,
    # Team rules to enforce, comma separated. Anything not listed is not checked.
    # noComments | noDebugPrints | noTodos
    # A plain string, not [string[]]: `powershell -File` never parses an array
    # argument, so "a,b,c" would arrive as one element and silently match nothing.
    [string]$Rules = 'noDebugPrints,noTodos'
)

# Two jobs, both deterministic - no model involved:
#
# 1. LINE MAP  -> $OutDir\linemap.txt, one "path:new_line" per line that can hold
#    an inline comment (added + context lines). The skill validates every anchor
#    the reviewer proposes against this file; anything not in it is degraded to a
#    general note instead of failing at POST time.
#
# 2. FINDINGS  -> stdout + $OutDir\findings.txt, one "rule|path:line|content" per
#    added line that breaks a configured team rule.

$ErrorActionPreference = 'Stop'
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

$ruleSet = @($Rules -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$changes = (Get-Content $ChangesJson -Raw | ConvertFrom-Json).changes

$lineMap  = New-Object System.Collections.Generic.List[string]
$findings = New-Object System.Collections.Generic.List[string]

# Extensions where '#' starts a comment, vs where it does not (C-family, CSS...)
$hashComment = @('.py', '.rb', '.sh', '.yml', '.yaml', '.tf', '.pl', '.r')
$htmlLike    = @('.html', '.htm', '.vue', '.svelte', '.xml')

foreach ($c in $changes) {
    if ($c.deleted_file) { continue }
    $path = $c.new_path
    $ext  = [System.IO.Path]::GetExtension($path).ToLower()
    $newLine = 0

    # A trailing newline in the diff produces one empty trailing element that is not
    # a real diff line. Interior empty strings ARE kept: some generators emit an
    # empty context line as "" instead of " ", and dropping those would shift every
    # line number after it.
    # A file whose change carries no text hunks comes back with an empty 'diff',
    # which splits into a single empty element. Trimming that with the loop below
    # never terminates: at Count 1, $diffLines[0..-1] is the range 0..-1, which
    # PowerShell expands to @(0, -1) and hands back TWO elements. Count then
    # oscillates 1 -> 2 -> 1 forever and the script spins until it is killed.
    # Hence Count -gt 1 in the loop, plus a guard on each side of it.
    $diffLines = @($c.diff -split "`r?`n")
    if ($diffLines.Count -eq 1 -and $diffLines[0] -eq '') { $diffLines = @() }
    while ($diffLines.Count -gt 1 -and $diffLines[-1] -eq '') {
        $diffLines = $diffLines[0..($diffLines.Count - 2)]
    }
    if ($diffLines.Count -eq 1 -and $diffLines[0] -eq '') { $diffLines = @() }

    foreach ($line in $diffLines) {
        if ($line -match '^@@ -\d+(?:,\d+)? \+(\d+)') { $newLine = [int]$Matches[1]; continue }
        if ($line.StartsWith('+++') -or $line.StartsWith('---')) { continue }
        if ($line.StartsWith('\')) { continue }
        if ($line.StartsWith('-')) { continue }   # removed: no line on the new side

        $isAdded = $line.StartsWith('+')
        $lineMap.Add("$path`:$newLine")           # added and context lines are anchorable

        if ($isAdded) {
            $content = $line.Substring(1)
            $trim = $content.Trim()

            if ($ruleSet -contains 'noDebugPrints') {
                if ($content -match 'System\.(out|err)\.' -or
                    $content -match '\.printStackTrace\s*\(' -or
                    $content -match 'console\.(log|debug|info|trace)\b' -or
                    $content -match '\bfmt\.Print' -or
                    $content -match '^\s*print\s*\(' -or
                    $content -match '\bvar_dump\s*\(' -or
                    $content -match '\bdebugger\b') {
                    $findings.Add("debugPrint|$path`:$newLine|$trim")
                }
            }

            if ($ruleSet -contains 'noTodos') {
                if ($content -match '\b(TODO|FIXME|XXX|HACK)\b') {
                    $findings.Add("todo|$path`:$newLine|$trim")
                }
            }

            if ($ruleSet -contains 'noComments') {
                $isComment = $false
                if ($htmlLike -contains $ext) {
                    if ($content -match '<!--') { $isComment = $true }
                }
                elseif ($hashComment -contains $ext) {
                    # '#' only counts at the start of the trimmed line: avoids '#'
                    # inside strings and CSS colours. Shebang is not a comment to flag.
                    if ($trim.StartsWith('#') -and -not $trim.StartsWith('#!')) { $isComment = $true }
                }
                else {
                    # C-family: '//' not preceded by ':' (skips http://), block comments,
                    # and javadoc/jsdoc continuation lines.
                    # A '//' inside a quoted string is NOT excluded here - those survive
                    # as false positives and are dropped by the model in step 6.1.
                    if ($content -match '(^|[^:])//' -or $content -match '/\*' -or $trim.StartsWith('*')) {
                        $isComment = $true
                    }
                }
                if ($isComment) { $findings.Add("comment|$path`:$newLine|$trim") }
            }
        }

        $newLine++
    }
}

$lineMap  -join "`n" | Out-File "$OutDir\linemap.txt"  -Encoding ascii
$findings -join "`n" | Out-File "$OutDir\findings.txt" -Encoding utf8

Write-Output "ANCHORABLE LINES: $($lineMap.Count)"
Write-Output "RULES: $($ruleSet -join ', ')"
Write-Output "FINDINGS: $($findings.Count)"
$findings | ForEach-Object { Write-Output $_ }
