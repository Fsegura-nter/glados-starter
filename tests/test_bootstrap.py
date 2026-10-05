import os, subprocess, json, pytest

def ps(raiz, tmp_path, *args):
    """Lanza `bootstrap.ps1` con `LOCALAPPDATA` redirigido a una subcarpeta de
    `tmp_path`, nunca al perfil real del usuario.

    Importante: NO se reusa `tmp_path` tal cual como `LOCALAPPDATA` porque el
    directorio de datos que crea el script es `LOCALAPPDATA\<Nombre>`, y en todas
    estas pruebas `<Nombre>` es `boveda` -- el mismo nombre que la carpeta del vault
    dentro de `tmp_path`. Si `LOCALAPPDATA` fuera `tmp_path` directamente, el venv
    acabaria DENTRO del vault y el `git add -A` del paso 7 lo arrastraria al commit.
    Por eso `LOCALAPPDATA` apunta a una hermana (`_lad`), no al propio `tmp_path`.
    """
    lad = tmp_path / "_lad"
    lad.mkdir(exist_ok=True)
    env = {**os.environ, "LOCALAPPDATA": str(lad)}
    return subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                           "-File", str(raiz / "bootstrap.ps1"), *args],
                          capture_output=True, text=True, encoding="utf-8",
                          env=env, timeout=900)

def test_rechaza_una_ruta_con_espacios(raiz, tmp_path):
    destino = tmp_path / "Mi Boveda"
    r = ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 1
    assert "espacios" in (r.stdout + r.stderr).lower()
    assert not destino.exists()

def test_rechaza_una_ruta_con_tilde(raiz, tmp_path):
    destino = tmp_path / "boveda-con-tilde-ñ"
    r = ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 1
    assert not destino.exists()

def test_dryrun_no_crea_nada(raiz, tmp_path):
    destino = tmp_path / "boveda"
    r = ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-DryRun")
    assert r.returncode == 0
    assert not destino.exists()

def test_deja_el_vault_con_hooks_resueltos_y_sin_remoto(raiz, tmp_path):
    destino = tmp_path / "boveda"
    assert ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    cfg = json.loads((destino / ".claude/settings.json").read_text(encoding="utf-8"))
    cmd = cfg["hooks"]["SessionStart"][0]["hooks"][0]["command"]
    assert "{{" not in cmd and "'" not in cmd and "&" not in cmd
    remotos = subprocess.run(["git", "remote"], cwd=destino, capture_output=True, text=True)
    assert remotos.stdout.strip() == ""
    assert (destino / ".glados/session_start.py").exists()

def test_relanzarlo_no_rompe_nada(raiz, tmp_path):
    destino = tmp_path / "boveda"
    ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias")
    (destino / "nota-del-usuario.md").write_text("no me borres", encoding="utf-8")
    assert ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    assert (destino / "nota-del-usuario.md").read_text(encoding="utf-8") == "no me borres"

def test_el_venv_no_sale_del_directorio_de_datos(raiz, tmp_path):
    """Hallazgo 1: sin `env=` en el helper, el venv de prueba se crea en el
    `%LOCALAPPDATA%` real del usuario, junto a datos irrecuperables. Esta prueba
    comprueba lo contrario de lo que fallaba: el venv nace bajo el `LOCALAPPDATA`
    redirigido, y nada que se parezca a un venv se cuela dentro del vault.
    """
    destino = tmp_path / "boveda"
    assert ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    lad = tmp_path / "_lad"
    assert (lad / "boveda" / "venv" / "Scripts" / "python.exe").exists()
    for patron in ("venv", "Scripts", "pyvenv.cfg"):
        assert list(destino.rglob(patron)) == [], f"se encontro '{patron}' dentro del vault"

def test_avisa_al_sobrescribir_un_script_del_nucleo_editado(raiz, tmp_path):
    """Hallazgo 2: el nucleo se refresca siempre (es la unica via de actualizacion
    del kit), pero si pisa una edicion local del usuario, ese reemplazo tiene que
    quedar escrito en la salida, no pasar en silencio.
    """
    destino = tmp_path / "boveda"
    assert ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias").returncode == 0
    script = destino / ".glados" / "session_start.py"
    with script.open("a", encoding="utf-8") as f:
        f.write("\n# edicion local de prueba\n")

    r = ps(raiz, tmp_path, "-Vault", str(destino), "-Nombre", "boveda", "-SinDependencias")
    assert r.returncode == 0
    assert "session_start.py" in r.stdout
    assert "AVISO" in r.stdout
    assert "# edicion local de prueba" not in script.read_text(encoding="utf-8")

def test_rechaza_un_nombre_ya_usado_por_otro_vault(raiz, tmp_path):
    """Hallazgo 3: el directorio de datos (%LOCALAPPDATA%\\<Nombre>) no tiene dueño
    sin un marcador. Dos bovedas con el mismo -Nombre no deben compartir estado.
    """
    vault_a = tmp_path / "boveda_a"
    vault_b = tmp_path / "boveda_b"
    assert ps(raiz, tmp_path, "-Vault", str(vault_a), "-Nombre", "boveda", "-SinDependencias").returncode == 0

    r = ps(raiz, tmp_path, "-Vault", str(vault_b), "-Nombre", "boveda", "-SinDependencias")
    assert r.returncode == 1
    assert str(vault_a) in (r.stdout + r.stderr)
    assert not vault_b.exists()
