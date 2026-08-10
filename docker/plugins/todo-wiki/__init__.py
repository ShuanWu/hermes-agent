"""Todo/Wiki slash commands — deterministic bypass calling back to the
user's mac mini todo-api (see dev/code/todo-wiki-line/todo_api.py).

Ports the exact command semantics of the original dispatch_fast()/
dispatch_wiki_async() in that project's line_webhook.py, just triggered by
`/todo` instead of a bare "todo " text prefix, so it can use Hermes's
plugin command-registration bypass (no LLM call at all for these).
"""
import asyncio
import json
import os
import re
import urllib.error
import urllib.request

TODO_API_URL = "https://macmini.taila4f347.ts.net/todo-api"
TODO_API_KEY = os.environ.get("TODO_API_KEY", "")
TIMEOUT = 15


def _call_sync(path: str, method: str = "GET", body: dict | None = None) -> dict:
    url = f"{TODO_API_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {TODO_API_KEY}",
            "Content-Type": "application/json",
        },
        method=method,
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


async def _call(path: str, method: str = "GET", body: dict | None = None) -> dict:
    return await asyncio.to_thread(_call_sync, path, method, body)


def _missing_key_reply() -> str:
    return "todo-wiki plugin 未設定 TODO_API_KEY 環境變數，無法連線 todo-api。"


async def _handle_todo(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    text = raw_args.strip()
    try:
        if text == "list" or text.startswith("list "):
            tag = text[len("list") :].strip().lstrip("#")
            path = f"/todo/list?tag={tag}" if tag else "/todo/list"
            data = await _call(path)
        else:
            data = await _call("/todo", method="POST", body={"content": text})
    except urllib.error.URLError as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_done(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    m = re.fullmatch(r"#?(\d+)", raw_args.strip())
    if not m:
        return "用法：/done <編號>，例如 /done 3"
    try:
        data = await _call("/todo/close", method="POST", body={"id": m.group(1)})
    except urllib.error.URLError as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_del(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    m = re.fullmatch(r"#?(\d+)", raw_args.strip())
    if not m:
        return "用法：/del <編號>，例如 /del 3"
    try:
        data = await _call("/todo/delete", method="POST", body={"id": m.group(1)})
    except urllib.error.URLError as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_wiki(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    text = raw_args.strip()
    if not text:
        return "用法：/wiki <內容或連結>"
    try:
        data = await _call("/wiki", method="POST", body={"content": text})
    except urllib.error.URLError as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


def register(ctx) -> None:
    ctx.register_command(
        "todo", handler=_handle_todo, description="建立/列出待辦（/todo <內容> 或 /todo list [#tag]）"
    )
    ctx.register_command("done", handler=_handle_done, description="標記待辦完成，例：/done 3")
    ctx.register_command("del", handler=_handle_del, description="刪除待辦，例：/del 3")
    ctx.register_command("wiki", handler=_handle_wiki, description="存進知識庫，例：/wiki <內容或連結>")
