#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "[Yao] Installing dependencies..."
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
echo "[Yao] Building Tauri app..."
npx --yes @tauri-apps/cli@latest build | cat
mkdir -p dist
echo "[Yao] Collecting installers to dist/ ..."
find src-tauri/target/release/bundle -type f \( -name "*.exe" -o -name "*.msi" -o -name "*.dmg" -o -name "*.AppImage" \) -exec cp -f {} dist/ \; 2>/dev/null || true
echo "[Yao] Done. See dist/ directory."


