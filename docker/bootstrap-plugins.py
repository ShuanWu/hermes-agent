#!/usr/bin/env python3
"""Re-install image-baked extra plugins into $HERMES_HOME/plugins on every boot.

/opt/data/plugins/ gets wiped by something in the cont-init.d chain on every
container restart (same class of bug worked around in
bootstrap-model-config.py for model.default — root cause not isolated:
verified empirically that files written there via `service exec` after boot
are gone after the next restart, even though other config.yaml edits like
platforms.line.* survive). Copying from the image-baked source here, right
before the gateway starts, guarantees the plugin is present every boot
regardless of whatever earlier step is clearing the volume directory.
"""
import shutil
import sys
from pathlib import Path

import yaml

SRC = Path("/opt/hermes/docker/plugins")
DST = Path("/opt/data/plugins")
CONFIG_PATH = Path("/opt/data/config.yaml")

if not SRC.is_dir():
    print("bootstrap-plugins: no docker/plugins/ in image, skipping", file=sys.stderr)
    sys.exit(0)

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

with open(CONFIG_PATH) as f:
    cfg = yaml.safe_load(f) or {}

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
