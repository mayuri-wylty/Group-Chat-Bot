from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(os.environ.get("A5_ROOT", Path(__file__).resolve().parent)).resolve()

CONFIG_PATH = BASE_DIR / "config.json"
STATUS_PATH = BASE_DIR / "runtime_status.json"
STATS_PATH = BASE_DIR / "runtime_stats.json"
LOG_DIR = BASE_DIR / "logs"


DEFAULT_CONFIG: dict[str, Any] = {
    "trigger_prefix": "/ai ",
    "whitelist": [],
    "group_whitelist": [],
    "enable_private": True,
    "enable_group": False,
    "llm_api_base": "",
    "llm_api_key": "",
    "llm_model": "",
    "llm_temperature": 0.7,
    "llm_timeout": 120,
    "history_max_messages": 20,
    "system_prompt": "你是一个通过 QQ 接入的 AI 助手。请用简洁、清晰、可靠的中文回答。",
    "max_chunk_size": 500,
    "thinking_msg": "收到，正在处理...",
    "onebot_api_base": "http://127.0.0.1:3000",
    "onebot_access_token": "",
    "bot_host": "127.0.0.1",
    "bot_port": 18089,
    "config_host": "127.0.0.1",
    "config_port": 7070,
}


def ensure_dirs() -> None:
    LOG_DIR.mkdir(exist_ok=True)


def _normalize_list(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    return [str(item).strip() for item in values if str(item).strip()]


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        save_config(DEFAULT_CONFIG)
        return DEFAULT_CONFIG.copy()

    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        data = json.load(file)
    merged = DEFAULT_CONFIG.copy()
    merged.update(data)
    merged["whitelist"] = _normalize_list(merged.get("whitelist", []))
    merged["group_whitelist"] = _normalize_list(merged.get("group_whitelist", []))
    return merged


def save_config(config: dict[str, Any]) -> None:
    merged = DEFAULT_CONFIG.copy()
    merged.update(config)
    merged["whitelist"] = _normalize_list(merged.get("whitelist", []))
    merged["group_whitelist"] = _normalize_list(merged.get("group_whitelist", []))
    with CONFIG_PATH.open("w", encoding="utf-8") as file:
        json.dump(merged, file, ensure_ascii=False, indent=2)


def read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return default.copy()
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except (OSError, json.JSONDecodeError):
        return default.copy()


def write_json(path: Path, data: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
