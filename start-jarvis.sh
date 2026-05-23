#!/bin/bash
# OpenJarvis Quick Start Script
# Autostart (Task Scheduler) veya terminalden calistirmak icin

# .env dosyalarindan API key'leri yukle
for envfile in ~/.env ~/Desktop/block/.env ~/Desktop/etsy-otomasyon/etsy-otomasyon/.env; do
    if [ -f "$envfile" ]; then
        export $(grep -v '^#' "$envfile" | grep '=' | xargs)
        break
    fi
done

cd "$(dirname "$0")"

ENGINE="${JARVIS_ENGINE:-cloud}"
MODEL="${JARVIS_MODEL:-claude-sonnet-4-6}"
PORT="${JARVIS_PORT:-8000}"

echo "=== OpenJarvis v1.0.1 Starting ==="
echo "  Engine: $ENGINE"
echo "  Model:  $MODEL"
echo "  Port:   $PORT"
echo ""

# uv sync sonrasi croniter ve Rust modulu kayboluyor — her baslatmada kontrol et
echo "[pre-flight] Checking croniter..."
if ! uv run python -c "import croniter" 2>/dev/null; then
    echo "[pre-flight] croniter eksik, kuruluyor..."
    uv pip install croniter 2>&1
fi

echo "[pre-flight] Checking openjarvis-rust..."
if ! uv run python -c "import openjarvis_rust" 2>/dev/null; then
    echo "[pre-flight] openjarvis-rust eksik, build ediliyor..."
    PYO3_USE_ABI3_FORWARD_COMPATIBILITY=1 uv run maturin develop -m rust/crates/openjarvis-python/Cargo.toml 2>&1
fi

echo "[pre-flight] OK"
echo ""

uv run jarvis serve \
    --host 127.0.0.1 \
    --port "$PORT" \
    -e "$ENGINE" \
    -m "$MODEL" \
    -a react
