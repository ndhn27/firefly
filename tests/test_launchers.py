"""Chạy trên Linux/macOS không cần tay: run.sh (môi trường .venv riêng), FireflyVideo.command (bấm đúp trên macOS),
install_linux_shortcut.sh (lối tắt menu Linux), mở trình duyệt không làm hỏng tool khi máy không có trình duyệt.
Các script được chạy thật bằng bash (không cần mạng: pip/python được thay bằng bản giả ghi lại lệnh)."""
import os
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

import app as A

HERE = Path(__file__).resolve().parent.parent
SCRIPTS = ["run.sh", "ffv_env.sh", "build_exe.sh", "FireflyVideo.command", "install_linux_shortcut.sh"]
unix = pytest.mark.skipif(sys.platform == "win32", reason="script bash")


def bash(code, env=None, cwd=None, inp=None):
    e = dict(os.environ if env is None else env)
    return subprocess.run(["/bin/bash", "-c", code], capture_output=True, text=True, env=e, cwd=cwd, input=inp, timeout=60)


def fake_exe(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + textwrap.dedent(body), "utf-8")
    path.chmod(path.stat().st_mode | stat.S_IEXEC)
    return path


@unix
@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_have_valid_bash_syntax(name):
    r = subprocess.run(["/bin/bash", "-n", str(HERE / name)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@unix
@pytest.mark.parametrize("name", ["run.sh", "build_exe.sh", "FireflyVideo.command", "install_linux_shortcut.sh"])
def test_entry_scripts_are_executable_so_double_click_works(name):
    assert os.access(HERE / name, os.X_OK), f"{name} thiếu quyền chạy (chmod +x); bấm đúp trên macOS/Linux sẽ không chạy"


@unix
def test_requirements_files_exist_for_the_scripts():
    for n in ("requirements.txt", "requirements-pack.txt"):
        assert (HERE / n).is_file()
    assert "pyinstaller" in (HERE / "requirements-pack.txt").read_text().lower()


# ----------------------------------------------------------------------------- tìm Python + tạo môi trường
@unix
def test_finds_a_python_310_or_newer():
    r = bash(f'. "{HERE}/ffv_env.sh"; ffv_find_python')
    assert r.returncode == 0
    v = subprocess.run([r.stdout.strip(), "-c", "import sys; print(sys.version_info >= (3, 10))"], capture_output=True, text=True)
    assert v.stdout.strip() == "True"


@unix
def test_old_python_is_rejected_with_install_hints(tmp_path):
    fake_exe(tmp_path / "bin" / "python3", "exit 1\n")  # giả một Python < 3.10: lệnh kiểm tra phiên bản trả lỗi
    env = dict(PATH=str(tmp_path / "bin"))
    assert bash(f'. "{HERE}/ffv_env.sh"; ffv_find_python', env=env).returncode == 1
    r = bash(f'. "{HERE}/ffv_env.sh"; ffv_venv "{tmp_path}/v"', env=env)
    assert r.returncode == 1 and "Python 3.10" in r.stderr and "brew install python" in r.stderr and "apt install python3" in r.stderr
    assert not (tmp_path / "v").exists()


@unix
def test_failed_venv_cleans_up_and_explains(tmp_path):
    for n in ("python3.13", "python3.12", "python3.11", "python3.10", "python3", "python"):  # che hết Python thật của máy chạy test
        fake_exe(tmp_path / "bin" / n, 'case "$1" in -c) exit 0;; -m) exit 1;; esac\n')  # đủ phiên bản nhưng thiếu python3-venv
    r = bash(f'. "{HERE}/ffv_env.sh"; mkdir -p "{tmp_path}/v"; ffv_venv "{tmp_path}/v"', env=dict(PATH=f"{tmp_path}/bin:/bin:/usr/bin"))
    assert r.returncode == 1 and "python3-venv" in r.stderr and not (tmp_path / "v").exists()


@unix
def test_real_venv_is_created_once_and_reused(tmp_path):
    r = bash(f'. "{HERE}/ffv_env.sh"; ffv_venv "{tmp_path}/v"')
    assert r.returncode == 0 and r.stdout.strip() == f"{tmp_path}/v/bin/python" and (tmp_path / "v" / "bin" / "python").exists()
    m = (tmp_path / "v" / "pyvenv.cfg").stat().st_mtime_ns
    assert bash(f'. "{HERE}/ffv_env.sh"; ffv_venv "{tmp_path}/v"').returncode == 0
    assert (tmp_path / "v" / "pyvenv.cfg").stat().st_mtime_ns == m, "lần sau dùng lại, không tạo lại"


# ----------------------------------------------------------------------------- chỉ cài khi requirements đổi
@unix
def test_libraries_are_installed_only_when_requirements_change(tmp_path):
    log = tmp_path / "pip.log"
    py = fake_exe(tmp_path / "v" / "bin" / "python", f'echo "$@" >> "{log}"\n')
    req = tmp_path / "requirements.txt"
    req.write_text("flask>=3.0\n")
    call = f'. "{HERE}/ffv_env.sh"; ffv_install "{py}" "{req}"'
    assert bash(call).returncode == 0
    assert bash(call).returncode == 0
    lines = log.read_text().splitlines()
    assert len(lines) == 1 and f"-r {req}" in lines[0] and "pip install" in lines[0], "chạy lần hai không cài lại"
    req.write_text("flask>=3.0\nnumpy\n")
    assert bash(call).returncode == 0
    assert len(log.read_text().splitlines()) == 2, "requirements đổi thì cài lại"


@unix
def test_install_failure_is_reported_and_retried_next_time(tmp_path):
    py = fake_exe(tmp_path / "v" / "bin" / "python", "exit 1\n")
    req = tmp_path / "r.txt"
    req.write_text("x\n")
    r = bash(f'. "{HERE}/ffv_env.sh"; ffv_install "{py}" "{req}"')
    assert r.returncode == 1 and "internet" in r.stderr
    assert not (tmp_path / "v" / ".requirements-stamp").exists(), "cài hỏng thì không đánh dấu là đã cài"


# ----------------------------------------------------------------------------- bấm đúp (macOS) và lối tắt (Linux)
@unix
def test_command_file_keeps_the_window_open_and_reports_the_exit_code(tmp_path):
    (tmp_path / "FireflyVideo.command").write_text((HERE / "FireflyVideo.command").read_text("utf-8"), "utf-8")
    fake_exe(tmp_path / "run.sh", "echo chay-gia; exit 3\n")
    r = bash("bash FireflyVideo.command", cwd=tmp_path, inp="\n")
    assert r.returncode == 3 and "chay-gia" in r.stdout and "mã 3" in r.stdout and "Bấm Enter" in r.stdout


@unix
def test_linux_shortcut_install_and_remove(tmp_path):
    env = dict(os.environ, HOME=str(tmp_path / "home"), XDG_DATA_HOME=str(tmp_path / "share"))
    (tmp_path / "home").mkdir()
    r = bash(f'"{HERE}/install_linux_shortcut.sh" --desktop', env=env)
    assert r.returncode == 0, r.stderr
    f = tmp_path / "share" / "applications" / "firefly-video.desktop"
    kv = dict(l.split("=", 1) for l in f.read_text("utf-8").splitlines() if "=" in l)
    assert f.read_text("utf-8").startswith("[Desktop Entry]") and kv["Type"] == "Application" and kv["Terminal"] == "true"
    assert kv["Exec"] == f'"{HERE}/run.sh"' and kv["Path"] == str(HERE) and os.access(f, os.X_OK)
    assert (tmp_path / "home" / "Desktop" / "firefly-video.desktop").exists() or any((tmp_path / "home").rglob("firefly-video.desktop"))
    assert bash(f'"{HERE}/install_linux_shortcut.sh" --remove', env=env).returncode == 0
    assert not f.exists() and not list((tmp_path / "home").rglob("firefly-video.desktop"))


@unix
def test_shortcut_handles_a_folder_with_spaces(tmp_path):
    d = tmp_path / "Firefly Video 0.9"
    d.mkdir()
    for n in ("install_linux_shortcut.sh", "run.sh"):
        (d / n).write_text((HERE / n).read_text("utf-8"), "utf-8")
        (d / n).chmod(0o755)
    env = dict(os.environ, HOME=str(tmp_path / "h"), XDG_DATA_HOME=str(tmp_path / "share"))
    assert bash(f'"{d}/install_linux_shortcut.sh"', env=env).returncode == 0
    assert f'Exec="{d}/run.sh"' in (tmp_path / "share" / "applications" / "firefly-video.desktop").read_text("utf-8")


# ----------------------------------------------------------------------------- mở trình duyệt
def test_no_browser_available_prints_the_address_instead_of_failing(monkeypatch, capsys):
    monkeypatch.delenv("FFV_NO_BROWSER", raising=False)
    monkeypatch.setattr(A.webbrowser, "open", lambda url: False)
    assert A.open_browser("http://localhost:8765") is False
    assert "http://localhost:8765" in capsys.readouterr().out


def test_browser_exception_is_swallowed(monkeypatch, capsys):
    monkeypatch.delenv("FFV_NO_BROWSER", raising=False)

    def boom(url):
        raise OSError("không có trình duyệt")
    monkeypatch.setattr(A.webbrowser, "open", boom)
    assert A.open_browser("http://localhost:1") is False


def test_ffv_no_browser_never_opens_one(monkeypatch):
    monkeypatch.setenv("FFV_NO_BROWSER", "1")
    monkeypatch.setattr(A.webbrowser, "open", lambda url: pytest.fail("không được mở trình duyệt"))
    assert A.open_browser("http://localhost:1") is False


def test_browser_opened_when_available(monkeypatch):
    monkeypatch.delenv("FFV_NO_BROWSER", raising=False)
    seen = []
    monkeypatch.setattr(A.webbrowser, "open", lambda url: seen.append(url) or True)
    assert A.open_browser("http://localhost:9") is True and seen == ["http://localhost:9"]
