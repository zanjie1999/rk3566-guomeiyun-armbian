# 刷机与回滚

> **结论先说**：现在出的是**整盘镜像**（ophub GPT 布局，p1 从 180 MiB 起）。
> 整盘写入会覆盖前 16 MiB，所以关键不是"绕开前 16 MiB"，而是
> **确认镜像里的 loader 与你 eMMC 上实际在跑的是同一份**。
>
> `wxy-loader` 变体就是按这个要求打的：它的前 16 MiB 与真机实测**逐字节一致**
> （`0x8000` 处 `RKSS`，GPT 同为 p1@180 MiB / p2@692 MiB），刷完**不需要补刷安全区**。

## 一、这台机器的 secure boot 状态

这台机器的 OTP 已经被上一轮折腾烧过，信任链是硬件钉死的。从 `安全区.img` 里
抠出 uboot 本体（偏移 `0x801000`，1 281 000 字节）翻字符串，三条证据互相印证：

**第 1 层 — BootROM → idbloader（扇区 64，32 KiB 处）**

BootROM 只认 OTP 里存的 hash 对应的那份 loader。换任何别的 loader 都不启动。

**第 2 层 — SPL → uboot 分区（8–12 MiB）的 FIT**

```
## Verified-boot: 1
sha256,rsa2048:dev
## Checking atf-1 ... sha256(6204b6f381...) + OK
## Checking uboot 0x00a00000 ... sha256(9b5584889e...) + OK
## Checking optee 0x08400000 ... sha256(66bbd17352...) + OK
```

`uboot` 分区里 package 的是 `ATF + OP-TEE + U-Boot`，SPL 用 rsa2048:dev 校验，
全 OK 才跳转。所以 8–16 MiB 也不能改。

**第 3 层 — uboot → boot 分区 —— 这一层实际不校验内核**

uboot 里没有厂商的签名证书，`sha256,rsa2048:dev` 那把只用在 SPL → uboot 那层。
`Vboot=1, SecureBoot enabled, AVB verify` 只是代码里有这个分支，配合
`androidboot.verifiedbootstate=orange`（解锁态），AOSP 给 `avb_slot_verify()`
传的是 `ALLOW_VERIFICATION_ERRORS` —— 失败只警告不拦。

所以 **DTB 可以随便换**，这也是本项目能成立的前提。

## 二、loader 签名的两个魔数（实测）

偏移 `0x8000` 的 16 字节就是区分点：

```
RKSS 00 00 00 00 80 01 02 00 11 00 00 00    <- 0x11=17，带分区 hash 表（OEC 签名链）
RKNS 00 00 00 00 80 01 02 00 01 00 00 00    <- 0x01=1，只含自身 hash（Rockchip 通用）
```

| ophub 镜像 | 魔数 | p1 起始 | p2 起始 |
|---|---|---|---|
| `wxy-oect` 6.1.157 bookworm | `RKSS` | 180 MiB | 692 MiB |
| `youyeetoo-yy3568` 6.18.59 bookworm | `RKNS` | 16 MiB | 528 MiB |

**这两个布局不能混用。** 把 `RKNS` 那份的前 16 MiB 套到 `RKSS` 的镜像上，
GPT 会指向不存在的位置，开机直接找不到分区。

判断某份镜像属于哪种，一行就够：

```bash
curl -fsSL -r 0-1048575 -o hdr.bin "<img.gz url>"
python3 -c "import gzip;d=gzip.GzipFile('hdr.bin').read(0x8010);print(d[0x8000:0x8010].hex(' '))"
```

## 三、当前镜像布局（ophub GPT）

`wxy-loader` 变体（`Armbian_26.11.0_rockchip_wxy-oect_bookworm_6.1.157`）：

```
LBA 起点      偏移        大小      内容
        0     0           180 MiB   GPT 主表 + idbloader（4 份副本）+ security + uboot FIT
                                  ↑ 这段镜像里已包含，与真机在跑的一致
   368640     180 MiB     511 MiB   p1  <- boot 分区（ext4，含 Image/uInitrd/dtb/）
  1417216     692 MiB     2999 MiB  p2  <- rootfs
                                  p2 之后到盘尾为空
```

`generic` 变体（`youyeetoo-yy3568`）的 p1 在 16 MiB、p2 在 528 MiB，
前 16 MiB 是 `RKNS` 的通用 loader。

## 四、刷写

### Linux / macOS

```bash
gzip -dc RK3566-Speaker-Armbian_wxy-loader_*.img.gz \
  | sudo dd of=/dev/sdX bs=4M status=progress conv=fsync
sync
```

`/dev/sdX` 是**整盘**，不是分区（不要写 `sdX1`）。

### Windows

1. 设备进 Loader / Maskrom 模式（按住恢复键上电，或 `rkdeveloptool rd` 后重插）
2. RKDevTool →「升级固件」→ 选解压后的 `.img`
3. 或 `rkdeveloptool db <MiniLoaderAll.bin>` + `rkdeveloptool wl 0 <img>`

> `rkdeveloptool db` 用的 loader 也必须是签名链里那一份，不能用 Rockchip SDK 的通用版。

## 五、为什么 wxy-loader 变体刷完不用补安全区

因为它的前 16 MiB 就是 eMMC 上现在跑的那份。实测对比（逐 64 KiB 比对）：

```
设备 eMMC 前 16 MiB  vs  ophub wxy-oect 镜像前 16 MiB
  0.06 MiB - 16.00 MiB : 完全一致（只有 0-0.06 MiB 的 GPT 头因磁盘容量不同而异）
```

workflow 里也有硬断言：改完 DTB 之后重新 `dd` 前 16 MiB 算 sha256，
必须与改动前那一份相同，否则构建失败。

**但要注意**：ophub 更新镜像时 loader 可能跟着变。workflow 的 `Record original layout`
步骤会打印 base 镜像前 16 MiB 的 sha256 和 `0x8000` 魔数，刷之前对一下：

```bash
# 你机器上现在这份
sudo dd if=/dev/mmcblk0 bs=1M count=16 status=none | sha256sum
```

两个值一样就不用补安全区；不一样就老老实实刷回安全区，别赌。

## 六、TTL 验收清单

串口：UART2（`0xfe660000`），**1500000 8N1**，三线 GND/TX/RX，别接 VCC。

### 成功应该依次看到

```
Starting kernel ...
[    0.000000] Booting Linux on physical CPU 0x0000000000 [0x412fd050]
[    0.000000] Machine model: Rockchip RK3566 EVB2 LP4X V10 Board
[    0.xxx] rockchip-dw-mipi-dsi fe060000.dsi: ...
[    0.xxx] panel-simple-dsi fe060000.dsi.0: ...
[    0.xxx] mmc_host mmc2: new SDIO card at address ...
[    0.xxx] EXT4-fs (mmcblk0p2): mounted filesystem
[    x.xxx] gm-speaker login:
```

`Machine model` 那行打出来，说明 DTB 被内核拿到了。

### 各类失败对应的意思

| TTL 输出 | 含义 | 下一步 |
|---|---|---|
| `FIT: No fit blob` | uboot 在预期位置找不到 FIT | 镜像的 loader 布局对不对？`0x8000` 魔数是 `RKSS` 还是 `RKNS`？ |
| `VFS: Unable to mount root fs on ...` | `root=` 解析失败 | ophub 用 `root=UUID=<ext4 fs uuid>`，检查 rootfs 有没有写进去 |
| 卡在 `=>` 提示符 | uboot 放弃了 | `printenv bootargs` / `mmc part` / `ls mmc 0:1 /boot` |
| 内核起了但外设全无 | DTB 没换成功，或内核缺 vendor 驱动 | `cat /proc/cmdline`、`cat /proc/device-tree/model` |
| 屏幕全黑但 TTL 正常 | 面板没起来 | 回 DTS 调 `panel-init-sequence` / `dsi` 参数 |

## 七、历史：早期为什么走"分区包"（已作废）

早期方案是只写 `boot` + `rootfs` 两个分区，绕开前 16 MiB。那是因为当时刷的是
**原厂 Android 的 uboot**，它按 GPT 名字找 `boot` 分区（25 MiB），而 ophub 整盘镜像
的 p1 在 180 MiB —— 位置完全错位，刷完只会得到 `FIT: No fit blob`。

后来发现设备实际跑的是 ophub 自己的布局（p1@180 MiB），原厂 Android 那套 GPT
（14 个分区，boot 在 25 MiB）已经不存在了。所以现在直接出整盘镜像，
`boot/boot.its` 和 `.github/workflows/build-bsp.yml` 都已删除。

原厂分区表仅作硬件参考保留如下：

```
LBA 起点      偏移        大小      名字            用途
        0     0           4 MiB     (保护/预留)     GPT 主表 + idbloader
     8192     4 MiB       4 MiB     security
    16384     8 MiB       4 MiB     uboot           FIT: ATF/OP-TEE/U-Boot
    24576     12 MiB      4 MiB     trust
    32768     16 MiB      4 MiB     misc
    40960     20 MiB      4 MiB     dtbo
    49152     24 MiB      1 MiB     vbmeta
    51200     25 MiB      40 MiB    boot
   133120     65 MiB      100 MiB   recovery
   337920     165 MiB     384 MiB   backup
  1124352     549 MiB     384 MiB   cache
  1910784     933 MiB     16 MiB    metadata
  1943552     949 MiB     1 MiB     baseparameter
  1945600     950 MiB     3.1 GiB   super
  8318976     4062 MiB    ~28 GiB   userdata
```

## 八、没有 SD 卡槽

这机器没有 SD 槽，SPL 日志里 `Trying to boot from MMC2 / Card did not respond` 就是因为这个，
最后落到 `MMC1`（eMMC）才起来。所以**没有"先用 SD 试"这条退路**，
所有验证都直接在 eMMC 上做。
