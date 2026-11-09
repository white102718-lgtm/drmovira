# MinIO 跨区迁移手册（新加坡 → 俄勒冈）

把旧系统 MinIO 的素材迁到新系统集群，并在新集群复刻冷层。

- 源：`aws_db`，ap-southeast-1b，i-0b7bc8a6b9f58875a，公网 18.139.123.178:9000
- 目标：`aws_adp_db`，us-west-2c，i-040dd887d0fc913c8，内网 172.31.8.119:9000
- 数据采集与实测时间：2026-09-14。两边 MinIO 均为 `RELEASE.2025-09-07T16-13-09Z`，单盘部署。

本文所有数字都来自在两台机器上的实际执行，不是估算。未验证的项在附录 A 单独标出。

**执行状态（2026-09-14）**：阶段 0（热盘扩到 3 TiB、冷盘 1.5 TiB 挂 `/mnt/colddisk`）、阶段 1（`adpulse-minio-cold` 已起）、阶段 2（COLDTIER 层 + 两条 ILM 规则）**均已完成**。阶段 3 全量迁移待跑。

## 基本情况

| 项 | 值 |
| --- | --- |
| 要迁的量 | `materials` 2.0 TiB / 211,383 个对象，其余小桶合计约 1 GiB |
| 不迁 | `tmp`（53 GiB，旧库本来就挂 7 天过期规则） |
| 全量耗时 | 约 7.3 小时（4 进程分片，实测 79.7 MiB/s） |
| 冷热切分 | 2026-07-01 之前进冷盘：91,497 个 / 747.5 GiB；之后留热盘：119,886 个 / 1297.2 GiB |

两条约束决定了整个方案的形状：

1. **两边只有公网通，内网不通**。2026-09-14 复测：新机 → 旧机 `18.139.123.178:9000` 返回 200、旧机 → 新机 `44.232.82.170:9000` 返回 200，RTT 均约 170ms；而两边的内网 IP（`172.31.40.125` / `172.31.8.119`）双向都不通，两台机上也没有 10.60 地址。根因是两边 VPC 都是 172.31，网段重叠。所以全程走旧机公网，由新机去拉。
2. **新库已有同名的 18 个桶且 `materials` 里有部分副本**（抽样 60/60 都在旧库存在），所以只能用 mirror 合并，不能挂盘接管。

### 旧库的冷层结构

旧机上跑着两个 MinIO 实例：

- 热实例 `minio`：端口 9000，数据在 `/opt/pvstore/data/minio`
- 冷实例 `minio-cold`：端口 9100，数据在 `/mnt/colddisk/minio`

热实例对 `materials` 配了 ILM：90 天转储到远程层 `COLDTIER`（bucket `cold-tier`，前缀 `archive/`）。

**`cold-tier` 不是独立数据**，是 `materials` 的转储尾巴，已经算在它的 2.0 TiB 逻辑体积里。它里面存的是这种东西：

```
archive/fdafdaefad577cab/00/02/0002fe38-e31c-4b43-bd3c-50bc00d9f8f7
```

uuid 命名的块，由热实例的转储管理器维护，对象键到块的映射在热实例的元数据里。所以：

- 迁移时只能迁 `materials` 的逻辑视图，**不能直接拷 `cold-tier`**。
- 新库那边也**没法把对象直接写进冷盘**，必须先落热盘再由规则搬过去。

已转冷的对象读取是透明的，不需要 restore（实测 rc=0，本机 30 MiB/s；未转冷的对象同机 144 MiB/s）。

---

## 阶段 0：加热盘 + 加冷盘（控制台操作）

两台机器都没有 IAM 实例角色，也没装 aws CLI，加盘只能在控制台或本地有凭证的机器上做。

### 热盘扩到 3 TiB

`mc mirror --preserve` **不保留 LastModified**（实测：源 2026-06-30 的对象，副本变成 2026-09-14）。所以 2.0 TiB 会先全部落在热盘，打完标签后才有 747.5 GiB 排到冷盘，稳定下来约 1.3 TiB。加上每月约 500 GiB 的增长，3 TiB 是合适起点，gp3 以后可以在线扩。

```bash
# 本地有 AWS 凭证的机器上（根卷 ID 从控制台 i-040dd887d0fc913c8 拿）
aws ec2 modify-volume --region us-west-2 --volume-id vol-xxxxxxxx --size 3072 --volume-type gp3

# 等状态变成 optimizing 之后，在 aws_adp_db 上扩分区和文件系统（不用停机）
lsblk
sudo growpart /dev/nvme0n1 1
sudo resize2fs /dev/nvme0n1p1
df -h /
```

`growpart` / `resize2fs` 新机上都有。根分区是 `/dev/nvme0n1p1`，ext4。

### 冷盘 1.5 TiB，挂到 /mnt/colddisk

迁移当天就有 747.5 GiB 进冷盘，1 TiB 的话第一天就到 73%，余量太薄（旧机冷盘现在正是 81% 的状态）。

旧机冷盘是整盘直接格式化、不分区，fstab 用 UUID 加 `nofail`。新机照同一套来：

```bash
# 控制台建 1.5 TiB gp3，可用区必须是 us-west-2c，挂到 i-040dd887d0fc913c8
lsblk                                    # 确认新盘名，通常是 /dev/nvme1n1
sudo mkfs.ext4 -m 0 /dev/nvme1n1
sudo mkdir -p /mnt/colddisk
UUID=$(sudo blkid -s UUID -o value /dev/nvme1n1)
echo "UUID=$UUID /mnt/colddisk ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a
sudo mkdir -p /mnt/colddisk/minio
df -h /mnt/colddisk
```

---

## 阶段 1：起新的冷 MinIO 实例

旧系统的冷实例是独立的 compose 项目（`/home/ubuntu/deploy/minio-cold`），但新系统所有库都在 `adpulse-db` 这一个 compose 里。按新系统的惯例走，加一个 service 到 `/home/ubuntu/adpulse-deploy/database/docker-compose.yml`，端口沿用旧机冷实例的 9100 / 9101：

```yaml
  minio-cold:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    container_name: adpulse-minio-cold
    restart: unless-stopped
    ports:
      - "${DB_PRIVATE_IP}:9100:9000"
      - "${DB_PRIVATE_IP}:9101:9001"
    environment:
      MINIO_ROOT_USER: ${MINIO_ROOT_USER}
      MINIO_ROOT_PASSWORD: ${MINIO_ROOT_PASSWORD}
    volumes:
      - /mnt/colddisk/minio:/data
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 10s
      timeout: 5s
      retries: 12
```

**不需要往 `.env` 加任何变量**：旧机上热、冷两个实例本来就共用同一套 root 凭证（已核对，用户名和密码都相同），冷层配置用的也是这一套。新机照此复用 `.env` 里已有的 `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`。想两套分开也行，但那是偏离现有约定，得自己加变量。

```bash
cd /home/ubuntu/adpulse-deploy/database
sudo docker compose up -d minio-cold
```

> 这台机上 `docker compose` **必须用 sudo**：`.env` 是 `-rw------- root root`，`ubuntu` 用户读不到，不加 sudo 会直接报 `open .env: permission denied`。

---

## 阶段 2：配冷层和转储规则

新机上没有 mc 二进制，但 `minio/mc` 镜像本地已有，用 docker 包装：

```bash
MC=minio/mc:RELEASE.2025-08-13T08-35-41Z
OLD="http://<旧root>:REDACTED_REFERENCE_SECRET@18.139.123.178:9000"
NEW="http://<新root>:REDACTED_REFERENCE_SECRET@172.31.8.119:9000"
COLD="http://<root>:REDACTED_REFERENCE_SECRET@172.31.8.119:9100"   # 与热实例同一套凭证
mcr(){ docker run --rm --network host -e MC_HOST_old="$OLD" -e MC_HOST_new="$NEW" -e MC_HOST_cold="$COLD" $MC "$@"; }
```

冷层的形状照抄旧库：bucket `cold-tier`、前缀 `archive/`、层名 `COLDTIER`。

```bash
mcr mb cold/cold-tier

mcr admin tier add minio new COLDTIER \
  --endpoint http://172.31.8.119:9100 \
  --bucket cold-tier --prefix archive/ \
  --access-key "$MINIO_ROOT_USER" --secret-key "$MINIO_ROOT_PASSWORD"
```

### 两条规则，分别管老数据和新数据

这是整个方案唯一需要动脑的地方。迁进来的对象在新库眼里都是「今天刚写的」，所以单靠 90 天规则，2.0 TiB 会在热盘躺满 90 天，然后几乎同时集体转冷——既压垮热盘也不符合原意。解法是老数据用标签驱动，新数据继续用天数驱动：

```bash
# 老数据：带 tier=cold 标签的立即转冷
mcr ilm rule add --tags "tier=cold" --transition-days 0 --transition-tier COLDTIER new/materials

# 新数据：90 天转冷，和旧库规则一致
mcr ilm rule add --transition-days 90 --transition-tier COLDTIER new/materials
```

> `--transition-days 0` 已于 2026-09-14 冷层建好后实测**被接受**，两条规则均已写入 `new/materials`，不需要退回 days=1。

---

## 阶段 3：全量迁移，4 片并行

单进程 128 workers 只有 34.6 MiB/s，2 进程 61.2，4 进程到 79.7 MiB/s，所以按 4 片跑。

`materials` 是一个扁平大桶（96% 的字节是 `V*` 开头的键，按首字母切不均），**按时间切才均匀**——33 / 69 / 97 天三个切点分出 481 / 533 / 519 / 511 GiB 四片。四个时间段的并集永远覆盖全桶，不管什么时候重跑都不会漏。

```bash
# 在 aws_adp_db 上，四条一起后台跑
nohup docker run --rm --network host -e MC_HOST_old="$OLD" -e MC_HOST_new="$NEW" $MC \
  mirror --preserve --max-workers 64 --newer-than 33d \
  old/materials new/materials > ~/mig_s1.log 2>&1 &

nohup docker run --rm --network host -e MC_HOST_old="$OLD" -e MC_HOST_new="$NEW" $MC \
  mirror --preserve --max-workers 64 --older-than 33d --newer-than 69d \
  old/materials new/materials > ~/mig_s2.log 2>&1 &

nohup docker run --rm --network host -e MC_HOST_old="$OLD" -e MC_HOST_new="$NEW" $MC \
  mirror --preserve --max-workers 64 --older-than 69d --newer-than 97d \
  old/materials new/materials > ~/mig_s3.log 2>&1 &

nohup docker run --rm --network host -e MC_HOST_old="$OLD" -e MC_HOST_new="$NEW" $MC \
  mirror --preserve --max-workers 64 --older-than 97d \
  old/materials new/materials > ~/mig_s4.log 2>&1 &
```

> **在哪个目录执行都行**：这些是 `docker run`，不读本地文件，只有 `> ~/mig_s1.log` 决定日志落在哪。（compose 命令则相反，必须 `cd` 到项目目录或用 `-f` 绝对路径，且都要 sudo。）
>
> **但新机 ssh 不到旧机**（实测 `Permission denied (publickey)`），所以 `$OLD` 里的旧库凭证没法在新机上就地取得。新机上已备好接好凭证的 `~/migrate_materials.sh`（700 权限，含明文凭证，迁完删掉）：
>
> ```bash
> bash ~/migrate_materials.sh start    # 启动 4 片全量迁移
> bash ~/migrate_materials.sh status   # 看进度
> bash ~/migrate_materials.sh small    # 迁其余小桶
> ```

小桶单独跑一遍就行，总共才 1 GiB 左右：

```bash
for b in agent-img-video content creative-generated creative-generated-img \
         creative-origin creative-origin-img material-commons telegram-media \
         meta-ad report-agents report-question-img instruction-reports \
         diagnostic-reports backtest-io tools material-orders; do
  mcr mirror --preserve --max-workers 32 "old/$b" "new/$b"
done
```

`agent-img-video` 两边键完全不重叠（旧 `products/…`、新 `generated/…`），直接并进去即可。

---

## 阶段 4：每天补增量

旧库还在写，9 月前 14 天新增 145 GiB / 13,490 个对象，约每天 10 GiB。把阶段 3 的四条命令原样重跑即可——已存在且一致的对象会被跳过，实测 757 个已存在对象重跑耗时 1.2 秒、传输 0 B。

---

## 阶段 5：给老对象打标签，排进冷盘

按业务口径切：**2026-07-01 之前的进冷盘**，实测 91,497 个对象 / 747.5 GiB（36.6%），留热盘 119,886 个 / 1297.2 GiB。用固定日期而不是「90 天前」，迁移拖几天这条线也不会漂。

其中 560.4 GiB / 69,965 个正是旧库冷层现在装的那批，剩下 187.1 GiB / 21,532 个在旧库还留在热盘上、从没转储过。也就是说这个集合比旧库的实际转储状态更宽，是业务口径，不是对旧库状态的复刻。

```bash
# 旧机上本地列举，快
mc ls --recursive --json t/materials | python3 -c "
import sys, json
CUT = '2026-07-01'
for l in sys.stdin:
    try: o = json.loads(l)
    except Exception: continue
    if o.get('type') == 'file' and o.get('lastModified','')[:10] < CUT:
        print(o['key'])
" > /tmp/cold_keys.txt
wc -l < /tmp/cold_keys.txt          # 预期 91,497 上下（切换当天重新生成）

# 直接管道送到新机，不落本地
ssh aws_db 'cat /tmp/cold_keys.txt' | ssh aws_adp_db 'cat > /tmp/cold_keys.txt'

# 新机批量打标签，实测 232 obj/s，9 万个约 6.6 分钟
docker run --rm -i --network host -e MC_HOST_new="$NEW" --entrypoint sh $MC -c '
i=0
while IFS= read -r k; do
  mc tag set "new/materials/$k" "tier=cold" >/dev/null 2>&1 &
  i=$((i+1)); [ $((i % 32)) -eq 0 ] && wait
done
wait' < /tmp/cold_keys.txt
```

打标签对后续增量是安全的，三件事都验证过：标签不改对象的 `Date`；打完标签后重跑 mirror 依然是 0 B；标签在重跑后仍然保留。

---

## 阶段 6：切换与核对

1. 旧系统停写。
2. 最后跑一遍四片增量，补上停写前的最后一批。
3. 核对对象数：`mcr du old/materials` 与 `mcr du new/materials` 应一致。
4. `mcr diff old/materials new/materials` 无输出即为一致（21 万对象跨洋比对耗时未实测，预留时间）。
5. 冷层生效情况：看 `df -h /mnt/colddisk /`（冷盘涨、热盘降）和抽查对象的 storage-class 是否为 `COLDTIER`。转储是本机热盘搬到冷盘、由 MinIO 的 scanner 推进，会慢慢流过去而不是一次到位。
   **注意别被 `admin tier info` 的 Usage 骗了**：实测对象已经转冷、冷盘上已出现 `archive/` 块时，该计数仍显示 `0 B / 0 objects`（用量统计滞后）。判断是否真的转了，要看对象的 storage-class 或冷盘内容，不要看这个计数。
6. 新系统改配置：桶名和对象键两边完全一致，所以只需把 endpoint 指到新 MinIO。如果库里存的是带旧域名的完整 URL，那批记录要一起改。

---

## 附录 A：已知风险与未验证项

| 项 | 状态 | 说明与应对 |
| --- | --- | --- |
| `--transition-days 0` | 已验证 | 2026-09-14 冷层注册完成后实测接受，规则已生效：`{"Filter":{"Tag":{"Key":"tier","Value":"cold"}},"Transition":{"StorageClass":"COLDTIER","Days":0}}`。 |
| 7 月 1 日之后的对象 | 已知后果 | 这 1297.2 GiB 留热盘，但它们在新库的「年龄」从迁移日重新计算，最晚会比原本晚 90 天才转冷。热盘按 3 TiB 备能吃下这个峰值。要精确可以按剩余天数分几档打标签，但没必要。 |
| 旧库持续写入 | 已量化 | 约 10 GiB/天。切换前必须停写并补最后一次增量。 |
| 跨区流量费 | 部分确定 | **已确定**（AWS 官方文档）：入站全免，只算源区域的出站；每月前 100 GB 免费（全服务全区域汇总）。**实际上线字节数 ≈ 2016 GiB**（materials 2044.7 − 新库已有 32 + 小桶 2.95）。**未确定**：走公网 IP 的跨区流量落进哪个 usage type——`APS1-USW2-AWS-Out-Bytes`（跨区，常见报价 ~$0.09/GB）还是 `APS1-DataTransfer-Out-Bytes`（互联网出口，新加坡 ~$0.12/GB）。查了 8 个来源含 AWS CUR 文档、global network FAQ、架构博客，都只列 usage type 不说公网 IP 跨区归哪类。**估算区间约 $180–260**。**定论办法**见下。 |
| 两边 9000 的暴露面 | 待确认 | 旧机 9000 能被新机公网出口连上；新机 9000 在 2026-09-14 也变成能被旧机公网连上了（当天早些时候还不通）。两边放行范围是不是 0.0.0.0/0 都未查——新库是全新的生产存储，建议先确认安全组只放行对端 IP，迁移完再收紧。 |
| 迁移不要走 VPN | 注意 | 实测的 79.7 MiB/s 走的是旧机公网 IP。以后若 10.60 内网打通，别顺手把 mirror 改到 VPN 上——OpenVPN 单机转发会成为瓶颈，改之前先重测。 |
| `mc diff` 在 21 万对象上的耗时 | 未实测 | 切换当天预留时间。 |
| 转储（热→冷）的整体速率 | 链路已验证，速率未实测 | 2026-09-14 端到端验证：打上 `tier=cold` 后 **60 秒内** storage-class 变 COLDTIER，冷盘出现 `archive/<uuid>/…` 块，读回字节数与源一致。但 747.5 GiB 整体搬完要多久没测。 |

## 附录 B：实测数据

2026-09-14 在 aws_db / aws_adp_db 上实际执行，测试用的临时桶（`migrate-*`）均已删除并核对。

| 测量项 | 结果 | 含义 |
| --- | --- | --- |
| 单流拉取 | 1.8 MiB/s | RTT 170ms 下被延迟卡死，不能单线程跑 |
| mirror 单进程 128 workers | 34.6 MiB/s | 16.9 h |
| mirror 2 进程 | 61.2 MiB/s | 9.5 h |
| mirror 4 进程 × 64 workers | **79.7 MiB/s** | **7.3 h**，方案采用值 |
| 重复对象跳过 | 0 B / 1.2 s | 757 个已存在对象，增量重跑几乎零成本 |
| 打标签速率 | 232 obj/s | 91,497 个约 6.6 分钟 |
| Content-Type 保留 | 已验证 | 源与副本同为 `image/jpeg` |
| LastModified 保留 | **不保留** | 源 2026-06-30 → 副本 2026-09-14，这是要用标签的原因 |
| COLDTIER 对象读取 | rc=0 · 30 MiB/s | 转冷对象读取透明，不需要 restore；同机未转冷对象 144 MiB/s |
| 标签→转储端到端 | **60 秒内生效** | 新库实测：打标签后 storage-class 变 COLDTIER，冷盘出现 `archive/<uuid>/…`，读回 5,000,000 字节与源一致 |
| `tier info` 的 Usage | **有滞后** | 对象已转冷时该计数仍显示 `0 B / 0 objects`，不能用它判断转储是否生效 |
| 旧库冷层实际规模 | 560 GiB / 69,965 | 与按 90 天算出的集合完全吻合 |
| 按 2026-07-01 切分 | 747.5 GiB / 91,497 | 进冷盘的业务口径；其中 187.1 GiB / 21,532 个在旧库还在热盘上 |
| 切分后留在热盘 | 1297.2 GiB / 119,886 | 占 63.4% |
| materials 键冲突 | 60 / 60 | 新库已有的都在旧库存在，是部分副本，会被跳过 |
| agent-img-video 键冲突 | 0 / 60 | 前缀完全不同，可直接合并 |
| 旧机负载余量 | load 0.9 / 8 核 | 当前出带宽 0.6 MiB/s，跑迁移不影响线上 |

网页版（同样内容）：https://claude.ai/code/artifact/e6819bc3-1f49-46cf-8b48-898c8990f59a
