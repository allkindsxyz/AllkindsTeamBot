#!/bin/bash
echo "Initializing database..."
python -c 'import asyncio; from src.db.init_db import init_db; asyncio.run(init_db())'
echo "Starting bot..."
python run.py
