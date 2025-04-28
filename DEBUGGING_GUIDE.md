# Debugging Guide for Allkinds Team Bot

## Recent Fixes and Enhancements

We've added enhanced debugging to help identify and fix issues with the "Go to team" button and "Find Match" functionality. This guide explains the changes made and provides recommendations for fixing common issues.

## Debug Logging

Enhanced logging has been added to key functions:

1. In `src/bot/handlers/start.py`:
   - Added debug logging to `on_go_to_group` handler (for "Go to team" button)
   - Added debug logging to `on_find_match_callback` handler
   - Added debug logging to `handle_find_match_message` handler

2. In `src/db/repositories/match_repo.py`:
   - Added debug logging to `find_matches` function

Look for log entries starting with `[DEBUG_TEAM]` and `DEBUG_MATCH` in your logs to track the execution flow.

## Common Issues and Fixes

### "Go to team" Button Not Responding

Possible causes:
1. **Incorrect callback data format**: The button might be using a different format than what the handler expects.
   - The button should use exactly: `callback_data=f"go_to_group:{group.id}"`
   - The handler expects data starting with `go_to_group:`

2. **Database session issues**: The handler might not be receiving a valid database session.
   - Check if DbSessionMiddleware is properly registered
   - Look for session-related errors in the logs

3. **Group ID problems**: The group ID might be invalid or the user doesn't have access.
   - Verify the group exists in the database
   - Check that the user is a member of the group

### Find Match Not Working

Possible causes:
1. **Session handling**: Database operations might be failing.
   - Make sure DbSessionMiddleware is properly registered
   - Check session object is correctly passed to handlers

2. **Points system**: Users might not have enough points.
   - The logs will show points deductions and refunds
   - Check the `FIND_MATCH_COST` constant and user point balance

3. **Insufficient data**: Users might not have answered enough questions.
   - Check the `MIN_QUESTIONS_FOR_MATCH` and `MIN_SHARED_QUESTIONS` constants
   - Logs will show if users have answered enough questions

4. **No eligible matches**: There might not be other users with enough overlap.
   - Make sure multiple users have answered questions in the same group
   - Try relaxing the matching criteria temporarily for testing

## Verification Steps

1. **Check middleware registration**:
   ```python
   # In src/bot/main.py
   logger.info("Registering middlewares")
   dp.update.middleware.register(DbSessionMiddleware(session_factory))
   ```

2. **Verify callback handler registration**:
   ```python
   # In src/bot/handlers/start.py - register_handlers function
   dp.callback_query.register(on_go_to_group, F.data.startswith("go_to_group:"))
   dp.callback_query.register(on_find_match_callback, F.data == "find_match")
   ```

3. **Check message handler registration**:
   ```python
   dp.message.register(handle_find_match_message, F.text == "Find Match", flags=needs_db)
   ```

## Running the Bot in Debug Mode

To see detailed logs:

1. Set logging level to DEBUG:
   ```
   export LOG_LEVEL=DEBUG
   ```

2. Run the bot in polling mode:
   ```
   USE_WEBHOOK=false python3 -m src.bot.main
   ```

## Next Steps for Development

1. Consider implementing more robust error handling in `find_matches` and other critical functions.
2. Use the keyboard utility function we provided to ensure consistent button behavior.
3. Add the import `from src.bot.utils.keyboards import get_group_menu_keyboard` to use the consistent keyboard builder.
4. Monitor the debug logs to identify any remaining issues.

## Contact

If you encounter issues that can't be resolved using this guide, please open a GitHub issue with:
1. The specific debug log entries
2. Steps to reproduce the issue
3. Current bot version or commit hash 