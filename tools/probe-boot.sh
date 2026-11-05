#!/bin/sh
# 探针：验证 build.yml 里"读 extlinux FDT -> 定位 DTB 文件"这条链在真机上成立
# 只读，不写任何东西
set -e

echo "=== filesystem of /boot ==="
stat -f -c '%T' /boot 2>/dev/null || echo unknown
df -h /boot | tail -1

echo
echo "=== extlinux.conf FDT line ==="
sed -n 's/^[[:space:]]*FDT[[:space:]]*//p' /boot/extlinux/extlinux.conf | head -n 1 | tr -d '\r'

echo
echo "=== armbianEnv.txt fdtfile ==="
sed -n 's/^[[:space:]]*fdtfile=//p' /boot/armbianEnv.txt | head -n 1 | tr -d '\r'

echo
echo "=== resolve target ==="
FDT_LINE=$(sed -n 's/^[[:space:]]*FDT[[:space:]]*//p' /boot/extlinux/extlinux.conf | head -n 1 | tr -d '\r')
if [ -n "$FDT_LINE" ]; then
  TARGET_REL=${FDT_LINE#/}
  echo "TARGET_REL = $TARGET_REL"
  if [ -f "/boot/$TARGET_REL" ]; then
    echo "exists: yes"
    ls -l "/boot/$TARGET_REL"
    sha256sum "/boot/$TARGET_REL"
  else
    echo "exists: NO  <-- 这里要是 NO，CI 会新建文件"
  fi
else
  echo "FDT line not found"
fi

echo
echo "=== dtb dir sample ==="
ls -l /boot/dtb/rockchip/ | grep -i 'rk3566' || echo "(no rk3566 dtb)"

echo
echo "=== 0x8000 on raw eMMC (0-1MiB only, read-only) ==="
dd if=/dev/mmcblk0 bs=512 skip=64 count=1 status=none | od -An -tx1 -N16
