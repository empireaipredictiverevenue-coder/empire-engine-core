#!/usr/bin/env python3
"""Transform JS import statements to UMD global destructuring."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

old = (
    "import { createElement as h, useState, useEffect, useRef, useCallback } from 'react';\n"
    "import { createRoot } from 'react-dom/client';\n"
    "import htm from 'htm';"
)

new = (
    "const { createElement: h, useState, useEffect, useRef, useCallback } = React;\n"
    "const { createRoot } = ReactDOM;"
)

new_content = content.replace(old, new, 1)
if new_content == content:
    print("ERROR: No replacement made!")
    sys.exit(1)

with open(sys.argv[2] if len(sys.argv) > 2 else sys.argv[1], 'w') as f:
    f.write(new_content)

print(f"Transformed: {len(content)} chars -> {len(new_content)} chars")
