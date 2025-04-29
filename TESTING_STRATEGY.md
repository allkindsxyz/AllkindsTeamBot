# Testing Strategy for Allkinds Team Bot

This document outlines our approach to testing the Allkinds Team Bot to ensure reliability and prevent regressions.

## Current Testing Status

The project currently has:
- Basic unit tests for some core functionality
- Limited integration tests
- Manual testing for deployment validation

## Testing Goals

1. **Improve stability** by catching regressions before deployment
2. **Prevent recurring bugs** through comprehensive test coverage
3. **Simplify development** by enabling confident refactoring
4. **Document behavior** through executable specifications

## Test Structure

### 1. Unit Tests

Focus on testing individual components in isolation:

- Repository methods (`src/db/repositories/`)
- Utility functions (`src/bot/utils/`, `src/core/utils/`)
- Data models and validation (`src/db/models/`)
- State management

Example structure:
```
tests/
└── unit/
    ├── test_matching.py  # Tests for matching algorithms
    ├── test_cohesion_calculation.py  # Tests for score calculations
    ├── test_user_repo.py  # Tests for user repository
    └── ...
```

### 2. Integration Tests

Test interactions between components:

- Database operations with actual schema
- Handler logic without Telegram API
- Workflow sequences (e.g., find match → start chat)

Example structure:
```
tests/
└── integration/
    ├── test_match_workflow.py
    ├── test_chat_session_creation.py 
    └── ...
```

### 3. System Tests

End-to-end tests that validate complete workflows:

- Simulate bot interactions
- Test webhook handling
- Verify deployment configurations

## Priority Test Cases

Based on recent issues, prioritize testing for:

1. **Match Finding**
   - Points deduction happens only when matches are found
   - No matches scenario is handled gracefully
   - Session errors are properly handled
   - Cohesion calculation works correctly with various inputs

2. **Database Session Management**
   - Sessions remain valid across async operations
   - Connection errors are handled properly
   - Transactions are correctly committed or rolled back

3. **Chat Session Creation**
   - Deep links are generated correctly
   - Sessions are created with proper participant records
   - Error states are handled correctly

## Test Implementation Plan

### Phase 1: Critical Functionality (Next 2 Weeks)

Create tests for:
- Match finding logic
- Point deduction systems
- Database session handling
- Error recovery mechanisms

### Phase 2: Core Features (Next 1 Month)

Add tests for:
- Group management
- Question creation/deletion
- Answer processing
- User registration

### Phase 3: Edge Cases (Ongoing)

Add tests for:
- Concurrency issues
- Network failures
- Invalid input handling
- Resource exhaustion

## Test Implementation Guidelines

### 1. Test Structure

Each test file should:
1. Import necessary fixtures
2. Define test cases in clear, descriptive functions
3. Group related tests in classes
4. Use comments to explain complex scenarios

Example:
```python
class TestMatchFinding:
    """Tests for the match finding functionality."""
    
    async def test_points_deducted_only_when_matches_found(self, db_session, test_users):
        """Ensure points are only deducted when matches are found."""
        # Test implementation
        
    async def test_cohesion_calculation_with_identical_answers(self, db_session):
        """Verify cohesion is 100% when answers are identical."""
        # Test implementation
```

### 2. Fixtures

Create reusable fixtures for:
- Database sessions
- Test users with predefined answers
- Groups with specific configurations
- Mock Telegram message objects

Example:
```python
@pytest.fixture
async def test_group_with_questions(db_session):
    """Create a test group with predefined questions."""
    # Implementation
    
@pytest.fixture
async def users_with_answers(db_session, test_group_with_questions):
    """Create test users with answers to questions in the test group."""
    # Implementation
```

### 3. Mocking External Dependencies

Mock:
- Telegram Bot API
- OpenAI API
- Railway-specific services
- Time-dependent functions

Example:
```python
@pytest.fixture
def mock_telegram_bot():
    """Mock the Telegram bot to simulate interactions."""
    # Implementation
```

## Continuous Integration

Implement CI pipeline to:
1. Run tests on every push
2. Block merges that break tests
3. Generate test coverage reports
4. Notify on test failures

## Manual Testing Checklist

Some scenarios that are difficult to automate should be verified manually:

1. **Before each release**:
   - Complete match finding workflow
   - Anonymous chat functionality
   - Group creation and management
   - Webhook configuration
   - Health check functionality

2. **After deployment**:
   - Verify the bot responds to /start
   - Check database connections
   - Ensure webhooks are properly configured
   - Monitor for unexpected errors

## Conclusion

By systematically implementing this testing strategy, we'll improve the reliability of the Allkinds Team Bot and reduce the frequency of recurring bugs. This will allow faster, more confident development and a better user experience. 