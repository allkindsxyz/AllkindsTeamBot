# Development Practices for Allkinds Team Bot

This document establishes practices to maintain code quality, stability, and integrity across development sessions. Following these guidelines will help minimize introducing bugs when making changes.

## Git Workflow

### 1. Branch Management
- **Feature branches**: Create branch for each new feature or bugfix
- **Naming convention**: `feature/description` or `fix/description`
- **Pull Requests**: All changes should undergo review before merging to main
- **Commit messages**: Use descriptive commits with reference to what's being fixed

### 2. Commit Process
```bash
# Before committing code
python run_tests.py              # Run tests to verify changes
python validate_code.py          # Validate code style and potential issues
git add <files>                  # Stage only relevant files
git commit -m "Descriptive message about changes"
git push
```

## Testing Strategy

### 1. Test Types
- **Unit tests**: For individual functions and components
- **Integration tests**: For interactions between components
- **Manual verification**: Key user workflows

### 2. Test Before Deployment
Always run the test suite before deploying:
```bash
pytest                           # Run all tests
pytest tests/unit/test_matching.py  # Test specific component
```

### 3. Test New Fixes
Create tests for any bug you fix to prevent regression:
```bash
# Example: For a match finding fix
# Add test to tests/unit/test_matching.py
```

## Change Management

### 1. Fix Script Pattern
When creating fix scripts:
- Always back up files before modifying them
- Use pattern matching to identify problematic code
- Add descriptive comments
- Log what's being changed
- Prefer idempotent changes (can run multiple times safely)

Example fix script structure:
```python
def create_backup(file_path):
    """Create backup before modifying"""
    # Backup logic here

def fix_issue():
    """Fix specific issue with clear documentation"""
    # 1. Backup original
    # 2. Identify problematic pattern
    # 3. Apply fix
    # 4. Verify change

if __name__ == "__main__":
    print("Applying fix for [specific issue]...")
    success = fix_issue()
    # Report result
```

### 2. Documentation
For every significant change:
1. Update the relevant documentation
2. Add entry to CHANGELOG.md
3. Update ARCHITECTURE.md if the change affects system design

## Code Review Checklist

Before considering any change complete, verify:

- [ ] All tests pass
- [ ] New tests added for new functionality
- [ ] Code follows project patterns
- [ ] Error handling is robust
- [ ] Database transactions are properly managed
- [ ] No security issues (tokens, credentials, etc.)
- [ ] Documentation updated

## Debugging and Troubleshooting

### 1. Logging
- Add context-rich logging for all key operations
- Use appropriate log levels (DEBUG, INFO, WARNING, ERROR)
- Include identifiers in logs (user_id, group_id, etc.)

Example:
```python
logger.info(f"Finding matches for user {user_id} in group {group_id}")
```

### 2. Structured Error Handling
- Handle expected errors at appropriate levels
- Provide informative user feedback
- Always log exceptions with context

Example:
```python
try:
    result = await find_matches(session, user_id, group_id)
except DatabaseError as e:
    logger.error(f"Database error in find_matches: {e}")
    await message.answer("Error connecting to database. Please try again.")
    return
except Exception as e:
    logger.exception(f"Unexpected error in find_matches: {e}")
    await message.answer("An unexpected error occurred. Our team has been notified.")
    return
```

## Database Operations

### 1. Session Management
- Always use the session from parameters
- Ensure proper transaction handling
- Commit early and often
- Use `with_retry` decorator for critical operations

### 2. Schema Changes
- Create migration scripts for all schema changes
- Test migrations in development before production
- Document all schema changes in ARCHITECTURE.md

## Production Deployment

### 1. Deployment Process
```bash
# Pre-deployment
git checkout main
git pull
pytest
python check_migrations.py

# Deployment
railway up
```

### 2. Deployment Verification
```bash
# Post-deployment
python check_webhook.py
python verify_deployment.py
```

## Managing Technical Debt

1. Keep a `TECH_DEBT.md` file listing known issues
2. Prioritize addressing critical technical debt
3. When fixing a bug, look for and address similar issues
4. Regularly schedule "cleanup" time to address technical debt

## Communication Practices

1. Document important decisions and their rationale
2. Update the team on significant changes
3. Keep issues, PRs, and documentation updated
4. Record deployment details and issues encountered

---

By following these practices, we can maintain a stable, high-quality codebase and minimize the introduction of new bugs while fixing existing issues. 