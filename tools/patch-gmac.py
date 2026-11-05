#!/usr/bin/env python3
"""Patch the gmac1 node of a decompiled ophub DTS so it matches the vendor
(RMII / gmac1 m0 pins) hardware description.

ophub DTB currently claims RGMII on gmac1-m1 pins, so MDIO never reaches the
PHY (phy_id reads back 0x0000ffff).

phandle translation table (vendor -> ophub):
    cru            0x1f -> 0x27
    gmac1_clkin    0x6c -> 0x164
    gpio4          0x6b -> 0xe3
    gmac1m0_miim   -> 0x25a
    gmac1m0_clkinout -> 0x25b
    gmac1m0_rx_er  -> 0x25c
    gmac1m0_rx_bus2 -> 0x25d
    gmac1m0_tx_bus2 -> 0x25e
    eth1m0-pins    -> 0x24e
"""
import re
import sys

SET = {
    'phy-mode': '"rmii"',
    'clock_in_out': '"input"',
    'snps,reset-gpio': '<0xe3 0x12 0x01>',
    'assigned-clocks': '<0x27 0x189 0x27 0x186 0x27 0xc6>',
    'assigned-clock-parents': '<0x27 0x188 0x164>',
    'assigned-clock-rates': '<0x00 0x00 0x17d7840>',
    'pinctrl-0': '<0x25a 0x25b 0x25e 0x25d 0x25c 0x24e>',
}
DELETE = ['tx_delay', 'rx_delay']


def find_block(lines, header_re):
    start = None
    for i, ln in enumerate(lines):
        if re.search(header_re, ln) and ln.rstrip().endswith('{'):
            start = i
            break
    if start is None:
        raise SystemExit(f'node not found: {header_re}')
    depth = 0
    for i in range(start, len(lines)):
        depth += lines[i].count('{') - lines[i].count('}')
        if depth <= 0 and i > start:
            return start, i
    raise SystemExit('unbalanced braces')


def main():
    src, dst = sys.argv[1], sys.argv[2]
    lines = open(src, 'r', encoding='utf-8').read().split('\n')

    # 1. external-gmac1-clock: 125MHz -> 50MHz (RMII reference from PHY)
    a, b = find_block(lines, r'gmac1_clkin: external-gmac1-clock')
    for i in range(a, b):
        if 'clock-frequency' in lines[i]:
            lines[i] = re.sub(r'<0x[0-9a-fA-F]+>', '<0x2faf080>', lines[i])

    # 2. gmac1 ethernet node
    a, b = find_block(lines, r'gmac1: ethernet@fe010000')
    indent = re.match(r'\s*', lines[a + 1]).group(0)

    body, seen = [], set()
    for i in range(a + 1, b):
        ln = lines[i]
        stripped = ln.strip()
        key = stripped.split('=')[0].strip() if '=' in stripped else None
        if key in DELETE:
            continue
        if key in SET:
            body.append(f'{indent}{key} = {SET[key]};')
            seen.add(key)
            continue
        body.append(ln)

    for key, val in SET.items():
        if key not in seen:
            body.append(f'{indent}{key} = {val};')

    out = lines[:a + 1] + body + lines[b:]
    open(dst, 'w', encoding='utf-8', newline='\n').write('\n'.join(out))
    print(f'patched node at line {a + 1}, wrote {dst}')


if __name__ == '__main__':
    main()
