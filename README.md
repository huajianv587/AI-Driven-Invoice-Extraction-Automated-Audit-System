# AI-Driven Invoice Extraction & Automated Audit System

English version first. Chinese version follows below.

---

# English

## 1. Overview

This project is a local, demo-ready invoice audit platform for finance operations. It ingests invoice images, extracts text with OCR, optionally parses structured fields with Dify, compares invoice data against purchase-order records in MySQL, triggers anomaly alerts by email, and provides a Streamlit review console where a reviewer can submit a work order and write the result back to the database.

The current repository is optimized for a Windows local environment and supports one-click startup for demo recording and delivery handoff.

## 2. What The System Can Do

- Read invoice images from the local `invoices/` folder.
- Run OCR through the local RapidOCR-based service.
- Use a Dify workflow for structured extraction when configured.
- Fall back to OCR-based parsing when Dify is unavailable.
- Match invoices to purchase orders in MySQL.
- Detect finance risks such as amount mismatch and supplier mismatch.
- Send risk alert emails with a work-order link.
- Persist invoice headers, items, review tasks, and audit events in MySQL.
- Capture local emails with Mailpit.
- Optionally sync structured results to Feishu Bitable.
- Provide a premium Streamlit dashboard and review workspace.

## 3. End-to-End Workflow

1. An invoice image is loaded from `invoices/`.
2. The OCR service extracts raw text.
3. The system tries Dify for structured JSON extraction.
4. If Dify is not configured or fails, OCR fallback parsing is used.
5. The system resolves the purchase-order number and looks up `purchase_orders`.
6. Risk rules compare invoice totals and metadata against purchase-order data.
7. The invoice, items, and risk result are inserted into MySQL.
8. If `risk_flag = 1`, the system sends an alert email.
9. The email contains a work-order link to the Streamlit anomaly form.
10. A reviewer submits the handling result.
11. The review result is written back to `invoices`, `invoice_review_tasks`, and `invoice_events`.

## 4. Key Features

- OCR-first pipeline with optional LLM extraction.
- Docker-based local MySQL and Mailpit setup.
- Idempotent schema bootstrap and demo reset scripts.
- Risk email alerts with work-order deep links.
- Full audit trail for ingestion, alerting, and manual review.
- One-click startup through `start.cmd`.
- Demo mode that always leaves the system in a recording-ready state.

## 5. Technology Stack

- Python 3.x
- FastAPI / Uvicorn
- RapidOCR
- Streamlit
- PyMySQL
- MySQL 8.4
- Docker Compose
- Mailpit
- Optional Dify integration
- Optional Feishu Bitable integration

## 6. Project Structure Map

The following tree shows the most important folders and files, with short annotations so the repository is easy to understand at a glance.

```text
.
|-- .env.example                         # Safe local configuration template
|-- .gitignore                           # Ignore local secrets, caches, and virtual env files
|-- README.md                            # Project documentation in English and Chinese
|-- docker-compose.yml                   # Starts MySQL and Mailpit locally
|-- ocr_server.py                        # Local OCR HTTP service
|-- requirements.txt                     # Python runtime dependencies
|-- start.cmd                            # Recommended double-click demo startup entrypoint
|-- start_demo.bat                       # Clean demo startup + reset + single invoice ingest
|-- start_local.bat                      # Full local startup + batch ingestion
|-- start_mysql.bat                      # MySQL-only startup helper
|-- start_ocr.bat                        # OCR-only startup helper
|-- start_ui.bat                         # Streamlit-only startup helper
|-- auto.py                              # Compatibility wrapper / lightweight helper entry
|-- industrial_rebuild_blueprint.py      # Local blueprint / design notes script
|
|-- invoices/                            # Sample invoices used for local testing and demo
|   |-- invoice.jpg                      # Primary demo invoice that triggers risk alert
|   |-- in2.jpg                          # Additional sample invoice
|   |-- 发票3.jpg                         # Extra sample invoice
|   `-- 发票4.jpg                         # Extra sample invoice
|
|-- scripts/                             # Operational scripts and validation helpers
|   |-- apply_schema.py                  # Applies all SQL schema files in order
|   |-- demo_e2e_test.py                 # End-to-end self-check for the full closed loop
|   |-- get_ui_port.py                   # Reads UI port from config
|   |-- list_bitable_tables.py           # Feishu helper script
|   |-- reset_demo_state.py              # Clears demo data and Mailpit inbox
|   |-- run_demo_ingest.py               # Inserts one demo invoice into the pipeline
|   |-- sync_bitable_fields.py           # Feishu field sync helper
|   |-- test_feishu_write.py             # Feishu write test helper
|   |-- wait_for_docker.py               # Waits until Docker is ready
|   |-- wait_for_http.py                 # Waits until an HTTP endpoint is healthy
|   `-- wait_for_ocr.py                  # Waits until the OCR service is ready
|
|-- sql/                                 # Database schema and demo seed files
|   |-- 01_create_invoices.sql           # Invoice header table
|   |-- 02_create_invoice_items.sql      # Invoice line-item table
|   |-- 03_create_invoice_events.sql     # Audit event table
|   |-- 04_create_purchase_orders.sql    # Purchase-order reference table
|   |-- 05_create_invoice_feishu_sync.sql# Feishu sync log table
|   |-- 06_create_invoice_review_tasks.sql # Manual review task table
|   |-- 07_seed_demo_purchase_orders.sql # Demo purchase-order seed row
|   `-- 08_alter_invoices_add_purchase_order_no.sql # Purchase-order linkage patch
|
`-- src/                                 # Main application source code
    |-- config.py                        # Loads .env and exposes flat config
    |-- main.py                          # Batch invoice ingestion entrypoint
    |
    |-- db/                             # Database access layer
    |   |-- mysql_client.py             # PyMySQL wrapper and common DB helpers
    |   `-- repositories.py             # Invoice, item, and event repositories
    |
    |-- jobs/                           # Background or batch jobs
    |   |-- batch_ingest.py             # Batch ingestion job wrapper
    |   |-- feishu_sync_job.py          # Feishu sync workflow
    |   |-- daily_log_job.py            # Placeholder daily task file
    |   `-- monthly_report_job.py       # Placeholder monthly task file
    |
    |-- services/                       # Core business logic
    |   |-- ingestion_service.py        # OCR -> parse -> risk -> DB -> email orchestration
    |   |-- risk_rules.py               # Finance risk rule engine
    |   |-- risk_alert_service.py       # Alert email subject/content builder
    |   |-- email_delivery_checker.py   # SMTP client and connectivity checks
    |   |-- integration_checks.py       # OCR / Dify / Feishu / SMTP health checks
    |   |-- ocr_client.py               # OCR HTTP client helper
    |   |-- dify_client.py              # Dify HTTP client helper
    |   `-- feishu_bitable_client.py    # Feishu Bitable client helper
    |
    `-- ui/                             # Product-facing review UI
        |-- streamlit_app.py            # Premium dashboard and analyst workspace
        `-- anomaly_form.py             # Direct anomaly review page entrypoint
```

## 7. How To Read This Repository

If you are new to the project, this is the fastest reading order:

1. Start with `start.cmd` and `start_demo.bat` to understand how the local demo is launched.
2. Read `src/main.py` to see the batch processing entrypoint.
3. Read `src/services/ingestion_service.py` for the full pipeline orchestration.
4. Read `src/services/risk_rules.py` and `src/services/risk_alert_service.py` for risk detection and alerting.
5. Read `src/ui/streamlit_app.py` for the delivery-ready UI.
6. Read `sql/` to understand the database structure.

## 8. Prerequisites

- Windows environment
- Python 3.10+ recommended
- Docker Desktop
- Available local ports:
  - `3307` for MySQL
  - `8000` for OCR
  - `8517` for Streamlit UI
  - `1025` for Mailpit SMTP
  - `8025` for Mailpit web inbox

If any of these ports are occupied, update the corresponding values in `.env`.

## 9. Quick Start

### Recommended: Double-click startup

1. Copy `.env.example` to `.env` if you want to customize configuration.
2. Double-click [`start.cmd`](./start.cmd).
3. Wait for the script to:
   - create `.venv` if needed
   - install dependencies
   - start Docker services
   - apply the schema
   - reset demo data
   - start OCR
   - start Streamlit
   - ingest the demo invoice
4. The script will open:
   - Dashboard: `http://127.0.0.1:8517/?view=dashboard`
   - Mailpit: `http://127.0.0.1:8025`

### Recommended demo flow

1. Double-click `start.cmd`.
2. Open the dashboard.
3. Open Mailpit and locate the risk alert email.
4. Click the work-order link in the email.
5. Submit a review result.
6. Return to the dashboard and confirm the updated state.

## 10. Demo Mode

[`start_demo.bat`](./start_demo.bat) is the cleanest startup mode for recording a product demo.

It will:

- start MySQL and Mailpit
- apply all SQL files
- reset previous demo invoices and review tasks
- clear Mailpit inbox messages
- start OCR if it is not already running
- start the Streamlit UI if it is not already running
- ingest only `invoices/invoice.jpg`

Expected result after startup:

- exactly one demo invoice in the database
- exactly one risk alert email in Mailpit
- one work-order link pointing to the anomaly review page

## 11. Manual Startup

### 11.1 Create and populate `.env`

```powershell
copy .env.example .env
```

### 11.2 Create virtual environment and install dependencies

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 11.3 Start MySQL and Mailpit

```powershell
docker compose up -d mysql mailpit
.\.venv\Scripts\python.exe scripts\apply_schema.py
```

### 11.4 Start OCR

```powershell
.\.venv\Scripts\python.exe ocr_server.py
```

### 11.5 Start the UI

```powershell
start_ui.bat
```

### 11.6 Run ingestion

For demo data:

```powershell
.\.venv\Scripts\python.exe scripts\run_demo_ingest.py invoice.jpg
```

For batch ingestion:

```powershell
.\.venv\Scripts\python.exe -m src.main
```

## 12. Configuration

Safe local defaults are provided in [`.env.example`](./.env.example).

### 12.1 Core environment variables

| Key | Purpose | Required |
|---|---|---|
| `MYSQL_HOST` | MySQL host | Yes |
| `MYSQL_PORT` | MySQL port | Yes |
| `MYSQL_USER` | MySQL user | Yes |
| `MYSQL_PASSWORD` | MySQL password | Yes |
| `MYSQL_DB` | Database name | Yes |
| `OCR_BASE_URL` | OCR service base URL | Yes |
| `INVOICES_DIR` | Local invoice folder | Yes |
| `PO_NO` | Purchase-order number used during local demo lookup | Recommended |
| `UI_PORT` | Streamlit port | Yes |
| `ANOMALY_FORM_BASE_URL` | Work-order form base URL embedded in risk emails | Yes |

### 12.2 SMTP configuration

| Key | Purpose | Required |
|---|---|---|
| `SMTP_HOST` | SMTP server host | Yes for email alerts |
| `SMTP_PORT` | SMTP server port | Yes for email alerts |
| `SMTP_USER` | SMTP username | Optional for Mailpit, usually required for real providers |
| `SMTP_PASS` | SMTP password or app password | Optional for Mailpit, usually required for real providers |
| `SMTP_FROM_NAME` | Sender display name | Recommended |
| `SMTP_FROM_EMAIL` | Sender email address | Recommended |
| `ALERT_FALLBACK_TO` | Fallback recipient if PO-level recipient is missing | Recommended |
| `SMTP_USE_TLS` | Enable STARTTLS | Depends on provider |
| `SMTP_USE_SSL` | Enable SMTP SSL | Depends on provider |

### 12.3 Optional Dify configuration

| Key | Purpose |
|---|---|
| `DIFY_API_KEY` | Dify API key |
| `DIFY_BASE_URL` | Dify API base URL |
| `DIFY_IMAGE_KEY` | Workflow image input key |
| `DIFY_WORKFLOW_ID` | Dify workflow ID |
| `DIFY_RETRY_MAX` | Retry count |
| `DIFY_RETRY_SLEEP_SEC` | Retry backoff |

### 12.4 Optional Feishu configuration

| Key | Purpose |
|---|---|
| `FEISHU_APP_ID` | Feishu app ID |
| `FEISHU_APP_SECRET` | Feishu app secret |
| `FEISHU_APP_TOKEN` | Bitable app token |
| `FEISHU_TABLE_ID` | Bitable table ID |
| `FEISHU_SYNC_MODE` | `off`, `inline`, or `job` |

## 13. Important Note: Not Everything Comes From `.env`

System configuration comes from `.env`, but business routing data comes from the database.

The email recipient and expected purchase-order amount are read from the `purchase_orders` table, not only from `.env`.

To trigger a risk email for amount mismatch, the system needs:

- a resolved purchase-order number
- a matching row in `purchase_orders`
- an `expected_amount`
- a `purchaser_email`
- optionally a `leader_email`

## 14. Purchase Order Data Required For Alerts

The table is defined in [`sql/04_create_purchase_orders.sql`](./sql/04_create_purchase_orders.sql).

Important fields:

- `purchase_no`
- `expected_amount`
- `supplier` or `supplier_name`
- `purchaser_name`
- `purchaser_email`
- `leader_email`
- `purchase_order_date`

The local demo row is seeded by [`sql/07_seed_demo_purchase_orders.sql`](./sql/07_seed_demo_purchase_orders.sql).

## 15. How Amount-Mismatch Email Alerts Are Triggered

An email alert will be sent when all of the following are true:

1. The invoice is newly inserted.
2. The invoice can be linked to a purchase order.
3. The invoice total differs from `purchase_orders.expected_amount`.
4. Risk rules mark the invoice as risky.
5. SMTP is configured.

Recipient routing logic:

- `To`: `purchase_orders.purchaser_email`
- `Cc`: `purchase_orders.leader_email`
- Fallback: `ALERT_FALLBACK_TO`

The email includes:

- purchase order number
- invoice code and number
- actual amount
- expected amount
- amount difference
- risk reasons
- work-order link

## 16. Running With Real Email Providers

If you want to send alerts to a real mailbox instead of Mailpit, update `.env` like this:

```env
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASS=your_app_password
SMTP_FROM_NAME=Invoice Audit System
SMTP_FROM_EMAIL=your_email@example.com
ALERT_FALLBACK_TO=finance@example.com
SMTP_USE_TLS=True
SMTP_USE_SSL=False
ANOMALY_FORM_BASE_URL=http://your-host-or-ip:8517/?view=anomaly_form
```

Also make sure:

- your UI URL is reachable by the email recipient
- the relevant row exists in `purchase_orders`
- `purchaser_email` and `leader_email` are valid

## 17. UI Surfaces

### Dashboard

The Streamlit dashboard includes:

- KPI cards
- recent invoice queue
- integration health panel
- risk spotlight cards
- invoice detail workspace
- raw OCR and parsed JSON views
- audit events and review history

### Anomaly Review Form

The work-order page supports:

- viewing invoice metadata
- viewing invoice line items
- reviewing risk reasons
- selecting a decision status
- writing a handling note
- saving the review result back to MySQL

## 18. Automated Validation

Run the end-to-end self-check before demo recording:

```powershell
.\.venv\Scripts\python.exe scripts\demo_e2e_test.py
```

This validates:

- OCR ingestion
- risk detection
- email generation
- work-order link generation
- MySQL writeback
- audit event persistence

## 19. Troubleshooting

### Docker is not running

- Start Docker Desktop first.
- Then re-run `start.cmd` or `start_demo.bat`.

### UI port conflict

- Change `UI_PORT` in `.env`.
- Keep `ANOMALY_FORM_BASE_URL` consistent with the new port.

### No email alert appears

Check:

- `SMTP_HOST` is configured
- the invoice is actually risky
- `PO_NO` matches a row in `purchase_orders`
- `expected_amount` differs from the invoice amount
- `purchaser_email` exists in the purchase-order row

### Work-order link is wrong

- Update `ANOMALY_FORM_BASE_URL` in `.env`.
- Restart the app.

### Dify is not available

- The project will continue in OCR fallback mode.
- This is expected for local demo mode.

## 20. Security Notes

- Do not commit your real `.env` file.
- Rotate real SMTP, Dify, or Feishu credentials if they were ever exposed.
- Keep production mailbox credentials out of screenshots and demo videos.

---

# 中文

## 1. 项目概述

这是一个面向财务发票审核场景的本地可运行演示系统。系统可以读取发票图片，先通过 OCR 提取文本，再可选地通过 Dify 工作流做结构化字段抽取，然后将发票信息与 MySQL 中的采购单数据进行比对，识别金额异常等风险，并通过邮件发送预警；邮件中会附带工单链接，审核人员可在 Streamlit 页面中填写处理结果，系统再将结果回写数据库，形成完整闭环。

当前仓库重点面向 Windows 本地开发、产品演示录制和交付展示。

## 2. 系统能力

- 从本地 `invoices/` 目录读取发票图片
- 通过本地 OCR 服务进行文字识别
- 配置 Dify 后可进行结构化字段抽取
- Dify 不可用时自动走 OCR 正则兜底
- 根据采购单号匹配 `purchase_orders`
- 进行金额不一致、供应商不一致等风控校验
- 发送带工单链接的异常预警邮件
- 将发票主表、明细、审核任务、事件日志写入 MySQL
- 通过 Mailpit 本地查看邮件
- 可选同步到飞书多维表
- 提供带科技感的 Streamlit 审核控制台

## 3. 端到端流程

1. 把发票图片放入 `invoices/`
2. OCR 服务提取原始文本
3. 系统优先尝试调用 Dify 做结构化抽取
4. 如果 Dify 未配置或失败，则使用 OCR 兜底解析
5. 根据采购单号查询 MySQL 中的 `purchase_orders`
6. 使用风控规则对比发票与采购单
7. 将发票、明细、风控结果写入数据库
8. 若 `risk_flag = 1`，则发送预警邮件
9. 邮件正文中包含工单链接
10. 审核人员打开工单页面并提交处理结果
11. 系统将审核结果回写到 `invoices`、`invoice_review_tasks`、`invoice_events`

## 4. 项目亮点

- OCR 优先，可选 LLM 抽取
- Docker 一键拉起 MySQL 和 Mailpit
- SQL 初始化和 demo 数据重置都是幂等的
- 风控邮件里直接带工单链接
- 审核全程可追溯，有事件留痕
- 支持 `start.cmd` 双击启动
- 支持 demo 模式，一键回到可录屏状态

## 5. 技术栈

- Python 3.x
- FastAPI / Uvicorn
- RapidOCR
- Streamlit
- PyMySQL
- MySQL 8.4
- Docker Compose
- Mailpit
- 可选 Dify 集成
- 可选飞书多维表集成

## 6. 项目结构图

下面这棵树把核心目录和关键文件都标出来了，并且在右侧补了注释，方便第一次看仓库的人快速知道每一部分是做什么的。

```text
.
|-- .env.example                         # 本地安全配置模板
|-- .gitignore                           # 忽略本地密钥、缓存和虚拟环境
|-- README.md                            # 英文 + 中文项目文档
|-- docker-compose.yml                   # 本地启动 MySQL 和 Mailpit
|-- ocr_server.py                        # 本地 OCR HTTP 服务
|-- requirements.txt                     # Python 依赖列表
|-- start.cmd                            # 推荐双击启动入口
|-- start_demo.bat                       # 清空旧数据并启动 demo 闭环
|-- start_local.bat                      # 本地完整启动 + 批量处理入口
|-- start_mysql.bat                      # 仅启动 MySQL 的辅助脚本
|-- start_ocr.bat                        # 仅启动 OCR 的辅助脚本
|-- start_ui.bat                         # 仅启动 Streamlit UI
|-- auto.py                              # 兼容入口 / 简单包装脚本
|-- industrial_rebuild_blueprint.py      # 本地蓝图说明脚本
|
|-- invoices/                            # 本地测试和 demo 用发票图片
|   |-- invoice.jpg                      # 主 demo 发票，会触发风险邮件
|   |-- in2.jpg                          # 额外样例发票
|   |-- 发票3.jpg                         # 额外样例发票
|   `-- 发票4.jpg                         # 额外样例发票
|
|-- scripts/                             # 运维、自检、等待服务、demo 脚本
|   |-- apply_schema.py                  # 按顺序执行所有 SQL
|   |-- demo_e2e_test.py                 # 全闭环端到端自检
|   |-- get_ui_port.py                   # 从配置中读取 UI 端口
|   |-- list_bitable_tables.py           # 飞书多维表辅助脚本
|   |-- reset_demo_state.py              # 清空 demo 数据和 Mailpit 邮件
|   |-- run_demo_ingest.py               # 导入一张 demo 发票
|   |-- sync_bitable_fields.py           # 飞书字段同步辅助脚本
|   |-- test_feishu_write.py             # 飞书写入测试脚本
|   |-- wait_for_docker.py               # 等待 Docker 就绪
|   |-- wait_for_http.py                 # 等待 HTTP 服务健康
|   `-- wait_for_ocr.py                  # 等待 OCR 服务就绪
|
|-- sql/                                 # 数据库 schema 和 demo 种子数据
|   |-- 01_create_invoices.sql           # 发票主表
|   |-- 02_create_invoice_items.sql      # 发票明细表
|   |-- 03_create_invoice_events.sql     # 审计事件表
|   |-- 04_create_purchase_orders.sql    # 采购单参考表
|   |-- 05_create_invoice_feishu_sync.sql# 飞书同步日志表
|   |-- 06_create_invoice_review_tasks.sql # 人工审核任务表
|   |-- 07_seed_demo_purchase_orders.sql # demo 采购单种子数据
|   `-- 08_alter_invoices_add_purchase_order_no.sql # 采购单关联字段补丁
|
`-- src/                                 # 主业务源码
    |-- config.py                        # 加载 .env 并输出统一配置
    |-- main.py                          # 批量发票处理入口
    |
    |-- db/                             # 数据库访问层
    |   |-- mysql_client.py             # PyMySQL 封装
    |   `-- repositories.py             # 发票、明细、事件等仓储层
    |
    |-- jobs/                           # 批处理或同步任务
    |   |-- batch_ingest.py             # 批量导入任务包装
    |   |-- feishu_sync_job.py          # 飞书同步任务
    |   |-- daily_log_job.py            # 预留的日任务文件
    |   `-- monthly_report_job.py       # 预留的月任务文件
    |
    |-- services/                       # 核心业务逻辑层
    |   |-- ingestion_service.py        # OCR -> 解析 -> 风控 -> DB -> 邮件 主流程编排
    |   |-- risk_rules.py               # 风控规则引擎
    |   |-- risk_alert_service.py       # 风险邮件标题和正文生成
    |   |-- email_delivery_checker.py   # SMTP 发送和连通性检查
    |   |-- integration_checks.py       # OCR / Dify / 飞书 / SMTP 健康检查
    |   |-- ocr_client.py               # OCR 客户端
    |   |-- dify_client.py              # Dify 客户端
    |   `-- feishu_bitable_client.py    # 飞书多维表客户端
    |
    `-- ui/                             # 面向交付的产品 UI
        |-- streamlit_app.py            # 高级仪表盘和审核工作台
        `-- anomaly_form.py             # 直接打开工单页的入口
```

## 7. 建议阅读顺序

如果你是第一次看这个项目，建议按下面顺序理解：

1. 先看 `start.cmd` 和 `start_demo.bat`，了解本地 demo 怎么启动
2. 再看 `src/main.py`，了解批量处理入口
3. 再看 `src/services/ingestion_service.py`，理解整个主链路
4. 然后看 `src/services/risk_rules.py` 和 `src/services/risk_alert_service.py`，理解风控与邮件
5. 接着看 `src/ui/streamlit_app.py`，理解交付界面
6. 最后看 `sql/`，理解数据库结构

## 8. 环境要求

- Windows 环境
- 推荐 Python 3.10+
- Docker Desktop
- 本地可用端口：
  - `3307`：MySQL
  - `8000`：OCR
  - `8517`：Streamlit UI
  - `1025`：Mailpit SMTP
  - `8025`：Mailpit 邮件网页

如果端口冲突，请修改 `.env`。

## 9. 快速开始

### 推荐方式：双击启动

1. 如果需要自定义配置，可先复制 `.env.example` 为 `.env`
2. 双击 [`start.cmd`](./start.cmd)
3. 脚本会自动完成：
   - 创建 `.venv`
   - 安装依赖
   - 启动 Docker 服务
   - 执行数据库 schema
   - 重置 demo 数据
   - 启动 OCR
   - 启动 Streamlit
   - 导入 demo 发票
4. 启动完成后会自动打开：
   - Dashboard：`http://127.0.0.1:8517/?view=dashboard`
   - Mailpit：`http://127.0.0.1:8025`

### 推荐演示流程

1. 双击 `start.cmd`
2. 打开 Dashboard
3. 打开 Mailpit 查看风险邮件
4. 点击邮件里的工单链接
5. 填写并提交审核结果
6. 返回 Dashboard 查看状态变化

## 10. Demo 模式

[`start_demo.bat`](./start_demo.bat) 是最适合录制演示视频的启动方式。

它会自动：

- 启动 MySQL 和 Mailpit
- 执行全部 SQL
- 清空旧 demo 发票和审核记录
- 清空 Mailpit 邮件
- 启动 OCR
- 启动 Streamlit
- 只导入 `invoices/invoice.jpg`

启动完成后，系统通常会保持在以下状态：

- 数据库里只有 1 张 demo 发票
- Mailpit 里有 1 封异常预警邮件
- 邮件中带有 1 个工单跳转链接

## 11. 手动启动

### 11.1 先准备 `.env`

```powershell
copy .env.example .env
```

### 11.2 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 11.3 启动 MySQL 和 Mailpit

```powershell
docker compose up -d mysql mailpit
.\.venv\Scripts\python.exe scripts\apply_schema.py
```

### 11.4 启动 OCR

```powershell
.\.venv\Scripts\python.exe ocr_server.py
```

### 11.5 启动 UI

```powershell
start_ui.bat
```

### 11.6 执行发票处理

导入 demo 发票：

```powershell
.\.venv\Scripts\python.exe scripts\run_demo_ingest.py invoice.jpg
```

批量处理目录中的发票：

```powershell
.\.venv\Scripts\python.exe -m src.main
```

## 12. 配置说明

默认安全本地配置在 [`.env.example`](./.env.example) 中提供。

### 12.1 核心配置

| 键名 | 作用 | 是否必填 |
|---|---|---|
| `MYSQL_HOST` | MySQL 主机 | 是 |
| `MYSQL_PORT` | MySQL 端口 | 是 |
| `MYSQL_USER` | MySQL 用户名 | 是 |
| `MYSQL_PASSWORD` | MySQL 密码 | 是 |
| `MYSQL_DB` | 数据库名 | 是 |
| `OCR_BASE_URL` | OCR 服务地址 | 是 |
| `INVOICES_DIR` | 本地发票目录 | 是 |
| `PO_NO` | 本地 demo 默认使用的采购单号 | 建议填写 |
| `UI_PORT` | Streamlit 端口 | 是 |
| `ANOMALY_FORM_BASE_URL` | 风险邮件中的工单链接前缀 | 是 |

### 12.2 SMTP 邮件配置

| 键名 | 作用 | 是否必填 |
|---|---|---|
| `SMTP_HOST` | SMTP 服务器地址 | 发邮件时必填 |
| `SMTP_PORT` | SMTP 端口 | 发邮件时必填 |
| `SMTP_USER` | SMTP 用户名 | Mailpit 可不填，真实邮箱一般必填 |
| `SMTP_PASS` | SMTP 密码或授权码 | Mailpit 可不填，真实邮箱一般必填 |
| `SMTP_FROM_NAME` | 发件人显示名 | 建议填写 |
| `SMTP_FROM_EMAIL` | 发件人邮箱 | 建议填写 |
| `ALERT_FALLBACK_TO` | 兜底收件邮箱 | 建议填写 |
| `SMTP_USE_TLS` | 是否启用 STARTTLS | 视邮箱服务商而定 |
| `SMTP_USE_SSL` | 是否启用 SSL SMTP | 视邮箱服务商而定 |

### 12.3 Dify 可选配置

| 键名 | 作用 |
|---|---|
| `DIFY_API_KEY` | Dify API Key |
| `DIFY_BASE_URL` | Dify 接口地址 |
| `DIFY_IMAGE_KEY` | 工作流图片输入字段名 |
| `DIFY_WORKFLOW_ID` | Dify 工作流 ID |
| `DIFY_RETRY_MAX` | 重试次数 |
| `DIFY_RETRY_SLEEP_SEC` | 重试间隔 |

### 12.4 飞书可选配置

| 键名 | 作用 |
|---|---|
| `FEISHU_APP_ID` | 飞书应用 ID |
| `FEISHU_APP_SECRET` | 飞书应用密钥 |
| `FEISHU_APP_TOKEN` | 多维表 App Token |
| `FEISHU_TABLE_ID` | 多维表 Table ID |
| `FEISHU_SYNC_MODE` | `off`、`inline` 或 `job` |

## 13. 重要说明：不是所有数据都来自 `.env`

`.env` 管的是系统配置，不是全部业务数据。

真正决定“发给谁”“采购单金额是多少”的，是 MySQL 里的 `purchase_orders` 表。

所以如果你要触发“发票金额与录入金额不一致”的邮件预警，除了 `.env`，还必须有对应的采购单数据。

## 14. 邮件预警依赖的采购单数据

采购单表定义见 [`sql/04_create_purchase_orders.sql`](./sql/04_create_purchase_orders.sql)。

关键字段包括：

- `purchase_no`
- `expected_amount`
- `supplier` 或 `supplier_name`
- `purchaser_name`
- `purchaser_email`
- `leader_email`
- `purchase_order_date`

当前本地 demo 的采购单种子数据由 [`sql/07_seed_demo_purchase_orders.sql`](./sql/07_seed_demo_purchase_orders.sql) 提供。

## 15. “金额不一致邮件警报”是如何触发的

满足以下条件时，系统会发送风控邮件：

1. 当前发票是新插入的，不是重复发票
2. 发票能够关联到采购单
3. 发票金额和 `purchase_orders.expected_amount` 不一致
4. 风控规则将该发票判定为风险发票
5. SMTP 已配置

收件人规则：

- 主收件人：`purchase_orders.purchaser_email`
- 抄送：`purchase_orders.leader_email`
- 兜底收件人：`ALERT_FALLBACK_TO`

邮件正文中会包含：

- 采购单号
- 发票代码与号码
- 实际金额
- 录入金额
- 差额
- 风险原因
- 工单链接

## 16. 如果你要发送真实邮箱

把 `.env` 里的 SMTP 改成真实邮箱服务商配置，例如：

```env
SMTP_HOST=smtp.your-provider.com
SMTP_PORT=587
SMTP_USER=your_email@example.com
SMTP_PASS=your_app_password
SMTP_FROM_NAME=Invoice Audit System
SMTP_FROM_EMAIL=your_email@example.com
ALERT_FALLBACK_TO=finance@example.com
SMTP_USE_TLS=True
SMTP_USE_SSL=False
ANOMALY_FORM_BASE_URL=http://你的IP或域名:8517/?view=anomaly_form
```

同时要保证：

- 邮件接收方能够访问你的工单页面地址
- `purchase_orders` 表中存在对应采购单
- `purchaser_email` 和 `leader_email` 已正确填写

## 17. UI 页面说明

### Dashboard

Streamlit 仪表盘包含：

- 指标卡片
- 发票队列表
- 集成健康状态面板
- 风险优先卡片
- 发票详情工作区
- OCR / 结构化 JSON 视图
- 审核事件与人工处理历史

### 异常工单页

工单页支持：

- 查看发票基础信息
- 查看发票明细
- 查看风控原因
- 选择处理结果
- 填写处理说明
- 将结果回写 MySQL

## 18. 自动化验证

录 demo 前建议先跑一遍端到端自检：

```powershell
.\.venv\Scripts\python.exe scripts\demo_e2e_test.py
```

它会验证：

- OCR 入库
- 风险识别
- 邮件生成
- 工单链接生成
- MySQL 回写
- 事件日志留痕

## 19. 常见问题排查

### Docker 没启动

- 先打开 Docker Desktop
- 然后重新运行 `start.cmd` 或 `start_demo.bat`

### UI 端口冲突

- 修改 `.env` 中的 `UI_PORT`
- 同时更新 `ANOMALY_FORM_BASE_URL`

### 没有收到邮件预警

重点检查：

- `SMTP_HOST` 是否已配置
- 发票是否真的被识别为风险发票
- `PO_NO` 是否能匹配到 `purchase_orders`
- `expected_amount` 是否和发票金额不同
- `purchase_orders.purchaser_email` 是否存在

### 邮件里的工单链接不对

- 修改 `.env` 中的 `ANOMALY_FORM_BASE_URL`
- 重启系统

### Dify 没有配置

- 系统会自动使用 OCR 兜底
- 这对本地 demo 是正常行为

## 20. 安全说明

- 不要把真实 `.env` 提交到仓库
- 如果真实 SMTP、Dify 或飞书凭证泄露过，请立刻轮换
- 录 demo 时避免把真实账号和密码拍进视频
