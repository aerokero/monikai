#!/usr/bin/env python3
"""Remove all legacy UI code from App.jsx"""

import re

# Read the file
with open('src/App.jsx', 'r', encoding='utf-8') as f:
    content = f.read()

# List of legacy window states to remove from state definitions
legacy_state_patterns = [
    r'\s*const \[showKasaWindow, setShowKasaWindow\] = useState\(false\);\n',
    r'\s*const \[showRemindersWindow, setShowRemindersWindow\] = useState\(false\);\n',
    r'\s*const \[showNotesWindow, setShowNotesWindow\] = useState\(false\);\n',
    r'\s*const \[showSessionNotesWindow, setShowSessionNotesWindow\] = useState\(false\);\n',
    r'\s*const \[showBrowserWindow, setShowBrowserWindow\] = useState\(false\);\n',
    r'\s*const \[showCompanionWindow, setShowCompanionWindow\] = useState\(false\);\n',
    r'\s*const \[showGoalsWindow, setShowGoalsWindow\] = useState\(false\);\n',
    r'\s*const \[showDailyBriefingWindow, setShowDailyBriefingWindow\] = useState\(false\);\n',
    r'\s*const \[showStudyWindow, setShowStudyWindow\] = useState\(false\);\n',
    r'\s*const \[showMinecraftWindow, setShowMinecraftWindow\] = useState\(false\);\n',
    r'\s*const \[showProgressionWindow, setShowProgressionWindow\] = useState\(false\);\n',
]

# Remove legacy state declarations
for pattern in legacy_state_patterns:
    content = re.sub(pattern, '', content)

# Remove elementPositionsRef  
content = re.sub(r'\s*const elementPositionsRef = useRef\(elementPositions\);\n', '', content)

# Remove bringToFront function
content = re.sub(
    r'\s*const bringToFront = \(id\) => \{[^}]*\n\s*\};?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove handleMouseDown function
content = re.sub(
    r'\s*const handleMouseDown = \(e, id\) => \{[^}]*window\.addEventListener\([^)]*\);[^}]*\n\s*\};?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove handleMouseDrag function  
content = re.sub(
    r'\s*const handleMouseDrag = \(e\) => \{[^}]*\n\s*\};?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove handleToggleWindow function
content = re.sub(
    r'\s*const handleToggleWindow = \(windowId, isVisible, setVisibility\) => \{[^}]*\n\s*\};?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove toggleWindowSmart function
content = re.sub(
    r'\s*const toggleWindowSmart = \(windowId, isVisible, setVisibility\) => \{[^}]*\n\s*\};?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove elementPositions effect that syncs to ref
content = re.sub(
    r'\s*useEffect\(\) \{[^}]*elementPositionsRef\.current = elementPositions;[^}]*\}, \[isModularMode, elementPositions\]\);?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove window drag & config useEffects
content = re.sub(
    r'\s*useEffect\(\(\) => \{[^}]*\/\/ Window Resize Handling[^}]*\n\s*\}, \[\]\);?\n',
    '',
    content,
    flags=re.DOTALL
)

# Remove keyboard shortcuts that use toggleWindowSmart
content = re.sub(
    r'\s*\/\/ Shortcuts for companion windows\s*useEffect\(\(\) => \{[^}]*if \(e\.altKey && \(e\.code === \'Key[CG]\'\)[^}]*\n\s*\}, \[showCompanionWindow, showGoalsWindow, adaptiveShellEnabled\]\);?\n',
    '',
    content,
    flags=re.DOTALL
)

# Write the file back
with open('src/App.jsx', 'w', encoding='utf-8') as f:
    f.write(content)

print("✓ Legacy UI code removed from App.jsx")
