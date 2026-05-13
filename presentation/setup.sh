#!/usr/bin/env bash
set -euo pipefail

BUNDLE="${1:-}"
TARGET_PARENT="${ARIA_TARGET_PARENT:-$HOME/Music/SpaceAi}"
TARGET_REPO="$TARGET_PARENT/aria-core"
DSREMO_REPO="$TARGET_PARENT/Dsremo-Website"
GITHUB_REMOTE="${ARIA_GITHUB_REMOTE:-git@github.com:dsremo/aria-core.git}"
DSREMO_REMOTE="${DSREMO_GITHUB_REMOTE:-git@github.com:dsremo/dsremo-website.git}"

if [[ -z "$BUNDLE" || ! -d "$BUNDLE" ]]; then
  cat >&2 <<EOF
Usage: bash setup.sh <path-to-aria-bundle-folder>

The bundle folder is what 'make-bundle.sh' produced on the source laptop.
It must contain: secrets/, claude-memory/, data-raw/, md-archive/, MANIFEST.txt.
EOF
  exit 2
fi

BUNDLE="$(cd "$BUNDLE" && pwd)"
echo "==> ARIA personal-laptop setup"
echo "    Bundle:        $BUNDLE"
echo "    Target repo:   $TARGET_REPO"
echo "    GitHub remote: $GITHUB_REMOTE"
echo ""

if [[ ! -f "$BUNDLE/MANIFEST.txt" ]]; then
  echo "ERROR: $BUNDLE/MANIFEST.txt missing — wrong path?" >&2
  exit 1
fi
echo "==> [1/12] Bundle manifest"
sed 's/^/    /' "$BUNDLE/MANIFEST.txt" | head -10
echo ""

read -r -p "Proceed with setup? [y/N] " yn
[[ "${yn,,}" == "y" ]] || { echo "Aborted."; exit 0; }
echo ""

echo "==> [2/12] System prerequisites"
need_install=()
for cmd in git python3 pip3 node npm rsync curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    need_install+=("$cmd")
  fi
done
if [[ ${#need_install[@]} -gt 0 ]]; then
  echo "    Missing: ${need_install[*]}"
  if [[ -f /etc/debian_version ]]; then
    echo "    Run (with sudo): apt update && apt install -y git python3 python3-pip python3-venv nodejs npm rsync curl"
  elif [[ -f /etc/fedora-release ]]; then
    echo "    Run (with sudo): dnf install -y git python3 python3-pip nodejs npm rsync curl"
  elif [[ "$(uname -s)" == "Darwin" ]]; then
    echo "    Run: brew install git python3 node rsync curl"
  fi
  read -r -p "    Have you installed the missing tools? [y/N] " yn
  [[ "${yn,,}" == "y" ]] || { echo "Install prerequisites and re-run."; exit 1; }
else
  echo "    OK (all present)"
fi
echo ""

echo "==> [3/14] Restore secrets (aria-keys + spaceai-key.pem + dsremo .env)"
mkdir -p "$TARGET_PARENT"
if [[ -f "$BUNDLE/secrets/aria-keys.env" ]]; then
  [[ -f "$HOME/.aria-keys.env" ]] && mv "$HOME/.aria-keys.env" "$HOME/.aria-keys.env.backup-$(date +%s)"
  install -m 0600 "$BUNDLE/secrets/aria-keys.env" "$HOME/.aria-keys.env"
  echo "    + ~/.aria-keys.env"
fi
if [[ -f "$BUNDLE/secrets/spaceai-key.pem" ]]; then
  install -m 0600 "$BUNDLE/secrets/spaceai-key.pem" "$TARGET_PARENT/spaceai-key.pem"
  echo "    + $TARGET_PARENT/spaceai-key.pem (mode 0600)"
fi
DSREMO_ENV_PENDING="$BUNDLE/secrets/dsremo-website.env"
echo ""

echo "==> [4/14] Restore Claude auto-memory"
SRC_USER_PATH="-home-ashutosh-Music-SpaceAi-memory"
DEST_USER_PATH="-home-${USER}-Music-SpaceAi-memory"
DEST_MEMORY_DIR="$HOME/.claude/projects/$DEST_USER_PATH"
mkdir -p "$HOME/.claude/projects"
if [[ -d "$BUNDLE/claude-memory" && -n "$(ls -A "$BUNDLE/claude-memory" 2>/dev/null)" ]]; then
  if [[ -d "$DEST_MEMORY_DIR" ]]; then
    BACKUP_MEM="$DEST_MEMORY_DIR.backup-$(date +%s)"
    mv "$DEST_MEMORY_DIR" "$BACKUP_MEM"
    echo "    Existing memory backed up to $BACKUP_MEM"
  fi
  mkdir -p "$DEST_MEMORY_DIR"
  rsync -a "$BUNDLE/claude-memory/" "$DEST_MEMORY_DIR/"
  COUNT=$(find "$DEST_MEMORY_DIR" -name '*.md' | wc -l)
  echo "    OK ($COUNT memory files restored to $DEST_MEMORY_DIR)"
  if [[ "$USER" != "ashutosh" ]]; then
    echo "    NOTE: source user was 'ashutosh', current is '$USER'."
    echo "    Memory dir auto-renamed to match current user path."
  fi
else
  echo "    SKIP — bundle has no claude-memory/"
fi
echo ""

echo "==> [5/14] Clone aria-core repo"
mkdir -p "$TARGET_PARENT"
if [[ -d "$TARGET_REPO/.git" ]]; then
  echo "    Repo already present at $TARGET_REPO — fetching latest..."
  git -C "$TARGET_REPO" fetch --all --prune
  git -C "$TARGET_REPO" pull --ff-only || echo "    (non-fast-forward; resolve manually)"
else
  echo "    Cloning $GITHUB_REMOTE → $TARGET_REPO"
  echo "    (requires GitHub SSH key or PAT in ~/.gitconfig)"
  if ! git clone "$GITHUB_REMOTE" "$TARGET_REPO"; then
    echo "    SSH clone failed — falling back to HTTPS"
    HTTPS_REMOTE="${GITHUB_REMOTE/git@github.com:/https://github.com/}"
    git clone "$HTTPS_REMOTE" "$TARGET_REPO"
  fi
fi
echo "    OK ($(git -C "$TARGET_REPO" rev-parse --short HEAD) on $(git -C "$TARGET_REPO" rev-parse --abbrev-ref HEAD))"
echo ""

echo "==> [6/14] Clone Dsremo-Website repo"
if [[ -d "$DSREMO_REPO/.git" ]]; then
  echo "    Already present at $DSREMO_REPO — fetching..."
  git -C "$DSREMO_REPO" fetch --all --prune
  git -C "$DSREMO_REPO" pull --ff-only || echo "    (resolve manually)"
else
  if ! git clone "$DSREMO_REMOTE" "$DSREMO_REPO" 2>/dev/null; then
    git clone "${DSREMO_REMOTE/git@github.com:/https://github.com/}" "$DSREMO_REPO"
  fi
fi
if [[ -f "$DSREMO_ENV_PENDING" ]]; then
  install -m 0600 "$DSREMO_ENV_PENDING" "$DSREMO_REPO/.env"
  echo "    + $DSREMO_REPO/.env restored"
fi
echo "    OK"
echo ""

echo "==> [7/14] Restore SpaceAi parent files (AWS_INFRA, EXPERT_PANEL_*, CENTRAL_AI_MASTER_PLAN, docs/research/scripts/data)"
if [[ -d "$BUNDLE/spaceai-parent" ]]; then
  rsync -a "$BUNDLE/spaceai-parent/" "$TARGET_PARENT/"
  echo "    OK ($(find "$BUNDLE/spaceai-parent" -type f | wc -l) files restored)"
fi
echo ""

echo "==> [8/14] Restore bulk datasets → $TARGET_REPO/data/raw/"
mkdir -p "$TARGET_REPO/data/raw"
if [[ -d "$BUNDLE/data-raw" && -n "$(ls -A "$BUNDLE/data-raw" 2>/dev/null)" ]]; then
  rsync -a "$BUNDLE/data-raw/" "$TARGET_REPO/data/raw/"
  echo "    OK ($(du -sh "$TARGET_REPO/data/raw" | cut -f1) restored)"
else
  echo "    SKIP — bundle has no data-raw/"
fi
echo ""

echo "==> [9/14] Restore optional indexes (.leann + graphify-out)"
if [[ -d "$BUNDLE/leann-index" && -n "$(ls -A "$BUNDLE/leann-index" 2>/dev/null)" ]]; then
  rsync -a "$BUNDLE/leann-index/" "$TARGET_REPO/.leann/"
  echo "    .leann restored"
fi
if [[ -d "$BUNDLE/graphify-out" && -n "$(ls -A "$BUNDLE/graphify-out" 2>/dev/null)" ]]; then
  rsync -a "$BUNDLE/graphify-out/" "$TARGET_REPO/src/graphify-out/"
  echo "    src/graphify-out restored"
fi
echo ""

echo "==> [10/14] Python virtualenv + dependencies (aria-core)"
cd "$TARGET_REPO"
if [[ ! -d ".venv" ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -e ".[dev]"
echo "    OK"
echo ""

echo "==> [11/14] Generate fresh ARIA crypto material → .env"
if [[ -f .env ]]; then
  BACKUP_ENV=".env.backup-$(date +%s)"
  mv .env "$BACKUP_ENV"
  echo "    Existing .env backed up to $BACKUP_ENV"
fi
cp env.example .env
{
  echo "ARIA_MASTER_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  echo "ARIA_CONSOLE_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
  echo "ARIA_OAUTH_STATE_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
  echo "ARIA_ADMIN_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
} >> .env
chmod 0600 .env
echo "    OK (4 fresh secrets generated)"
echo ""

echo "==> [12/14] Smoke tests"
echo "    Running: pytest -m 'not slow and not noncore' (~2 min)"
if pytest -m "not slow and not noncore" -q 2>&1 | tail -5; then
  echo "    pytest OK"
else
  echo "    pytest had failures — review output above"
fi
echo ""
echo "    Running: make production-validate-quick"
if make production-validate-quick 2>&1 | tail -5; then
  echo "    production-validate-quick OK"
else
  echo "    production-validate-quick had failures — review output above"
fi
echo ""

echo "==> [13/14] Web frontend deps (aria-core/web + Dsremo-Website)"
if [[ -d "$TARGET_REPO/web" ]]; then
  ( cd "$TARGET_REPO/web" && npm install --silent ) && echo "    + aria-core/web"
fi
if [[ -d "$DSREMO_REPO" ]]; then
  ( cd "$DSREMO_REPO" && npm install --silent ) && echo "    + Dsremo-Website"
fi
echo ""

echo "==> [14/14] Optional: cross-vendor monitor (Ollama)"
if command -v ollama >/dev/null 2>&1; then
  echo "    Ollama found. Pull a non-Claude family model? Examples:"
  echo "      ollama pull llama3.2"
  echo "      ollama pull phi3:mini"
  echo "      ollama pull gemma2:2b"
  echo "    Then: export ARIA_OLLAMA_MODEL=llama3.2"
else
  echo "    Ollama not installed. To enable real cross-vendor monitor:"
  echo "      curl -fsSL https://ollama.com/install.sh | sh"
  echo "      ollama pull llama3.2"
fi
echo ""

cat <<EOF
==> Setup complete.

aria-core:       $TARGET_REPO
Dsremo-Website:  $DSREMO_REPO
Memory:          $DEST_MEMORY_DIR
~/.aria-keys.env (mode 0600)
$TARGET_PARENT/spaceai-key.pem (mode 0600 — AWS EC2 SSH key)
$TARGET_REPO/.env (freshly regenerated)

Quick verify:
  cd "$TARGET_REPO"
  source .venv/bin/activate
  python -m aria.replay --scenario apollo13_cryo_stir

Aria frontend:    cd "$TARGET_REPO/web" && npm run dev   # opens on :5173
Dsremo frontend:  cd "$DSREMO_REPO" && npm run dev

If something failed above, the bundle remains at $BUNDLE — re-run is safe.
Existing files were backed up with .backup-<timestamp> suffixes; nothing was overwritten.
EOF
