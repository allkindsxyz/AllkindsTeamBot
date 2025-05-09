#!/bin/bash

echo "Monitoring logs for question-related entries..."
echo "Press Ctrl+C to stop"

# Filter for relevant terms
tail -f bot_output.log | grep -E "question|direct|handle_|confirm|cancel|reviewing|creating|viewing" --color=always 