# Technical Debt Tracking

This document tracks known technical issues that need addressing. It helps prioritize fixes and ensures issues aren't forgotten across development sessions.

## Priority Levels
- **P0**: Critical issue affecting core functionality or security
- **P1**: Major issue causing frequent errors or poor user experience
- **P2**: Moderate issue that should be addressed soon
- **P3**: Minor issue that can be addressed during regular maintenance

## Current Technical Debt

### Database & Session Management

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| DB-1 | Session handling in callbacks | P1 | Session management in callback handlers needs improvement | `src/bot/handlers/start.py` | May cause intermittent database errors |
| DB-2 | Transaction isolation | P2 | Some operations need better transaction isolation | `src/db/repositories/` | Could lead to race conditions |
| DB-3 | Connection pool exhaustion | P1 | Need to optimize connection pooling | `src/db/base.py` | Fix partially applied in `fix_db_connection_cancelled.py` |

### Match Finding System

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| MATCH-1 | Point deduction timing | P0 | Points should only be deducted after matches are found | `src/bot/handlers/start.py` | Fixed in some handlers but needs verification |
| MATCH-2 | Error handling in cohesion calculation | P2 | Improve error handling when calculating cohesion scores | `src/bot/utils/matching.py` | May cause matching failures |
| MATCH-3 | Session recovery logic | P1 | Need better recovery from failed sessions during matching | `src/db/repositories/match_repo.py` | Causes "no matches found" errors |

### Anonymous Chat

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| CHAT-1 | Deep link generation | P1 | Problems with deep link generation to communicator bot | `src/bot/handlers/start.py` | Partially fixed, needs verification |
| CHAT-2 | Error handling in message forwarding | P2 | Better error handling when forwarding messages | `src/communicator_bot/handlers.py` | Some messages may not be delivered |
| CHAT-3 | Chat session cleanup | P3 | Need better cleanup of expired/abandoned chat sessions | `src/db/repositories/chat_repo.py` | May cause DB bloat over time |

### Error Handling

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| ERR-1 | Inconsistent error messages | P2 | User-facing error messages need standardization | Throughout codebase | Improves user experience |
| ERR-2 | Missing try/except in some handlers | P1 | Some handlers lack proper exception handling | Various files | May cause unexpected crashes |
| ERR-3 | Error recovery logic | P2 | Need better retry mechanisms for transient errors | Various files | Resilience improvement |

### Deployment & Configuration

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| DEPLOY-1 | Webhook configuration | P1 | Webhook setup sometimes fails on deployment | `reset_webhook.py` | May require manual intervention |
| DEPLOY-2 | Environment variable handling | P2 | Better validation of required env variables | `src/core/config.py` | Prevents silent failures |
| DEPLOY-3 | Health check improvements | P1 | Health checks need to verify database connectivity | `health_server.py` | Critical for Railway deployment |

### Code Quality

| ID | Issue | Priority | Description | Location | Notes |
|----|-------|----------|-------------|----------|-------|
| CODE-1 | Duplicate code in handlers | P3 | Refactor duplicate patterns in handlers | `src/bot/handlers/` | Maintenance burden |
| CODE-2 | Inconsistent logging | P2 | Standardize logging format and levels | Throughout codebase | Improves debugging |
| CODE-3 | Missing type hints | P3 | Add type hints to improve code quality | Various files | Better IDE support |

## Recently Resolved Issues

| ID | Issue | Fixed In | Description | Notes |
|----|-------|----------|-------------|-------|
| FIXED-1 | CancelledError handling | fix_db_connection_cancelled.py | Added proper handling for asyncio CancelledError | Deployed on [date] |
| FIXED-2 | Points deduction in find_match | fix_on_find_match.py | Updated point deduction logic to happen after matches found | Deployed on [date] |

## Action Plan

### Immediate (Next 2 weeks)
1. Resolve P0 issues: MATCH-1
2. Address high-impact P1 issues: DB-1, DB-3, MATCH-3, CHAT-1, DEPLOY-1
3. Improve test coverage for match finding and chat session creation

### Short-term (Next 1 month)
1. Resolve remaining P1 issues
2. Address high-impact P2 issues: ERR-1, ERR-2, DEPLOY-2
3. Create monitoring for critical functions

### Long-term
1. Comprehensive refactoring of handler structure
2. Improve test automation
3. Address remaining P2 and P3 issues

## How to Use This Document

1. **When fixing an issue:** Mark it as resolved and move to "Recently Resolved"
2. **When finding a new issue:** Add it to the appropriate section with details
3. **During planning:** Use this to prioritize technical work
4. **Before deployment:** Review P0 and P1 issues for potential conflicts

*Last updated: [Current Date]* 