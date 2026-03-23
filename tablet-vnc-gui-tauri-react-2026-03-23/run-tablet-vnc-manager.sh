#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_BIN="$ROOT_DIR/src-tauri/target/release/tablet-vnc-gui-tauri-react-2026-03-23"

if [[ ! -x "$APP_BIN" ]]; then
  echo "Release binary missing. Building Tablet VNC Manager..."
  (cd "$ROOT_DIR" && npm run tauri build)
fi

exec "$APP_BIN"
