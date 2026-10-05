import subprocess, json, pytest

def ps(raiz, *args):
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", str(raiz / "bootstrap.ps1"), *args],
                          capture_output=True, text=True, timeout=900)

def test_rechaza_una_ruta_con_espacios(raiz, tmp_path):
    destino = tmp_path / "Mi Boveda"
    r = ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 1
    assert "espacios" in (r.stdout + r.stderr).lower()
    assert not destino.exists()

def test_rechaza_una_ruta_con_tilde(raiz, tmp_path):
    destino = tmp_path / "boveda-con-tilde-ñ"
    r = ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 1
    assert not destino.exists()

def test_dryrun_no_crea_nada(raiz, tmp_path):
    destino = tmp_path / "boveda"
    r = ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 0
    assert not destino.exists()

def test_deja_el_vault_con_hooks_resueltos_y_sin_remoto(raiz, tmp_path):
    destino = tmp_path / "boveda"
    assert ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    cfg = json.loads((destino / ".claude/settings.json").read_text(encoding="utf-8"))
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "{{" not in cmd and "'" not in cmd and "&" not in cmd
    remotos = subprocess.run(["git", "remote"], cwd=destino, capture_output=True, text=True)
    assert remotos.stdout.strip() == ""
    assert (destino / ".glados/session_start.py").exists()

def test_relanzarlo_no_rompe_nada(raiz, tmp_path):
    destino = tmp_path / "boveda"
    ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias")
    (destino / "nota-del-usuario.md").write_text("no me borres", encoding="utf-8")
    assert ps(raiz, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    assert (destino / "nota-del-usuario.md").read_text(encoding="utf-8") == "no me borres"
