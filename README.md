# AI-Driven Invoice Extraction & Automated Audit System

English version first. Chinese version follows below. A dedicated Chinese deployment guide for a brand-new machine is at the end.

---

# English Version

## 1. Overview

This repository is a local, demo-ready invoice audit system for finance operations.

It supports:

- invoice image / PDF ingestion from the local `invoices/` folder
- OCR extraction through the local RapidOCR service
- Dify-based structured extraction when configured
- OCR fallback parsing when Dify is unavailable
- purchase-order matching against MySQL
- risk detection for amount mismatch, supplier mismatch, and related signals
- email alerts with work-order links
- Streamlit-based review and operations console
- Feishu Bitable sync with retry and compensation workflows

## 2. System Architecture

The project is not "just Dify". Dify is only one external AI extraction component inside the full system.

The actual runtime architecture is:

```text
+----------------------+
| Invoice Files        |
| invoices/*.jpg/pdf   |
+----------+-----------+
           |
           v
+----------------------+
| OCR Service          |
| RapidOCR / FastAPI   |
+----------+-----------+
           |
           +------------> Dify Workflow
           |              structured extraction
           |
           +------------> OCR Fallback Parser
                          line-item recovery
           |
           v
+----------------------+
| Ingestion Service    |
| risk rules + routing |
+----------+-----------+
           |
           +------------> MySQL
           |              invoices / items / events / reviews
           |
           +------------> SMTP / Mailpit
           |              risk alert email
           |
           +------------> Feishu Bitable
           |              sync + retry worker
           |
           v
+----------------------+
| Streamlit UI         |
| dashboard + review   |
+----------------------+
```

Component responsibilities:

- `Streamlit UI`: the project’s actual frontend for dashboard, review form, sync recovery, and audit visibility
- `OCR service`: local text extraction from invoice files
- `Dify`: optional external AI workflow for structured invoice parsing
- `OCR fallback parser`: local backup parser when Dify is disabled or fails
- `Ingestion service`: orchestration layer for parsing, risk checks, database writes, and notifications
- `MySQL`: persistent storage for invoices, line items, events, review tasks, and sync state
- `SMTP / Mailpit`: alert delivery layer
- `Feishu Bitable`: optional collaboration layer for cloud-side data visibility

## 3. Main Features

- OCR + Dify hybrid extraction pipeline
- enhanced OCR fallback line-item parsing
- duplicate invoice protection and concurrent re-entry protection
- risk checks for amount mismatch, supplier mismatch, and date anomalies
- local Mailpit support and real SMTP support
- Streamlit dashboard for review, audit trail, and machine output
- Feishu Bitable sync, retry, recent failed list, and auto-compensation worker
- end-to-end demo scripts and regression scripts

## 4. Quick Start

### 4.1 Fastest path on a brand-new Windows machine

1. Install `Python 3.10+`, `Git`, and `Docker Desktop`.
2. Pull this repository.
3. Double-click [init_fresh_machine.bat](./init_fresh_machine.bat).
4. After bootstrap finishes, double-click [start.cmd](./start.cmd).

This path uses safe local defaults:

- local MySQL in Docker
- local OCR service
- local Mailpit inbox
- OCR fallback if Dify is not configured
- no real SMTP or Feishu secret required

### 4.2 Instant demo data from git

The repository includes a tracked demo SQL snapshot at [demo/demo_snapshot.sql](./demo/demo_snapshot.sql).

You can import it manually with:

```powershell
.\.venv\Scripts\python.exe scripts\import_demo_sql.py
```

This gives a fresh machine a preloaded demo invoice, line items, and event history without depending on your current local database state.

## 5. Local Startup Files

- [init_fresh_machine.bat](./init_fresh_machine.bat): bootstrap a brand-new Windows machine
- [start.cmd](./start.cmd): recommended local demo entrypoint
- [start_demo.bat](./start_demo.bat): reset + OCR + UI + single-invoice live demo
- [start_local.bat](./start_local.bat): batch local startup
- [start_feishu_retry.bat](./start_feishu_retry.bat): start the Feishu retry worker only

## 6. Important Scripts

- [scripts/check_env.py](./scripts/check_env.py): validate `.env`
- [scripts/apply_schema.py](./scripts/apply_schema.py): apply MySQL schema
- [scripts/import_demo_sql.py](./scripts/import_demo_sql.py): import git-tracked demo snapshot
- [scripts/init_fresh_machine.py](./scripts/init_fresh_machine.py): bootstrap a brand-new local machine
- [scripts/run_demo_ingest.py](./scripts/run_demo_ingest.py): process one live invoice
- [scripts/demo_e2e_test.py](./scripts/demo_e2e_test.py): end-to-end self-check
- [scripts/multi_sample_regression.py](./scripts/multi_sample_regression.py): multi-invoice regression
- [scripts/deep_product_regression.py](./scripts/deep_product_regression.py): duplicate / retry / fallback regression
- [scripts/retry_feishu_sync.py](./scripts/retry_feishu_sync.py): manual Feishu compensation
- [scripts/run_feishu_retry_daemon.py](./scripts/run_feishu_retry_daemon.py): periodic Feishu retry worker

## 7. Configuration

The tracked [`.env.example`](./.env.example) is intentionally safe for git.

Default local behavior from `.env.example`:

- `SMTP_HOST=127.0.0.1` and `SMTP_PORT=1025` route email to Mailpit
- Dify is disabled until `DIFY_API_KEY` and `DIFY_WORKFLOW_ID` are filled
- Feishu is disabled until `FEISHU_*` values are filled
- the local demo still works because OCR fallback is enabled

Optional integrations:

- Dify: fill `DIFY_API_KEY`, `DIFY_WORKFLOW_ID`, and optionally adjust `DIFY_IMAGE_KEY`
- real email: replace Mailpit SMTP values with your real provider
- Feishu: fill `FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `FEISHU_APP_TOKEN`, `FEISHU_TABLE_ID`

Feishu retry worker knobs:

- `FEISHU_RETRY_WORKER_ENABLED`
- `FEISHU_RETRY_INTERVAL_SEC`
- `FEISHU_RETRY_MODE`
- `FEISHU_RETRY_BATCH_LIMIT`

If enabled, [start_demo.bat](./start_demo.bat) and [start_local.bat](./start_local.bat) auto-start the worker.

## 8. What A Fresh Machine Can Do Without Extra Secrets

After `git pull` and [init_fresh_machine.bat](./init_fresh_machine.bat), a new Windows machine can already do this:

- start MySQL and Mailpit
- open the Streamlit dashboard
- run OCR locally
- parse invoice items with OCR fallback
- ingest sample invoices
- trigger local alert emails into Mailpit
- review invoices in the UI
- import the tracked demo SQL snapshot

What still requires manual configuration:

- real SMTP delivery to external inboxes
- real Dify workflow execution
- real Feishu Bitable sync

## 9. Notes About Git

Real secrets are not committed.

That means:

- `.env` is ignored by git
- your local Dify key is not pushed
- your local SMTP password is not pushed
- your local Feishu secret is not pushed
- your current MySQL runtime data is not automatically identical on another machine

The git-tracked demo SQL snapshot is the safe replacement for “clone my local DB state”.

---

# 中文版

## 1. 项目简介

这是一个本地可演示、可试运行的发票审计系统，已经具备完整闭环：

- 发票图片 / PDF 读取
- OCR 识别
- Dify 结构化抽取
- OCR fallback 兜底解析
- MySQL 采购单匹配
- 风险校验
- 邮件预警
- Streamlit 人工复核
- 飞书多维表同步
- 飞书失败补偿与自动重试

## 2. 系统架构图说明

这个项目不是“没有前端、前端就是 Dify”。

更准确地说：

- 你自己的前端是 `Streamlit`
- `Dify` 只是可选的 AI 结构化抽取服务
- 整个系统还有 OCR、MySQL、邮件、飞书同步和补偿链路

当前运行架构如下：

```text
+----------------------+
| 发票文件目录          |
| invoices/*.jpg/pdf   |
+----------+-----------+
           |
           v
+----------------------+
| OCR 服务             |
| RapidOCR / FastAPI   |
+----------+-----------+
           |
           +------------> Dify 工作流
           |              结构化抽取
           |
           +------------> OCR fallback
                          本地兜底明细解析
           |
           v
+----------------------+
| 发票处理服务          |
| 解析 / 风控 / 路由    |
+----------+-----------+
           |
           +------------> MySQL
           |              发票 / 明细 / 事件 / 复核
           |
           +------------> SMTP / Mailpit
           |              风险预警邮件
           |
           +------------> 飞书多维表
           |              同步 / 重试 / 补偿
           |
           v
+----------------------+
| Streamlit 前端        |
| 仪表盘 / 工单 / 运维   |
+----------------------+
```

各层职责：

- `Streamlit 前端`：项目真正的前端界面，负责仪表盘、工单页、飞书补偿、审计查看
- `OCR 服务`：本地发票识别入口
- `Dify`：可选 AI 结构化抽取能力
- `OCR fallback`：Dify 失败时的本地兜底解析器
- `发票处理服务`：整条链路的业务编排中心，负责解析、风控、入库、通知
- `MySQL`：主数据存储，保存发票、明细、事件、复核任务、同步状态
- `SMTP / Mailpit`：邮件预警层
- `飞书多维表`：云端协同与展示层

## 3. 当前已经支持的功能

- 本地 OCR 服务识别发票
- Dify 文件上传与工作流调用
- Dify 异常时自动回退到 OCR fallback
- OCR fallback 已支持明细行解析
- 风险校验包括金额不一致、供应商不一致、日期异常等
- 重复发票防重、并发防重入、失败后补发
- 风险邮件预警，支持 Mailpit 和真实 SMTP
- Streamlit 仪表盘、工单页、事件日志、机器输出查看
- 飞书多维表写入、失败重试、最近失败列表、定时补偿 worker

## 4. 本地最常用的入口

- [init_fresh_machine.bat](./init_fresh_machine.bat)：新电脑初始化
- [start.cmd](./start.cmd)：推荐的一键本地 demo 入口
- [start_demo.bat](./start_demo.bat)：重置环境并跑单票 live 演示
- [start_local.bat](./start_local.bat)：完整本地批量模式
- [start_feishu_retry.bat](./start_feishu_retry.bat)：只启动飞书补偿进程

## 5. git 拉下来后默认可用的能力

如果你不填写任何真实外部密钥，只使用仓库里的默认配置，也可以直接跑本地 demo。

默认效果是：

- MySQL 用 Docker 本地起
- 邮件发到 Mailpit，不发外部邮箱
- Dify 默认为关闭
- 飞书默认为关闭
- 但 OCR fallback 会生效，所以主流程仍然能跑通

也就是说，新机器不填真实 Dify / 飞书 / 邮件账号，也能看到完整的本地演示效果。

## 6. demo SQL

仓库里已经新增了可直接导入的 demo 数据文件：

- [demo/demo_snapshot.sql](./demo/demo_snapshot.sql)

导入命令：

```powershell
.\.venv\Scripts\python.exe scripts\import_demo_sql.py
```

这份 SQL 是 git 跟踪的、安全的、本地可导入的，它的作用是：

- 给新机器快速生成可展示的 demo 发票数据
- 不依赖你当前这台电脑的数据库状态
- 不包含真实密钥

---

# 中文版：新机器部署手册

## 1. 目标

这份手册针对“全新的 Windows 电脑”，目标是做到：

- `git pull` 代码
- 一次初始化
- 直接开始本地 demo

## 2. 前置要求

新机器先安装：

1. `Git`
2. `Python 3.10+`
3. `Docker Desktop`

## 3. 部署步骤

### 第一步：拉代码

```powershell
git clone https://github.com/huajianv587/AI-Driven-Invoice-Extraction-Automated-Audit-System.git
cd AI-Driven-Invoice-Extraction-Automated-Audit-System
```

### 第二步：初始化新机器

双击：

- [init_fresh_machine.bat](./init_fresh_machine.bat)

或者命令行执行：

```powershell
python scripts\init_fresh_machine.py
```

它会自动做这些事：

1. 如果没有 `.env`，就从 [`.env.example`](./.env.example) 复制一份
2. 创建 `.venv`
3. 安装 `requirements.txt`
4. 校验 `.env`
5. 拉起 Docker Desktop
6. 启动本地 MySQL 和 Mailpit
7. 执行数据库建表脚本
8. 导入 git 跟踪的 demo SQL

### 第三步：启动本地 demo

双击：

- [start.cmd](./start.cmd)

或者直接执行：

```powershell
start.cmd
```

这会继续完成：

- 启动 OCR 服务
- 启动 Streamlit UI
- 跑一张 demo 发票
- 打开 Dashboard
- 打开 Mailpit

## 4. 新机器默认能达到什么效果

初始化完成后，不改任何真实密钥，也可以做到：

- 本地 OCR 跑通
- 发票入库
- 风险识别
- 本地邮件预警写到 Mailpit
- 仪表盘查看发票、风险、事件、明细
- 工单页提交人工复核

## 5. 如果想和你当前电脑一样接真实服务

还需要手动补 `.env` 里的真实配置：

### 真实邮件

填写：

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASS`
- `SMTP_FROM_EMAIL`
- `ALERT_FALLBACK_TO`

### Dify

填写：

- `DIFY_API_KEY`
- `DIFY_WORKFLOW_ID`

### 飞书

填写：

- `FEISHU_APP_ID`
- `FEISHU_APP_SECRET`
- `FEISHU_APP_TOKEN`
- `FEISHU_TABLE_ID`

## 6. 结论

现在这套仓库已经能做到：

- 新电脑 `git pull` 后，不需要你手工搭太多东西
- 先跑本地 demo 基本不用再配置
- 如果要“和你当前电脑完全一样”的真实外部集成效果，仍然需要补真实 `.env`

也就是说：

- 本地演示级效果：现在已经接近一拉即用
- 真实 Dify / 真实邮箱 / 真实飞书：仍然需要你填密钥
