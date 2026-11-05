#!/bin/sh
# 设备侧补丁：重刷 Armbian 镜像后，在目标机上执行一次即可。
# 只改 /lib/firmware 与 NetworkManager 配置，不碰前 16MiB 安全区，零启动风险。
#
# 用法（在设备上，root）：
#   sh device-setup.sh
set -eu

FW=/lib/firmware/aic8800_sdio

# ---------------------------------------------------------------- 1. WiFi 固件
# 驱动通过 IS_CHIP_ID_H() 判定为 H 版芯片（chip rev == 7），只找
#   fmacfw_8800d80_h_u02.bin
# 而 Armbian 固件包里只有不带 _h 的 fmacfw_8800d80_u02.bin，全盘也无 _h 版。
# 实测用软链接顶上去后固件下载成功，wlan0 正常出现并能扫描 / 连接。
if [ -f "$FW/fmacfw_8800d80_u02.bin" ]; then
    if [ ! -e "$FW/fmacfw_8800d80_h_u02.bin" ]; then
        ln -s fmacfw_8800d80_u02.bin "$FW/fmacfw_8800d80_h_u02.bin"
        echo "[ok] linked fmacfw_8800d80_h_u02.bin"
    else
        echo "[--] fmacfw_8800d80_h_u02.bin already present"
    fi
else
    echo "[!!] $FW/fmacfw_8800d80_u02.bin missing, skip"
fi

# ------------------------------------------------------- 2. WiFi 模块开机加载
# SDIO 枚举正常时 modalias 会自动加载；这里显式声明一次，防止某些启动顺序下漏加载。
cat > /etc/modules-load.d/aic8800.conf <<'EOF'
aic8800_sdio_wlan
EOF
echo "[ok] /etc/modules-load.d/aic8800.conf"

# ------------------------------------------------- 3. WiFi MAC 固定（可选，推荐）
# 该模块默认每次开机随机 MAC，导致 DHCP 每次都换 IP，调试时很难找设备。
# stable = 由连接名 + 主机名派生的稳定 MAC，重启不变。
if command -v nmcli >/dev/null 2>&1; then
    for c in $(nmcli -t -f NAME,TYPE connection show | grep ':802-11-wireless$' | cut -d: -f1); do
        nmcli connection modify "$c" wifi.cloned-mac-address stable || true
        echo "[ok] stable MAC for connection: $c"
    done
    # 关闭扫描随机 MAC，避免部分路由器行为异常
    printf '[device]\nwifi.scan-rand-mac-address=no\n' > /etc/NetworkManager/conf.d/99-wifi-mac.conf
    echo "[ok] /etc/NetworkManager/conf.d/99-wifi-mac.conf"
fi

# ----------------------------------------------------------- 4. 功放使能兜底
# 正常情况下由 DTB 里的 spk-amp（regulator-fixed, gpio1 RK_PA6 = gpio-38）拉高。
# 若换用了不含该节点的 DTB，用这条兜底。
if ! grep -q 'spk-amp' /sys/kernel/debug/gpio 2>/dev/null; then
    if [ ! -e /sys/class/gpio/gpio38 ]; then
        echo 38 > /sys/class/gpio/export 2>/dev/null || true
    fi
    echo out > /sys/class/gpio/gpio38/direction 2>/dev/null || true
    echo 1   > /sys/class/gpio/gpio38/value     2>/dev/null || true
    echo "[ok] speaker amp gpio-38 pulled high (fallback)"
else
    echo "[--] speaker amp already claimed by DTB (spk-amp)"
fi

echo
echo "done. verify with:"
echo "  ip -br link"
echo "  aplay -l"
echo "  grep -i spk /sys/kernel/debug/gpio"
