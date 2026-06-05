#!/usr/bin/env python3
"""
quicknotes core store.

A single source of truth for capturing, reading, and managing notes — shared by the `qn`
CLI, the session-reminder hook, and the skill. Notes are one markdown file per note under
`<home>/notes/<id>.md`, with JSON-encoded frontmatter values (valid YAML, but parseable with
the stdlib `json` module — no third-party dependency).

`home` defaults to $QUICKNOTES_HOME or ~/.quicknotes; tests pass an explicit temp home.
"""

import json
import os
import re
import random
import subprocess
from datetime import datetime, timezone
from pathlib import Path


FIELDS = ["id", "title", "created", "updated", "priority",
          "project", "cwd", "branch", "tags", "due", "refs"]

# Lifecycle: a note is active until completed; `complete()` deletes it. There is no
# status field — every persisted note is active.
_ID_SAFE = re.compile(r"[0-9A-Za-z._-]+")  # no path separators / traversal
_HEX = "0123456789abcdef"


def default_home() -> Path:
    return Path(os.environ.get("QUICKNOTES_HOME") or (Path.home() / ".quicknotes"))


def notes_dir(home: Path | None = None) -> Path:
    return (Path(home) if home else default_home()) / "notes"


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_id(now: datetime | None = None, rand: str | None = None) -> str:
    now = now or datetime.now(timezone.utc)
    suffix = rand or "".join(random.choices(_HEX, k=4))
    return now.strftime("%Y%m%d-%H%M%S-") + suffix


# --- tags --------------------------------------------------------------------------------

# A hashtag: `#token` at the start of a word (so `C#` / `issue#5` mid-word don't match).
_HASHTAG = re.compile(r"(?<![^\s])#([A-Za-z0-9_-]+)")


def normalize_tag(tag: str) -> str:
    """Canonical tag form: drop leading '#', lowercase, collapse whitespace to '-'."""
    t = tag.strip().lstrip("#").strip().lower()
    return re.sub(r"\s+", "-", t)


def normalize_tags(tags) -> list[str]:
    out, seen = [], set()
    for t in tags or []:
        n = normalize_tag(t)
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def extract_hashtags(text: str) -> tuple[str, list[str]]:
    """Split `#hashtags` out of free text. Returns (text_without_tags, raw_tags)."""
    tags = _HASHTAG.findall(text)
    cleaned = re.sub(r"\s{2,}", " ", _HASHTAG.sub("", text)).strip()
    return cleaned, tags


# --- git/project metadata (best-effort; never raise) -------------------------------------

def _git(cwd: str, *args: str) -> str | None:
    try:
        out = subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, timeout=2)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def detect_project(cwd: str) -> str:
    remote = _git(cwd, "remote", "get-url", "origin")
    if remote:
        return re.sub(r"\.git$", "", remote.rstrip("/").split("/")[-1])
    return Path(cwd).name


def detect_branch(cwd: str) -> str | None:
    return _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")


# --- (de)serialization -------------------------------------------------------------------

def _within(base: Path, candidate: Path) -> bool:
    try:
        return candidate.resolve().is_relative_to(base.resolve())
    except (OSError, ValueError):
        return False


def write_note(home: Path, note: dict, body: str) -> Path:
    d = notes_dir(home)
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{note['id']}.md"
    if not _within(d, path):
        raise ValueError(f"refusing to write outside notes dir: {path}")
    lines = ["---"]
    lines += [f"{k}: {json.dumps(note.get(k))}" for k in FIELDS]
    lines += ["---", "", body.rstrip("\n"), ""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def read_note(path: Path) -> dict | None:
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError:
        return None
    if not raw.startswith("---"):
        return None
    lines = raw.split("\n")
    end = next((i for i in range(1, len(lines)) if lines[i].strip() == "---"), None)
    if end is None:
        return None
    note: dict = {}
    for line in lines[1:end]:
        if not line.strip():
            continue
        key, sep, val = line.partition(": ")
        if not sep:
            continue
        try:
            note[key.strip()] = json.loads(val)
        except json.JSONDecodeError:
            note[key.strip()] = val
    if "id" not in note:
        return None
    note.setdefault("tags", [])
    note.setdefault("refs", [])
    note["body"] = "\n".join(lines[end + 1:]).strip("\n")
    note["path"] = str(path)
    return note


# --- operations --------------------------------------------------------------------------

def capture(text: str, home: Path | None = None, now: datetime | None = None,
            project: str | None = None, cwd: str | None = None, branch: str | None = None,
            tags: list | None = None, title: str | None = None, priority: str | None = None,
            due: str | None = None, rand: str | None = None) -> dict:
    home = Path(home) if home else default_home()
    now = now or datetime.now(timezone.utc)
    cwd = cwd if cwd is not None else os.getcwd()
    project = project if project is not None else detect_project(cwd)
    branch = branch if branch is not None else detect_branch(cwd)
    body = (text or "").strip()
    if title is None:
        title = (body.splitlines()[0][:80] if body else "")
    note = {
        "id": new_id(now, rand), "title": title,
        "created": _iso(now), "updated": _iso(now),
        "priority": priority,
        "project": project, "cwd": str(cwd), "branch": branch,
        "tags": normalize_tags(tags), "due": due, "refs": [],
    }
    write_note(home, note, body)
    note["body"] = body
    return note


def get(home: Path, nid: str) -> dict | None:
    if not nid or not _ID_SAFE.fullmatch(nid):
        return None
    path = notes_dir(home) / f"{nid}.md"
    if not _within(notes_dir(home), path) or not path.is_file():
        return None
    return read_note(path)


def list_notes(home: Path, project: str | None = None,
               tag: str | None = None) -> list[dict]:
    out = []
    for path in sorted(notes_dir(home).glob("*.md"), reverse=True):  # id sorts chronologically
        note = read_note(path)
        if not note:
            continue
        if project and note.get("project") != project:
            continue
        if tag and tag not in (note.get("tags") or []):
            continue
        out.append(note)
    return out


def _haystack(note: dict) -> str:
    return " ".join([note.get("title", ""), note.get("body", ""),
                     " ".join(note.get("tags", [])), note.get("project", "") or ""]).lower()


def search(home: Path, query: str) -> list[dict]:
    q = query.lower().strip()
    scored = []
    for note in list_notes(home):
        hay = _haystack(note)
        score = hay.count(q) * 3 if q in hay else 0
        score += sum(1 for w in q.split() if w in hay)
        if score:
            scored.append((score, note))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [n for _, n in scored]


def resolve(home: Path, ref: str) -> tuple[dict | None, list[dict]]:
    """Resolve a target note from an id or fuzzy text. Returns (note, candidates)."""
    exact = get(home, ref)
    if exact:
        return exact, []
    low = ref.lower()
    cands = [n for n in list_notes(home) if low in _haystack(n)]
    return (cands[0], []) if len(cands) == 1 else (None, cands)


def complete(home: Path, nid: str) -> dict | None:
    """Mark a note done by DELETING its file. Returns the note (pre-delete) or None.

    Hard delete — the note is removed from the filesystem. If the notes dir is a git
    repo and the note was committed, it remains recoverable from history.
    """
    note = get(home, nid)
    if not note:
        return None
    path = notes_dir(home) / f"{nid}.md"
    if _within(notes_dir(home), path) and path.is_file():
        path.unlink()
    return note


_EDITABLE = {"title", "tags", "priority", "due", "project"}


def update(home: Path, nid: str, now: datetime | None = None, body: str | None = None,
           **changes) -> dict | None:
    note = get(home, nid)
    if not note:
        return None
    if "tags" in changes:
        changes["tags"] = normalize_tags(changes["tags"])
    for k, v in changes.items():
        if k in _EDITABLE:
            note[k] = v
    if body is not None:
        note["body"] = body
    note["updated"] = _iso(now or datetime.now(timezone.utc))
    write_note(home, note, note["body"])
    return note


def add_ref(home: Path, id_a: str, id_b: str, now: datetime | None = None) -> bool:
    a, b = get(home, id_a), get(home, id_b)
    if not a or not b or id_a == id_b:
        return False
    ts = _iso(now or datetime.now(timezone.utc))
    for note, other in ((a, id_b), (b, id_a)):
        refs = note.get("refs") or []
        if other not in refs:
            refs.append(other)
        note["refs"] = refs
        note["updated"] = ts
        write_note(home, note, note["body"])
    return True


def due_notes(home: Path, now: datetime | None = None) -> list[dict]:
    cutoff = _iso(now or datetime.now(timezone.utc))
    return [n for n in list_notes(home) if n.get("due") and n["due"] <= cutoff]


def here_notes(home: Path, project: str | None = None, cwd: str | None = None) -> list[dict]:
    cwd = cwd if cwd is not None else os.getcwd()
    project = project if project is not None else detect_project(cwd)
    return [n for n in list_notes(home)
            if n.get("project") == project or n.get("cwd") == str(cwd)]
