#!/usr/bin/env bash
# Opt-in installer for the `qn` shell function (instant, zero-turn note capture).
#
# Idempotent and confirmation-gated: it shows what it will add and asks before editing your
# shell rc. Pass --yes to skip the prompt (e.g. for scripted installs).
#
#   bash install_alias.sh          # prompts before writing
#   bash install_alias.sh --yes    # no prompt
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QN_PY="$SKILL_DIR/scripts/qn.py"
MARKER="# quicknotes qn() alias"
ASSUME_YES="${1:-}"

# Pick the rc file from the current shell.
case "${SHELL:-}" in
  *zsh)  RC="$HOME/.zshrc" ;;
  *bash) RC="$HOME/.bashrc" ;;
  *)     RC="${ZDOTDIR:-$HOME}/.profile" ;;
esac

read -r -d '' SNIPPET <<EOF || true
$MARKER
qn() { python3 "$QN_PY" "\$@"; }
EOF

if [ -f "$RC" ] && grep -qF "$MARKER" "$RC"; then
  echo "✓ qn alias already present in $RC — nothing to do."
  exit 0
fi

echo "Will append the following to $RC:"
echo "----------------------------------------"
echo "$SNIPPET"
echo "----------------------------------------"

if [ "$ASSUME_YES" != "--yes" ]; then
  printf "Proceed? [y/N] "
  read -r reply
  case "$reply" in
    y|Y|yes|YES) ;;
    *) echo "Aborted — no changes made."; exit 0 ;;
  esac
fi

printf "\n%s\n" "$SNIPPET" >> "$RC"
echo "✓ Added qn() to $RC. Open a new shell or run: source $RC"
