#!/usr/bin/env python3
"""Re-install image-baked extra plugins/memory into $HERMES_HOME on every boot.

/opt/data/plugins/ AND /opt/data/memories/ both get wiped by something in
the cont-init.d chain on every container restart (same class of bug worked
around in bootstrap-model-config.py for model.default — root cause not
isolated: verified empirically that files written there via `service exec`
after boot, including a hand-written MEMORY.md, are gone after the next
restart, even though other config.yaml edits like platforms.line.* and the
persistent volume in general survive). Copying from image-baked sources
here, right before the gateway starts, guarantees both are present every
boot regardless of whatever earlier step is clearing those two volume
directories specifically.

Caveat: this only restores the FIXED baseline baked into the image at
docker/memory/. Anything the agent itself learns and writes to MEMORY.md
between boots is still lost on the next restart — same underlying
limitation, just mitigated for facts important enough to hardcode here.
"""
import shutil
import sys
from pathlib import Path

import yaml

SRC = Path("/opt/hermes/docker/plugins")
DST = Path("/opt/data/plugins")
CONFIG_PATH = Path("/opt/data/config.yaml")
MEMORY_SRC = Path("/opt/hermes/docker/memory")
MEMORY_DST = Path("/opt/data/memories")

if not SRC.is_dir():
    print("bootstrap-plugins: no docker/plugins/ in image, skipping", file=sys.stderr)
else:
    DST.mkdir(parents=True, exist_ok=True)

    installed = []
    for plugin_dir in sorted(SRC.iterdir()):
        if not plugin_dir.is_dir():
            continue
        target = DST / plugin_dir.name
        if target.exists() or target.is_symlink():
            shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(plugin_dir, target)
        installed.append(plugin_dir.name)
        print(f"bootstrap-plugins: installed {plugin_dir.name}")

    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(CONFIG_PATH) as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError:
        # First boot on a fresh/reset volume — same race as
        # bootstrap-model-config.py, hermes hasn't written config.yaml yet.
        cfg = {}

    plugins_cfg = cfg.get("plugins")
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
    enabled = plugins_cfg.get("enabled")
    if not isinstance(enabled, list):
        enabled = []
    for name in installed:
        if name not in enabled:
            enabled.append(name)
    plugins_cfg["enabled"] = enabled
    cfg["plugins"] = plugins_cfg

    with open(CONFIG_PATH, "w") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    print(f"bootstrap-plugins: plugins.enabled = {enabled}")

if not MEMORY_SRC.is_dir():
    print("bootstrap-plugins: no docker/memory/ in image, skipping", file=sys.stderr)
else:
    MEMORY_DST.mkdir(parents=True, exist_ok=True)
    for mem_file in sorted(MEMORY_SRC.iterdir()):
        if not mem_file.is_file():
            continue
        target = MEMORY_DST / mem_file.name
        shutil.copy2(mem_file, target)
        target.chmod(0o600)
        print(f"bootstrap-plugins: restored memory file {mem_file.name}")
