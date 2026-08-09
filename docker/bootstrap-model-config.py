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
"""
import os
import sys

import yaml

PATH = "/opt/data/config.yaml"

base_url = os.environ.get("OMNIROUTE_BASE_URL", "").strip()
api_key = os.environ.get("OMNIROUTE_API_KEY", "").strip()

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
cfg["model"]["default"] = "auto/best-free"

cfg["custom_providers"] = [
    {
        "name": "omniroute",
        "base_url": base_url,
        "api_key": api_key,
    }
]

with open(PATH, "w") as f:
    yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

print("bootstrap-model-config: applied omniroute custom provider config")
