#!/usr/bin/env python3
"""Remove all legacy window rendering JSX from App.jsx"""

import re

with open('src/App.jsx', 'r', encoding='utf-8') as f:
    lines = f.readlines()

output = []
skip_until = -1
i = 0

while i < len(lines):
    line = lines[i]
    
    # Skip ToolsModule rendering block
    if '<ToolsModule' in line:
        # Find the closing />
        j = i
        while j < len(lines) and '/>' not in lines[j]:
            j += 1
        skip_until = j
        i += 1
        continue
    
    # Skip window rendering blocks: {showKasaWindow && (
    legacy_patterns = [
        'showKasaWindow &&',
        'showRemindersWindow &&',
        'showNotesWindow &&',
        'showSessionNotesWindow &&',
        'showBrowserWindow &&',
        'showCompanionWindow &&',
        'showDailyBriefingWindow &&',
        'showStudyWindow &&',
        'showGoalsWindow &&',
        'showMinecraftWindow &&',
        'showProgressionWindow &&',
    ]
    
    is_legacy_block = any(p in line for p in legacy_patterns)
    
    if is_legacy_block and '{' in line:
        # Find matching closing brace
        j = i
        brace_count = 0
        started = False
        while j < len(lines):
            for char in lines[j]:
                if char == '{':
                    brace_count += 1
                    started = True
                elif char == '}':
                    brace_count -= 1
                    if started and brace_count == 0:
                        skip_until = j
                        break
            if started and brace_count == 0:
                break
            j += 1
        i = skip_until + 1
        continue
    
    # Skip lines we should skip
    if i > skip_until:
        skip_until = -1
    
    if i <= skip_until:
        i += 1
        continue
    
    # Remove lines that reference deleted states in useEffect dependencies
    if '}, [showCompanionWindow, showGoalsWindow, adaptiveShellEnabled]);' in line:
        i += 1
        continue
    
    # Remove references to deleted state vars in setPanelVisibility calls
    if 'setPanelVisibility' in line and any(ws in line for ws in ['showCompanionWindow', 'showGoalsWindow', 'showStudyWindow', 'showNotesWindow', 'showRemindersWindow']):
        i += 1
        continue
    
    # Remove useEffect for window positioning
    if 'useEffect(() => {' in line and i < len(lines) - 1:
        # Check if next lines contain window positioning logic
        next_block = ''.join(lines[i:min(i+20, len(lines))])
        if 'setElementPositions' in next_block or 'setPanelVisibility' in next_block and 'showGoalsWindow' in next_block:
            # Skip this effect
            j = i
            brace_count = 0
            while j < len(lines):
                for char in lines[j]:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            skip_until = j
                            break
                if brace_count == 0:
                    break
                j += 1
            i = skip_until + 2  # +1 for the }, +1 to move to next line
            continue
    
    # Remove bringToFront('study') call
    if "bringToFront('study')" in line:
        i += 1
        continue
    
    output.append(line)
    i += 1

# Remove consecutive blank lines
cleaned = []
prev_blank = False
for line in output:
    is_blank = line.strip() == ''
    if is_blank and prev_blank:
        continue
    cleaned.append(line)
    prev_blank = is_blank

with open('src/App.jsx', 'w', encoding='utf-8') as f:
    f.writelines(cleaned)

print("✓ Legacy window rendering JSX removed")
