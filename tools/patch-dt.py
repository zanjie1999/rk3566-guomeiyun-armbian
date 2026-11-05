#!/usr/bin/env python3
"""DT fixes verified on device, applied to the decompiled ophub DTS.

1. Add a root-level regulator-fixed node holding the speaker-amp enable line.
   mainline sound/soc/codecs/dummy-codec.c ignores the vendor `spk-ctl-gpios`
   property on cs4333-codec, so nothing ever drives the amp on.
   amp enable = gpio1 RK_PA6 = gpio-38, ophub phandle for gpio1 is 0xb8.

2. Fix hynitron touch display-coords: 1080x1920 -> 800x1280 (real panel).
"""
import re
import sys

SPK_AMP = """\tspk_amp: spk-amp {
\t\tcompatible = "regulator-fixed";
\t\tregulator-name = "spk-amp-en";
\t\tenable-active-high;
\t\tregulator-always-on;
\t\tregulator-boot-on;
\t\tgpio = <0xb8 0x06 0x00>;
\t};
"""


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

    # 1. hynitron display-coords
    a, b = find_block(lines, r'hynitron@5a')
    for i in range(a, b):
        if 'display-coords' in lines[i]:
            lines[i] = re.sub(r'<[^>]*>', '<0x00 0x00 0x320 0x500>', lines[i])
            print(f'  touch display-coords -> 800x1280 (line {i + 1})')

    # 2. append spk-amp before the final root closing brace
    last = max(i for i, ln in enumerate(lines) if ln.strip() == '};')
    lines[last:last] = SPK_AMP.rstrip('\n').split('\n')
    print(f'  spk-amp node inserted before line {last + 1}')

    open(dst, 'w', encoding='utf-8', newline='\n').write('\n'.join(lines))
    print(f'wrote {dst}')


if __name__ == '__main__':
    main()
