#!/bin/bash
# Wrapper để cron chạy daily crawl (load .env rồi gọi main.py crawl)
set -e
cd "$(dirname "$0")/.."
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi
exec .venv/bin/python main.py crawl "$@"
