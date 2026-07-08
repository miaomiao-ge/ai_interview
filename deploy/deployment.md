# AI Interview 自动化部署流程

## 1. 准备环境变量

复制 `.env.example` 为 `.env`，并填入真实配置。数据库连接必须放在 `.env`：

```env
MYSQL_URL=mysql+pymysql://ai_interview:your-password@127.0.0.1:3306/interview_db?charset=utf8mb4
```

如果需要自动建库和授权，还要配置管理员连接：

```env
MYSQL_ADMIN_URL=mysql+pymysql://root:root-password@127.0.0.1:3306/mysql?charset=utf8mb4
MYSQL_DATABASE=interview_db
MYSQL_APP_USER=ai_interview
MYSQL_APP_PASSWORD=your-password
MYSQL_APP_HOST=%
```

生产环境建议：

```env
APP_ENV=production
DB_AUTO_MIGRATE_ON_STARTUP=0
```

## 2. 一键部署

```bash
python tools/deploy.py all --year 2026 --ports 8001,8002,8003,8004
```

首次部署或依赖不完整时：

```bash
python tools/deploy.py all --install-deps --year 2026 --ports 8001,8002,8003,8004
```

流程会依次执行：

1. 可选安装 `requirements.txt`
2. 自动创建 MySQL 数据库和业务用户
3. 执行数据库迁移和结构检查
4. 导入 `questions.xlsx` 到 `question_bank`
5. 调用西电学生接口并 upsert 到 `users`
6. 启动多 API 实例
7. 启动后台 worker
8. 检查 `/ready`

## 3. 常用拆分命令

只建库授权：

```bash
python tools/deploy.py bootstrap-db
```

只迁移表结构：

```bash
python tools/deploy.py migrate
```

只导入题库：

```bash
python tools/deploy.py import-questions --questions-file questions.xlsx
```

只同步学生数据：

```bash
python tools/deploy.py sync-students --year 2026
```

如果 OSS 照片配置还没准备好：

```bash
python tools/deploy.py sync-students --year 2026 --skip-photo
```

## 4. 跳过步骤

已有数据库管理员不希望脚本建库时：

```bash
python tools/deploy.py all --skip-bootstrap
```

临时跳过外部学生接口：

```bash
python tools/deploy.py all --skip-student-sync
```

只做初始化，不启动服务：

```bash
python tools/deploy.py all --skip-api --skip-worker --skip-ready-check
```
