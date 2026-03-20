#!/usr/bin/env bash
# Hook: Force long-running test/evaluation Bash commands to run in background.
# Matches: pytest (full suite), evaluate_scenarios.py
# Returns updatedInput with run_in_background=true if the command matches.

set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('command',''))" 2>/dev/null || echo "")
ALREADY_BG=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('run_in_background', False))" 2>/dev/null || echo "False")

# Skip if already set to background
if [ "$ALREADY_BG" = "True" ] || [ "$ALREADY_BG" = "true" ]; then
  echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
  exit 0
fi

# Check if this is a full test suite run or scenario evaluation
IS_LONG_RUN=false

# Full pytest suite (not a single file)
if echo "$COMMAND" | grep -qE 'pytest\s+--tb' && ! echo "$COMMAND" | grep -qE 'pytest\s+tests/\S+\.py'; then
  IS_LONG_RUN=true
fi

# Evaluator script (without --scenario for single)
if echo "$COMMAND" | grep -q 'evaluate_scenarios'; then
  IS_LONG_RUN=true
fi

if [ "$IS_LONG_RUN" = "true" ]; then
  # Force run_in_background
  TIMEOUT=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('timeout', 600000))" 2>/dev/null || echo "600000")
  DESC=$(echo "$INPUT" | python -c "import sys,json; print(json.load(sys.stdin).get('tool_input',{}).get('description', 'Long-running test/eval'))" 2>/dev/null || echo "Long-running test/eval")

  cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow","updatedInput":{"command":"$COMMAND","description":"$DESC","timeout":$TIMEOUT,"run_in_background":true},"additionalContext":"Hook forced run_in_background=true for long-running test/evaluation command. Wait for background notification instead of polling."}}
EOF
  exit 0
fi

# Not a long-running command — allow as-is
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
exit 0
