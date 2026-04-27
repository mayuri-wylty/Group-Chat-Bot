# Group Chat Bot

一个基于 NapCatQQ + OneBot v11 的 QQ AI 机器人，支持个人私聊和 QQ 群聊 `@机器人` 触发，并可在前端配置 OpenAI 兼容的大模型接口。

## 功能

- 支持 OpenAI 兼容接口：自定义 API Base、API Key、模型名称、Temperature。
- 支持自定义系统提示词。
- 支持个人 QQ 私聊：发送 `/ai 问题` 激活后可连续对话。
- 支持 QQ 群聊：开启群聊接入后，群内 `@机器人 问题` 触发回复。
- 支持个人 QQ 白名单和 QQ 群白名单。
- 支持上下文记忆，每个私聊或群聊用户独立保存短期会话历史。
- 提供本地 Web 配置页，默认地址为 `http://127.0.0.1:7070/`。
- 支持一键启动 Bot、配置页和 NapCatQQ。

## 目录说明

- `main.py`：OneBot HTTP 上报入口，处理 QQ 私聊和群聊消息。
- `llm_client.py`：OpenAI 兼容大模型接口客户端。
- `qq_client.py`：OneBot HTTP API 客户端。
- `config_utils.py`：配置读写和默认配置。
- `config_server.py`：本地 Web 配置服务。
- `web/index.html`：配置页前端。
- `Start-A5.ps1`：一键启动核心脚本。
- `启动NapCatQQ.ps1`：NapCatQQ 启动脚本。
- `config.example.json`：配置示例。

## 使用前准备

1. 安装并登录 NapCatQQ。
2. 在 NapCatQQ 中启用 OneBot v11 HTTP 服务：
   - HTTP API：`http://127.0.0.1:3000`
   - HTTP 上报：`http://127.0.0.1:18089/`
3. 复制 `config.example.json` 为 `config.json`，或直接通过配置页保存生成。
4. 准备一个 OpenAI 兼容的大模型接口 Key。

## 启动

运行：

```powershell
.\Start-A5.ps1
```

或双击：

```text
一键启动A5.bat
```

启动后打开配置页：

```text
http://127.0.0.1:7070/
```

## 配置大模型

在配置页填写：

- `API Base`：例如 `https://api.openai.com/v1`，或其他兼容 `/chat/completions` 的接口地址。
- `API Key`：模型服务商提供的密钥。
- `模型名称`：例如 `gpt-4o-mini`、`deepseek-chat` 或服务商提供的模型 ID。
- `系统提示词`：机器人身份、回答风格和行为边界。

保存配置后点击 `启动/重启 Bot`。

## 私聊使用

向机器人账号发送：

```text
/ai 你好，介绍一下你自己
```

激活后后续可以直接发送消息继续会话。

常用命令：

- `/help`：查看帮助。
- `/stop`：退出当前会话。
- `/new`：清空当前会话。

## 群聊使用

在配置页开启 `启用 QQ 群聊`，按需填写群白名单并保存。

群内发送：

```text
@机器人 你好，回复一句测试成功
```

只有 @ 机器人时才会触发，普通群消息会被忽略。

## 安全说明

以下文件和目录默认不会提交到 Git：

- `config.json`
- `runtime_status.json`
- `runtime_stats.json`
- `logs/`
- `NapCatCompat/`
- `dist/`
- `build/`

请不要把 QQ 号、Token、API Key、登录缓存或 NapCat 运行目录提交到公开仓库。
