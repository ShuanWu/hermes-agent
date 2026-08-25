"""Todo/Wiki slash commands — deterministic bypass calling back to the
user's mac mini todo-api (see dev/code/todo-wiki-line/todo_api.py).

Handlers catch bare ``Exception`` (not just ``urllib.error.URLError``):
gateway/run.py's plugin-command dispatch wraps the handler call in its own
try/except and, on ANY exception escaping the handler, silently falls
through to the full LLM agent turn instead of surfacing an error — the
user sees the model improvising a confused answer instead of a fast, clear
failure message. A narrower except here (e.g. only URLError) lets timeouts,
JSON decode errors, or other transient failures slip through that gap.

Ports the exact command semantics of the original dispatch_fast()/
dispatch_wiki_async() in that project's line_webhook.py, just triggered by
slash commands instead of a bare "todo " text prefix, so it can use
Hermes's plugin command-registration bypass (no LLM call at all for these).

Commands are registered as ytodo/ydone/ydel/ywiki (a "y" prefix, not the
bare todo/done/del/wiki names): Hermes has its own internal "todo" TOOL
(tools/todo_tool.py — the agent's own multi-step task-planning scratchpad)
that intercepted a bare `/todo` before this plugin's registered command
ever got a chance to run, even though `hermes_cli/commands.py`'s
COMMAND_REGISTRY has no such entry — confirmed empirically via a real
LINE-webhook-signed test message (200 OK, but nothing ever reached
todo_api.py), not just guessed. The `y` prefix sidesteps the collision
entirely rather than trying to out-priority Hermes's own tool.

Note: the `/ytodo`-style names below are ONLY the Hermes slash-command
names. The HTTP paths this file calls on todo_api.py (/todo, /todo/list,
/todo/close, /todo/delete, /wiki) are unrelated and unchanged — that's a
separate local API with its own routing, see todo_api.py.

Also registers the same actions as agent TOOLS (todo_add/todo_list/
todo_done/todo_delete/wiki_save), not just slash commands. Slash commands
only bypass the LLM when the user types the exact `/ytodo ...` syntax —
a natural-language request ("幫我記一下買牛奶") never sets event.get_command(),
so it falls through to a normal agent turn. Without a real tool to call,
the LLM's only path to "helping" is guessing at direct filesystem writes
against paths like /mnt/persist/obsidian/..., which don't exist (the
container has no mount of the user's real vault) and get rejected by
HERMES_WRITE_SAFE_ROOT — confirmed via a live "File-mutation verifier"
denial. These tools give the LLM a real, working action for the same
natural-language case instead.
"""
import asyncio
import json
import os
import re
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


async def _handle_ytodo(raw_args: str) -> str:
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
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_ydone(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    m = re.fullmatch(r"#?(\d+)", raw_args.strip())
    if not m:
        return "用法：/ydone <編號>，例如 /ydone 3"
    try:
        data = await _call("/todo/close", method="POST", body={"id": m.group(1)})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_ydel(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    m = re.fullmatch(r"#?(\d+)", raw_args.strip())
    if not m:
        return "用法：/ydel <編號>，例如 /ydel 3"
    try:
        data = await _call("/todo/delete", method="POST", body={"id": m.group(1)})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _handle_ywiki(raw_args: str) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    text = raw_args.strip()
    if not text:
        return "用法：/ywiki <內容或連結>"
    try:
        data = await _call("/wiki", method="POST", body={"content": text})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _tool_todo_add(args: dict, **kw) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    content = str(args.get("content") or "").strip()
    if not content:
        return "content 不可為空"
    try:
        data = await _call("/todo", method="POST", body={"content": content})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _tool_todo_list(args: dict, **kw) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    tag = str(args.get("tag") or "").strip().lstrip("#")
    path = f"/todo/list?tag={tag}" if tag else "/todo/list"
    try:
        data = await _call(path)
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _tool_todo_done(args: dict, **kw) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    todo_id = str(args.get("id") or "").strip().lstrip("#")
    if not todo_id:
        return "id 不可為空"
    try:
        data = await _call("/todo/close", method="POST", body={"id": todo_id})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _tool_todo_delete(args: dict, **kw) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    todo_id = str(args.get("id") or "").strip().lstrip("#")
    if not todo_id:
        return "id 不可為空"
    try:
        data = await _call("/todo/delete", method="POST", body={"id": todo_id})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


async def _tool_wiki_save(args: dict, **kw) -> str:
    if not TODO_API_KEY:
        return _missing_key_reply()
    content = str(args.get("content") or "").strip()
    if not content:
        return "content 不可為空"
    try:
        data = await _call("/wiki", method="POST", body={"content": content})
    except Exception as e:
        return f"todo-api 呼叫失敗：{e}"
    return data.get("reply") or data.get("error", "未知錯誤")


_TODO_ADD_SCHEMA = {
    "name": "todo_add",
    "description": (
        "在使用者的個人待辦清單新增一項待辦事項。這會寫入使用者本機的 Obsidian "
        "vault（透過使用者 mac mini 上的本機服務），不是我自己容器裡的檔案系統——"
        "我沒有使用者 vault 的直接檔案存取權，需要新增待辦時一律呼叫這個工具，"
        "不要嘗試自己用檔案工具寫檔。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "待辦事項內容"}},
        "required": ["content"],
    },
}

_TODO_LIST_SCHEMA = {
    "name": "todo_list",
    "description": "列出使用者的個人待辦事項，可選擇依標籤篩選。",
    "parameters": {
        "type": "object",
        "properties": {"tag": {"type": "string", "description": "選填，篩選用的標籤（不含 # 號）"}},
        "required": [],
    },
}

_TODO_DONE_SCHEMA = {
    "name": "todo_done",
    "description": "把使用者的一項待辦事項標記為完成。",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "待辦事項編號"}},
        "required": ["id"],
    },
}

_TODO_DELETE_SCHEMA = {
    "name": "todo_delete",
    "description": "刪除使用者的一項待辦事項。",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "待辦事項編號"}},
        "required": ["id"],
    },
}

_WIKI_SAVE_SCHEMA = {
    "name": "wiki_save",
    "description": (
        "把內容或連結存進使用者的個人知識庫（Obsidian wiki 筆記）。這會寫入使用者"
        "本機的 vault（透過使用者 mac mini 上的本機服務），不是我自己容器裡的檔案"
        "系統——我沒有使用者 vault 的直接檔案存取權，需要記錄筆記時一律呼叫這個"
        "工具，不要嘗試自己用檔案工具寫檔。"
    ),
    "parameters": {
        "type": "object",
        "properties": {"content": {"type": "string", "description": "要存入的內容或連結"}},
        "required": ["content"],
    },
}


def register(ctx) -> None:
    ctx.register_command(
        "ytodo", handler=_handle_ytodo, description="建立/列出待辦（/ytodo <內容> 或 /ytodo list [#tag]）"
    )
    ctx.register_command("ydone", handler=_handle_ydone, description="標記待辦完成，例：/ydone 3")
    ctx.register_command("ydel", handler=_handle_ydel, description="刪除待辦，例：/ydel 3")
    ctx.register_command("ywiki", handler=_handle_ywiki, description="存進知識庫，例：/ywiki <內容或連結>")

    ctx.register_tool(name="todo_add", toolset="todo-wiki", schema=_TODO_ADD_SCHEMA, handler=_tool_todo_add, is_async=True, emoji="📝")
    ctx.register_tool(name="todo_list", toolset="todo-wiki", schema=_TODO_LIST_SCHEMA, handler=_tool_todo_list, is_async=True, emoji="📋")
    ctx.register_tool(name="todo_done", toolset="todo-wiki", schema=_TODO_DONE_SCHEMA, handler=_tool_todo_done, is_async=True, emoji="✅")
    ctx.register_tool(name="todo_delete", toolset="todo-wiki", schema=_TODO_DELETE_SCHEMA, handler=_tool_todo_delete, is_async=True, emoji="🗑️")
    ctx.register_tool(name="wiki_save", toolset="todo-wiki", schema=_WIKI_SAVE_SCHEMA, handler=_tool_wiki_save, is_async=True, emoji="📚")
