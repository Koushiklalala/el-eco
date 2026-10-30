#!/bin/sh
set -eu
exec python -m uvicorn el_eco.main:app --host 0.0.0.0 --port "${PORT:-8000}"
