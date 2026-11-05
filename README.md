# RK3566 国美云触屏音箱 → Armbian

目标机：RK3566 / 4GB / 800×1280 MIPI-DSI 触摸屏 / eMMC / AIC8800 SDIO WiFi / RTL8201F 百兆网口
序列号：GM260200482

**当前状态：能正常启动，屏幕、扬声器、麦克风、WiFi 全部可用。触摸、有线网口待解。**

| 功能 | 状态 | 关键点 |
|---|---|---|
| 启动 / 显示 | ✅ | `drm-logo` 保留区归零 |
| 扬声器 | ✅ | DTB 里 `spk-amp`（regulator-fixed）拉高 gpio-38 |
| 麦克风 | ✅ | PDM 阵列，card0 同时提供 `pcmC0D0c` / `pcmC0D0p` |
| WiFi | ✅ | AIC8800；需补一个固件软链（见第四节） |
| 触摸 | ⚠️ | I2C 0x5a 无 ACK，`cst3240_enter_boot failed` |
| 有线网口 | ⚠️ | PHY 已识别（RTL8201F），`Failed to reset the dma` |

---

## 一、重要前提：Secure Boot 已熔断，前 16 MiB 绝对不能碰

这台机器的 **OTP/eFuse verified-boot 标志已烧成 1**，loader 和 uboot 都换不了
（机主实测：其他 loader 直接不启动）。从 `安全区.img` 抠出 uboot 本体
（偏移 `0x801000`，1 281 000 字节）翻字符串，证据：

```
Vboot=1, SecureBoot enabled, AVB verify
bootcmd=boot_fit;
boot_extlinux=sysboot ... extlinux.conf      ← 编进来了，但 bootcmd 里没走
```

| 层 | 位置 | 能否改 |
|---|---|---|
| BootROM → idbloader | 扇区 64（0–4 MiB） | ❌ OTP hash |
| SPL → uboot/ATF/OP-TEE | 8–16 MiB | ❌ `sha256,rsa2048:dev` |
| uboot → kernel/dtb | `boot` 分区 | ✅ 解锁态 `verifiedbootstate=orange`，不签名 |

**硬规则：任何写入偏移 ≥ 25 MiB。**

另外 `bootcmd=boot_fit` 会失败（`FIT: No boot partition`），然后回落到
`extlinux/extlinux.conf` —— 所以 **实际生效的是 extlinux 的 `APPEND` cmdline**，
DTB 里 `chosen/bootargs` 写了也没用。

---

## 二、已修问题与根因

全部改动都落在 DTB 里（`dts/rk3566-guomeiyun.dts`），来源是 ophub 镜像自带的
`/boot/dtb/rockchip/rk3566-wxy-oec-turbo-4g.dtb` 反编译。

### 2.1 花屏（紫条纹 / 黑屏有背光）

不是驱动缺失，也不是面板没绑上。

`drm-logo@0` 节点保留了 `reg = <0x0 0xedf00000 0x0 0xbba000>`，指向一块 12 MiB
的**垃圾区**。启动首帧 VOP 从这块无效 IOVA 取图 → IOMMU page fault（`iova 0x100`）
→ 显示管线锁死 → `POST_BUF_EMPTY` FIFO 下溢刷屏。

```
修复：reg = <0x00 0xedf00000 0x00 0xbba000>  ->  reg = <0x00 0x00 0x00 0x00>
```

对齐 EVB2 官方 DTB 的写法。改完 `POST_BUF_EMPTY = 0`，无 page fault，Video Port1 ACTIVE。

> 排查期间用 DSI 的 VPG（`/sys/kernel/debug/fe060000.dsi/vpg`）直接出测试图案，
> 证明 DSI/PHY/面板/背光链路本身完全正常，把问题锁定在 VOP 侧。这一招很好用。

### 2.2 WiFi 能用但 `wlan0` 不出现

两个独立问题，**顺序**很重要。

**(a) SDIO 枚举失败** —— `pinconfig core: failed to register map default (1): no configs given`

DTB 手工合并留下了重复的 `phandle` / `rockchip,pins`，而且有 4 处
`rockchip,pins` 把 `0xff`（那是**引脚组** `spi3m0_pins_hs` 的 phandle）当
pinconf 句柄用。改成真正的 pinconf：

```
0xff  ->  0x130    # pcfg_pull_none
```

**(b) SDIO tuning 永远失败** —— `All phases bad` / `tuning execution failed: -5`

`mmc@fe2c0000` 声明了 `sd-uhs-sdr104`，但硬件没有 1.8V 信令（缺 `vqmmc-supply`），
SDR104 必然起不来。**直接把 `sd-uhs-sdr104` 删掉**，退到 SDR50/SDR25 即可。

修完出现 `mmc2:390b:1` / `mmc2:390b:2`，**确认芯片是 AIC8800**（DTS 里叫 `rk960` 只是名字）。

### 2.3 声卡不注册

```
could not get #sound-dai-cells for /multi-dais
probe of pdm-mic-array failed with error -22
```

`multi-dais` 和 `cs4333-codec` 的 `#sound-dai-cells` 是**空值**（合并残留）。
改成 `#sound-dai-cells = <0x00>;` → `0 [rockchippdmmica]: simple-card` 注册成功。

### 2.4 有声音吗？没有 —— 功放使能脚没人管

`cs4333-codec` 带厂商私有属性 `spk-ctl-gpios`，那是 Rockchip 给 `dummy-codec`
打的补丁；**mainline `dummy-codec.c` 根本不解析它**，所以功放常闭。

功放使能是 **gpio1 RK_PA6 = gpio-38**。在 DTB 里加一个固定开启的 regulator：

```dts
spk-amp {
    compatible = "regulator-fixed";
    regulator-name = "spk-amp-en";
    enable-active-high;
    regulator-always-on;
    regulator-boot-on;
    gpio = <0xb8 0x06 0x00>;      /* &gpio1 6 GPIO_ACTIVE_HIGH */
};
```

验证：`grep -i spk /sys/kernel/debug/gpio` 应显示
`gpio-38 ( |spk-amp ) out hi`。

> 注意播放要用单声道：`speaker-test -D plughw:0,0 -c 1`。
> 用 `-c 2` 会在哑 codec 上拿不到第二路，刷一堆 `Write error: -32 (EPIPE)`。

### 2.5 触摸坐标不对

驱动读到的分辨率来自 `display-coords`，原来是 `1080×1920`，实际面板 800×1280：

```
display-coords = <0x00 0x00 0x438 0x780>  ->  <0x00 0x00 0x320 0x500>
```

改完 `[HYN]dts x_res = 800,y_res = 1280`。但 IC 仍不应答，见第五节。

---

## 三、仓库结构

```
dts/rk3566-guomeiyun.dts          实际启动用设备树（ophub DTB 反编译 + 上述补丁）
dts/reference/rk3566-speaker-vendor.dts   原厂 DTB 反编译（另一块板），留作硬件参考
firmware/rk3566-speaker.dtb       当前工作 DTB（181917 B）—— CI 用它替换镜像里的 DTB
firmware/rk3566-guomeiyun.dtb     同一份，易读文件名
firmware/rk3566-wxy-oec-turbo-4g.dtb   ophub 原始 DTB（181827 B，未改动，留作基线对照）
tools/patch-dt.py                 第一轮补丁（spk-amp + display-coords）
tools/patch-gmac.py               gmac1 RGMII/m1 -> RMII/m0
tools/phmap.py                    phandle -> 节点名 映射（跨两份 DTS 翻译用）
tools/mmio.py                     /dev/mem 读 32 位寄存器（诊断时钟/复位用）
tools/wavstat.py                  量录音电平，判断麦克风是不是静音
tools/rsh.ps1                     本机 → 设备的 SSH 封装（免密码）
tools/device-setup.sh             重刷镜像后在设备上跑一次（WiFi 固件软链等）
tools/build-dtb.sh                dts -> dtb
tools/bin/dtc.exe                 dtc 1.8.1（Windows 本地可编）
.github/workflows/build.yml       把 firmware/rk3566-speaker.dtb 塞进镜像
docs/FLASH.md                     分区表、烧写命令、TTL 验收清单、回滚
```

编译并校验（重新编译必须与线上那份**字节一致**）：

```bash
./tools/bin/dtc.exe -I dts -O dtb -o build/x.dtb dts/rk3566-guomeiyun.dts
md5sum build/x.dtb firmware/rk3566-guomeiyun.dtb     # 应相同
```

---

## 四、重刷镜像后必须做的一步

```bash
sh tools/device-setup.sh
```

核心是这一条：驱动通过 `IS_CHIP_ID_H()` 判定为 H 版芯片（chip rev 7），只找
`fmacfw_8800d80_h_u02.bin`，而 Armbian 固件包里只有**不带 `_h`** 的
`fmacfw_8800d80_u02.bin`，全盘也没有 `_h` 版。

```bash
ln -s fmacfw_8800d80_u02.bin /lib/firmware/aic8800_sdio/fmacfw_8800d80_h_u02.bin
```

不补这个软链，日志会是这样（很有误导性，看着像上电失败）：

```
aicbsp: aicwf_sdio_aicbsp_set_subsys, subsys: AIC_WIFI, state to: 1
aicbsp: aicbsp_platform_power_on
8800d80 download wifi fw fail
aicbsp: fail to set AIC_WIFI power state to 1
```

顺带 `aicbsp_dummy_sdmmc: probe of mmc2:390b:1 failed with error -123` 那两行
是驱动故意返回 ENOMEDIUM 让出设备的**正常噪音**，不是错误。

另外该模块默认每次开机随机 MAC，DHCP 会一直换 IP，`device-setup.sh` 里把它固定成
`wifi.cloned-mac-address=stable`。

---

## 五、待解

### 5.1 有线网口 `Failed to reset the dma`

已确认的部分（都是对的）：

| 检查项 | 结果 |
|---|---|
| PHY 识别 | ✅ `PHY [stmmac-1:00] driver [RTL8201F Fast Ethernet]` |
| MDIO | ✅ 之前 `phy_id = 0x0000ffff`（全 1 = 无应答），改 RMII 后正常 |
| GRF 模式寄存器 | ✅ `0xfdc6038c = 0x40`，bit6 置位、bit4/5 清零 = RMII |
| 引脚复用 | ✅ 11 个引脚全归 `fe010000.ethernet`，含 pin112 `gmac1m0-clkinout` |
| `rockchip,grf` | ✅ 指向 `sysconf@fdc60000`（`rockchip,rk3568-grf`） |
| grf/时钟配置 | ✅ 与 `dts/reference/` 里原厂节点逐行等价 |
| `aclk_mac` / `pclk_mac` | ✅ 297 MHz / 99 MHz，都在跑 |

失败的落点：

```
0xfe011000 (DMA_Mode) = 0x00000001     ← SWR 位卡在 1，软复位永不完成
clk_gmac1              = 50 MHz
clk_gmac1_rmii_speed   = 2.5 MHz
clk_gmac1_rx_tx        = 2.5 MHz       ← MAC 收发时钟
```

`clock_in_out = "input"` 时，驱动不自己产生时钟，**`clk_gmac1` 完全依赖 PHY 从
`gmac1m0-clkinout` 引脚送进来的 50 MHz REF_CLK**。SWR 卡死 + MDIO 正常
（MDIO 走 `pclk_mac`，与 REF_CLK 无关）这两个现象同时出现，最可能是**这条 REF_CLK 实际没到**。

两条待选路线（都要动 DT，重启一次）：

- **A. `clock_in_out = "output"`** —— 让 SoC 自己产生 50 MHz 送给 PHY。
  副作用风险：如果 PHY 本来就在驱动这条线，会变成两个输出对打（引脚争用）。
- **B. 保持 input，把 `assigned-clock-parents` 改成内部 PLL 供时钟** ——
  纯诊断手段，可确认"是不是没时钟"，但时钟源与 PHY 不同步，链路仍可能不通。

要动手前请确认：**网线插上后网口灯亮不亮？** 灯亮说明 PHY 侧链路和它自己的时钟是活的。

### 5.2 触摸 `0x5a` 无应答

```
[HYN]== Hynitron V2.11 20250217 ==
[HYN]vdd_ana not config
[HYN]vdd_i2c not config
[HYN]cst3240_enter_boot failed
[HYN][Error]hyn_ts_probe:hyn_check_ic failed
```

- 坐标已经修好（`x_res = 800, y_res = 1280`），只剩 IC 不应答。
- `i2cdetect -y -r 1` 上只有 **0x51** 有应答，0x5a / 0x14 全 `--`。
- probe 失败后 `reset-gpios`（gpio0-14）/ `irq-gpios`（gpio0-13）已被释放，
  `/sys/kernel/debug/gpio` 里看不到，无法据此判断复位态。
- 下一步方向：确认触摸供电（`power-supply` 缺失，两路 vdd 都 `not config`）、
  复位极性是否该是 `ACTIVE_LOW`、以及 0x51 那个应答到底是不是触摸 IC 换了地址。

---

## 六、风险

- 前 16 MiB 一个字节不能碰，刷机只碰 `boot` / `rootfs`，详见 [`docs/FLASH.md`](docs/FLASH.md)。
- 改 DTB 有回滚路径：设备上留了 `/boot/GOOD.dtb`（原始）、`/boot/GOOD-step0.dtb`、
  `/boot/GOOD-step1.dtb`，串口或 SSH 里 `cp` 回去重启即可。
- `dts/` 里那份是 dtc 反编译产物，phandle 是裸数字，改的时候务必用
  `tools/phmap.py` 查清句柄指向，别直接猜。
