#!/usr/bin/env bash
# 编译板级 DTS -> DTB。Linux/CI 用系统 dtc，Windows 用仓库自带的 tools/bin/dtc.exe。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="${1:-$ROOT/dts/rk3566-guomeiyun.dts}"
OUT="${2:-$ROOT/firmware/rk3566-guomeiyun.dtb}"

if command -v dtc >/dev/null 2>&1; then
  DTC=dtc
elif [ -x "$ROOT/tools/bin/dtc.exe" ]; then
  DTC="$ROOT/tools/bin/dtc.exe"
else
  echo "找不到 dtc。Linux: apt install device-tree-compiler" >&2
  exit 1
fi

echo "dtc      : $DTC"
echo "source   : $SRC"
echo "output   : $OUT"

# 单元地址/reg 之类的告警对原厂 DTS 是常态，不阻断；真正的语法错误会以非 0 退出
"$DTC" -I dts -O dtb -o "$OUT" "$SRC" 2>"$OUT.warn" || {
  echo "编译失败：" >&2
  grep -i "error" "$OUT.warn" >&2 || cat "$OUT.warn" >&2
  exit 1
}

echo "warnings : $(grep -c Warning "$OUT.warn" 2>/dev/null || echo 0) 条（见 $OUT.warn）"
echo "magic    : $(od -An -tx1 -N4 "$OUT" | tr -d ' \n')  (应为 d00dfeed)"

# 结构自检：反编译一次，确保生成的 blob 可被 dtc 读回
"$DTC" -I dtb -O dts -o /dev/null "$OUT" 2>/dev/null
echo "verify   : OK"
ls -l "$OUT"
