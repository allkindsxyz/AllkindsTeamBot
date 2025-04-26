#!/usr/bin/env python3
import os
import sys

def fix_admin_ids():
    """Fix the ADMIN_IDS environment variable format."""
    print("Fixing ADMIN_IDS environment variable...")
    
    # Set a default value for ADMIN_IDS if it's not set or is invalid
    if 'ADMIN_IDS' not in os.environ or not os.environ['ADMIN_IDS'] or os.environ['ADMIN_IDS'] == '${ADMIN_IDS}':
        os.environ['ADMIN_IDS'] = '123456789,987654321'
        print("✅ Set ADMIN_IDS to default value: 123456789,987654321")
    else:
        print(f"ADMIN_IDS is already set to: {os.environ['ADMIN_IDS']}")

if __name__ == "__main__":
    fix_admin_ids()
    
    # If arguments are provided, run the command with fixed environment
    if len(sys.argv) > 1:
        command = sys.argv[1:]
        print(f"Running command: {' '.join(command)}")
        os.execvp(command[0], command) 