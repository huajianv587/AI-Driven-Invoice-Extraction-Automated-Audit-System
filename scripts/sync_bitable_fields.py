import time
from pathlib import Path
import sys
from typing import List, Tuple, Dict, Any, Optional

import requests


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Feishu Bitable field type:
# 1: text, 2: number, 5: date, 7: checkbox
MYSQL_TO_FEISHU_TYPE = {
    "varchar": 1,
    "text": 1,
    "char": 1,
    "json": 1,
    "decimal": 2,
    "float": 2,
    "double": 2,
    "int": 2,
    "bigint": 2,
    "date": 5,
    "datetime": 5,
    "timestamp": 5,
    "tinyint": 7,  # 常用于布尔
}

def get_existing_fields(app_token: str, table_id: str, tenant_token: str) -> Dict[str, Any]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    headers = {"Authorization": f"Bearer {tenant_token}"}

    existing: Dict[str, Any] = {}
    page_token = None
    printed = False

    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token

        resp = requests.get(url, headers=headers, params=params, timeout=20)
        data = resp.json()

        if not printed:
            print("[Feishu] list_fields resp (first page):", data)
            printed = True

        if data.get("code") != 0:
            raise RuntimeError(f"List fields failed: {data}")

        data_obj = data.get("data") or {}
        items = data_obj.get("items") or []   # ✅ items None -> []

        for it in items:
            existing[it.get("field_name")] = it

        has_more = data_obj.get("has_more", False)
        page_token = data_obj.get("page_token")

        if not has_more:
            break

    return existing


def create_field(app_token: str, table_id: str, tenant_token: str, field_name: str, field_type: int) -> Dict[str, Any]:
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/fields"
    headers = {"Authorization": f"Bearer {tenant_token}"}
    payload = {
        "field_name": field_name,
        "type": field_type,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=20)
    return resp.json()

def sync_fields(
    app_token: str,
    table_id: str,
    tenant_token: str,
    mysql_columns: List[Tuple[str, str]],
    *,
    sleep_sec: float = 0.15,
    dry_run: bool = False,
) -> None:
    """
    mysql_columns: [(col_name, mysql_type), ...]
    """
    existing = get_existing_fields(app_token, table_id, tenant_token)

    to_create = []
    for col_name, mysql_type in mysql_columns:
        mysql_type = mysql_type.lower().strip()

        # tinyint 有时表示数值，不一定是checkbox。这里按你的字段习惯先映射checkbox，
        # 如果你后面发现 tinyint 其实是枚举/数值，可以改成 number(type=2)。
        feishu_type = MYSQL_TO_FEISHU_TYPE.get(mysql_type, 1)

        if col_name in existing:
            continue
        to_create.append((col_name, feishu_type))

    print(f"[INFO] Existing fields: {len(existing)}")
    print(f"[INFO] Need create fields: {len(to_create)}")

    for i, (name, ftype) in enumerate(to_create, 1):
        if dry_run:
            print(f"[DRYRUN] create: {name} type={ftype}")
            continue

        res = create_field(app_token, table_id, tenant_token, name, ftype)
        if res.get("code") == 0:
            print(f"[OK] ({i}/{len(to_create)}) {name}")
        else:
            # 常见报错：字段已存在、权限不足、速率限制等
            print(f"[FAIL] ({i}/{len(to_create)}) {name} -> {res}")

        time.sleep(sleep_sec)

if __name__ == "__main__":
    from src.config import load_config
    from src.services.feishu_bitable_client import FeishuBitableClient

    cfg = load_config()

    # 1) 你的 MySQL 字段清单（保持不变）
    mysql_columns = [
        ("invoice_id", "varchar"),
        ("ingest_action", "varchar"),
        ("file_name", "varchar"),
        ("purchase_order_no", "varchar"),
        ("amount_diff", "decimal"),
        ("amount_in_words", "varchar"),
        ("buyer_address", "varchar"),
        ("buyer_bank", "varchar"),
        ("buyer_bank_account", "varchar"),
        ("buyer_name", "varchar"),
        ("buyer_phone", "varchar"),
        ("buyer_tax_id", "varchar"),
        ("check_code", "varchar"),
        ("created_at", "datetime"),
        ("drawer", "varchar"),
        ("expected_amount", "decimal"),
        ("handled_at", "datetime"),
        ("handler_reason", "text"),
        ("handler_user", "varchar"),
        ("id", "bigint"),
        ("invoice_code", "varchar"),
        ("invoice_date", "date"),
        ("invoice_number", "varchar"),
        ("invoice_status", "varchar"),
        ("invoice_type", "varchar"),
        ("is_red_invoice", "tinyint"),
        ("leader_user", "varchar"),
        ("llm_json", "json"),
        ("machine_code", "varchar"),
        ("notify_leader_msg_id", "varchar"),
        ("notify_leader_status", "varchar"),
        ("notify_personal_msg_id", "varchar"),
        ("notify_personal_status", "varchar"),
        ("payee", "varchar"),
        ("raw_ocr_json", "json"),
        ("red_invoice_ref", "varchar"),
        ("remarks", "text"),
        ("reviewer", "varchar"),
        ("risk_flag", "tinyint"),
        ("risk_reason", "json"),
        ("schema_version", "varchar"),
        ("seller_address", "varchar"),
        ("seller_bank", "varchar"),
        ("seller_bank_account", "varchar"),
        ("seller_name", "varchar"),
        ("seller_phone", "varchar"),
        ("seller_tax_id", "varchar"),
        ("source_file_path", "varchar"),
        ("total_amount_with_tax", "decimal"),
        ("total_amount_without_tax", "decimal"),
        ("total_tax_amount", "decimal"),
        ("unique_hash", "char"),
        ("updated_at", "datetime"),
    ]

    # 2) 用配置创建 Feishu client
    client = FeishuBitableClient(
        app_id=cfg.feishu.app_id,
        app_secret=cfg.feishu.app_secret,
        app_token=cfg.feishu.bitable_app_token,
        table_id=cfg.feishu.bitable_table_id,
    )

    tenant_token = client.get_tenant_token()
    if not tenant_token:
        raise RuntimeError("Failed to get tenant token. Check FEISHU_APP_ID / FEISHU_APP_SECRET in .env")

    # 3) 先 dry run（只打印，不创建）
    sync_fields(
        app_token=cfg.feishu.bitable_app_token,
        table_id=cfg.feishu.bitable_table_id,
        tenant_token=tenant_token,
        mysql_columns=mysql_columns,
        dry_run=False,
    )

    print("\n[INFO] Dry run finished. If ok, set dry_run=False to create fields.\n")

