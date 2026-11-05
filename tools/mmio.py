#!/usr/bin/env python3
"""Read/write 32-bit MMIO registers via /dev/mem.

  mmio.py 0xfe011000                 # read
  mmio.py 0xfe011000 0xfffffffe      # clear bit0
  mmio.py -p 0xfe011000 0xfffffffe   # poll: read, mask-write same value back

Values are ANDed onto the current register (read-modify-write) unless the
--set flag is given, in which case the raw value is written.
"""
import mmap
import os
import struct
import sys

PAGE = 0x1000
_fd = None
_maps = {}


def _open(write=False):
    global _fd
    if _fd is None:
        flags = os.O_RDWR | os.O_SYNC if write else os.O_RDONLY | os.O_SYNC
        _fd = os.open('/dev/mem', flags)
    return _fd


def _map(addr, write=False):
    base = addr & ~(PAGE - 1)
    key = (base, write)
    m = _maps.get(key)
    if m is None:
        prot = mmap.PROT_READ | (mmap.PROT_WRITE if write else 0)
        m = mmap.mmap(_open(write), PAGE, mmap.MAP_SHARED, prot, offset=base)
        _maps[key] = m
    return m, addr - base


def rd32(addr):
    m, off = _map(addr)
    return struct.unpack('<I', m[off:off + 4])[0]


def wr32(addr, val):
    m, off = _map(addr, write=True)
    m[off:off + 4] = struct.pack('<I', val)
    m.flush()


def main():
    args = sys.argv[1:]
    raw = False
    if args and args[0] == '--set':
        raw = True
        args = args[1:]
    if not args:
        print(__doc__)
        return 1
    addr = int(args[0], 0)
    cur = rd32(addr)
    if len(args) > 1:
        val = int(args[1], 0)
        new = val if raw else (cur & val)
        wr32(addr, new)
        back = rd32(addr)
        print('0x%08x: 0x%08x -> write 0x%08x -> read 0x%08x' % (addr, cur, new, back))
    else:
        print('0x%08x = 0x%08x' % (addr, cur))
    return 0


if __name__ == '__main__':
    sys.exit(main())
