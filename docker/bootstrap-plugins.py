#!/usr/bin/env python3
"""Re-install image-baked extra plugins into $HERMES_HOME/plugins on every boot.

Earlier versions of this script (and bootstrap-model-config.py) hardcoded
/opt/data instead of reading $HERMES_HOME. /opt/data is NOT the persistent
volume — it lives on the container's own ephemeral root filesystem and gets
recreated empty on every restart. $HERMES_HOME (/mnt/persist in this
deployment) is the real persistent volume (a separate ext4 mount, confirmed
via `mount` inside the container). Writing to /opt/data was a silent no-op:
every boot recreated a fresh, empty scratch copy nobody read, while the
actual plugin directory Hermes loads from ($HERMES_HOME/plugins) sat
untouched since it was first manually seeded — so every plugin-code fix
pushed to this repo after that point never reached the running gateway,
even though the build/deploy pipeline itself succeeded. Confirmed by diffing
$HERMES_HOME/plugins/todo-wiki/__init__.py against the image-baked source
after a "successful" deploy: the persistent copy was still the original
file from initial setup, missing every fix made since.

$HERMES_HOME/memories/ is deliberately NOT touched here (removed from an
earlier version of this script). It's real, persistent, and the agent
actively writes to it between boots — a blind restore-from-image would
have clobbered live learned memory the moment this script started pointing
at the correct persistent path instead of the dead-end /opt/data one.
"""
import os
import shutil
import sys
from pathlib import Path

import yaml

HERMES_HOME = Path(os.environ["HERMES_HOME"])
SRC = Path("/opt/hermes/docker/plugins")
DST = HERMES_HOME / "plugins"
CONFIG_PATH = HERMES_HOME / "config.yaml"

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
        with open(CONFIG_PATH, encoding="utf-8") as f:
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

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)

    print(f"bootstrap-plugins: plugins.enabled = {enabled}")
