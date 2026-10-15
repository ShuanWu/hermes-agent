#!/usr/bin/env python3
"""Mirror PaaS-injected secrets (Zeabur service variables) into $HERMES_HOME/.env on every boot.

Since v0.22 the gateway multiplexes profiles whenever more than one exists, and in multiplex mode
the default profile's secrets are read ONLY from $HERMES_HOME/.env (agent/secret_scope.py
build_profile_secret_scope) -- os.environ is never consulted. Zeabur delivers TELEGRAM_BOT_TOKEN,
OMNIROUTE_API_KEY, etc. as process env vars, so without this mirror the gateway logs
"Skipping telegram on default profile: no bot credential" and tools lose their API keys.

Zeabur stays the source of truth: keys listed below overwrite the .env value when set in env.
Other .env lines are left untouched. Override the key list with HERMES_ENV_SYNC_KEYS (comma-separated).
"""
import os
import re
import sys
import tempfile
from pathlib import Path

DEFAULT_KEYS = [
    "TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_USERS",
    "LINE_CHANNEL_ACCESS_TOKEN", "LINE_CHANNEL_SECRET", "LINE_ALLOWED_USERS", "LINE_PUBLIC_URL", "LINE_PORT",
    "OPENROUTER_API_KEY", "OMNIROUTE_BASE_URL", "OMNIROUTE_API_KEY", "OMNIROUTE_MODEL",
    "TODO_API_KEY", "GITHUB_TOKEN", "NETLIFY_AUTH_TOKEN", "BITLY_ACCESS_TOKEN",
    "FELO_API_KEY", "TAVILY_API_KEY",
]


def main() -> int:
    home = Path(os.environ.get("HERMES_HOME") or "/opt/data")
    env_path = home / ".env"
    keys = [k.strip() for k in os.environ.get("HERMES_ENV_SYNC_KEYS", "").split(",") if k.strip()] or DEFAULT_KEYS
    wanted = {k: os.environ[k] for k in keys if os.environ.get(k)}
    if not wanted:
        return 0

    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    seen = set()
    out = []
    for line in lines:
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=", line)
        if m and m.group(1) in wanted:
            key = m.group(1)
            if key in seen:
                continue
            seen.add(key)
            out.append(f"{key}={wanted[key]}")
        else:
            out.append(line)
    out.extend(f"{k}={v}" for k, v in wanted.items() if k not in seen)

    fd, tmp = tempfile.mkstemp(dir=str(home), prefix=".env.")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    if env_path.exists():
        st = env_path.stat()
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except PermissionError:
            pass
    os.replace(tmp, env_path)
    print(f"bootstrap-env-secrets: synced {len(wanted)} key(s) into {env_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # never block gateway startup
        print(f"bootstrap-env-secrets: failed: {exc}", file=sys.stderr)
        sys.exit(0)
