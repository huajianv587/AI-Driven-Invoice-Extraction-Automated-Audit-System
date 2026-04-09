from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.services.feishu_bitable_client import FeishuBitableClient


def main():
    load_env()
    cfg = load_flat_config()

    client = FeishuBitableClient(
        app_id=cfg["feishu_app_id"],
        app_secret=cfg["feishu_app_secret"],
        app_token=cfg["bitable_app_token"],
        table_id=cfg["bitable_table_id"],
    )

    token = client.get_tenant_token()
    if not token:
        raise RuntimeError("Failed to get tenant token (check FEISHU_APP_ID/SECRET)")

    fields = {
        "file_name": "test_from_python",
        "invoice_number": "00000001",
        "total_amount_with_tax": 123.45,
    }

    ok, resp = client.add_record(token, fields)
    print("ok=", ok)
    print(resp)


if __name__ == "__main__":
    main()
