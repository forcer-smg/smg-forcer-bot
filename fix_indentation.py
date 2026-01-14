#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fix indentation error in desktop_ai_handler.py"""

import sys
import re

def fix_file(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Split by newlines (handle both \n and \r\n)
        lines = content.split('\n')
        if len(lines) == 1:
            # Try splitting by \r\n
            lines = content.split('\r\n')
        if len(lines) == 1:
            # Try splitting by \r
            lines = content.split('\r')
        
        print(f"Total lines: {len(lines)}")
        
        # Check around line 3136 (0-indexed: 3135)
        if len(lines) > 3135:
            print(f"\nLine 3136: {repr(lines[3135])}")
            print(f"Line 3135: {repr(lines[3134])}")
            print(f"Line 3137: {repr(lines[3136])}")
            
            # Look for the problematic else:
            for i in range(max(0, 3130), min(len(lines), 3145)):
                line = lines[i]
                if 'else:' in line and i == 3135:
                    print(f"\nFound else: at line {i+1}")
                    print(f"Context:")
                    for j in range(max(0, i-5), min(len(lines), i+5)):
                        marker = ">>>" if j == i else "   "
                        print(f"{marker} {j+1}: {repr(lines[j])}")
                    
                    # Check indentation
                    indent = len(line) - len(line.lstrip())
                    prev_indent = len(lines[i-1]) - len(lines[i-1].lstrip()) if i > 0 else 0
                    
                    print(f"\nCurrent indent: {indent} spaces")
                    print(f"Previous line indent: {prev_indent} spaces")
                    
                    # Fix: else should match the if statement's indent
                    # Look backwards for the matching if
                    if_indent = None
                    for j in range(i-1, max(0, i-20), -1):
                        if lines[j].strip().startswith('if '):
                            if_indent = len(lines[j]) - len(lines[j].lstrip())
                            break
                    
                    if if_indent is not None:
                        print(f"Matching if indent: {if_indent} spaces")
                        # Fix the else: to match the if indent
                        fixed_line = ' ' * if_indent + 'else:'
                        lines[i] = fixed_line
                        print(f"Fixed line {i+1}: {repr(fixed_line)}")
                    else:
                        print("Could not find matching if statement")
        
        # Write back
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        
        print("\nFile fixed!")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    fix_file(r'c:\Users\Ready\smg-forcer-bot\desktop_ai_handler.py')
