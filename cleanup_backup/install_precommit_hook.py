#!/usr/bin/env python3
"""
Install a pre-commit hook to prevent committing sensitive information.

This script installs a pre-commit hook that scans staged files for potential
tokens or credentials before allowing a commit.
"""

import os
import sys
import stat
from pathlib import Path

# Git hook directory
GIT_HOOKS_DIR = Path(".git/hooks")
PRE_COMMIT_PATH = GIT_HOOKS_DIR / "pre-commit"

# Use raw string to avoid escape sequence warnings
# Pre-commit hook content
PRE_COMMIT_HOOK = r"""#!/bin/bash
# Pre-commit hook to prevent committing sensitive information

echo "🔒 Running security checks before commit..."

# Get the list of staged files
STAGED_FILES=$(git diff --cached --name-only --diff-filter=ACM)

if [ -z "$STAGED_FILES" ]; then
    echo "No staged files to check."
    exit 0
fi

# Check for sensitive patterns
echo "Checking for sensitive information in staged files..."

# Patterns to check for
PATTERNS=(
    # API tokens and keys
    '["\']?[a-zA-Z0-9_-]{20,}["\']?'
    'api[_-]?key["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{16,}["\']?'
    'token["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{16,}["\']?'
    'secret["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{16,}["\']?'
    'password["\']?\s*[:=]\s*["\']?[a-zA-Z0-9_-]{8,}["\']?'
    
    # Telegram bot tokens
    '[0-9]{8,10}:[a-zA-Z0-9_-]{35}'
    
    # OpenAI API keys
    'sk-[a-zA-Z0-9]{48}'
    
    # Database connection strings
    'postgres(ql)?://[^:]+:[^@]+@'
    'mysql://[^:]+:[^@]+@'
    'mongodb://[^:]+:[^@]+@'
)

# Check each staged file
FOUND_SENSITIVE=0

for FILE in $STAGED_FILES; do
    # Skip binary files, images, etc.
    if [[ ! -f "$FILE" || -z $(grep -I '' "$FILE") ]]; then
        continue
    fi
    
    # Skip files that are in the .gitignore
    if git check-ignore -q "$FILE"; then
        continue
    fi
    
    # Check each pattern
    for PATTERN in "${PATTERNS[@]}"; do
        MATCHES=$(grep -n -E "$PATTERN" "$FILE" | grep -v "SAFE_TO_COMMIT" | grep -v "example")
        
        if [ -n "$MATCHES" ]; then
            echo "❌ Possible sensitive information found in $FILE:"
            echo "$MATCHES"
            FOUND_SENSITIVE=1
        fi
    done
done

if [ $FOUND_SENSITIVE -eq 1 ]; then
    echo "Error: Potential sensitive information found in staged files."
    echo "Please remove sensitive data before committing."
    echo ""
    echo "If you're sure this is safe to commit, you can:"
    echo "1. Add '# SAFE_TO_COMMIT' at the end of the line with the false positive"
    echo "2. Use --no-verify to bypass this check (not recommended)"
    echo ""
    exit 1
fi

echo "✅ No sensitive information detected in staged files."
exit 0
"""

def install_pre_commit_hook():
    """Install the pre-commit hook."""
    # Check if .git directory exists
    if not Path(".git").is_dir():
        print("Error: Not a git repository (or .git directory not found).")
        return False
    
    # Create hooks directory if it doesn't exist
    if not GIT_HOOKS_DIR.exists():
        GIT_HOOKS_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Created hooks directory: {GIT_HOOKS_DIR}")
    
    # Check if pre-commit already exists
    backup_path = None
    if PRE_COMMIT_PATH.exists():
        backup_path = PRE_COMMIT_PATH.with_suffix(".bak")
        PRE_COMMIT_PATH.rename(backup_path)
        print(f"Backed up existing pre-commit hook to {backup_path}")
    
    # Write new pre-commit hook
    try:
        with open(PRE_COMMIT_PATH, 'w') as f:
            f.write(PRE_COMMIT_HOOK)
        
        # Make the hook executable
        st = os.stat(PRE_COMMIT_PATH)
        os.chmod(PRE_COMMIT_PATH, st.st_mode | stat.S_IEXEC)
        
        print(f"✅ Successfully installed pre-commit hook to {PRE_COMMIT_PATH}")
        print("The hook will prevent committing files with potential sensitive information.")
        return True
    except Exception as e:
        print(f"Error installing pre-commit hook: {e}")
        
        # Restore backup if it exists
        if backup_path and backup_path.exists():
            backup_path.rename(PRE_COMMIT_PATH)
            print(f"Restored previous pre-commit hook from {backup_path}")
        
        return False

def main():
    print("Installing pre-commit hook for security checks...")
    success = install_pre_commit_hook()
    
    if success:
        print("\nPre-commit hook installed successfully!")
        print("\nThis hook will check for:")
        print("- API keys and tokens")
        print("- Passwords and secrets")
        print("- Database connection strings with credentials")
        print("- Telegram bot tokens")
        print("- Other potentially sensitive information")
        print("\nTo bypass the hook in special cases (not recommended), use:")
        print("git commit --no-verify")
    else:
        print("\nFailed to install pre-commit hook.")
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(main()) 