#!/usr/bin/env bash
# Build graphify + leann indexes for aria-core.  CPU-only; safe to run on a
# fresh clone.  Requires: `graphify` on PATH, and `leann` installed via
# `uv tool install leann-core --with leann`.
#
# Re-runs are safe: graphify does an incremental update, and leann wipes
# the named index before rebuilding.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
INDEX_NAME="spaceai-aria-core"

echo "== graphify: updating knowledge graph at src/graphify-out/ =="
cd "$ROOT"
graphify update src/

echo
echo "== leann: rebuilding semantic index '$INDEX_NAME' =="
# Force CPU — the machine's GPU OOMs with 3.67 GB VRAM shared with the desktop.
# Path injection matches the uv tool install layout.
export PATH="/home/ashutosh/snap/code/233/.local/share/uv/tools/leann-core/bin:$PATH"
rm -rf "$ROOT/.leann/indexes/$INDEX_NAME"
CUDA_VISIBLE_DEVICES="" leann build "$INDEX_NAME" \
    --embedding-mode sentence-transformers \
    --embedding-model all-MiniLM-L6-v2 \
    --backend hnsw \
    --docs $(git -C "$ROOT" ls-files | grep -E "\.py$" | tr '\n' ' ')

echo
echo "== done =="
echo "Search with: CUDA_VISIBLE_DEVICES='' leann search $INDEX_NAME '<query>' --top-k 5"
echo "Graph report: src/graphify-out/GRAPH_REPORT.md"
