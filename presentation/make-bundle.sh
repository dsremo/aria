#!/usr/bin/env bash
set -euo pipefail

DEST="${1:-$HOME/spaceai-bundle-$(date +%F)}"
SPACEAI_PARENT="${SPACEAI_PARENT:-$HOME/Music/SpaceAi}"
ARIA_REPO="${ARIA_REPO:-$SPACEAI_PARENT/aria-core}"
DSREMO_REPO="${DSREMO_REPO:-$SPACEAI_PARENT/Dsremo-Website}"
MEMORY_DIR="${MEMORY_DIR:-$HOME/.claude/projects/-home-ashutosh-Music-SpaceAi/memory}"
KEYS_FILE="${KEYS_FILE:-$HOME/.aria-keys.env}"

if [[ ! -d "$ARIA_REPO" ]]; then
  echo "ERROR: aria-core repo not found at $ARIA_REPO" >&2
  echo "Set ARIA_REPO=/path/to/aria-core and re-run." >&2
  exit 1
fi

echo "==> Bundle destination: $DEST"
mkdir -p "$DEST"/{secrets,claude-memory,data-raw,md-archive,leann-index,graphify-out,spaceai-parent}

echo "==> [1/8] Upstream API keys + AWS EC2 SSH key + Dsremo .env"
if [[ -f "$KEYS_FILE" ]]; then
  install -m 0600 "$KEYS_FILE" "$DEST/secrets/aria-keys.env"
  echo "    + aria-keys.env ($(wc -l < "$KEYS_FILE") lines)"
fi
if [[ -f "$SPACEAI_PARENT/spaceai-key.pem" ]]; then
  install -m 0600 "$SPACEAI_PARENT/spaceai-key.pem" "$DEST/secrets/spaceai-key.pem"
  echo "    + spaceai-key.pem (AWS EC2 SSH key — UNRECOVERABLE if lost)"
fi
if [[ -f "$DSREMO_REPO/.env" ]]; then
  install -m 0600 "$DSREMO_REPO/.env" "$DEST/secrets/dsremo-website.env"
  echo "    + dsremo-website.env"
fi

echo "==> [2/8] Claude auto-memory ($MEMORY_DIR)"
if [[ -d "$MEMORY_DIR" ]]; then
  rsync -a --delete "$MEMORY_DIR/" "$DEST/claude-memory/"
  COUNT=$(find "$DEST/claude-memory/" -name '*.md' | wc -l)
  echo "    OK ($COUNT memory files)"
else
  echo "    SKIP — $MEMORY_DIR not found"
fi

echo "==> [3/8] Bulk datasets (data/raw/eden_iss + genelab + horizons + nasa_battery)"
for sub in eden_iss eden_iss.zip genelab horizons nasa_battery; do
  if [[ -e "$ARIA_REPO/data/raw/$sub" ]]; then
    rsync -a "$ARIA_REPO/data/raw/$sub" "$DEST/data-raw/"
    echo "    + $sub ($(du -sh "$ARIA_REPO/data/raw/$sub" | cut -f1))"
  fi
done

echo "==> [4/8] Flat .md archive (preserves hierarchy under aria-core/)"
( cd "$ARIA_REPO" && \
  find . -name '*.md' \
    -not -path './node_modules/*' \
    -not -path './.git/*' \
    -not -path './.venv/*' \
    -not -path './venv/*' \
    -not -path '*/site-packages/*' \
    -not -path './web/node_modules/*' \
    -print0 \
  | rsync -a --files-from=- --from0 . "$DEST/md-archive/" ) || true
MD_COUNT=$(find "$DEST/md-archive/" -name '*.md' 2>/dev/null | wc -l)
echo "    OK ($MD_COUNT .md files archived)"

echo "==> [5/8] SpaceAi parent files (AWS_INFRA, EXPERT_PANEL_*, CENTRAL_AI_MASTER_PLAN, docs/research/scripts)"
for f in AWS_INFRA.md CENTRAL_AI_MASTER_PLAN.md EXPERT_PANEL_CRITIQUE.md EXPERT_PANEL_CRITIQUE_V3.md EXPERT_PANEL_CRITIQUE_DSREMO_V3.md; do
  if [[ -f "$SPACEAI_PARENT/$f" ]]; then
    cp "$SPACEAI_PARENT/$f" "$DEST/spaceai-parent/$f"
    echo "    + $f"
  fi
done
for sub in docs research scripts data; do
  if [[ -d "$SPACEAI_PARENT/$sub" ]]; then
    rsync -a "$SPACEAI_PARENT/$sub/" "$DEST/spaceai-parent/$sub/"
    echo "    + $sub/"
  fi
done
read -r -p "    Include logs/ ($(du -sh "$SPACEAI_PARENT/logs" 2>/dev/null | cut -f1 || echo 'n/a'))? [y/N] " yn
if [[ "${yn,,}" == "y" && -d "$SPACEAI_PARENT/logs" ]]; then
  rsync -a "$SPACEAI_PARENT/logs/" "$DEST/spaceai-parent/logs/"
  echo "    + logs/"
fi
echo ""

echo "==> [6/8] Optional: leann index + graphify-out (regeneratable but slow)"
read -r -p "    Include .leann/ ($(du -sh "$ARIA_REPO/.leann" 2>/dev/null | cut -f1 || echo 'n/a'))? [y/N] " yn
if [[ "${yn,,}" == "y" ]]; then
  rsync -a "$ARIA_REPO/.leann/" "$DEST/leann-index/"
  echo "    OK"
fi
read -r -p "    Include src/graphify-out/ ($(du -sh "$ARIA_REPO/src/graphify-out" 2>/dev/null | cut -f1 || echo 'n/a'))? [y/N] " yn
if [[ "${yn,,}" == "y" ]]; then
  rsync -a "$ARIA_REPO/src/graphify-out/" "$DEST/graphify-out/"
  echo "    OK"
fi

echo "==> [7/8] Verify both git repos clean + pushed"
for repo in "$ARIA_REPO" "$DSREMO_REPO"; do
  if [[ -d "$repo/.git" ]]; then
    cd "$repo"
    DIRTY=$(git status --porcelain | wc -l)
    UNPUSHED=$(git log @{u}..HEAD --oneline 2>/dev/null | wc -l)
    if [[ "$DIRTY" -gt 0 || "$UNPUSHED" -gt 0 ]]; then
      echo "    WARNING $(basename "$repo"): $DIRTY dirty, $UNPUSHED unpushed — NOT SAFE TO DELETE"
    else
      echo "    OK $(basename "$repo"): clean + pushed → $(git rev-parse --short HEAD)"
    fi
  fi
done
cd - > /dev/null
echo ""

echo "==> [8/8] Bundle manifest"
cat > "$DEST/MANIFEST.txt" <<EOF
ARIA portable bundle
Created: $(date -Iseconds)
Source host: $(hostname)
Source user: $(whoami)
Source repo HEAD: $(cd "$ARIA_REPO" && git rev-parse HEAD)
Source repo branch: $(cd "$ARIA_REPO" && git rev-parse --abbrev-ref HEAD)
Source repo origin: $(cd "$ARIA_REPO" && git remote get-url origin)

Contents:
$(cd "$DEST" && find . -maxdepth 2 -type d | sort)

Sizes:
$(cd "$DEST" && du -sh */ 2>/dev/null | sort -h)

Restore: copy this folder to a pen drive, then on the new laptop run
    bash setup.sh /path/to/aria-bundle-<date>
The setup script lives at presentation/setup.sh in the cloned repo;
a copy is included in this bundle for first-run convenience.
EOF
cp "$ARIA_REPO/presentation/setup.sh" "$DEST/setup.sh" 2>/dev/null || true
chmod +x "$DEST/setup.sh" 2>/dev/null || true

echo ""
echo "==> Done."
echo "    Bundle: $DEST"
echo "    Total:  $(du -sh "$DEST" | cut -f1)"
echo ""
echo "Next steps:"
echo "  1. Copy '$DEST' to your pen drive."
echo "  2. On the new laptop, plug in the pen drive."
echo "  3. cd into the bundle and run:  bash setup.sh ."
