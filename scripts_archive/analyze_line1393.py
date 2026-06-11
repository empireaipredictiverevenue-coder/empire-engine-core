#!/usr/bin/env python3
import sys

with open('/tmp/spa_final_check.js', 'rb') as f:
    lines = f.read().split(b'\n')

for i in range(1380, 1415):
    if i >= len(lines):
        break
    l = lines[i]
    ob = l.count(b'{')
    cb = l.count(b'}')
    bt = l.count(b'`')
    s = l[:120].decode('utf-8', errors='replace')
    print(f"{i+1:4d}  ob:{ob}  cb:{cb}  bt:{bt}  | {s}")
