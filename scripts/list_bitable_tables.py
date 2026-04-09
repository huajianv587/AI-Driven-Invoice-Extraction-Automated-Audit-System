import os
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN = os.getenv("FEISHU_APP_TOKEN")  # 也就是 URL 里 base/ 后面那串

def get_tenant_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=20)
    data = resp.json()
    print("[tenant_token]", data)
    return data.get("tenant_access_token")

def list_tables(token: str):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=20)
    print("[list_tables] http =", resp.status_code)
    data = resp.json()
    print("[list_tables] resp =", data)
    return data

if __name__ == "__main__":
    t = get_tenant_token()
    if not t:
        raise SystemExit("Failed to get tenant token.")
    list_tables(t)
