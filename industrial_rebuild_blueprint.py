# -*- coding: utf-8 -*-
"""
工业级重构蓝图

用途：
1. 作为当前项目的工业化升级蓝图
2. 便于后续继续修改、拆分、细化为实施计划
3. 可直接运行，终端中打印蓝图内容
"""

from __future__ import annotations

from typing import Any, Dict, List


BLUEPRINT: Dict[str, Any] = {
    "project_name": "invoice-audit-system",
    "target": (
        "把当前以单机脚本为主的发票审计项目，升级为可部署、可扩展、可审计、可运维的企业级发票审计平台。"
    ),
    "overall_judgment": {
        "strengths": [
            "业务链路已经形成闭环，具备 OCR、结构化解析、风险规则、邮件预警、飞书同步等能力。",
            "代码已经有服务分层雏形，具备继续工程化演进的基础。",
            "核心业务场景明确，适合逐步重构而不是推倒重来。",
        ],
        "weaknesses": [
            "当前更像可运行的原型/POC，而不是正式可交付系统。",
            "系统仍以单机脚本思维运转，本地依赖重，部署和交接成本高。",
            "工程骨架、配置治理、安全治理、测试体系和运维能力明显不足。",
        ],
        "core_conclusion": (
            "最关键的问题不是使用了本地 MySQL，而是整体仍停留在单机脚本阶段；"
            "最优路线是保留现有业务逻辑，重做工程骨架，先从脚本项目升级为服务项目，再进一步平台化。"
        ),
    },
    "current_problems": [
        {
            "title": "配置层重复且不一致",
            "details": [
                "存在多套配置入口，默认值不一致，后续维护容易出现环境漂移。",
                "建议只保留一套 Settings 模型，统一管理环境变量和默认值。",
            ],
        },
        {
            "title": "数据库访问层重复实现",
            "details": [
                "项目中同时存在不同的 MySQL 访问实现，造成维护复杂度增加。",
                "应统一为一套数据库访问层，明确连接池、事务、异常和迁移机制。",
            ],
        },
        {
            "title": "旧脚本与主流程存在接口漂移",
            "details": [
                "历史脚本和当前服务接口已经不完全一致，说明代码变更没有收敛到统一入口。",
                "这类问题在上线后容易导致批处理偶发失败和交接困难。",
            ],
        },
        {
            "title": "交付物不完整",
            "details": [
                "缺少完整 README、依赖声明、可用的部署文件、数据库迁移脚本。",
                "当前项目不具备标准化部署和团队交接条件。",
            ],
        },
        {
            "title": "安全治理存在明显风险",
            "details": [
                "示例文件和旧脚本中出现真实风格的数据库、Dify、飞书、SMTP 凭证。",
                "正式项目必须把密钥移出代码，立即轮换已暴露凭证。",
            ],
        },
        {
            "title": "外部依赖强耦合在主链路",
            "details": [
                "OCR、Dify、飞书、邮件等都在串行主流程中执行。",
                "任何一个外部系统响应慢或失败，都可能影响整条处理流水线。",
            ],
        },
        {
            "title": "文件依赖本地磁盘",
            "details": [
                "原始发票文件仍依赖本地目录存储，不利于多机部署、备份、审计和扩容。",
                "应迁移到对象存储，数据库只保留元数据和访问地址。",
            ],
        },
        {
            "title": "测试与可观测性薄弱",
            "details": [
                "缺少完整的单元测试、集成测试和端到端测试体系。",
                "日志虽然存在，但缺少结构化日志、监控指标、告警机制和链路追踪。",
            ],
        },
    ],
    "architecture_blueprint": {
        "summary": "建议升级为 API + Worker + OCR Service + MySQL + Redis + Object Storage 的服务化架构。",
        "components": [
            {
                "name": "gateway/api",
                "responsibility": [
                    "负责上传发票、查询任务、人工复核、报表查询、重试任务接口。",
                    "统一对外鉴权、限流、审计和错误处理。",
                ],
            },
            {
                "name": "worker",
                "responsibility": [
                    "异步执行 OCR、结构化解析、风险校验、飞书同步、邮件通知。",
                    "和 API 解耦，避免串行阻塞。",
                ],
            },
            {
                "name": "ocr-service",
                "responsibility": [
                    "独立部署 OCR 服务，便于模型替换和水平扩展。",
                    "保留现有 OCR 能力，但升级为可运维服务。",
                ],
            },
            {
                "name": "db",
                "responsibility": [
                    "采用托管 MySQL/RDS，保存结构化数据、任务状态、审计记录。",
                    "通过迁移工具统一管理 schema 变化。",
                ],
            },
            {
                "name": "cache/queue",
                "responsibility": [
                    "使用 Redis 作为任务队列、幂等锁、短期缓存和重试基础设施。",
                ],
            },
            {
                "name": "object-storage",
                "responsibility": [
                    "存放原始发票、OCR 文本、解析结果快照、异常附件等二进制文件。",
                ],
            },
            {
                "name": "observability",
                "responsibility": [
                    "监控任务成功率、耗时、外部依赖错误率、队列堆积、邮件与同步失败率。",
                ],
            },
        ],
    },
    "recommended_directory_structure": [
        "invoice-audit-system/",
        "├─ apps/",
        "│  ├─ api/",
        "│  │  ├─ main.py",
        "│  │  ├─ routers/",
        "│  │  ├─ schemas/",
        "│  │  └─ deps/",
        "│  ├─ worker/",
        "│  │  ├─ tasks/",
        "│  │  ├─ consumers/",
        "│  │  └─ scheduler/",
        "│  └─ admin/",
        "│     └─ dashboard/",
        "├─ src/",
        "│  ├─ domain/",
        "│  │  ├─ invoice/",
        "│  │  ├─ risk/",
        "│  │  ├─ sync/",
        "│  │  └─ notification/",
        "│  ├─ application/",
        "│  │  ├─ commands/",
        "│  │  ├─ services/",
        "│  │  └─ workflows/",
        "│  ├─ infrastructure/",
        "│  │  ├─ db/",
        "│  │  ├─ repositories/",
        "│  │  ├─ queue/",
        "│  │  ├─ storage/",
        "│  │  ├─ ocr/",
        "│  │  ├─ llm/",
        "│  │  ├─ feishu/",
        "│  │  └─ email/",
        "│  ├─ shared/",
        "│  │  ├─ config/",
        "│  │  ├─ logging/",
        "│  │  ├─ exceptions/",
        "│  │  └─ utils/",
        "│  └─ tests/",
        "│     ├─ unit/",
        "│     ├─ integration/",
        "│     └─ e2e/",
        "├─ migrations/",
        "├─ deploy/",
        "│  ├─ docker/",
        "│  ├─ compose/",
        "│  └─ k8s/",
        "├─ scripts/",
        "├─ docs/",
        "└─ pyproject.toml",
    ],
    "module_refactor_plan": [
        {
            "module": "配置层",
            "direction": [
                "合并所有配置入口。",
                "统一改成单一 Settings 模型，按环境加载。",
            ],
        },
        {
            "module": "数据层",
            "direction": [
                "淘汰多套 DB 实现，统一使用 SQLAlchemy 2.0 + Alembic。",
                "明确连接池、事务、超时、重试和异常模型。",
            ],
        },
        {
            "module": "任务流",
            "direction": [
                "把大而全的 ingestion_service 拆成多个职责单一的 service。",
                "拆分为 OCR、解析、风控、同步、通知等独立模块。",
            ],
        },
        {
            "module": "集成层",
            "direction": [
                "将飞书、Dify、OCR、邮件统一放到 infrastructure 层。",
                "为所有外部接口统一超时、重试、熔断和错误包装。",
            ],
        },
    ],
    "data_model_blueprint": {
        "invoice_files": [
            "id",
            "file_name",
            "storage_url",
            "content_hash",
            "source_type",
            "uploaded_by",
            "uploaded_at",
        ],
        "invoice_tasks": [
            "id",
            "invoice_file_id",
            "task_type",
            "status",
            "retry_count",
            "started_at",
            "finished_at",
            "error_code",
            "error_message",
        ],
        "invoices": [
            "保留现有主体字段",
            "增加 file_id",
            "增加 processing_status",
            "增加 review_status",
            "增加 confidence_score",
            "增加 version",
        ],
        "invoice_items": [
            "保留发票明细",
            "建议增加 line_no",
        ],
        "invoice_events": [
            "保留事件审计",
            "每次状态流转都记录一条事件",
        ],
        "risk_results": [
            "invoice_id",
            "risk_level",
            "risk_flag",
            "risk_reason",
            "rule_version",
            "evaluated_at",
        ],
        "external_sync_records": [
            "统一记录飞书、ERP、邮件等外部同步结果",
            "不建议只针对单一外部系统单独建同步表",
        ],
        "manual_reviews": [
            "invoice_id",
            "reviewer",
            "review_result",
            "review_comment",
            "reviewed_at",
        ],
    },
    "standard_workflow": [
        "上传文件",
        "文件入对象存储",
        "创建任务",
        "OCR 识别",
        "LLM 结构化解析",
        "风险规则计算",
        "发票入库",
        "外部系统同步",
        "预警通知",
        "人工复核",
        "完成/归档",
    ],
    "status_machine": [
        "PENDING",
        "UPLOADED",
        "OCR_DONE",
        "PARSE_DONE",
        "RISK_DONE",
        "PERSISTED",
        "SYNCED",
        "NOTIFIED",
        "REVIEW_REQUIRED",
        "DONE",
        "FAILED",
    ],
    "technology_stack": {
        "api": "FastAPI",
        "orm": "SQLAlchemy 2.0",
        "migration": "Alembic",
        "queue": "Celery + Redis",
        "config": "pydantic-settings",
        "validation": "Pydantic",
        "database": "MySQL 8.x 托管版",
        "storage": "MinIO / OSS / S3",
        "logging": "structlog 或 logging + JSON formatter",
        "monitoring": "Prometheus + Grafana",
        "testing": "pytest",
        "quality": "ruff + black + mypy",
    },
    "deployment_blueprint": {
        "minimum_production_topology": [
            "Nginx / API Gateway",
            "FastAPI API",
            "Celery Worker",
            "OCR Service",
            "Redis",
            "MySQL RDS",
            "MinIO / OSS / S3",
        ],
        "environments": ["dev", "test", "staging", "prod"],
        "required_deliverables": [
            "Dockerfile",
            "真正可用的 docker-compose.yml",
            "不含真实密钥的 .env.example",
            "数据库迁移脚本",
            "部署手册",
            "回滚手册",
        ],
    },
    "security_blueprint": [
        "立即轮换项目中已出现或疑似泄露的数据库密码、SMTP 授权码、Dify key、飞书凭证。",
        "禁止在代码、示例文件和旧脚本中硬编码任何密码、token、授权码。",
        "数据库账号改为最小权限业务账号，不再使用 root。",
        "上传入口增加文件类型校验、大小限制和安全扫描预留。",
        "敏感日志脱敏，避免输出邮箱、税号、token、金额细节等敏感信息。",
        "审计日志单独保留，满足问题追踪和合规要求。",
    ],
    "testing_blueprint": {
        "unit_tests": [
            "金额勾稽",
            "去重哈希",
            "风险规则",
            "OCR fallback 解析",
            "配置加载",
        ],
        "integration_tests": [
            "DB repository",
            "OCR client",
            "Dify client",
            "Feishu client",
            "Email client",
        ],
        "e2e_tests": [
            "上传单张发票直至最终入库",
            "异常任务重试",
            "飞书同步失败补偿",
            "邮件通知失败回退",
        ],
    },
    "phased_roadmap": [
        {
            "phase": "Phase 1：地基收敛",
            "duration": "1周",
            "goals": [
                "合并配置层",
                "合并 DB 层",
                "清理硬编码密钥",
                "补 README、依赖、启动方式",
                "修复旧脚本和主流程接口漂移",
            ],
        },
        {
            "phase": "Phase 2：生产化",
            "duration": "1到2周",
            "goals": [
                "接入托管 MySQL",
                "接入对象存储",
                "引入 Alembic",
                "把主流程抽成标准 service",
                "增加结构化日志和错误码",
            ],
        },
        {
            "phase": "Phase 3：异步化",
            "duration": "1到2周",
            "goals": [
                "引入 Redis + Worker",
                "将 OCR、Dify、飞书、邮件改成异步执行",
                "增加任务表、重试表、失败补偿机制",
            ],
        },
        {
            "phase": "Phase 4：治理化",
            "duration": "1到2周",
            "goals": [
                "建设管理后台",
                "建设人工复核流",
                "建设监控告警",
                "建设报表与运营视图",
                "建设权限与审计体系",
            ],
        },
    ],
    "priority": {
        "P0": [
            "配置统一",
            "DB 层统一",
            "密钥清理轮换",
            "数据库迁移补齐",
            "文档和部署文件补齐",
        ],
        "P1": [
            "托管 MySQL",
            "对象存储",
            "异步任务",
            "状态机",
            "测试框架",
        ],
        "P2": [
            "后台管理",
            "人工复核",
            "规则引擎配置化",
            "BI 报表",
            "多租户和权限体系",
        ],
    },
    "final_recommendation": (
        "最合适的路线不是推倒重来，而是保留现有业务逻辑，重做工程骨架；"
        "保留发票入库、风险规则、邮件预警、飞书同步等业务能力，"
        "重点重构配置、数据访问、任务调度、文件存储、部署方式和安全体系。"
    ),
}


def _render_list(items: List[Any], indent: int = 0) -> List[str]:
    lines: List[str] = []
    prefix = " " * indent
    for item in items:
        if isinstance(item, dict):
            lines.extend(_render_dict(item, indent=indent))
        else:
            lines.append(f"{prefix}- {item}")
    return lines


def _render_dict(data: Dict[str, Any], indent: int = 0) -> List[str]:
    lines: List[str] = []
    prefix = " " * indent
    for key, value in data.items():
        title = str(key)
        if isinstance(value, dict):
            lines.append(f"{prefix}{title}:")
            lines.extend(_render_dict(value, indent=indent + 2))
        elif isinstance(value, list):
            lines.append(f"{prefix}{title}:")
            lines.extend(_render_list(value, indent=indent + 2))
        else:
            lines.append(f"{prefix}{title}: {value}")
    return lines


def render_blueprint() -> str:
    lines = [
        "工业级重构蓝图",
        "=" * 40,
    ]
    lines.extend(_render_dict(BLUEPRINT, indent=0))
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_blueprint())
