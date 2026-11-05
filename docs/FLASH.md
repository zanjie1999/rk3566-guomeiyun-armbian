# 刷机与回滚

> 结论先说：**只写 `boot` 和 `rootfs` 两个分区，前 16 MiB 一个字节都不碰。**
> 这样 uboot/ATF/OP-TEE 永远在，刷坏了最多重写 40 MiB，不用再刷"安全区"、不用拆 eMMC。

## 零、这台机器是 Secure Boot（OTP 熔断），且已实测不可换

这不是"uboot 版本锁"，是 **eFuse/OTP 已经把 verified-boot 标志烧成 1**，
所以信任链是硬件钉死的。从 `安全区.img` 里抠出 uboot 本体（偏移 `0x801000`，
1 281 000 字节）翻字符串，三条证据互相印证：

**第 1 层 — BootROM → idbloader（扇区 64，32 KiB 处）**

BootROM 只认 OTP 里存的 hash 对应的那份 loader。**换任何别的 loader 都不启动**——
这是"[安全区] 必须每次刷"和"CPU 被锁"的真正原因。

**第 2 层 — SPL → uboot 分区（8–12 MiB）的 FIT**

```
## Verified-boot: 1
sha256,rsa2048:dev
## Checking atf-1 ... sha256(6204b6f381...) + OK
## Checking uboot 0x00a00000 ... sha256(9b5584889e...) + OK
## Checking optee 0x08400000 ... sha256(66bbd17352...) + OK
```

`uboot` 分区里 package 的是 `ATF + OP-TEE + U-Boot`，SPL 用 rsa2048:dev 校验，
全 OK 才跳转。所以 8–16 MiB 也**不能改一个字节**。

**第 3 层 — uboot → boot 分区（25 MiB）——这是唯一能动的一层**

从 uboot 二进制里挖出的运行时常量和 env 默认值：

```
bootcmd=boot_fit;                                  ← 只走 FIT，不扫 extlinux
fit_get_blob                                       ← OneCloud 定制函数名
second_image_load=off
kernel_addr_r=0x00280000   fdt_addr_r=0x0a100000
Vboot=1, SecureBoot enabled, AVB verify            ← 有这个分支（见第六节：实际不校验内核）
Vboot=0, AVB images, AVB verify
boot_extlinux=sysboot ... extlinux/extlinux.conf   ← 存在，但不在 bootcmd 里
```

> 注意区分：`Vboot=` 只是"代码里有这条分支"，**不等于**当前机器的值。
> 判定这台机器 OTP 已熔断的依据是机主实测——换 loader 直接不启动。

所以：

| 层 | 位置 | 能否改 | 后果 |
|---|---|---|---|
| BootROM → loader | 扇区 64 起（0–4 MiB 内） | **绝对不能** | 一改就完全不开机，只能拆 eMMC |
| SPL → uboot/ATF/OP-TEE | 8–16 MiB | **绝对不能** | 同上 |
| uboot → kernel/dtb | `boot` 分区 25–65 MiB | 可以改 | 最多停在 `=>`，可回滚 |

**硬规则（写进流程，不要凭记忆）：**

1. `rkdeveloptool wl` / RKDevTool 的任何写入，起始偏移 **≥ 0x01900000（25 MiB）**
2. `rkdeveloptool db` 的 `MiniLoaderAll.bin` **必须是这套 wxy 固件里的那份签名 loader**，
   不能用 Rockchip SDK 里通用的那个（downloader 也是签名链的一环）
3. 手边永远留一份 `安全区.img`（16 MiB 原样前 16 MiB），它是唯一的"复活卡"

> 注：`security` 分区（4–8 MiB）是 OTP/keybox 之类，和"安全区.img"不是一回事——
> "安全区"指的是 0–16 MiB 这一整段签名链。

## 一、这台机器的分区表（原厂 Android GPT）

> **设备名注意**：同一块 eMMC，Android 里叫 `/dev/mmcblk2`，现运行的 Armbian 里叫 `/dev/mmcblk1`。
> 所以分区是 `mmcblk1p1 .. mmcblk1p14`。备份文件名沿用了 Android 的 `mmcblk2*` 命名，指的是同一块盘。
> 正因为设备名会变，**cmdline 和 fstab 都用 PARTUUID**，不用 `/dev/mmcblkXpY`。

```
LBA 起点      偏移        大小      名字            用途
        0     0           4 MiB     (保护/预留)     ← GPT 主表 + idbloader，禁止碰
     8192     4 MiB       4 MiB     security
    16384     8 MiB       4 MiB     uboot           ← FIT: ATF/OP-TEE/U-Boot，校验链在这
    24576     12 MiB      4 MiB     trust
    32768     16 MiB      4 MiB     misc
    40960     20 MiB      4 MiB     dtbo
    49152     24 MiB      1 MiB     vbmeta
    51200     25 MiB      40 MiB    boot            ← 写 boot.img
   133120     65 MiB      100 MiB   recovery
   337920     165 MiB     384 MiB   backup
  1124352     549 MiB     384 MiB   cache
  1910784     933 MiB     16 MiB    metadata
  1943552     949 MiB     1 MiB     baseparameter
  1945600     950 MiB     3.1 GiB   super           (Linux 用不到)
  8318976     4062 MiB    ~28 GiB   userdata        ← 写 rootfs.img
```

前 16 MiB 里那段 `uboot` 分区是一个 FIT，里面装的是：

```
description = "FIT Image with ATF/OP-TEE/U-Boot/MCU"
  uboot  0x00a00000  sha256 9b5584889e...
  atf-1  0x00040000  sha256 6204b6f381...
  optee  0x08400000  sha256 66bbd17352...
```

反过来说：只要不动前 16 MiB，就永远不会变砖。

## 二、烧写

先用 `gzip -d rootfs.img.gz` 解出 `rootfs.img`。

### RKDevTool（Windows）

1. 设备进 Loader / Maskrom 模式（按住恢复键上电，或 `rkdeveloptool rd` 后重插）
2. 切到「高级功能 / 分区写」页
3. 按 `config.cfg` 的写法加两行：

| 分区名 | 起始扇区 | 文件 |
|---|---|---|
| boot | 51200 | `boot.img` |
| userdata | 8318976 | `rootfs.img` |

### rkdeveloptool（Linux / macOS）

```bash
rkdeveloptool db  <wxy固件里那份 MiniLoaderAll.bin>   # ← 不能换成通用版
rkdeveloptool wl  51200    boot.img
rkdeveloptool wl  8318976  rootfs.img
rkdeveloptool rd
```

`wl` 后面的数字是**起始扇区**，不是字节偏移。别把 `wl` 写成 `wl 0`。

## 三、TTL 验收清单

串口：UART2（`0xfe660000`），**1500000 8N1**，三线 GND/TX/RX，别接 VCC。

### 成功应该依次看到

```
Starting kernel ...
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x412fd050]
[    0.000000] Machine model: Rockchip RK3566 EVB2 LP4X V10 Board
[    0.xxx] rockchip-dw-mipi-dsi fe060000.dsi: ...
[    0.xxx] panel-simple-dsi fe060000.dsi.0: ...
[    0.xxx] mmc_host mmc2: new SDIO card at address ...
[    0.xxx] EXT4-fs (mmcblk1p14): mounted filesystem
[    x.xxx] gm-speaker login:
```

`Machine model` 那行如果打出来，说明 FIT 里的 DTB 已经被内核拿到了。
`panel-simple-dsi` 那行打出来，屏幕就不该再是紫条纹了。

### 各类失败对应的意思

| TTL 输出 | 含义 | 下一步 |
|---|---|---|
| `FIT: No fit blob` / `FIT: No FIT image` | uboot 不认这个 FIT 格式 | 换 Android boot.img 格式再试 |
| `ERROR: Did not find a cmdline Flattened Device Tree` | FIT 里没带 dtb | 检查 `boot.its` 的 `configurations` |
| `VFS: Unable to mount root fs on ...` | `root=` 解析失败或分区没写进去 | cmdline 用的是 `root=PARTUUID=84120000-...`（userdata 的 GPT 常量），核对 GPT 是否还在 |
| 停在 `=>` 提示符 | uboot 放弃了，可以直接敲命令 | `printenv bootargs` / `mmc part` / `ls mmc 0:7` |
| 内核起了但挂不上根 | uboot 可能用 env 里的 `bootargs` 覆盖了 DTB 的 `chosen/bootargs` | 见下面「cmdline 被覆盖」 |
| 屏幕全黑但 TTL 正常 | 面板没起来 | 回到 DTS 调 `panel-init-sequence` / `dsi` 参数 |

> 停在 `=>` 是**好事**：可以直接在 uboot 控制台里 `ls mmc 0:7 /` 看 boot 分区内容、
> `printenv` 看 bootargs、`bootm` 手动试，不用反复刷机。

### cmdline 被覆盖怎么办

我们的 `root=PARTUUID=...` 写在 DTB 的 `chosen/bootargs` 里。Rockchip 这套 uboot
也可能用 env 里的 `bootargs` 覆盖它。真遇到时不用重新刷机，在 `=>` 敲：

```
setenv bootargs console=ttyS2,1500000n8 earlycon=uart8250,mmio32,0xfe660000 root=PARTUUID=84120000-0000-4b2f-8000-0f5100000a64 rootwait rw rootfstype=ext4 loglevel=7
boot
```

起来了就说明是这个问题，回头我们把 cmdline 直接写进 FIT 的 `configurations/conf`
（U-Boot 会优先用 config 里的 `bootargs`），一劳永逸。

排查时先看内核拿到的到底是什么：

```
cat /proc/cmdline
```

## 四、回滚

只写了 boot 和 rootfs，回滚也就是把这两个写回去：

```
boot     : 备份/mmcblk2p7        (原厂 Android boot.img，文件名沿用 Android 命名)
userdata : 原厂没有备份的话，格式化即可 —— 里面只是 Android 的用户数据
```

`rkdeveloptool wl 51200 备份/mmcblk2p7` 就回到 Android 的 boot。
（写的是扇区偏移，跟设备叫 mmcblk1 还是 mmcblk2 无关。）
前 16 MiB 从没被动过，所以**根本不需要再刷安全区**——这也是这套方案最大的好处。

## 五、为什么不再出整盘镜像

旧流水线是「拿 ophub 整盘 img.gz 替换 DTB」。但一比 GPT 就发现位置完全错位：

```
ophub 镜像 :  p1 180 MiB (boot)   p2 692 MiB (rootfs)
这台机器   :  boot 25 MiB         userdata 4062 MiB
```

原厂 uboot 是按 GPT 名字找 `boot` 分区的，所以它去 25 MiB 找 FIT，
那里放的是 ophub 镜像的"backup 分区"内容 → `FIT: No fit blob` → 掉到 `=>` 提示符。

ttl.txt 里那一串就是这么来的：

```
Failed to load DTB, ret=-19        ← 没有 resource 分区
No find valid DTB, ret=-22
FIT: No fit blob                   ← boot 分区里没有 FIT
FIT: No FIT image
=>
```

## 六、第 3 层不校验内核（已确认）

**结论：`boot` 分区里的 FIT 不需要签名，可以随便换。**

依据两条：

1. uboot 里根本没有 wxy/厂商的签名证书 —— 它没有可用来验 `boot` 的密钥
   （`sha256,rsa2048:dev` 那把只用在 **SPL → uboot 那层**，密钥烧在 SPL 里，与内核无关）
2. 现运行的这套系统本身就是"自定义 DTB + mainline 内核"跑起来的，
   要校验的话早该卡住了

`Vboot=1, SecureBoot enabled, AVB verify` 这句只是**代码里有这个分支**，
配合 bootargs 里的 `androidboot.verifiedbootstate=orange`（解锁态），
AOSP 给 `avb_slot_verify()` 传的是 `ALLOW_VERIFICATION_ERRORS` —— 失败只警告不拦。

所以：**按 `boot/boot.its` 直接 `mkimage` 就行，不用签。**

> 想再确认一遍的话（可选，只读）：`sudo dd if=/dev/mmcblk1p7 of=/tmp/boot.img bs=1M count=40`，
> 看 FIT 里有没有 `signature` 节点。注意 eMMC 在这套系统里是 **mmcblk1**，
> 而备份文件名沿用 Android 的 `mmcblk2*` 命名，两者指同一块盘。

**退路 A（默认路线，最稳）**：`boot/boot.its` 照抄现成那份 FIT 的骨架，
只替换 `Image.gz` 和 `board.dtb`，其它属性（load 地址、节点名、hash 节点）一字不改。

**退路 B（uboot 里现成的后门）**：`bootcmd=boot_fit`，但二进制里确实编进了

```
boot_extlinux=sysboot ${devtype} ${devnum}:${distro_bootpart} any ${scriptaddr} ${prefix}extlinux/extlinux.conf
scan_dev_for_extlinux / distro_bootcmd / boot_targets=mmc1 mmc0 ...
```

停在 `=>` 时手敲就能走标准 extlinux（Armbian 原生路径，不碰 FIT）：

```
setenv devtype mmc; setenv devnum 0; setenv distro_bootpart 7
run boot_extlinux
```

`devnum 0` 是 eMMC（uboot 日志 `sdhci@fe310000: 0`），`distro_bootpart 7` 是 boot 分区。
这条路能彻底绕开 FIT 格式问题，代价是每次开机要手敲（除非改 `bootcmd` 并 `saveenv`，
而 env 存在 mmc 固定偏移、仍在 16 MiB 内 —— 想动它必须先确认 `安全区.img` 能回滚）。

## 七、没有 SD 卡槽

这机器没有 SD 槽，SPL 日志里 `Trying to boot from MMC2 / Card did not respond` 就是因为这个，
最后落到 `MMC1`（eMMC）才起来。所以**没有"先用 SD 试"这条退路**，
所有验证都直接在 eMMC 上做 —— 更要守住"只写 25 MiB 之后"这条线。
