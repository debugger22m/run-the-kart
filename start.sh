#!/usr/bin/env python3
"""
Convenience startup script — reads .env, then launches the server.
Usage:
  ./start.sh           (port 8000)
  PORT=8800 ./start.sh
"""
import os
import sys

# Load .env without relying on dotenv so there's no import-before-venv issue
env_path = os.path.join(os.path.dirname(__file__), ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

sys.path.insert(0, os.path.dirname(__file__))

import uvicorn
from src.api.app import create_app

port = int(os.environ.get("PORT", 8000))
uvicorn.run(create_app(), host="0.0.0.0", port=port, log_level="info")
