#!/usr/bin/env python3
"""Re-apply the OmniRoute custom-provider model config on every boot.

Something in the cont-init.d chain resets config.yaml's model.default back
to the factory anthropic/claude-opus-4.6 on every container restart (root
cause not isolated). Writing model.* and custom_providers directly here
(rather than via `hermes config set custom_providers.0.x`, which creates a
dict instead of a YAML list when the key doesn't exist yet) guarantees a
correct, idempotent result regardless of prior state.

OMNIROUTE_BASE_URL / OMNIROUTE_API_KEY come from Zeabur environment
variables, not hardcoded here — this file lives in a public GitHub fork.

OMNIROUTE_MODEL picks the model re-applied on every boot (default
auto/best-free). Read from an env var rather than hardcoded so switching
models via the dashboard's model picker only requires updating one Zeabur
variable, not editing this file — a manual dashboard model change was
getting silently reverted to a hardcoded value here otherwise.
"""
import os
import sys

import yaml

PATH = "/opt/data/config.yaml"

base_url = os.environ.get("OMNIROUTE_BASE_URL", "").strip()
api_key = os.environ.get("OMNIROUTE_API_KEY", "").strip()
model_default = os.environ.get("OMNIROUTE_MODEL", "").strip() or "auto/best-free"

if not base_url or not api_key:
    print(
        "bootstrap-model-config: OMNIROUTE_BASE_URL/OMNIROUTE_API_KEY not set, "
        "skipping custom-provider config",
        file=sys.stderr,
    )
    sys.exit(0)

with open(PATH) as f:
    cfg = yaml.safe_load(f) or {}

cfg.setdefault("model", {})
cfg["model"]["provider"] = "custom"
cfg["model"]["base_url"] = base_url
cfg["model"]["default"] = model_default

cfg["custom_providers"] = [
    {
        "name": "omniroute",
        "base_url": base_url,
        "api_key": api_key,
    }
]

# Same reset behavior hits platforms.line.enabled (verified empirically:
# `hermes config set platforms.line.enabled true` survives right up until
# the next restart, then reads back as unset again). Reassert it here too
# whenever real LINE credentials are present, since the whole point of this
# deploy is Hermes owning the LINE webhook directly.
if os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "").strip():
    platforms_cfg = cfg.setdefault("platforms", {})
    if not isinstance(platforms_cfg, dict):
        platforms_cfg = {}
        cfg["platforms"] = platforms_cfg
    line_cfg = platforms_cfg.setdefault("line", {})
    if not isinstance(line_cfg, dict):
        line_cfg = {}
        platforms_cfg["line"] = line_cfg
    line_cfg["enabled"] = True

# Same reassertion for Telegram — it defaults to long-polling (no inbound
# port/domain needed, unlike LINE's webhook), but platforms.telegram.enabled
# is still subject to the same boot-time reset.
if os.environ.get("TELEGRAM_BOT_TOKEN", "").strip():
    platforms_cfg = cfg.setdefault("platforms", {})
    if not isinstance(platforms_cfg, dict):
        platforms_cfg = {}
        cfg["platforms"] = platforms_cfg
    telegram_cfg = platforms_cfg.setdefault("telegram", {})
    if not isinstance(telegram_cfg, dict):
        telegram_cfg = {}
        platforms_cfg["telegram"] = telegram_cfg
    telegram_cfg["enabled"] = True

with open(PATH, "w") as f:
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

print("bootstrap-model-config: applied omniroute custom provider config")
