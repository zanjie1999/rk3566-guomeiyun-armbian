#!/usr/bin/env python3
"""Read 32-bit MMIO registers via /dev/mem.  Usage: mmio.py 0xfe010000 ..."""
import mmap
import os
import struct
import sys

PAGE = 0x1000
_fd = None
_maps = {}


def rd32(addr):
    global _fd
    if _fd is None:
        _fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
    base = addr & ~(PAGE - 1)
    m = _maps.get(base)
    if m is None:
        m = mmap.mmap(_fd, PAGE, mmap.MAP_SHARED, mmap.PROT_READ, offset=base)
        _maps[base] = m
    off = addr - base
    return struct.unpack('<I', m[off:off + 4])[0]


def main():
    for arg in sys.argv[1:]:
        a = int(arg, 16) if arg.lower().startswith('0x') else int(arg, 0)
        print('0x%08x = 0x%08x' % (a, rd32(a)))


if __name__ == '__main__':
    main()
