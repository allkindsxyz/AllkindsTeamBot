#!/bin/bash
echo "Installing system dependencies..."
apt-get update
apt-get install -y zlib1g-dev libpq-dev gcc python3-dev
echo "Dependencies installed successfully" 