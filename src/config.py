import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

def env(key: str, default: str | None = None) -> str | None:
    v = os.getenv(key)
    if v is None or str(v).strip() == "":
        return default
    return v

@dataclass
class MySQLCfg:
    host: str
    port: int
    user: str
    password: str
    db: str

def get_mysql_cfg() -> MySQLCfg:
    return MySQLCfg(
        host=env("MYSQL_HOST", "127.0.0.1") or "127.0.0.1",
        port=int(env("MYSQL_PORT", "3306") or "3306"),
        user=env("MYSQL_USER", "root") or "root",
        password=env("MYSQL_PASSWORD", "") or "",
        db=env("MYSQL_DB", "invoice_db") or "invoice_db",
    )

def get_app_base_url() -> str:
    return env("APP_BASE_URL", "http://127.0.0.1:8000") or "http://127.0.0.1:8000"
