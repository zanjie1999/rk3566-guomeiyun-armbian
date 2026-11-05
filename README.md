# RK3566 国美云触屏音箱 → Armbian

目标机：RK3566 / 4GB / 800×1280 MIPI-DSI 触摸屏 / eMMC / AIC8800 SDIO WiFi / RTL8201F 百兆网口
序列号：GM260200482

**当前状态：能正常启动，屏幕、扬声器、麦克风、WiFi、电源灯/系统灯、USB 2.0 口全部可用。
触摸的驱动、坐标、DTB 均已就绪，但测试机触摸芯片到屏幕的排线断了，无法实测；
有线网口与 USB 3.0 口的 5V 待解。**

| 功能 | 状态 | 关键点 |
|---|---|---|
| 启动 / 显示 | ✅ | `drm-logo` 保留区归零 |
| 屏幕方向 | ✅ | 面板竖装横置，控制台 `fbcon=rotate:3` |
| 扬声器 | ✅ | DTB 里 `spk-amp`（regulator-fixed）拉高 gpio-38 |
| 麦克风 | ✅ | PDM 阵列，card0 同时提供 `pcmC0D0c` / `pcmC0D0p` |
| WiFi | ✅ | AIC8800；需补一个固件软链（见第四节） |
| 电源灯 / 系统灯 | ✅ | gpio0-10 红灯常亮、gpio0-19 蓝灯 heartbeat（见 2.7） |
| USB 2.0（OTG 口） | ✅ | `dr_mode = "host"` + `vcc5v0_otg` 常开（见 2.8） |
| USB 3.0 口供电 | ⚠️ | `fd000000.usb` 控制器正常，VBUS 无输出（见 6.3） |
| 触摸 | ⚠️ | 驱动/坐标/DTB 已就绪，测试机排线断裂，无法验证（见 6.2） |
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

改完 `[HYN]dts x_res = 800,y_res = 1280`。至于 IC 本身正不正常，这台测试机上验证不了 ——
触摸芯片到屏幕的排线断了，详见 6.2。

### 2.6 屏幕方向：竖屏面板横装

面板原生是 **800×1280 竖屏**，但横着装进机身里，**面板原生的"上"边朝机身右侧**。
所以直接输出时画面整体顺时针转了 90°，即"文字的上方在屏幕右侧、下方在左侧"。

要补回来就得反向转 90°，对应 `fbcon=rotate:3`（0=不转 1=顺时针90 2=180 3=逆时针90）。

面板节点里**没有** `rotation` 属性，且 `simple-panel-dsi` 不是主线驱动，所以不从 DT 走。
也不用改 `extlinux.conf` 的 `APPEND`（那条改错就开不了机），改成 systemd 单次任务，
**零启动链风险**：

```bash
echo 3 > /sys/class/graphics/fbcon/rotate          # 立刻生效，可现场试 0/1/2/3
systemctl enable --now fbcon-rotate                # device-setup.sh 会装好
```

内核需 `CONFIG_FRAMEBUFFER_CONSOLE_ROTATION=y` —— 这台机器是 `=y`。

> 触摸修正要跟着这个方向走：`pos-swap` / `reversex` / `reversey` 的组合要和
> `rotate:3` 一致，否则触摸方向会和画面错 90°。换到排线完好的机器上再一起调。

### 2.7 两个指示灯：引脚全写错了

ophub 的 DTB 只有一个 `work_led`，挂在 **gpio0-15**（pin 15）。实测把这个脚在 0/1 之间
来回切，**两颗灯都不亮** —— 那个脚在这块板上什么都没接。

原厂 DTB 里是两颗灯，引脚完全不同：

| 灯 | 原厂引脚 | 现 DTB | 触发器 |
|---|---|---|---|
| 红灯（电源） | GPIO0_B2 = gpio0-**10** | `power_led` | `default-on` 常亮 |
| 蓝灯（sys） | GPIO0_C3 = gpio0-**19** | `work_led` | `heartbeat` |

验证方式（运行时，不用重启）：

```bash
echo 19 > /sys/class/gpio/export; echo out > /sys/class/gpio/gpio19/direction
echo 1  > /sys/class/gpio/gpio19/value      # 蓝灯亮
echo 1  > /sys/class/gpio/gpio10/value      # 红灯亮；echo 0 即灭
```

> 蓝灯用 `heartbeat`，系统空闲时几乎常亮、负载高时快闪，这是正常的。
> 想让它固定节奏闪，把 `linux,default-trigger` 换成 `timer` 即可。

### 2.8 USB 2.0 口（原 OTG 口）

两个问题叠在一起：

1. **VBUS 使能脚错位** —— ophub 把 `vcc5v0_otg` 的 gpio 写成 `pin 5`，原厂是
   **GPIO0_C6 = pin 22**。拉错脚当然没反应，那个口一点电都没有。
2. **`dr_mode = "otg"`** —— 没插带接地 ID 脚的线时，这个口一直待在 device 模式
   （`extcon0: USB=1`），插 U 盘、手柄永远不会枚举。

改了两处：

```
vcc5v0-otg-regulator: gpio = <&gpio0 22 0> + regulator-boot-on + regulator-always-on
usbdrd_dwc3:          dr_mode = "host"
```

结果：

```
gpio-22 (vcc5v0-otg-regulator) out hi
extcon0: USB-HOST=1
lsusb: 8 个 root hub（多了 xhci-hcd.1.auto，Bus 7/8）
usb 5-1: New USB device found, idVendor=067b ... USB SD Card Reader   ← 实测枚举成功
```

> `regulator-always-on` 会让这个口**一直输出 5V**（原厂是等 OTG 检测才给电）。
> 如果以后要把它当 gadget 用（RNDIS / 串口），把 `dr_mode` 改回 `otg`，
> 并去掉这个 regulator 的 `always-on`。

---

## 三、仓库结构

```
dts/rk3566-guomeiyun.dts          实际启动用设备树（ophub DTB 反编译 + 上述补丁）
dts/reference/rk3566-speaker-vendor.dts   原厂 DTB 反编译（另一块板），留作硬件参考
firmware/rk3566-guomeiyun.dtb     当前工作 DTB（182039 B）—— CI 用它替换镜像里的 DTB
firmware/rk3566-speaker.dtb       同一份，兼容旧文件名
firmware/rk3566-wxy-oec-turbo-4g.dtb   ophub 原始 DTB（181827 B，未改动，留作基线对照）
tools/patch-dt.py                 第一轮补丁（spk-amp + display-coords）
tools/patch-gmac.py               gmac1 RGMII/m1 -> RMII/m0
tools/phmap.py                    phandle -> 节点名 映射（跨两份 DTS 翻译用）
tools/mmio.py                     /dev/mem 读写 32 位寄存器（诊断时钟/复位用）
tools/wavstat.py                  量录音电平，判断麦克风是不是静音
tools/rsh.ps1                     本机 → 设备的 SSH 封装（免密码）
tools/find-device.ps1             扫网段 + 试 SSH 自动定位设备 IP（MAC 变了也不怕）
tools/device-setup.sh             重刷镜像后在设备上跑一次（WiFi 固件软链 / 稳定 MAC / 屏幕旋转 / 功放兜底）
tools/build-dtb.sh                dts -> dtb
tools/bin/dtc.exe                 dtc 1.8.1（Windows 本地可编）
.github/workflows/build.yml       双变体构建 + 自动发 Release（见第四节）
docs/FLASH.md                     分区表、烧写命令、TTL 验收清单、回滚
```

编译并校验（重新编译必须与线上那份**字节一致**）：

```bash
./tools/bin/dtc.exe -I dts -O dtb -o build/x.dtb dts/rk3566-guomeiyun.dts
md5sum build/x.dtb firmware/rk3566-guomeiyun.dtb     # 应相同
```

---

## 四、构建镜像（GitHub Actions）

`build.yml` 一次跑出**两个整盘镜像**，DTB 完全相同，区别只在 base 带来的 loader/uboot/内核：

| 变体 | base 板型 | 内核 | `0x8000` 处 | 用途 |
|---|---|---|---|---|
| `wxy-loader` | `wxy-oect` | 6.1.157 | **`RKSS`**（17 个 hash） | **这台机器用这个**，与 eMMC 实际在跑的签名链一致 |
| `generic` | `youyeetoo-yy3568` | 取该板型最新（现为 6.18.59） | **`RKNS`**（1 个 hash） | 通用 loader，不碰 OTP |

`RKSS` / `RKNS` 这两个魔数是实测出来的，位置在偏移 `0x8000`：

```
RKSS 00 00 00 00 80 01 02 00 11 00 00 00    <- OEC 签名链，带 17 个分区 hash
RKNS 00 00 00 00 80 01 02 00 01 00 00 00    <- Rockchip 通用，只含自身 hash
```

两者连 GPT 布局都不一样：`wxy-oect` 的 p1 在 **180 MiB**，`youyeetoo-yy3568` 的 p1 在 **16 MiB**。
所以绝不能把两者的前 16 MiB 互相套用。

### 触发

仓库 → Actions → **Build Armbian images** → Run workflow：

| 输入 | 默认 | 说明 |
|---|---|---|
| `release` | `bookworm` | Armbian 发行版 |
| `kernel` | `6.1.157` | **wxy-loader 变体**的内核 |
| `generic_board` | `youyeetoo-yy3568` | generic 变体的板型（必须存在于 ophub releases） |
| `generic_kernel` | `any` | generic 变体的内核：`any` / `latest-6.1` / 具体版本 |
| `publish_release` | `true` | 跑完自动建 Release 并上传 |
| `release_tag` | 空 | 留空 = `images-<release>-r<run_number>` |

### generic 变体的代价（重要）

ophub 里 **6.1.x 这条线只剩 `wxy-oect`**，所有 RK3568/3588 板型都已迁到 6.18/6.12。
而这块板的驱动全靠 6.1 BSP 派生内核：

```
CONFIG_RFKILL_RK / rockchip,dummy-codec / simple-panel-dsi / wlan-platdata / rockchip,pdm-mic-array
```

所以：

- `wxy-loader` → 屏幕、WiFi、声卡、功放、麦克风全部可用
- `generic` → 能启动，但主线内核没有这些 vendor binding，外设大概率不工作

generic 的用途是**验证这类 loader 不会碰 OTP**，不是当日常系统跑。

### 每个变体做了什么

```
1. 按板型/发行版/内核从 ophub releases 里挑出 .img.gz（带 token，避开匿名限流）
2. gunzip（不保留 base.img.gz，省 ~900 MB 磁盘）
3. losetup --partscan 挂 p1，找 extlinux/extlinux.conf 的 FDT 行
4. 直接覆盖它指向的那个 .dtb —— 不改配置，避免
     extlinux:   /dtb/rockchip/x.dtb          (绝对)
     armbianEnv: rockchip/x.dtb               (相对 /boot/dtb)
   这两个前缀不一致的坑
5. 另外放一份 dtb/rockchip/rk3566-guomeiyun.dtb 供人工核对
6. 回读 sha256 必须等于源文件
7. 断言前 16 MiB sha256 与改动前一致（证明 loader 一个字节没动）
8. gzip -9，出 .img.gz + .sha256 + .buildinfo.txt
9. 构建完**直接** `gh release create/upload` —— 不走 artifact，
   因为 900 MB × 2 会把私有仓库的 artifact 配额撑爆；两个 matrix job 抢建 release 有重试
```

`publish_release=false` 时才退回 artifact（retention 3 天），用于只构建不发版。

### 本地复现构建结果

```bash
# 只验证选片逻辑（不用真下载）
curl -fsSL 'https://api.github.com/repos/ophub/amlogic-s9xxx-armbian/releases?per_page=100' -o rel.json
jq -r --arg b "wxy-oect" --arg r "bookworm" --arg k "6.1.157" '
  [ .[] | .assets[] | select(.name | test("\\.img\\.gz$")) ]
  | map(select(.name | test("_rockchip_" + $b + "_" + $r + "_")))
  | map(select(if $k=="any" then true
               elif $k=="latest-6.1" then (.name | test("_6\\.1\\.[0-9]+_"))
               else (.name | test("_" + $k + "_")) end))
  | sort_by(.name) | last | .browser_download_url
' rel.json
```

---

## 五、重刷镜像后必须做的一步

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

## 六、待解

### 6.1 有线网口 `Failed to reset the dma`

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
0xfe011000 (DMA_Bus_Mode) = 0x00000001   ← SWR 位卡在 1，软复位永不完成
0xfe010110 (MAC_Version)  = 0x00003051   ← MAC 本体活着（Synopsys ID 0x51）
```

**已排除的假设：**

| 假设 | 怎么验的 | 结果 |
|---|---|---|
| 缺 RMII 的 50 MHz REF_CLK | 删掉 `assigned-clock-parents`，让 `clk_gmac1` 从内部 PLL 出 125 MHz | ❌ 依然 `Failed to reset the dma` |
| SDR104/tuning 之类 SDIO 问题 | — | 无关，那是 WiFi |
| 引脚被抢 / 模式没切 | pinmux + GRF `0xfdc6038c=0x40` | 都对 |
| MAC 被按在复位里 | 读 `MAC_Version`，值正常 | 不在复位 |
| 手工清 SWR 绕过 | `/dev/mem` 写映射 | ❌ 内核策略拒绝（`PermissionError`） |

**结论**：MAC 活着、时钟在跑、模式正确、PHY 认得，唯独 **DMA 块不肯完成软复位**。
这跟 PHY 模式无关（最初 RGMII 配置也是同一个报错），是这块板子上独立的问题。

**下一步（需要插网线）**：先插网线再 `ip link set eth0 up` 试一次。
没插线时 PHY 处于低功耗态，某些设计下 `mac_clk_rx` 不跑，
而 `dwmac4_dma_reset` 有可能依赖它 —— 这是目前最省事、最可能翻盘的验证。
若插线后仍失败，就只剩两条路：改 `clock_in_out = "output"`（有引脚对打风险），
或者换回过 BSP 内核（机主实测 BSP 内核上网口是通的）。

### 6.2 触摸：测试机排线断裂，无法验证

**这不是软件问题。** 这台测试机的触摸芯片到屏幕之间排线断了，属硬件损坏，换排线才能修。

软件侧该做的都做完了：

- 驱动 `hyn,3240` 正常加载
- `display-coords` 从 `1080×1920` 修正为 `800×1280`
- `power-supply` 指向 `vcc3v3_lcd0_n`，该 regulator 注册成功
- 复位脚 `gpio0-14`、中断脚 `gpio0-13` 定义正确

断线状态下看到下面这些报错是必然结果，不要当成 bug 去查：

```
[HYN]== Hynitron V2.11 20250217 ==
[HYN]dts x_res = 800,y_res = 1280,touch-number = 5 swap_xy = 0 reversex = 0 reversey = 0
[HYN]cst3240_enter_boot failed
[HYN][Error]hyn_ts_probe:hyn_check_ic failed
hyn_ts: probe of 1-005a failed with error -2
```

`error -2` = `ENOENT`，就是 I2C 上问不到 `0x5a`。`i2cdetect -y -r 1` 只有 **0x51** 有应答，
那是同一条总线上的另一颗器件，不是触摸 IC 换了地址。

**结论：应该能用，只是这台测试机测不了。** 换成排线完好的机器后，如果触按方向不对，
按 2.6 的 `rotate:3` 去调 `pos-swap` / `posx-reverse` / `posy-reverse`。

### 6.3 USB 3.0 口的 5V

控制器本身是好的，`fd000000.usb`（`xhci-hcd.1.auto`）正常挂出 Bus 7（480M）和 Bus 8（5000M），
`Host supports USB 3.0 SuperSpeed`。问题只在那一路 **VBUS 没有电压**，插什么都没反应。

已经做过的检查：

| 检查 | 结果 |
|---|---|
| `vcc5v0_host` gpio | `gpio0-6`，与**原厂 DTB 完全一致**（不是猜的） |
| pin 6 复用 | `pinmux-pins`: `vcc5v0-host-regulator gpio0:6 function usb group vcc5v0-host-en`，纯 GPIO 输出，没被别的功能占 |
| 电平 | `gpio-6 ... out hi` |
| regulator 重新初始化 | `unbind` + `bind` 一次（制造电平边沿）后仍为 `out hi` |
| DTB 里的 5V 开关数量 | 只有 `vcc5v0_otg`(pin22)、`vcc5v0_host`(pin6)、`vcc5v0_usb`（无 gpio，中间轨）三路，**没有第三路可控开关** |

也就是说：软件侧能开的都开了、引脚映射也和原厂一致，仍然没有输出。
剩下的怀疑对象是那个口的座子 / 限流开关管（这机器触摸排线都断了，硬件状况本来就差）。

**待确认**：那个口是标准 USB-A 还是别的形态；插一个带灯的设备，看灯亮不亮，
同时看 `dmesg` 里 Bus 7/8 有没有 `new SuperSpeed USB device` 之类的枚举记录。

---

## 七、风险

- 前 16 MiB 一个字节不能碰，刷机只碰 `boot` / `rootfs`，详见 [`docs/FLASH.md`](docs/FLASH.md)。
- 改 DTB 有回滚路径：设备上留了 `/boot/GOOD.dtb`（原始）、`/boot/GOOD-step0.dtb`、
  `/boot/GOOD-step1.dtb`，串口或 SSH 里 `cp` 回去重启即可。
- `dts/` 里那份是 dtc 反编译产物，phandle 是裸数字，改的时候务必用
  `tools/phmap.py` 查清句柄指向，别直接猜。
