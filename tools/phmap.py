#!/usr/bin/env python3
"""Map phandle values to node labels/paths in a decompiled DTS file.

Usage:
    python tools/phmap.py <file.dts> <hex1> [<hex2> ...]
    python tools/phmap.py <file.dts> --node <node-substring>   # show node's props
"""
import re
import sys

NODE_RE = re.compile(r'^\s*([A-Za-z0-9_,.\-]+)\s*:\s*([A-Za-z0-9_,.@\-]+)\s*\{\s*$|^\s*([A-Za-z0-9_,.@\-]+)\s*\{\s*$')
PH_RE = re.compile(r'phandle\s*=\s*<(0x[0-9a-fA-F]+)>')


def scan(path):
    """Return dict phandle -> (label, nodename, line_no) and list of (line_no, text)."""
    lines = open(path, 'r', encoding='utf-8', errors='replace').read().splitlines()
    stack = []
    cur = None
    ph = {}
    for i, ln in enumerate(lines):
        m = NODE_RE.match(ln)
        if m:
            if m.group(2):
                stack.append((m.group(1), m.group(2)))
            else:
                stack.append((None, m.group(3)))
            cur = stack[-1]
        if ln.strip().startswith('}'):
            if stack:
                stack.pop()
            cur = stack[-1] if stack else None
            continue
        pm = PH_RE.search(ln)
        if pm and cur:
            ph[int(pm.group(1), 16)] = (cur[0], cur[1], i + 1)
    return ph, lines


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    path = sys.argv[1]
    ph, lines = scan(path)

    if sys.argv[2] == '--node':
        needle = sys.argv[3]
        inside = False
        depth = 0
        for i, ln in enumerate(lines):
            if not inside and needle in ln and ln.rstrip().endswith('{'):
                inside = True
                depth = 0
            if inside:
                print(f'{i+1:5d}: {ln}')
                depth += ln.count('{') - ln.count('}')
                if depth <= 0 and '}' in ln:
                    break
        return 0

    for a in sys.argv[2:]:
        v = int(a, 16)
        if v in ph:
            label, node, ln = ph[v]
            print(f'0x{v:04x} -> {label or "-"}  node={node}  (line {ln})')
        else:
            print(f'0x{v:04x} -> NOT FOUND')
    return 0


if __name__ == '__main__':
    sys.exit(main())
