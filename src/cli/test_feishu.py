import os
from dotenv import load_dotenv
from src.clients.feishu_bitable_client import FeishuBitableClient

def main():
    load_dotenv()

    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    app_token = os.getenv("FEISHU_APP_TOKEN")
    table_id = os.getenv("FEISHU_TABLE_ID")

    print("FEISHU_APP_TOKEN =", app_token)
    print("FEISHU_TABLE_ID  =", table_id)

    client = FeishuBitableClient(app_id, app_secret, app_token, table_id)
    token = client.get_tenant_token()
    print("tenant_token ok =", bool(token))

    fields = {
        "file_name": "test.jpg",
        "invoice_id": 999999,
        "invoice_code": "123",
        "invoice_number": "456"
    }

    ok, record_id, raw = client.add_record(token, fields)
    print("add_record ok =", ok)
    print("record_id =", record_id)
    print("raw =", raw)

if __name__ == "__main__":
    main()
