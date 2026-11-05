#!/usr/bin/env python3
"""Minimal pure-python flattened device tree (DTB) -> DTS decompiler.

Usage: fdt2dts.py <in.dtb> [out.dts]

No external dependencies. Handles FDT v17 (and older) struct/strings blocks.
"""
import struct
import sys

FDT_MAGIC = 0xD00DFEED
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9


def align4(x):
    return (x + 3) & ~3


class Fdt:
    def __init__(self, data):
        self.d = data
        (magic, totalsize, off_struct, off_strings, off_rsvmap, version,
         last_comp, boot_cpuid, size_strings, size_struct) = struct.unpack_from(">10I", data, 0)
        if magic != FDT_MAGIC:
            raise ValueError("not a DTB (bad magic)")
        self.version = version
        self.total = totalsize
        self.off_struct = off_struct
        self.off_strings = off_strings
        self.off_rsvmap = off_rsvmap
        self.size_struct = size_struct
        self.size_strings = size_strings
        self.boot_cpuid = boot_cpuid

    def string_at(self, off):
        s = self.off_strings + off
        e = self.d.index(b"\0", s)
        return self.d[s:e].decode("utf-8", "replace")

    def reservations(self):
        out = []
        p = self.off_rsvmap
        while True:
            addr, size = struct.unpack_from(">QQ", self.d, p)
            p += 16
            if addr == 0 and size == 0:
                break
            out.append((addr, size))
        return out


def fmt_value(v):
    """Heuristic formatting of a property value, mirroring dtc behaviour."""
    if len(v) == 0:
        return None
    # string / stringlist
    if v.endswith(b"\0"):
        parts = v.split(b"\0")[:-1]
        try:
            strs = [p.decode("utf-8") for p in parts]
        except UnicodeDecodeError:
            strs = None
        if strs is not None and all(
            all(32 <= ord(c) < 127 for c in s) for s in strs
        ):
            return ", ".join('"%s"' % s.replace('"', '\\"') for s in strs)
    if len(v) % 4 == 0:
        cells = struct.unpack(">%dI" % (len(v) // 4), v)
        if all(c == 0 or c >= 0x100 for c in cells):
            return "<%s>" % " ".join("0x%x" % c for c in cells)
        return "<%s>" % " ".join(
            ("0x%x" % c) for c in cells
        ) + " /* %s */" % " ".join(str(c) for c in cells)
    return "[%s]" % " ".join("%02x" % b for b in v)


def decompile(fdt, show_rsv=True):
    d = fdt.d
    p = fdt.off_struct
    lines = []
    indent = 0
    path = []
    labels = {}
    rsv = fdt.reservations() if show_rsv else []
    for addr, size in rsv:
        if size:
            lines.append("/memreserve/ 0x%x 0x%x;" % (addr, size))

    def emit(s):
        lines.append("    " * indent + s)

    while p < fdt.off_struct + fdt.size_struct:
        tok, = struct.unpack_from(">I", d, p)
        p += 4
        if tok == FDT_BEGIN_NODE:
            e = d.index(b"\0", p)
            name = d[p:e].decode("utf-8", "replace")
            p = align4(e + 1)
            path.append(name)
            full = "/" + "/".join(x for x in path if x)
            if not name:
                continue  # root: handled below
            emit("%s {" % name)
            indent += 1
        elif tok == FDT_END_NODE:
            indent -= 1
            emit("};")
            if path:
                path.pop()
            if indent == 0:
                lines.append("")
        elif tok == FDT_PROP:
            ln, nameoff = struct.unpack_from(">II", d, p)
            p += 8
            val = d[p:p + ln]
            p = align4(p + ln)
            pname = fdt.string_at(nameoff)
            fv = fmt_value(val)
            if fv is None:
                emit("%s;" % pname)
            else:
                # long values: wrap
                emit("%s = %s;" % (pname, fv))
        elif tok == FDT_NOP:
            continue
        elif tok == FDT_END:
            break
        else:
            raise ValueError("bad token 0x%x at 0x%x" % (tok, p - 4))
    return "\n".join(lines)


def main():
    src = sys.argv[1]
    with open(src, "rb") as f:
        data = f.read()
    fdt = Fdt(data)
    sys.stderr.write(
        "FDT v%d size=%d struct=0x%x strings=0x%x rsvmap=0x%x\n"
        % (fdt.version, fdt.total, fdt.off_struct, fdt.off_strings, fdt.off_rsvmap)
    )
    out = "/dts-v1/;\n\n" + decompile(fdt)
    if len(sys.argv) > 2:
        with open(sys.argv[2], "w", encoding="utf-8") as f:
            f.write(out + "\n")
        sys.stderr.write("wrote %s (%d lines)\n" % (sys.argv[2], out.count("\n")))
    else:
        print(out)


if __name__ == "__main__":
    main()
