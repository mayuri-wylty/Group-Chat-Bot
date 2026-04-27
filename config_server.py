from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import time
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from config_utils import BASE_DIR, STATS_PATH, STATUS_PATH, load_config, read_json, save_config
from qq_client import OneBotClient


WEB_DIR = BASE_DIR / "web"
NAPCAT_ROOT = BASE_DIR / "NapCatCompat"
NAPCAT_SHELL_DIR = NAPCAT_ROOT / "NapCat.41785.Shell"
NAPCAT_LAUNCHER = BASE_DIR / "启动NapCatQQ.ps1"
NAPCAT_WEBUI_CONFIG = (
    NAPCAT_SHELL_DIR
    / "versions"
    / "9.9.23-41785"
    / "resources"
    / "app"
    / "napcat"
    / "config"
    / "webui.json"
)
BOT_PROCESS: subprocess.Popen | None = None


def is_pid_running(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def is_tcp_listening(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def current_launcher_qq() -> str:
    if not NAPCAT_LAUNCHER.exists():
        return ""
    text = NAPCAT_LAUNCHER.read_text(encoding="utf-8", errors="replace")
    match = re.search(r'NapCatWinBootMain\.exe"\s+(\d+)', text)
    return match.group(1) if match else ""


def write_napcat_launcher(qq: str | None) -> None:
    quick_login = f" {qq}" if qq else ""
    content = f"""$OutputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new()
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$napcatDir = Join-Path $root "NapCatCompat\\NapCat.41785.Shell"
Set-Location $napcatDir
& ".\\NapCatWinBootMain.exe"{quick_login}
"""
    NAPCAT_LAUNCHER.write_text(content, encoding="utf-8", newline="\r\n")


def run_powershell(script: str, timeout: int = 10) -> subprocess.CompletedProcess[str]:
    startupinfo = None
    creationflags = 0
    if os.name == "nt":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        creationflags = subprocess.CREATE_NO_WINDOW
    return subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        cwd=str(BASE_DIR),
        text=True,
        capture_output=True,
        timeout=timeout,
        startupinfo=startupinfo,
        creationflags=creationflags,
    )


def napcat_processes() -> list[dict[str, Any]]:
    root = str(NAPCAT_ROOT.resolve()).replace("'", "''")
    script = f"""
$root = '{root}'
$items = Get-CimInstance Win32_Process | Where-Object {{
  ($_.ExecutablePath -like "$root*") -or
  (($_.Name -in @('NapCatWinBootMain.exe','QQ.exe')) -and ($_.CommandLine -like "*NapCatCompat*"))
}} | Select-Object ProcessId,Name,ExecutablePath,CommandLine
$items | ConvertTo-Json -Compress
"""
    try:
        result = run_powershell(script)
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout.strip():
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    return data if isinstance(data, list) else []


def stop_napcat_processes() -> int:
    root = str(NAPCAT_ROOT.resolve()).replace("'", "''")
    script = f"""
$root = '{root}'
$items = Get-CimInstance Win32_Process | Where-Object {{
  ($_.ExecutablePath -like "$root*") -or
  (($_.Name -in @('NapCatWinBootMain.exe','QQ.exe')) -and ($_.CommandLine -like "*NapCatCompat*"))
}}
$count = @($items).Count
$items | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }}
$count
"""
    result = run_powershell(script, timeout=15)
    try:
        return int(result.stdout.strip().splitlines()[-1])
    except (IndexError, ValueError):
        return 0


def start_napcat() -> int:
    if not NAPCAT_LAUNCHER.exists():
        raise FileNotFoundError(f"找不到启动脚本：{NAPCAT_LAUNCHER}")
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoExit",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(NAPCAT_LAUNCHER),
        ],
        cwd=str(BASE_DIR),
        creationflags=subprocess.CREATE_NEW_CONSOLE,
    )
    return process.pid


def restart_napcat(qq: str | None, update_launcher: bool = True) -> dict[str, Any]:
    if update_launcher:
        write_napcat_launcher(qq)
    stopped = stop_napcat_processes()
    time.sleep(1)
    pid = start_napcat()
    return {"ok": True, "pid": pid, "stopped": stopped, "quick_login_qq": qq or ""}


class ConfigHandler(SimpleHTTPRequestHandler):
    server_version = "QQAIBotConfig/1.0"

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(WEB_DIR), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        body = self.rfile.read(length).decode("utf-8", errors="replace")
        return json.loads(body or "{}")

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (ConnectionAbortedError, BrokenPipeError, ConnectionResetError, OSError):
            return

    def do_GET(self) -> None:
        if self.path == "/api/config":
            self._json_response(200, load_config())
            return
        if self.path == "/api/status":
            self._json_response(200, self._status())
            return
        if self.path == "/api/napcat/status":
            self._json_response(200, self._napcat_status())
            return
        if self.path == "/api/me":
            self._json_response(200, self._login_info())
            return
        super().do_GET()

    def do_POST(self) -> None:
        global BOT_PROCESS
        if self.path == "/api/config":
            try:
                data = self._read_body()
                save_config(data)
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
                return
            self._json_response(200, {"ok": True})
            return

        if self.path == "/api/restart":
            if BOT_PROCESS and BOT_PROCESS.poll() is None:
                BOT_PROCESS.terminate()
                try:
                    BOT_PROCESS.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    BOT_PROCESS.kill()
            bot_exe = BASE_DIR / "A5Bot.exe"
            if getattr(sys, "frozen", False) and bot_exe.exists():
                BOT_PROCESS = subprocess.Popen([str(bot_exe)], cwd=str(BASE_DIR))
            else:
                BOT_PROCESS = subprocess.Popen([sys.executable, str(BASE_DIR / "main.py")], cwd=str(BASE_DIR))
            self._json_response(200, {"ok": True, "pid": BOT_PROCESS.pid})
            return

        if self.path == "/api/napcat/switch":
            try:
                data = self._read_body()
                qq = str(data.get("qq", "")).strip()
                if not re.fullmatch(r"\d{5,12}", qq):
                    raise ValueError("QQ 号格式不正确")
                result = restart_napcat(qq)
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
                return
            self._json_response(200, result)
            return

        if self.path == "/api/napcat/qrcode":
            try:
                result = restart_napcat(None)
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
                return
            self._json_response(200, result)
            return

        if self.path == "/api/napcat/restart":
            try:
                qq = current_launcher_qq() or None
                result = restart_napcat(qq, update_launcher=False)
            except Exception as exc:
                self._json_response(400, {"ok": False, "error": str(exc)})
                return
            self._json_response(200, result)
            return

        self._json_response(404, {"error": "not found"})

    def _status(self) -> dict[str, Any]:
        config = load_config()
        status = read_json(STATUS_PATH, {})
        stats = read_json(STATS_PATH, {"days": {}})
        today = f"{datetime.now():%Y-%m-%d}"
        today_stats = stats.get("days", {}).get(today, {"trigger_count": 0})
        bot_pid = status.get("bot_pid")
        bot_running = bool(BOT_PROCESS and BOT_PROCESS.poll() is None)
        if not bot_running:
            bot_running = is_pid_running(bot_pid)
        if not bot_running:
            bot_running = is_tcp_listening(str(config.get("bot_host", "127.0.0.1")), int(config.get("bot_port", 18089)))
        login = self._login_info()
        return {
            "bot_running": bot_running,
            "bot_pid": bot_pid,
            "bot_host": status.get("bot_host", config.get("bot_host")),
            "bot_port": status.get("bot_port", config.get("bot_port")),
            "onebot_api_base": config.get("onebot_api_base"),
            "onebot_ok": login.get("ok", False),
            "self_id": login.get("user_id"),
            "nickname": login.get("nickname"),
            "today_trigger_count": today_stats.get("trigger_count", 0),
            "napcat": self._napcat_status(),
        }

    def _napcat_status(self) -> dict[str, Any]:
        processes = napcat_processes()
        webui = read_json(NAPCAT_WEBUI_CONFIG, {})
        port = webui.get("port") or 6099
        token = webui.get("token") or ""
        webui_url = f"http://127.0.0.1:{port}/webui"
        if token:
            webui_url += f"?token={token}"
        return {
            "running": bool(processes),
            "process_count": len(processes),
            "processes": processes,
            "launcher_qq": current_launcher_qq(),
            "webui_url": webui_url,
            "shell_dir": str(NAPCAT_SHELL_DIR),
        }

    def _login_info(self) -> dict[str, Any]:
        config = load_config()
        try:
            client = OneBotClient(config["onebot_api_base"], config.get("onebot_access_token", ""), timeout=3)
            data = client.get_login_info()
            info = data.get("data") or {}
            return {
                "ok": data.get("status") == "ok",
                "user_id": info.get("user_id"),
                "nickname": info.get("nickname"),
                "raw": data,
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc)}


def main() -> None:
    config = load_config()
    host = str(config.get("config_host", "127.0.0.1"))
    port = int(config.get("config_port", 7070))
    url = f"http://{host}:{port}"
    print(f"配置页已启动：{url}")
    server = ThreadingHTTPServer((host, port), ConfigHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
