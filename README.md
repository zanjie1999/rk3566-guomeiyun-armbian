# RK3566 触屏音箱 Armbian

这是针对一台 RK3566 触屏音箱的第一版专用 Armbian 固件构建仓库。

## 方案

本仓库**不重新编译 U-Boot / miniloader**。

它使用已经验证可以在目标机器进入 U-Boot/Loader 的 WXY-OEC RK3566 启动链和 OEC 的 6.1.118 Armbian 基础镜像，只替换 boot 文件系统中的 `rk3566-wxy-oec-turbo-4g*.dtb` 内容为本机从 `/sys/firmware/fdt` 提取的真实 FDT。

这样第一版保留：

- 原有 WXY-OEC bootloader
- 原有 U-Boot 启动方式
- 原有 RK35xx 6.1 内核
- Armbian userspace
- 本机真实的 RK3566 Device Tree
- 本机 800×1280 MIPI DSI 屏幕定义
- 本机背光/触摸/网口/eMMC 等硬件描述

## 当前真实 DTB

SHA256:

`d38a9382415b6b65d93f3e841ebfd5d02cc50ccc1e6495cb72d6b45a275155ac`

来源：目标设备 `/sys/firmware/fdt`。

已确认其中包括：

- RK3566
- `dsi@fe060000`
- 800×1280
- 4-lane MIPI DSI
- `simple-panel-dsi`
- panel init/exit sequence
- PWM backlight
- FocalTech / GSLX680 / Jadard touchscreen 描述
- `sdhci@fe310000`
- `dwmmc@fe2c0000`
- GMAC RMII
- Wi-Fi / Bluetooth
- CS4333 audio codec

## 编译

GitHub → Actions → `Build RK3566 Speaker Armbian` → `Run workflow`。

第一次请直接使用默认：

- Release: `bookworm`
- Kernel: `6.1.118`

构建完成后下载：

`RK3566-Speaker-Armbian.img.gz`

## 刷机建议

**不要先覆盖整个 eMMC。**

由于你的机器可以通过按键进入 Loader/U-Boot，而且已经有完整救砖备份，建议第一轮仍然先确认启动链：

1. 保留现有可救砖方案。
2. 使用你已经验证过的 WXY-OEC miniloader。
3. 再测试这个 Armbian 镜像。
4. 如果 U-Boot 能启动但 Linux/屏幕异常，再只调整 DTB，不重新折腾 bootloader。

本仓库的第一版刻意没有修改原厂 `uboot/trust`。

## 重要

这个 DTB 是从实际设备运行时 FDT 得到的，不是根据相似开发板猜测出来的。

如果第一版能启动但屏幕仍然黑，下一步优先分析 Linux 6.1 对该 `simple-panel-dsi` 节点的兼容性，而不是更换 bootloader。
