# MinIO 冷层(Cold Tier)部署

用一块独立的便宜 EBS 盘单独跑一个 MinIO 当冷层,把热层(`../minio`,端口 9000/9001)里的旧对象自动分层(transition)过来。
分层后业务照旧只连热层 9000,读写路径不变,冷数据由 MinIO 透明回取。

- 热层:`../minio`,数据盘 `/opt/pvstore/data/minio`,端口 9000/9001
- 冷层:本目录,数据盘 `/mnt/colddisk/minio`,端口 9100/9101

---

## 1. 在 AWS 新建一块冷盘并挂载

### 1.1 控制台新建 EBS 卷

EC2 → Elastic Block Store → 卷 → 创建卷:

| 字段 | 值 |
|------|-----|
| 卷类型 | `sc1`(Cold HDD,最便宜)或 `gp3` |
| 大小 | 按需,如 800 GiB(sc1 最小 125 GiB) |
| 可用区 | **必须和实例一致**(本例 `ap-southeast-1b`),否则挂不上 |

记下新卷 `vol-xxxx`。

### 1.2 附加到实例

选中卷 → 操作 → 挂载卷:
- 实例:目标 EC2 实例
- 设备名:`/dev/sdf`(仅控制台用名;Nitro 机型进系统后会显示为 `nvme1n1`)

### 1.3 在系统里格式化并挂载

```bash
lsblk        # 找新盘:无子分区、大小等于新卷的那块,通常是 nvme1n1
```

确认是 `nvme1n1` 后(⚠️ 别误格式化系统盘 nvme0n1):

```bash
sudo mkfs.ext4 /dev/nvme1n1
sudo mkdir -p /mnt/colddisk
sudo mount /dev/nvme1n1 /mnt/colddisk

# 永久挂载,重启不丢(用 UUID)
UUID=$(sudo blkid -s UUID -o value /dev/nvme1n1)
echo "UUID=$UUID /mnt/colddisk ext4 defaults,nofail 0 2" | sudo tee -a /etc/fstab
sudo mount -a        # 不报错说明 fstab 没问题

sudo mkdir -p /mnt/colddisk/minio
df -h | grep colddisk
```

---

## 2. 启动冷层容器

把本目录拷到服务器,然后:

```bash
cd minio-cold
docker compose up -d          # 本机只有坏掉的 docker-compose v1,见下方说明
docker ps | grep minio        # 应看到 minio 和 minio-cold 两个
```

> ⚠️ 本机 `docker-compose`(v1.29.2)对新版镜像在**重建容器**时会崩(`KeyError: 'ContainerConfig'`),
> 且没装 `docker compose`(v2 插件)。改 compose 后重建,用以下任一方式(数据在 bind mount 上,删容器不丢):
> ```bash
> # 方式一:先删旧容器再 up(全新创建,绕过 v1 的 bug)
> docker rm -f minio-cold && docker-compose up -d
> # 方式二:直接 docker run,完全绕开 compose
> docker rm -f minio-cold
> docker run -d --name minio-cold --restart unless-stopped \
>   -p 9100:9000 -p 9101:9001 -v /mnt/colddisk/minio:/data \
>   -e MINIO_ROOT_USER=<同热层USER> -e MINIO_ROOT_PASSWORD=<同热层PASS> \
>   minio/minio server /data --console-address ":9001"
> ```

冷层控制台:`http://<服务器IP>:9101`

> 冷层 root 账号已统一为热层那套(从 `docker exec minio env | grep MINIO_ROOT` 读取)。
> 注意:仓库里 `../minio/docker-compose.yml` 的明文口令与生产不符,真实口令以运行中容器的环境变量为准。

---

## 3. 装 mc 并配 alias

minio server 镜像不带 mc,在宿主机单独装:

```bash
curl -L https://dl.min.io/client/mc/release/linux-amd64/mc -o /usr/local/bin/mc   # 必须 -L 跟随重定向
chmod +x /usr/local/bin/mc
mc --version

# <USER>/<PASS> 用真实口令(docker exec minio env | grep MINIO_ROOT),冷热一致
mc alias set hot  http://localhost:9000 <USER> <PASS>
mc alias set cold http://localhost:9100 <USER> <PASS>
mc ls hot          # 列出热层桶
```

## 4. 扩冷盘(本部署 materials+tmp ≈ 792G,超过初始 787G 必须先扩)

控制台:EC2 → 卷 → 选冷盘 → 操作 → 修改卷 → 改大(如 1200 GiB)→ 等 completed。然后撑大文件系统:

```bash
lsblk                          # 确认 nvme1n1 已变大
sudo resize2fs /dev/nvme1n1    # ext4 在线扩容,不用卸载
df -h | grep colddisk
```

## 5. 注册 tier + 加分层规则

```bash
# 冷层建接收 bucket
mc mb cold/cold-tier

# 注册 tier —— endpoint 必须是宿主机内网 IP(热层容器去连冷层),不能写 localhost
mc ilm tier add minio hot COLDTIER \
  --endpoint http://<宿主机内网IP>:9100 \
  --access-key <USER> --secret-key <PASS> \
  --bucket cold-tier --prefix archive/

# 本部署规则:
# - materials:创建满 90 天搬冷层
# - tmp:临时桶,创建满 7 天直接删除(不搬冷层)
mc ilm rule add hot/materials --transition-days 90 --transition-tier COLDTIER
mc ilm rule add hot/tmp       --expire-days 7

mc ilm rule ls hot/materials
mc ilm rule ls hot/tmp
```

---

## 验证 / 运维

```bash
mc ilm tier info hot              # 看搬过去多少数据
mc ls   hot/materials/<对象>      # 分层后 stub 还在,名字大小不变
mc stat hot/materials/<对象>      # 看 transition 状态/所在 tier
mc cat  hot/materials/<对象>      # 仍从热层透明取回
df -h | grep colddisk             # 盯冷盘水位,接近满就再扩卷+resize2fs
```

注意:

- `--transition-days` / `--expire-days` 按**对象年龄**算,不是按最近访问时间;社区版无访问频率智能分层。
- 改 ILM 规则(add/remove/edit)**热生效,不用重启 MinIO**;过期删除会连已搬到冷层的副本一起删。
- 分层对客户端透明:**presigned 签名 URL、读取代码全不用改**,仍对热层(9000)生成/读取,GET 时自动从冷层回取;唯一区别是冷对象首次读取更慢(多一跳 + 走 sc1/HDD)。
- 冷层是**在线** tier,GET 直接透明回取,无需像 Glacier 先 restore 解冻。
- 冷层 `cold-tier` bucket 是 MinIO 内部编排数据,**不要手动翻改**;读文件始终走热层。
- materials 仍在增长,冷盘要持续盯水位、必要时继续扩卷(EBS 只能扩不能缩)。
- EBS 按配置容量计费,不按实际占用;数据搬到冷盘不会自动减少热盘账单。

---

## 6. 搬迁限速与 I/O 排查(存量首次搬迁会打满冷盘)

加完规则后,过 90 天的存量对象会被后台一次性搬到冷盘。本部署 materials 640G/7.9 万对象灌入 **sc1(Cold HDD)**,会把冷盘 I/O 打满,现象是 `top` 显示"CPU 接近 100%"。

### 判断:是 iowait 不是算力
```bash
top -bn1 | head            # 看每核 wa(iowait);若 wa 高、id≈0、us+sy 很低 → 是等磁盘,不是 CPU 忙
iostat -x 2 3              # 没装:sudo apt install -y sysstat
```
看 `iostat` 里 `nvme1n1`(冷盘):`%util≈100`、`wkB/s` 才 ~16MB/s、`w_await` 几百 ms、`aqu-sz` 几十 → 冷盘被打满,sc1 写入上限就是 ~16MB/s。`nvme0n1` 是系统/热盘。

### 调搬迁速度(scanner speed)
档位:`slowest / slow / default / fast / fastest`。它控制的是**多久扫一批去搬**(占空比),不是单批吞吐——单批峰值始终被冷盘的 16MB/s 卡住。
- slowest:批间歇很久,冷盘大多数时间近 0,最温和但搬完最慢
- default:几乎不歇,冷盘持续 100%,搬得快但一直堵、热盘读也忙(会挤占同机 Doris)
- slow:折中(本部署用这档)

```bash
mc admin config set hot scanner speed=slow      # set 完看输出:只说 Successfully 就已生效,不用重启
mc admin config get hot scanner                 # 确认当前值
# 仅当 set 输出提示需要时才重启:
# mc admin service restart hot
```

### 监控搬迁进度 / 判断搬完
```bash
mc ilm tier info hot       # 冷层已用容量在涨=还在搬;不再涨=这批搬完
iostat -x 2 3              # nvme1n1 %util 持续接近 0 = 搬迁停了
# 注意:别用 mc du hot/materials 判断剩余——对象搬走后 stub 仍按原大小报体积,du 不会减少
```

### 慢是一次性的,sc1 是对的(本部署目标=省成本)
sc1 慢只疼"首次搬 640G 存量"这一段,且只疼一次;搬完后日常只有新对象陆续满 90 天的涓流,sc1 足够。**为省成本就保留 sc1 + 调慢 scanner + 耐心等**,慢不花钱、不伤业务(业务/Doris 在另一块盘)。

不要为了快把冷盘改 gp3——gp3 比 sc1 贵约 5 倍,会把分层省下的钱贴回去,与省成本目标相悖。**唯一**值得改 gp3 的情况:冷数据需要被**频繁读取**且 ~500ms 延迟不可接受(此时它已不算"冷"数据,本就不该分层)。
