#!/bin/bash

# Sticker Processor Service Launcher

MODE="${1:-dev}"

echo "🚀 Starting Sticker Processor Service in $MODE mode..."

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Copying from example..."
    cp config.env.example .env
    echo "📝 Please edit .env file with your configuration"
    echo "   Especially set TELEGRAM_BOT_TOKEN"
    exit 1
fi

# Check for optional tgs2json tool
if command -v tgs2json &> /dev/null; then
    echo "✅ tgs2json CLI tool is available (optional)"
else
    echo "ℹ️  tgs2json CLI tool not found (optional - service will work with lottie library)"
fi

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Load environment variables
source .env 2>/dev/null || true

# Get port from env or use default
PORT="${SERVER_PORT:-8081}"
WORKERS="${WORKERS:-4}"

echo "📖 Swagger UI will be available at: http://localhost:$PORT/docs"
echo "🔍 Health check: http://localhost:$PORT/health"

# Start the service based on mode
if [ "$MODE" = "prod" ] || [ "$MODE" = "production" ]; then
    echo "🎯 Starting service in PRODUCTION mode with $WORKERS workers..."
    gunicorn app.main:app \
        --workers "$WORKERS" \
        --worker-class uvicorn.workers.UvicornWorker \
        --bind "0.0.0.0:$PORT" \
        --timeout 120 \
        --keepalive 5 \
        --max-requests 1000 \
        --max-requests-jitter 100 \
        --log-level info \
        --access-logfile - \
        --error-logfile -
else
    echo "🎯 Starting service in DEVELOPMENT mode with auto-reload..."
    uvicorn app.main:app --host 0.0.0.0 --port "$PORT" --reload
fi
