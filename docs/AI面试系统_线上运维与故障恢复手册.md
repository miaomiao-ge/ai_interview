# AI 面试系统：线上运维与故障恢复手册

> 最后核对时间：2026-09-01 15:14（Asia/Shanghai）  
> 适用服务器：`8.137.78.198`  
> 本文不保存密码和 API 密钥。连接凭据见本机私密文件：  
> `E:\pythonweb\服务器私密资料\AI面试系统_服务器连接凭据_PRIVATE.md`

## 0. 当前必须优先处理的风险

| 级别 | 当前情况 | 影响 | 建议 |
|---|---|---|---|
| P0 | `cryptollm.net` 对外 TLS 证书已于 2026-08-25 过期 | 普通浏览器和 API 客户端会拒绝连接 | 立即在宝塔中续签/替换 `8.137.78.198` 站点证书，测试配置后重载宝塔 Nginx |
| P1 | 每天 05:00 的学生同步从 2026-08-21 起连续以失败状态结束 | 大部分学生能更新，但始终有 1 条失败 | 查看 `/var/log/ai_interview_student_sync.log`；当前见过 MySQL `1205 Lock wait timeout`，还需定位失败记录 |
| P1 | 根分区使用率 90%，仅余约 5.7 GB | 数据库、日志、上传和归档可能因磁盘写满而失败 | 优先检查 `/var/lib/docker`（约 27 GB），确认其他业务依赖后再清理 |
| P1 | 6 个 API 都在运行，但公网 `/interview/` 只转发到 `127.0.0.1:9001` | 9001 是单点；9002–9006 没承担公网请求 | 后续将宝塔活动配置改成 upstream 负载均衡 |
| P1 | API 与面试 Worker 没有 systemd 自启动服务 | 服务器重启后不会自动恢复面试系统 | 建立 systemd 单元；完成前按本文“重启后恢复”手动启动 |
| P2 | `/opt/ai_interview/.env` 权限为 `0644` | 服务器其他本地用户理论上可读取密钥 | 确认不影响运行后执行 `chmod 600 /opt/ai_interview/.env` |
| P2 | 线上 Git 工作树有未提交的 ASR 修复 | 错误 reset/pull 会丢失线上修复 | 拉取、切分支或覆盖文件前先审查并保存这些改动 |

## 1. 服务器和项目总览

| 项目 | 当前值 |
|---|---|
| 云服务器 | 阿里云 ECS，KVM |
| 公网 IP | `8.137.78.198` |
| SSH | `root@8.137.78.198:22` |
| 操作系统 | Ubuntu 22.04.5 LTS，x86-64 |
| 主域名 | `cryptollm.net`、`www.cryptollm.net` |
| 学生端入口 | `https://cryptollm.net/interview/` |
| 项目目录 | `/opt/ai_interview` |
| Python | `/opt/ai_interview/.venv/bin/python`，Python 3.10.12 |
| Git | `main`，远端 `https://github.com/miaomiao-ge/ai_interview.git` |
| 数据库 | MySQL 8.0.46，`127.0.0.1:3306`，库 `interview_db`，用户 `ai_interview` |
| Redis | Redis 6.0.16，`127.0.0.1:6379`，默认 DB 0 |
| 时区 | Asia/Shanghai / CST |

这是共享服务器，还运行 CryptoAgent（8001）、Open WebUI（Docker，公网 8082）、宝塔面板（8888）、ZeroTier、FRP、JetBrains Remote Development 等。处理面试系统故障时，不要停止这些无关服务，也不要直接执行全局 Docker 清理。

## 2. SSH 连接

### Windows PowerShell（推荐密钥）

```powershell
ssh -i "E:\pythonweb\.ssh\ai_interview_server" root@8.137.78.198
```

密码连接：

```powershell
ssh root@8.137.78.198
```

随后在密码提示处输入私密凭据文件中的 root 密码。不要把密码写在命令行里。

### MobaXterm

- Remote host：`8.137.78.198`
- Specify username：`root`
- Port：`22`
- 推荐：Advanced SSH settings → Use private key → `E:\pythonweb\.ssh\ai_interview_server`
- 也可不选择密钥，连接后由 MobaXterm 弹窗询问 root 密码

### Codex/ChatGPT SSH 设置

- 显示名称：`AI面试系统`
- 主机名：`root@8.137.78.198`
- SSH 端口：`22`
- 身份验证：选择“身份文件”
- 身份文件：`E:\pythonweb\.ssh\ai_interview_server`

“无身份验证”不会保存或询问密码，它要求 SSH Agent/默认密钥已经可免密登录；本服务器应直接选择身份文件。

## 3. 请求链路和端口

```text
学生浏览器
    ↓ HTTPS 443
宝塔 Nginx 1.26.3
    ↓ 当前只转发到 127.0.0.1:9001
FastAPI / Uvicorn
    ├─ MySQL 127.0.0.1:3306：账号、逐字稿、成绩、任务记录
    ├─ Redis 127.0.0.1:6379：面试会话、并发控制、后台队列
    ├─ 阿里云 ASR/TTS：语音识别与面试官语音
    └─ 阿里云 OSS：录像、照片等对象文件

后台 interview_worker（4 个 worker）
    ↓ 消费 Redis 队列
归档录像 + 生成评价 + 写入 MySQL
```

面试系统监听 `9001`–`9006`。六个实例当前都健康，但活动宝塔 Nginx 只代理 9001。不要把 `/etc/nginx/conf.d/ai_interview_upstream.conf` 当成已生效的公网配置；真正活动的配置在宝塔目录。

## 4. 进程与中间件

| 组件 | 当前运行方式 | 关键位置 |
|---|---|---|
| FastAPI | 6 个独立 Uvicorn，端口 9001–9006 | `/opt/ai_interview/.runtime/multi_instance/pids.json` |
| 后台 Worker | `python -m core.interview_worker --workers 4` | `/opt/ai_interview/.runtime/worker.pid` |
| MySQL | `mysql.service` | 数据库 `interview_db`，数据目录 `/var/lib/mysql` |
| Redis | `redis-server.service` | `127.0.0.1:6379` |
| Nginx | 宝塔 Nginx，不是 Ubuntu systemd Nginx | `/www/server/nginx/sbin/nginx` |
| 学生同步 | systemd timer，每天 05:00 | `ai-interview-student-sync.timer` |
| 证书续签 | 宝塔 root cron 每天 02:11；另有 certbot timer | 当前 cryptollm 证书仍已过期 |

应用默认值（`.env` 未覆盖时）：

- Redis URL：`redis://localhost:6379/0`
- Redis key 前缀：`ai_interview`
- 后台队列：`interview_jobs`
- 录像策略：`av_only`
- 最大活跃面试：300
- 最大实时 ASR 连接：300
- Worker 实际启动并发：4
- 当前人脸核验：`FACE_VERIFY_ENABLED=true`

生产密钥位于 `/opt/ai_interview/.env`，包括 MySQL、JWT、阿里云、DashScope、OSS、SMTP、西电数据接口和外部成绩接口密钥。排障时只确认变量存在，不要把 `.env` 全文粘贴到聊天、工单或日志。

## 5. 30 秒健康检查

```bash
cd /opt/ai_interview

curl -sS http://127.0.0.1:9001/health
curl -sS http://127.0.0.1:9001/ready
curl -sS -o /dev/null -w '%{http_code}\n' https://cryptollm.net/interview/health

cat .runtime/multi_instance/pids.json
cat .runtime/worker.pid
ps -ef | grep -E 'uvicorn main:app|core.interview_worker' | grep -v grep
ss -lntp | grep -E ':900[1-6]|:3306|:6379|:443'

redis-cli ping
systemctl is-active mysql redis-server ai-interview-student-sync.timer
df -h /
free -h
```

正常结果：内网 `/health`、`/ready` 返回 200；Redis 返回 `PONG`；MySQL、Redis、同步 timer 为 active；有 6 个 Uvicorn 和 1 个 interview_worker 主进程。

证书过期时，公网 `curl` 会报错。临时诊断可用 `curl -k` 判断后端是否仍工作，但 `-k` 不是修复办法。

## 6. 日志位置

| 内容 | 路径/命令 |
|---|---|
| API 9001 输出 | `/opt/ai_interview/.runtime/multi_instance/api-9001.out.log` |
| API 9001 错误 | `/opt/ai_interview/.runtime/multi_instance/api-9001.err.log` |
| 其他 API | 将 9001 替换成 9002–9006 |
| 后台 Worker | `/opt/ai_interview/.runtime/worker.out.log`、`worker.err.log` |
| 活动 Nginx 访问日志 | `/var/log/nginx/access.log` |
| 活动 Nginx 错误日志 | `/var/log/nginx/error.log` |
| 学生同步 | `/var/log/ai_interview_student_sync.log` |
| MySQL | `journalctl -u mysql`、`/var/log/mysql/` |
| Redis | `journalctl -u redis-server`、`/var/log/redis/` |

```bash
tail -n 200 /opt/ai_interview/.runtime/multi_instance/api-9001.out.log
tail -n 200 /opt/ai_interview/.runtime/multi_instance/api-9001.err.log
tail -f /var/log/nginx/error.log
journalctl -u mysql -n 100 --no-pager
journalctl -u redis-server -n 100 --no-pager
journalctl -u ai-interview-student-sync.service -n 100 --no-pager
```

## 7. 安全启动、停止和重启

### API：完整停止和启动

先确认没有正在面试的学生：

```bash
cd /opt/ai_interview
PYTHONPATH=. ./.venv/bin/python -c "from core.concurrency_guard import get_capacity_snapshot; print(get_capacity_snapshot())"
```

只有 `active_interviews` 和 `active_asr_connections` 都为 0 时才执行：

```bash
cd /opt/ai_interview
./.venv/bin/python tools/stop_multi_instance.py
sleep 3
./.venv/bin/python tools/start_multi_instance.py \
  --python /opt/ai_interview/.venv/bin/python \
  --ports 9001,9002,9003,9004,9005,9006

for p in 9001 9002 9003 9004 9005 9006; do
  printf "$p "
  curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:$p/ready
done
```

当前公网只使用 9001，所以重启 9001 会影响所有在线学生。

### 后台 Worker

先判断 PID 是否真实存在：

```bash
cd /opt/ai_interview
pid=$(cat .runtime/worker.pid 2>/dev/null || true)
ps -p "$pid" -o pid,etime,args
```

正常停止：

```bash
kill -TERM "$(cat /opt/ai_interview/.runtime/worker.pid)"
```

确认退出后再启动：

```bash
cd /opt/ai_interview
rm -f .runtime/worker.pid
./.venv/bin/python tools/deploy.py start-worker \
  --python /opt/ai_interview/.venv/bin/python \
  --worker-concurrency 4 \
  --worker-node-id worker-001
```

不要在旧 Worker 尚未退出时删除 PID 文件并再启动，否则可能重复消费任务。

### 宝塔 Nginx

`systemctl status nginx` 当前显示 failed，但活动网站由宝塔 Nginx 提供，不能据此判断网站宕机。

```bash
/etc/init.d/nginx status
/www/server/nginx/sbin/nginx -t -c /www/server/nginx/conf/nginx.conf
```

只有配置测试成功后才重载：

```bash
/etc/init.d/nginx reload
```

活动站点配置：

```text
/www/server/panel/vhost/nginx/html_8.137.78.198.conf
```

修改前备份：

```bash
cp -a /www/server/panel/vhost/nginx/html_8.137.78.198.conf \
  /www/server/panel/vhost/nginx/html_8.137.78.198.conf.backup-$(date +%F-%H%M%S)
```

不要只修改 `/etc/nginx/sites-enabled/` 或 `/etc/nginx/conf.d/` 后就认为公网已经生效。

### MySQL 和 Redis

```bash
systemctl status mysql redis-server --no-pager
redis-cli ping
systemctl restart mysql
systemctl restart redis-server
```

最后两条只在确认服务故障后使用。Redis 保存面试会话、并发占用和后台队列；不要在有活跃面试时重启。

## 8. 服务器重启后的恢复顺序

1. 检查 MySQL、Redis：`systemctl is-active mysql redis-server`。
2. 检查宝塔 Nginx：`/etc/init.d/nginx status`。
3. 确认 `/opt/ai_interview/.env` 和 `.venv` 存在。
4. 仅在进程确实不存在时清除陈旧 PID 文件。
5. 按上一节启动 9001–9006 API。
6. 启动 `interview_worker --workers 4`。
7. 检查 6 个 `/ready`、公网 `/interview/health`、Redis 和 MySQL。
8. 检查后台队列是否积压。

队列快照：

```bash
cd /opt/ai_interview
PYTHONPATH=. ./.venv/bin/python -c \
  "from core.interview_job_service import get_worker_queue_snapshot; print(get_worker_queue_snapshot())"
```

## 9. 常见故障处理

### 9.1 SSH 连接失败

```powershell
Test-NetConnection 8.137.78.198 -Port 22
ssh -vvv -i "E:\pythonweb\.ssh\ai_interview_server" root@8.137.78.198
```

- 端口不通：检查阿里云安全组、UFW、服务器是否开机；
- `Permission denied`：用户名应为 root，检查密钥路径或使用密码登录；
- 主机指纹冲突：先确认服务器是否重装/更换，不要盲目删除 `known_hosts`。

### 9.2 网站证书错误

```bash
echo | openssl s_client -connect cryptollm.net:443 -servername cryptollm.net 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

当前活动证书：

```text
/www/server/panel/vhost/cert/8.137.78.198/fullchain.pem
/www/server/panel/vhost/cert/8.137.78.198/privkey.pem
```

在宝塔中为 `cryptollm.net` 站点续签/部署证书，随后做 Nginx 配置测试和 reload。证书私钥不能发到聊天或 Git。

### 9.3 网站出现 502/504

```bash
curl -sS http://127.0.0.1:9001/ready
ss -lntp | grep ':9001'
tail -n 200 /var/log/nginx/error.log
tail -n 200 /opt/ai_interview/.runtime/multi_instance/api-9001.err.log
```

- 9001 不健康：无活跃面试时重启 API；
- 9001 健康但公网失败：检查宝塔 Nginx、证书和防火墙；
- 9002–9006 健康不能掩盖 9001 故障，因为公网只走 9001。

### 9.4 接口 404/403 或 WebSocket 失败

正确 ASR WebSocket 路径：

```text
wss://cryptollm.net/interview/api/user/ws/asr
```

检查页面实际加载的脚本和 Nginx `sub_filter`，不能重复拼成：

```text
/interview/interview/api/user/ws/asr
```

活动 `sub_filter` 位于 `/www/server/panel/vhost/nginx/html_8.137.78.198.conf`。

### 9.5 录像有声音，但逐字稿“未作答”

录像归档和 ASR 是独立链路：有音轨只证明录制成功，不证明实时识别成功。

```bash
grep -R "\[ASR\]" /opt/ai_interview/.runtime/multi_instance/api-900*.out.log | tail -200
grep -R "ws_connect\|file_result\|chosen\|No Answer" /opt/ai_interview/.runtime/multi_instance/api-900*.out.log | tail -200
```

重点确认 WebSocket 不是 403、收到音频 chunks/bytes、`recognized_text` 非空。当前代码的 ASR 空结果应要求学生重新回答，不应写入 `No Answer`。

### 9.6 成绩/归档一直处理中

```bash
ps -ef | grep core.interview_worker | grep -v grep
cd /opt/ai_interview
PYTHONPATH=. ./.venv/bin/python -c \
  "from core.interview_job_service import get_worker_queue_snapshot; print(get_worker_queue_snapshot())"
tail -n 200 .runtime/worker.err.log
redis-cli LLEN ai_interview:queue:interview_jobs
```

Worker 不存在时按本文启动；队列不断增长时检查 OSS、数据库、LLM 和 Worker 错误。不要直接删除 Redis 队列。

### 9.7 每天 05:00 学生同步失败

```bash
systemctl status ai-interview-student-sync.service --no-pager -l
journalctl -u ai-interview-student-sync.service -n 100 --no-pager
tail -n 200 /var/log/ai_interview_student_sync.log
systemctl list-timers ai-interview-student-sync.timer --all
```

包装脚本 `/usr/local/sbin/ai-interview-student-sync` 执行：

```bash
cd /opt/ai_interview
./.venv/bin/python sync_xidian_students.py --year "$(date +%Y)"
```

当前每次约接收 981 条，约 980 条更新成功、1 条失败，因此 systemd 显示 failed。修复前先定位失败记录；不要因为多数成功而忽略非零退出码。

### 9.8 磁盘空间不足

```bash
df -h /
du -xhd1 /var/lib /root /opt /www 2>/dev/null | sort -h
docker system df
```

当前 `/var/lib/docker` 约 27 GB，其中 overlay2 约 15 GB、volumes 约 12 GB。服务器还承载其他业务，禁止未经确认执行：

```bash
docker system prune -a --volumes
rm -rf /var/lib/docker/*
```

先确认容器、镜像、卷的业务归属，再单项清理；删除数据库和录像前必须备份。

## 10. 代码发布注意事项

当前线上工作树包含尚未提交的 ASR 修复：

```text
M  frontend/user/index.html
M  frontend/user/js/interview_media.js
M  frontend/user/js/main.js
M  routers/user_api.py
?? tests/interview_media_asr.test.mjs
?? tests/test_asr_empty_guard.py
```

发布前：

```bash
cd /opt/ai_interview
git status --short --branch
git diff --check
git diff
```

禁止直接执行 `git reset --hard`、`git clean -fd` 或覆盖整个项目。先保存/提交线上改动，再拉取。更新依赖、迁移数据库和重启前应有数据库备份和回滚点。

## 11. 备份与恢复

本次盘点没有发现明确的 `interview_db` 定期 SQL 备份。应建立：

- 每日 MySQL 逻辑备份；
- `/opt/ai_interview/.env` 加密备份；
- 宝塔活动 Nginx 配置和证书备份；
- Git 保存代码，但绝不提交 `.env`、私钥或密码；
- 定期验证备份可以恢复。

MySQL 备份不要把密码写在命令行。可使用仅 root 可读的 client 配置文件：

```bash
mkdir -p /root/backups/ai_interview
mysqldump --defaults-extra-file=/root/.my.cnf \
  --single-transaction --routines --triggers interview_db \
  | gzip > /root/backups/ai_interview/interview_db-$(date +%F-%H%M%S).sql.gz
```

恢复是高风险写操作，应先在新库验证备份，再安排停机窗口。

## 12. 禁操作清单

- 不把 root 密码、SSH 私钥、`.env`、JWT、阿里云/西电密钥发到聊天或 Git。
- 不执行 `git reset --hard`、`git clean -fd`，除非已经确认并备份线上改动。
- 不在活跃面试时重启 Redis、MySQL、9001 或 Worker。
- 不用 `systemctl restart nginx` 管理当前宝塔 Nginx。
- 不盲目执行 Docker 全局 prune；这台服务器承载其他业务。
- 不删除 MySQL、OSS 录像和 Redis 队列来“腾空间”，除非有备份和数据保留策略。
- 不把六个 API 都健康误认为公网有负载均衡；当前公网只走 9001。

## 13. 每月维护检查表

- [ ] `df -h /` 低于 80%
- [ ] 域名证书剩余有效期大于 30 天
- [ ] 6 个 API `/ready` 均为 200
- [ ] Worker 存活，队列无持续积压
- [ ] MySQL、Redis 健康，数据库备份可恢复
- [ ] 05:00 学生同步最近 7 天均成功
- [ ] Nginx 活动配置与备份一致
- [ ] Git 工作树变更已解释、测试并保存
- [ ] `.env` 与 SSH 私钥权限严格
- [ ] 抽测一次学生登录、ASR、逐字稿、录像和评分流程

