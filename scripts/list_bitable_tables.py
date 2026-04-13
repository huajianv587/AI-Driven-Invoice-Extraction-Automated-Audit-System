import os
import requests
from dotenv import load_dotenv

load_dotenv()

APP_ID = os.getenv("FEISHU_APP_ID")
APP_SECRET = os.getenv("FEISHU_APP_SECRET")
APP_TOKEN = os.getenv("FEISHU_APP_TOKEN")  # 也就是 URL 里 base/ 后面那串


def mask_secret(value: str, keep: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= keep * 2:
        return "*" * len(text)
    return f"{text[:keep]}...{text[-keep:]}"

def get_tenant_token():
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={"app_id": APP_ID, "app_secret": APP_SECRET}, timeout=20)
    data = resp.json()
    print(
        "[tenant_token]",
        {
            "code": data.get("code"),
            "msg": data.get("msg"),
            "expire": data.get("expire"),
            "tenant_access_token": mask_secret(data.get("tenant_access_token")),
        },
    )
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
