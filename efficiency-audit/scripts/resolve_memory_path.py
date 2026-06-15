#!/usr/bin/env python3
"""Print the path of the project MEMORY.md, honouring autoMemoryDirectory if set."""
import json
import os
import subprocess
import sys

for p in [
    os.path.expanduser("~/.claude/settings.json"),
    ".claude/settings.json",
    ".claude/settings.local.json",
]:
    try:
        d = json.load(open(p))
        if "autoMemoryDirectory" in d:
            print(os.path.join(os.path.expanduser(d["autoMemoryDirectory"]), "MEMORY.md"))
            sys.exit(0)
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass

try:
    root = subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.DEVNULL, text=True
    ).strip()
except subprocess.CalledProcessError:
    root = os.getcwd()

proj = root.replace("/", "-").replace(".", "-")
print(os.path.expanduser(f"~/.claude/projects/{proj}/memory/MEMORY.md"))
