#!/usr/bin/env python3
"""Print peak / RMS of a 16-bit WAV file. Usage: wavstat.py /tmp/mic.wav"""
import math
import struct
import sys
import wave

path = sys.argv[1] if len(sys.argv) > 1 else '/tmp/mic.wav'
w = wave.open(path)
n = w.getnframes()
ch = w.getnchannels()
sw = w.getsampwidth()
d = w.readframes(n)
s = struct.unpack('<%dh' % (len(d) // 2), d)


def stat(x):
    if not x:
        return 0, 0.0
    pk = max(abs(v) for v in x)
    rms = math.sqrt(sum(v * v for v in x) / len(x))
    return pk, rms


print('file=%s frames=%d ch=%d width=%d' % (path, n, ch, sw))
if ch >= 2:
    for name, x in (('L', s[0::2]), ('R', s[1::2])):
        pk, rms = stat(x)
        print('%s peak=%d rms=%.1f' % (name, pk, rms))
else:
    pk, rms = stat(s)
    print('M peak=%d rms=%.1f' % (pk, rms))
