# CRITICAL FIX NEEDED: Follow-Up Query Detection

## Problem

When user asks:
- "what did you hit"
- "what currently running"  
- "tell me in plain words what really running now"

The bot treats these as **NEW tasks** instead of **follow-up queries**, so it:
1. Generates NEW code/scripts
2. Doesn't use existing execution results
3. Creates infinite loops (same script executed 11+ times)
4. Generates broken code (syntax errors)

## Root Cause

The bot doesn't detect follow-up queries **BEFORE** task execution starts. It goes through:
1. Intent classification
2. Deep thinking
3. Plan creation
4. Code generation

Instead of:
1. Detecting it's a follow-up query
2. Retrieving existing execution results
3. Presenting results in plain text

## Solution

Add follow-up query detection at the **START** of `handle_with_streaming`:

```python
# Check if this is a follow-up query (before task execution)
message_lower = message.lower()
is_followup_query = any(keyword in message_lower for keyword in [
    'what did you', 'what did we', 'what currently', 'what is running',
    'tell me', 'show me', 'give me', 'send me',
    'update', 'status', 'progress', 'results', 'findings'
])

if is_followup_query:
    # Check if we have execution results from previous task
    if hasattr(context, 'user_data'):
        execution_results = context.user_data.get('last_execution_results', [])
        if execution_results:
            # Present existing results instead of generating new code
            # Format and send results to user
            return formatted_results
```

## Implementation Location

Add this check at the **beginning** of `handle_with_streaming` method, before:
- Intent classification
- Deep thinking
- Plan creation

## Expected Behavior

**Before Fix:**
- User: "what did you hit"
- Bot: Generates NEW code, executes 11 times, syntax errors

**After Fix:**
- User: "what did you hit"
- Bot: Presents existing execution results in plain text
