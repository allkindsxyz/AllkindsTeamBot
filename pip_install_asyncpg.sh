#!/bin/bash

# Uninstall psycopg2 first to avoid conflicts
pip uninstall -y psycopg2-binary

# Install asyncpg explicitly
pip install --upgrade asyncpg

# Install psycopg2 again but after asyncpg
pip install psycopg2-binary

# Show installed packages
pip list | grep -E 'psycopg2|asyncpg'

echo "Installation complete!" 