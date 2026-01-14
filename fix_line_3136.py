#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix indentation error at line 3136 in desktop_ai_handler.py"""

import sys
import re

def fix_indentation_error(filepath):
    """Fix the else: statement at line 3136"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"Total lines: {len(lines)}")
        
        if len(lines) < 3136:
            print(f"Error: File has only {len(lines)} lines, need at least 3136")
            return False
        
        # Check line 3136 (0-indexed: 3135)
        line_idx = 3135
        line = lines[line_idx]
        
        print(f"\nLine 3136: {repr(line)}")
        
        # Check if it's an else: statement
        if 'else:' not in line:
            print("Line 3136 does not contain 'else:'")
            # Show context
            for i in range(max(0, line_idx - 5), min(len(lines), line_idx + 5)):
                marker = ">>>" if i == line_idx else "   "
                print(f"{marker} {i+1}: {repr(lines[i])}")
            return False
        
        # Find the matching if statement
        if_indent = None
        if_line_idx = None
        
        # Look backwards for the matching if
        for i in range(line_idx - 1, max(0, line_idx - 30), -1):
            stripped = lines[i].lstrip()
            if stripped.startswith('if ') and not stripped.startswith('if __'):
                # Check if this if has a corresponding else
                # Count indentation
                current_indent = len(lines[i]) - len(lines[i].lstrip())
                if_indent = current_indent
                if_line_idx = i
                print(f"\nFound matching if at line {i+1} with indent: {current_indent} spaces")
                break
        
        if if_indent is None:
            print("\nCould not find matching if statement")
            # Show context
            print("\nContext around line 3136:")
            for i in range(max(0, line_idx - 10), min(len(lines), line_idx + 5)):
                marker = ">>>" if i == line_idx else "   "
                print(f"{marker} {i+1}: {repr(lines[i])}")
            return False
        
        # Fix the else: to match the if indent
        current_indent = len(line) - len(line.lstrip())
        fixed_line = ' ' * if_indent + 'else:\n'
        
        if line.endswith('\n'):
            # Preserve original line ending
            if not fixed_line.endswith('\n'):
                fixed_line += '\n'
        else:
            # No newline at end, preserve that
            fixed_line = fixed_line.rstrip('\n')
        
        print(f"\nCurrent indent: {current_indent} spaces")
        print(f"Target indent: {if_indent} spaces")
        print(f"Original line: {repr(line)}")
        print(f"Fixed line: {repr(fixed_line)}")
        
        lines[line_idx] = fixed_line
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print("\n✅ File fixed successfully!")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    filepath = '/app/desktop_ai_handler.py' if len(sys.argv) < 2 else sys.argv[1]
    success = fix_indentation_error(filepath)
    sys.exit(0 if success else 1)
