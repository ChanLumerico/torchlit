#!/usr/bin/env bash
# Build the torchlit-progress Rust binary for the current platform
# and copy it to torchlit/bin/ with the platform suffix.
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CLI_DIR="$SCRIPT_DIR/torchlit/cli"
BIN_DIR="$SCRIPT_DIR/torchlit/bin"

# Detect platform suffix
SYSTEM="$(uname -s)"
ARCH="$(uname -m)"

case "$SYSTEM" in
  Darwin) SUFFIX="darwin-$ARCH" ;;
  Linux)  SUFFIX="linux-$ARCH"  ;;
  *)      echo "⚠️  Unsupported platform: $SYSTEM"; exit 1 ;;
esac

echo "⚙️  Building torchlit-progress for $SUFFIX..."
cd "$CLI_DIR"
source ~/.cargo/env 2>/dev/null || true
cargo build --release

mkdir -p "$BIN_DIR"
cp target/release/torchlit-progress "$BIN_DIR/torchlit-progress-$SUFFIX"
echo "✅  Binary ready at torchlit/bin/torchlit-progress-$SUFFIX"
