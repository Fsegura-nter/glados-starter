---
name: mr
description: Reviews a GitLab Merge Request of any stack (Spring Boot, NestJS, FastAPI, Django, Go, .NET, Laravel, Rails, Angular, React, Vue, Next, Svelte) and, after human approval, publishes the comments as inline discussions or general notes. Detects the stack and version from the repo itself and routes backend and frontend files to their own reviewer, so a full-stack MR is reviewed in one pass. Use it when the user types "/mr <URL>" or asks to review a merge request. Requires ~/.claude/mr-review/config.json with, per project, a GitLab token or a tokenFrom pointer to where it is stored.
---

# /mr — GitLab MR review, any stack

You automate the code review of a Merge Request. The argument is the MR URL.
Follow these steps IN ORDER. **You never publish anything to GitLab without the user explicitly approving in step 7.**

The GitLab token must NEVER appear in your text output, in a command line, or in a message. It is only ever read into a PowerShell variable inside the command that uses it.

> **Token economy (all steps):** API responses are NEVER printed whole into the conversation. Every fetch uses PowerShell with `curl.exe` (never the `curl` alias) and is either filtered with `ConvertFrom-Json | Select-Object` or saved to disk with `-o`. The diff, the docs and the file contents live ONLY in `$DIR`; the reviewer subagent reads them itself.

> **Output language:** your reasoning and these steps are in English. Everything shown at the gate (step 7) and everything published to GitLab is written in the project's `language` from the config (default `en`).

> **Requirements:** Windows with PowerShell 5.1+ and `curl.exe` (bundled with Windows 10+). The three helper scripts are PowerShell.

## Step 0 — Parse the URL
From `https://<host>/<group>/<repo>/-/merge_requests/<iid>` extract:
- `GITLAB_BASE` = `https://<host>`
- `PROJECT_PATH` = `<group>/<repo>` (may contain subgroups: `g/sub/repo`)
- `PROJECT_PATH_ENCODED` = `PROJECT_PATH` with `/` → `%2F`
- `MR_IID` = `<iid>`

If the URL does not match, stop and ask for it properly.

## Step 1 — Locate the scripts and read the config

### 1.1 Resolve the script directory
The skill ships three helper scripts that live next to this file. Their location differs between a plugin install and a manual one, so resolve it once and reuse `$SCRIPTS` in every later step:
```powershell
$SCRIPTS = @(
  @(Get-ChildItem "$env:USERPROFILE\.claude\plugins\marketplaces" -Recurse -Filter check-diff.ps1 -EA SilentlyContinue | ForEach-Object { $_.DirectoryName }),
  "$env:CLAUDE_PLUGIN_ROOT\skills\mr",
  "$env:USERPROFILE\.claude\skills\mr",
  @(Get-ChildItem "$env:USERPROFILE\.claude\plugins\cache" -Recurse -Filter check-diff.ps1 -EA SilentlyContinue | ForEach-Object { $_.DirectoryName })
) | ForEach-Object { $_ } | Where-Object { $_ -and (Test-Path "$_\check-diff.ps1") } | Select-Object -First 1
if ($SCRIPTS) { $SCRIPTS } else { "SCRIPTS-NOT-FOUND" }
```
The `marketplaces` path comes first on purpose: `$env:CLAUDE_PLUGIN_ROOT` points at a version-pinned cache that is not refreshed on plugin update ([issue #15642](https://github.com/anthropics/claude-code/issues/15642)), so preferring it would keep running the scripts from the version you installed rather than the one you updated to.

If `SCRIPTS-NOT-FOUND`, stop and tell the user the plugin files are missing — point them at the install guide.

### 1.2 Read the config
Do NOT read `~/.claude/mr-review/config.json` with the Read tool — the token must not enter the context. Read only the non-secret settings:
```powershell
$c = Get-Content "$env:USERPROFILE\.claude\mr-review\config.json" -Raw | ConvertFrom-Json
$p = $c.projects.'<PROJECT_PATH>'
if (-not $p) { "MISSING" } else {
  "stack=$(if ($p.stack) { $p.stack } else { 'auto' })"
  "language=$(if ($p.language) { $p.language } elseif ($c.defaults.language) { $c.defaults.language } else { 'en' })"
  "rules=$((@($p.rules) + @($c.defaults.rules) | Where-Object { $_ } | Select-Object -First 9) -join ',')"
  "tone=$(if ($p.tone) { $p.tone } else { $c.defaults.tone })"
}
```

If `MISSING`, stop and show the user the format to add (never invent a token). `stack` is optional — omit it and step 5 detects it:
```json
{
  "defaults": { "language": "en", "rules": ["noDebugPrints", "noTodos"] },
  "projects": { "group/repo": { "token": "glpat-xxxx" } }
}
```

A project may declare `tokenFrom` instead of `token`, which points at a JSON file outside this config and a dotted key path inside it. Offer it when the user's setup forbids credentials under `~/.claude`; the config still names every project, so the skill stays portable:
```json
{
  "projects": {
    "group/repo": {
      "tokenFrom": { "file": "%LOCALAPPDATA%\\store.json", "path": "gitlab.tokens.group/repo.value" }
    }
  }
}
```
`%VARS%` in `file` are expanded, and a key segment may itself contain dots — the path is resolved by longest match, so `a.b/c.value` finds a key literally named `a.b/c`.

Shell state does not persist between commands, so EVERY command that calls the API starts with this prefix, where `<SCRIPTS>` is the directory resolved in step 1.1:
```powershell
$TOKEN = & "<SCRIPTS>\get-token.ps1" '<PROJECT_PATH>'
```
`get-token.ps1` resolves `token` or `tokenFrom` and writes nothing but the token, so it never enters the context. If it fails it prints a diagnostic on stderr and `$TOKEN` is empty — stop and show that line rather than firing a request with no credential.

The token needs the `api` scope (a project access token with the Developer role is enough).

## Step 2 — Fetch MR info (filtered)
```powershell
<token prefix>; curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" "<GITLAB_BASE>/api/v4/projects/<PROJECT_PATH_ENCODED>/merge_requests/<MR_IID>" |
  ConvertFrom-Json | Select-Object title, state, source_branch, target_branch, @{n='author';e={$_.author.name}} | Format-List
```
If `state` != `opened`, warn and continue only if the user wants.

## Step 3 — Fetch diff versions (SHAs, filtered)
```powershell
<token prefix>; (curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../merge_requests/<MR_IID>/versions" | ConvertFrom-Json)[0] |
  Select-Object base_commit_sha, head_commit_sha, start_commit_sha | Format-List
```
The versions endpoint names them `base_commit_sha` / `head_commit_sha` / `start_commit_sha` (NOT `base_sha` — those names only appear later, in the discussions payload). All three are mandatory to anchor inline comments.

## Step 4 — Fetch diff, docs and file contents (to disk)
Set `$DIR = "$env:TEMP\mr-review\<MR_IID>"`. Create `$DIR` and `$DIR\files`, then:

1. **Diff** → `$DIR\changes.json`:
```powershell
<token prefix>; curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../merge_requests/<MR_IID>/changes" -o "$DIR\changes.json"
$j = Get-Content "$DIR\changes.json" -Raw | ConvertFrom-Json
"overflow=$($j.overflow) files=$($j.changes.Count) too_large=$(@($j.changes | Where-Object { $_.too_large }).Count)"
```

**If `overflow` is `True`**, the diff was truncated and reviewing it would silently miss files. Refetch paginated and rebuild `changes.json` in the same shape:
```powershell
<token prefix>; $all = @(); $page = 1
do {
  $r = curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../merge_requests/<MR_IID>/diffs?per_page=100&page=$page" | ConvertFrom-Json
  $all += $r; $page++
} while ($r.Count -eq 100 -and $page -le 20)
@{ changes = $all } | ConvertTo-Json -Depth 10 | Out-File "$DIR\changes.json" -Encoding utf8
"files=$($all.Count)"
```
Report any file with `too_large: true` to the user — it is not reviewable and must be checked by hand.

2. **Plain unified diff** for the reviewer:
```powershell
$ch = (Get-Content "$DIR\changes.json" -Raw | ConvertFrom-Json).changes
($ch | ForEach-Object { "--- a/$($_.old_path)`n+++ b/$($_.new_path)`n$($_.diff)" }) -join "`n" | Out-File "$DIR\diff.patch" -Encoding utf8
```

3. **Project docs** of the target branch — their rules are **mandatory** (priority 0). Fetch each into `$DIR`, ignoring 404s silently: `README.md`, `CONTRIBUTING.md`, `CLAUDE.md`:
```powershell
<token prefix>; foreach ($d in @('README.md','CONTRIBUTING.md','CLAUDE.md')) {
  curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../repository/files/$d/raw?ref=<TARGET_BRANCH>" -o "$DIR\$d"
  if ((Get-Content "$DIR\$d" -Raw -EA SilentlyContinue) -match '^\s*\{"message"') { Remove-Item "$DIR\$d" }
}
Get-ChildItem $DIR -Filter *.md | Select-Object Name, Length
```

4. **Full content of each modified file** — bounded to **exactly the files in the diff** (`changes[].new_path`, skipping `deleted_file`) and **no other repo file, ever**. Fetch the raw at `HEAD_SHA` into `$DIR\files\`, encoding `/` as `__` in the local name:
```powershell
<token prefix>; foreach ($f in $files) { $enc = [uri]::EscapeDataString($f);
  curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../repository/files/$enc/raw?ref=<HEAD_SHA>" -o "$DIR\files\$($f -replace '[\\/]','__')" }
```

Print ONLY the list of modified file paths.

## Step 5 — Detect the stack and route the files
**Always run detection**, even when the config declares a `stack`. The config gives you a name; detection gives you the name **and the version** read from the real manifest, and the per-file routing that a full-stack MR needs. A declared `stack` is only a fallback for when detection finds no manifest, or an override when the user says the detection is wrong.

```powershell
powershell -NoProfile -File "$SCRIPTS\detect-stack.ps1" `
  -Base "<GITLAB_BASE>" -ProjectPath "<PROJECT_PATH>" -Ref "<TARGET_BRANCH>" `
  -ChangesJson "$DIR\changes.json" -OutDir "$DIR"
```

It finds the nearest manifest for every changed file (`pom.xml`, `build.gradle`, `package.json`, `go.mod`, `pyproject.toml`, `requirements.txt`, `composer.json`, `Gemfile`, `Cargo.toml`, `*.csproj`), derives **stack and version**, and writes `$DIR\routing.txt` with one `layer:path` per file. It prints:
```
STACK back spring-boot 3.3.6 pom.xml
STACK front angular 18.2.13 package.json
ROUTE back 7
ROUTE front 4
```

Rules:
- **The version matters** — pass `<stack> <version>` to the reviewer so context7 resolves the right docs. Without it the reviewer guesses the version and its API claims drift.
- If a layer has 0 files, do not launch its reviewer.
- If detection returns `STACK none`, fall back to the `stack` declared in the config. If there is none either, tell the user and stop — do not guess a stack.
- Files routed as `other` (docs, CI config, SQL migrations with no owning manifest) go to the backend reviewer if one runs, otherwise to the frontend one.

## Step 6 — Deterministic pass, then review

### 6.1 Rule check + line map (script, always)
```powershell
powershell -NoProfile -File "$SCRIPTS\check-diff.ps1" `
  -ChangesJson "$DIR\changes.json" -OutDir "$DIR" -Rules "<comma-separated rules from step 1>"
```
Pass the rules as a single quoted, comma-separated string (`"noDebugPrints,noTodos"`). `powershell -File` does not parse array arguments — an unquoted list would arrive as one element and match nothing, silently producing zero findings.

It writes `$DIR\linemap.txt` (every line that can hold an inline comment) and prints one `rule|path:line|content` per violation of the **configured** team rules:
- `noDebugPrints` — `System.out`/`printStackTrace`/`console.log`/`fmt.Print`/`print(`/`var_dump`/`debugger`
- `noTodos` — leftover `TODO`/`FIXME`/`XXX`/`HACK`
- `noComments` — code comments. Only enable it for teams that actually ban comments; on a project that documents with JSDoc/JavaDoc this rule is pure noise.

Turn each finding into a `[SUGGESTION]` (never `[BLOCKING]`) anchored inline at that line — fix for debug prints: "replace with the project logger / remove"; for TODOs: "resolve it or move it to an issue"; for comments: "remove the comment". **Discard the obvious false positives** the regex let through: `//` inside a string or URL, a `#` inside a string, a `console.error` in a legitimate error handler, a commented-out annotation the language requires.

### 6.2 Fetch existing discussions (dedupe)
```powershell
<token prefix>; curl.exe -s --header "PRIVATE-TOKEN: $TOKEN" ".../merge_requests/<MR_IID>/discussions?per_page=100" -o "$DIR\existing.json"
((Get-Content "$DIR\existing.json" -Raw | ConvertFrom-Json).notes | Measure-Object).Count
```
Re-running `/mr` after a push must not republish what is already there.

### 6.3 Review (isolated subagent, one per layer)
Launch **mr-back-reviewer** and/or **mr-front-reviewer** with the Agent tool (`model: "opus"` — the review is the only step that benefits from the stronger model; the orchestration steps do not need it). **If both layers have files, launch them in the same message so they run in parallel.**

The subagents have no access to this conversation. Pass in the prompt:
- the **stack and version** (`spring-boot 3.3.6`), the MR **title** and **iid**,
- the **list of files of its layer** (from `routing.txt`) — it comments only on those,
- the **paths**, not the contents: `$DIR\diff.patch`, the docs found in step 4.3, and `$DIR\files\` with the `/`→`__` name mapping. It reads them itself.

Each returns comments in the `REVIEW SUMMARY / ---COMMENT--- / ---END---` format. Parse each `---COMMENT---` block into `index`, `type`, `file`, `line`, `severity`, `body`, `fix`. **Renumber indexes across both reviewers so they are unique.**

Discard clear false positives — a symbol the reviewer named that does not exist in the file, or a claim about code that did not change. Never publish a `general` finding without a concrete premise.

### 6.4 Validate every anchor (script, before the gate)
Write `$DIR\anchors.txt` with the Write tool, one `index|path|line` per proposed inline comment, then:
```powershell
powershell -NoProfile -File "$SCRIPTS\check-anchors.ps1" `
  -AnchorsFile "$DIR\anchors.txt" -OutDir "$DIR"
```
Apply the verdicts:
- `OK` → keep as inline
- `DEGRADE:*` → convert to `general` and prepend the location to the body (`<file>:<line> — …`), so the reader still knows where it is
- `DUPLICATE` → drop it, and count it in the gate summary as "already commented"

This is what stops GitLab from rejecting a post over a line number.

## Step 6.5 — Rewrite to publication text
Rewrite every comment (reviewers' + step 6.1's) into the exact text that will be published, in the config's `language`. Do NOT show the reviewer's verbose format. Tone: formal peer-to-peer, one developer to another; **no emojis**, and never appeal to "team conventions" in the abstract — cite the concrete rule if there is one. If the config defines `tone`, follow it.

```
**[SEVERITY] <file> — <short title of the problem>**
<paragraph: what the change does and why it is a problem / what the impact is>
Suggested fix: <concrete fix in one or two sentences>
```

- Severity in UPPERCASE in brackets: `[BLOCKING]`, `[SUGGESTION]`, `[NIT]`.
- Closing line always with the literal `Suggested fix:`.
- Affirmative, **no questions** ("what do you think?", "shall we look at it?"): state the fix and stop.

Keep `index`, `type`, `file` and `line` for step 8.

## Step 7 — Human GATE (mandatory)
Print the full list with the final texts, grouped by severity (blocking first), and a one-line header:
```
MR !<iid> — <title>
<stack back> · <stack front> · N comments (X blocking · Y suggestion · Z nit) · M already commented, skipped
```
Then ask:
```
send          publish all
skip 2,5      publish all except those indexes
only 1,3      publish only those indexes
edit 4        rewrite comment 4 before deciding
cancel        discard everything
```

**Do not continue to step 8 without one of these answers.** If the user does not answer, you publish nothing.

## Step 8 — Publish
For each approved comment:

**Inline** (`type: inline`). The `body` is markdown with newlines, quotes and dashes, so it must be a valid JSON string.

**Write the payload file with the Write tool, NEVER with PowerShell.** Two failure modes hit in practice when building it in PowerShell:
- In double-quoted strings, the backticks of markdown code spans are PowerShell's escape character and corrupt the body.
- `Out-File -Encoding utf8` and `[System.Text.Encoding]::UTF8` both prepend a UTF-8 BOM in PowerShell 5.1, and GitLab answers `{"error":"Invalid JSON format"}`.

The Write tool writes UTF-8 without BOM and treats content literally. So: Write `$DIR\payload<index>.json`, then post it:
```powershell
<token prefix>; curl.exe -s -o "$DIR\resp<index>.json" -w "%{http_code}" --request POST --header "PRIVATE-TOKEN: $TOKEN" `
  --header "Content-Type: application/json" `
  "<GITLAB_BASE>/api/v4/projects/<PROJECT_PATH_ENCODED>/merge_requests/<MR_IID>/discussions" `
  --data "@$DIR\payload<index>.json"
```
Payload (body already JSON-escaped — real newlines become `\n`):
```json
{
  "body": "<step 6.5 text, markdown, JSON-escaped>",
  "position": {
    "position_type": "text",
    "base_sha": "<BASE_SHA>",
    "head_sha": "<HEAD_SHA>",
    "start_sha": "<START_SHA>",
    "new_path": "<new_path>",
    "old_path": "<old_path>",
    "new_line": <line>
  }
}
```
`old_path` is **required** — GitLab needs both sides of the position for a modified file. Take it from `changes[].old_path`: it equals `new_path` for a normal modification and differs for a renamed file. Omitting it is the usual cause of an inline that fails for no visible reason.

**General** (`type: general`, or an inline that still fails):
```powershell
<token prefix>; curl.exe -s -o "$DIR\resp<index>.json" -w "%{http_code}" --request POST --header "PRIVATE-TOKEN: $TOKEN" `
  --header "Content-Type: application/json" `
  "<GITLAB_BASE>/api/v4/projects/<PROJECT_PATH_ENCODED>/merge_requests/<MR_IID>/notes" `
  --data "@$DIR\payload<index>.json"
```
with `{ "body": "..." }` only.

If an inline returns a non-2xx, print the response and retry it automatically as general — a post must never be lost over a line number.

When done, summarize: how many published inline, how many general, how many skipped by the user, how many dropped as duplicates. Never show the token.

## Rules
- Nothing is published without the step 7 approval.
- The token never appears in output, in a command line, or in a payload.
- Only comment on lines that changed. Full file contents are context, not review surface.
- Every `blocking` needs a concrete `fix`. Without one it is downgraded to `suggestion`.
- Do not modify the reviewer's technical claim when rewriting in step 6.5 — only its form.
