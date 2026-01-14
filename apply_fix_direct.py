#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Direct fix for indentation error at line 3136
Run this on Railway: python apply_fix_direct.py
"""

import sys
import re

def fix_line_3136():
    filepath = '/app/desktop_ai_handler.py'
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        print(f"Total lines: {len(lines)}")
        
        if len(lines) < 3136:
            print(f"Error: File has only {len(lines)} lines")
            return False
        
        # Line 3136 (0-indexed: 3135)
        line_idx = 3135
        line = lines[line_idx]
        
        print(f"\nLine 3136: {repr(line)}")
        
        # Check if it contains else:
        if 'else:' not in line:
            print("Line 3136 does not contain 'else:' - showing context:")
            for i in range(max(0, line_idx - 5), min(len(lines), line_idx + 5)):
                marker = ">>>" if i == line_idx else "   "
                print(f"{marker} {i+1}: {lines[i].rstrip()}")
            return False
        
        # Find matching if statement
        if_indent = None
        for i in range(line_idx - 1, max(0, line_idx - 30), -1):
            stripped = lines[i].lstrip()
            if stripped.startswith('if ') and not stripped.startswith('if __'):
                if_indent = len(lines[i]) - len(lines[i].lstrip())
                print(f"\nFound matching if at line {i+1} with {if_indent} spaces indent")
                break
        
        if if_indent is None:
            print("\nCould not find matching if - showing context:")
            for i in range(max(0, line_idx - 10), min(len(lines), line_idx + 5)):
                marker = ">>>" if i == line_idx else "   "
                print(f"{marker} {i+1}: {lines[i].rstrip()}")
            return False
        
        # Fix the line
        current_indent = len(line) - len(line.lstrip())
        new_line = ' ' * if_indent + 'else:'
        
        # Preserve line ending
        if line.endswith('\r\n'):
            new_line += '\r\n'
        elif line.endswith('\n'):
            new_line += '\n'
        
        print(f"\nCurrent indent: {current_indent} spaces")
        print(f"Target indent: {if_indent} spaces")
        print(f"Original: {repr(line)}")
        print(f"Fixed:    {repr(new_line)}")
        
        lines[line_idx] = new_line
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print("\n✅ Fixed successfully!")
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = fix_line_3136()
    sys.exit(0 if success else 1)
