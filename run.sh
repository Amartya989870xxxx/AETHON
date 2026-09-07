#!/usr/bin/env bash
# PlateTrail — one-command bring-up.
set -euo pipefail
cd "$(dirname "$0")"

case "${1:-serve}" in
  seed)   python3 scripts/seed.py "${@:2}" ;;
  test)   cd backend && python3 -m pytest tests/ -q ;;
  demo)   python3 scripts/demo.py "${@:2}" ;;
  serve)
    echo "PlateTrail API  ->  http://localhost:8000/docs"
    cd backend && python3 -m uvicorn app.main:app --reload --port 8000
    ;;
  *) echo "usage: ./run.sh [seed|serve|test|demo]"; exit 1 ;;
esac
