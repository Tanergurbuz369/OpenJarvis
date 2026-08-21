"""Safety contract for the POSIX uninstaller."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(os.name == "nt", reason="POSIX shell script")


def _run_uninstaller(
    tmp_path: Path,
    *args: str,
    answer: str = "",
    openjarvis_home: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    script = Path(__file__).parents[2] / "scripts" / "install" / "jarvis-uninstall.sh"
    fake_home = tmp_path / "home"
    fake_home.mkdir(exist_ok=True)
    data_home = openjarvis_home or fake_home / ".openjarvis"
    env = {
        **os.environ,
        "HOME": str(fake_home),
        "OPENJARVIS_HOME": str(data_home),
        "PATH": "/usr/bin:/bin",
    }
    return subprocess.run(
        ["bash", str(script), *args],
        input=answer,
        text=True,
        capture_output=True,
        env=env,
        check=False,
    )


def _populate_install(tmp_path: Path) -> tuple[Path, Path]:
    fake_home = tmp_path / "home"
    data_home = fake_home / ".openjarvis"
    (data_home / "connectors").mkdir(parents=True)
    (data_home / "config.toml").write_text("[engine]\n", encoding="utf-8")
    (data_home / "MEMORY.md").write_text("remember this", encoding="utf-8")
    (data_home / "connectors" / "oauth.json").write_text("{}", encoding="utf-8")
    shim_dir = fake_home / ".local" / "bin"
    shim_dir.mkdir(parents=True)
    shim = shim_dir / "jarvis"
    shim.write_text("shim", encoding="utf-8")
    return data_home, shim


def test_declining_confirmation_preserves_data_and_shims(tmp_path: Path) -> None:
    data_home, shim = _populate_install(tmp_path)

    result = _run_uninstaller(tmp_path, answer="no\n")

    assert result.returncode == 0
    assert 'Type "yes"' in result.stdout
    assert "was not removed" in result.stdout
    assert (data_home / "MEMORY.md").read_text(encoding="utf-8") == "remember this"
    assert shim.exists()


@pytest.mark.parametrize("args,answer", [((), "yes\n"), (("--yes",), "")])
def test_explicit_confirmation_removes_data_and_shims(
    tmp_path: Path,
    args: tuple[str, ...],
    answer: str,
) -> None:
    data_home, shim = _populate_install(tmp_path)

    result = _run_uninstaller(tmp_path, *args, answer=answer)

    assert result.returncode == 0
    assert not data_home.exists()
    assert not shim.exists()


def test_unsafe_install_root_is_rejected(tmp_path: Path) -> None:
    fake_home = tmp_path / "home"
    fake_home.mkdir()

    result = _run_uninstaller(
        tmp_path,
        "--yes",
        openjarvis_home=fake_home,
    )

    assert result.returncode == 2
    assert "Refusing unsafe OPENJARVIS_HOME" in result.stderr
    assert fake_home.exists()


def test_help_does_not_touch_existing_install(tmp_path: Path) -> None:
    data_home, shim = _populate_install(tmp_path)

    result = _run_uninstaller(tmp_path, "--help")

    assert result.returncode == 0
    assert "Usage:" in result.stdout
    assert data_home.exists()
    assert shim.exists()
