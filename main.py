from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from config_utils import LOG_DIR, STATUS_PATH, STATS_PATH, ensure_dirs, load_config, read_json, write_json
from llm_client import LLMError, ask_llm
from qq_client import OneBotClient


ACTIVE_SESSIONS: set[str] = set()
SESSION_HISTORY: dict[str, list[dict[str, str]]] = {}
STOP_COMMANDS = {"/stop", "/ai stop", "/退出"}
NEW_COMMANDS = {"/new", "/ai new", "/新会话"}
HELP_TEXT = """可用命令：
/ai 问题 - 私聊中激活 AI 会话，后续可直接发送消息
/stop - 退出当前 AI 会话
/new - 清空当前 AI 会话
/help - 查看帮助

群聊模式：
开启群聊接入后，@机器人 并发送问题即可触发。"""


def setup_logging() -> None:
    ensure_dirs()
    log_file = LOG_DIR / f"{datetime.now():%Y-%m-%d}.log"
    logging.basicConfig(
        force=True,
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def write_event_log(event_type: str, payload: dict[str, Any]) -> None:
    ensure_dirs()
    path = LOG_DIR / f"events-{datetime.now():%Y-%m-%d}.jsonl"
    record = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "event_type": event_type,
        "payload": payload,
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")


def update_status(**kwargs: Any) -> None:
    status = read_json(STATUS_PATH, {})
    status.update(kwargs)
    status["updated_at"] = datetime.now().isoformat(timespec="seconds")
    write_json(STATUS_PATH, status)


def increment_trigger_count() -> None:
    today = f"{datetime.now():%Y-%m-%d}"
    stats = read_json(STATS_PATH, {"days": {}})
    days = stats.setdefault("days", {})
    current = days.setdefault(today, {"trigger_count": 0})
    current["trigger_count"] = int(current.get("trigger_count", 0)) + 1
    write_json(STATS_PATH, stats)


def split_message(text: str, max_size: int) -> list[str]:
    max_size = max(100, int(max_size or 500))
    if len(text) <= max_size:
        return [text]
    chunks = [text[i : i + max_size] for i in range(0, len(text), max_size)]
    total = len(chunks)
    return [f"[{index}/{total}]\n{chunk}" for index, chunk in enumerate(chunks, start=1)]


def send_chunks(client: OneBotClient, target_type: str, target_id: int, text: str, max_size: int) -> None:
    chunks = split_message(text, max_size)
    for index, chunk in enumerate(chunks, start=1):
        if target_type == "group":
            response = client.send_group_msg(target_id, chunk)
            write_event_log("send_group_msg", {"group_id": target_id, "chunk": chunk, "response": response})
        else:
            response = client.send_private_msg(target_id, chunk)
            write_event_log("send_private_msg", {"user_id": target_id, "chunk": chunk, "response": response})
        logging.info("已发送回复到 %s %s：第 %s/%s 段，长度 %s", target_type, target_id, index, len(chunks), len(chunk))
        time.sleep(0.3)


def normalize_list(values: list[Any]) -> set[str]:
    return {str(item).strip() for item in values if str(item).strip()}


def is_user_allowed(user_id: int, config: dict[str, Any]) -> bool:
    whitelist = normalize_list(config.get("whitelist", []))
    return not whitelist or str(user_id) in whitelist


def is_group_allowed(group_id: int, config: dict[str, Any]) -> bool:
    group_whitelist = normalize_list(config.get("group_whitelist", []))
    return not group_whitelist or str(group_id) in group_whitelist


def message_to_text(message: Any, raw_message: str = "") -> str:
    if isinstance(message, list):
        parts = []
        for item in message:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "text":
                data = item.get("data") or {}
                parts.append(str(data.get("text", "")))
        return "".join(parts).strip()
    text = raw_message or str(message or "")
    text = re.sub(r"\[CQ:at,qq=\d+\]", "", text)
    return text.strip()


def message_mentions_self(event: dict[str, Any], self_id: int | None) -> bool:
    if not self_id:
        return False
    message = event.get("message")
    if isinstance(message, list):
        for item in message:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "at":
                data = item.get("data") or {}
                if str(data.get("qq")) == str(self_id):
                    return True
    raw_message = str(event.get("raw_message") or "")
    return f"[CQ:at,qq={self_id}]" in raw_message


def build_session_key(event: dict[str, Any]) -> str:
    message_type = str(event.get("message_type") or "")
    user_id = int(event.get("user_id", 0) or 0)
    if message_type == "group":
        group_id = int(event.get("group_id", 0) or 0)
        return f"group:{group_id}:user:{user_id}"
    return f"private:{user_id}"


def trim_history(history: list[dict[str, str]], max_messages: int) -> list[dict[str, str]]:
    max_messages = max(2, int(max_messages or 20))
    return history[-max_messages:]


def ask_model(prompt: str, session_key: str, config: dict[str, Any]) -> str:
    history = trim_history(SESSION_HISTORY.get(session_key, []), int(config.get("history_max_messages", 20)))
    reply = ask_llm(
        prompt,
        api_base=str(config.get("llm_api_base", "")),
        api_key=str(config.get("llm_api_key", "")),
        model=str(config.get("llm_model", "")),
        system_prompt=str(config.get("system_prompt", "")),
        history=history,
        temperature=float(config.get("llm_temperature", 0.7)),
        timeout=int(config.get("llm_timeout", 120)),
    )
    history.extend([{"role": "user", "content": prompt}, {"role": "assistant", "content": reply}])
    SESSION_HISTORY[session_key] = trim_history(history, int(config.get("history_max_messages", 20)))
    return reply


def handle_command(text: str, session_key: str, client: OneBotClient, target_type: str, target_id: int) -> bool:
    if text == "/help":
        send_chunks(client, target_type, target_id, HELP_TEXT, 1000)
        return True
    if text in STOP_COMMANDS:
        ACTIVE_SESSIONS.discard(session_key)
        send_chunks(client, target_type, target_id, "已退出 AI 会话。再次发送 /ai 问题 可重新激活。", 1000)
        return True
    if text in NEW_COMMANDS:
        SESSION_HISTORY.pop(session_key, None)
        ACTIVE_SESSIONS.discard(session_key)
        send_chunks(client, target_type, target_id, "已清空当前 AI 会话。", 1000)
        return True
    return False


def handle_message(event: dict[str, Any]) -> None:
    config = load_config()
    message_type = str(event.get("message_type") or "")
    user_id = int(event.get("user_id", 0) or 0)
    group_id = int(event.get("group_id", 0) or 0)
    raw_message = str(event.get("raw_message") or "")
    text = message_to_text(event.get("message"), raw_message)
    prefix = str(config.get("trigger_prefix", "/ai "))
    self_id = int(event.get("self_id", 0) or 0)
    session_key = build_session_key(event)
    client = OneBotClient(config["onebot_api_base"], config.get("onebot_access_token", ""))

    if not user_id:
        logging.warning("忽略缺少 user_id 的事件：%s", event)
        return
    if not is_user_allowed(user_id, config):
        logging.info("忽略非白名单 QQ：%s", user_id)
        return

    if message_type == "private":
        if not bool(config.get("enable_private", True)):
            logging.info("忽略私聊消息：私聊接入未启用")
            return
        target_type = "private"
        target_id = user_id
        is_activation = raw_message.startswith(prefix)
        if handle_command(text, session_key, client, target_type, target_id):
            return
        if not is_activation and session_key not in ACTIVE_SESSIONS:
            logging.info("忽略 QQ %s 的私聊消息：未激活。原文：%s", user_id, raw_message)
            return
        prompt = raw_message[len(prefix) :].strip() if is_activation else text
    elif message_type == "group":
        if not bool(config.get("enable_group", False)):
            logging.info("忽略群聊消息：群聊接入未启用")
            return
        if not group_id or not is_group_allowed(group_id, config):
            logging.info("忽略未允许群聊：%s", group_id)
            return
        if not message_mentions_self(event, self_id):
            logging.info("忽略群 %s 消息：未 @ 机器人", group_id)
            return
        target_type = "group"
        target_id = group_id
        if handle_command(text, session_key, client, target_type, target_id):
            return
        prompt = text
    else:
        logging.info("忽略未知消息类型：%s", message_type)
        return

    if not prompt:
        ACTIVE_SESSIONS.add(session_key)
        send_chunks(client, target_type, target_id, "已进入 AI 会话。发送 /stop 退出，/new 清空会话。", 1000)
        return

    ACTIVE_SESSIONS.add(session_key)
    increment_trigger_count()
    logging.info("收到 %s %s 的消息：%s", target_type, target_id, prompt)

    thinking = str(config.get("thinking_msg", "")).strip()
    if thinking:
        try:
            send_chunks(client, target_type, target_id, thinking, int(config.get("max_chunk_size", 500)))
        except Exception as exc:
            logging.warning("发送处理中提示失败：%s", exc)

    try:
        result = ask_model(prompt, session_key, config)
    except LLMError as exc:
        result = str(exc)
    except Exception:
        logging.exception("模型调用失败")
        result = "模型调用失败，请查看本地日志。"

    logging.info("模型返回到 %s %s，长度：%s，预览：%s", target_type, target_id, len(result), result[:120].replace("\n", " "))
    send_chunks(client, target_type, target_id, result, int(config.get("max_chunk_size", 500)))


class OneBotHandler(BaseHTTPRequestHandler):
    server_version = "QQModelBot/1.0"

    def log_message(self, format: str, *args: Any) -> None:
        logging.info("%s - %s", self.address_string(), format % args)

    def _json_response(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._json_response(200, {"ok": True})
            return
        self._json_response(404, {"error": "not found"})

    def _read_request_body(self) -> str:
        transfer_encoding = self.headers.get("Transfer-Encoding", "").lower()
        if "chunked" in transfer_encoding:
            chunks: list[bytes] = []
            while True:
                size_line = self.rfile.readline().strip()
                if not size_line:
                    continue
                size = int(size_line.split(b";", 1)[0], 16)
                if size == 0:
                    self.rfile.readline()
                    break
                chunks.append(self.rfile.read(size))
                self.rfile.readline()
            return b"".join(chunks).decode("utf-8", errors="replace")

        length = int(self.headers.get("Content-Length", "0") or 0)
        return self.rfile.read(length).decode("utf-8", errors="replace")

    def do_POST(self) -> None:
        body = self._read_request_body()
        try:
            event = json.loads(body or "{}")
        except json.JSONDecodeError:
            write_event_log("invalid_json", {"headers": dict(self.headers), "body": body})
            self._json_response(400, {"error": "invalid json"})
            return

        write_event_log("raw_post", {"path": self.path, "headers": dict(self.headers), "body": body, "event": event})
        self._json_response(200, {"status": "ok"})

        if event.get("post_type") == "message" and event.get("message_type") in {"private", "group"}:
            logging.info("收到 OneBot 消息事件：%s", json.dumps(event, ensure_ascii=False))
            threading.Thread(target=handle_message_safe, args=(event,), daemon=True).start()
        else:
            logging.info("忽略非消息事件：%s", json.dumps(event, ensure_ascii=False))


def handle_message_safe(event: dict[str, Any]) -> None:
    try:
        handle_message(event)
    except Exception:
        logging.exception("处理 OneBot 消息事件失败：%s", json.dumps(event, ensure_ascii=False))


def main() -> None:
    setup_logging()
    config = load_config()
    host = str(config.get("bot_host", "127.0.0.1"))
    port = int(config.get("bot_port", 18089))
    update_status(bot_running=True, bot_host=host, bot_port=port, bot_pid=os.getpid())
    logging.info("QQ Model Bot 启动，监听 OneBot 上报：http://%s:%s", host, port)
    logging.info("请在 NapCatQQ 中配置 HTTP 上报地址：http://%s:%s/", host, port)

    try:
        server = ThreadingHTTPServer((host, port), OneBotHandler)
        server.serve_forever()
    finally:
        update_status(bot_running=False)


if __name__ == "__main__":
    main()
