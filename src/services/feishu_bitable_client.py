# src/services/feishu_bitable_client.py
import json
import re
import requests
from typing import Dict, Any, Tuple, Optional


class FeishuBitableClient:
    """
    最稳版本：
    1) get_tenant_token
    2) add_record 前自动读取 fields 定义(type)
    3) 按 type 强制转换：
       - Number -> float（解析失败直接丢字段）
       - Checkbox -> bool
       - DateTime -> unix ms（解析失败丢字段）
       - 其它 -> text
    4) 最终写入只带“飞书能接受”的字段，避免整条被 reject
    """

    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.app_token = app_token
        self.table_id = table_id

    @staticmethod
    def _mask_secret(value: Optional[str], keep: int = 4) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        if len(text) <= keep * 2:
            return "*" * len(text)
        return f"{text[:keep]}...{text[-keep:]}"

    @staticmethod
    def _preview_text(value: Optional[str], limit: int = 240) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        compact = " ".join(text.split())
        if len(compact) <= limit:
            return compact
        return compact[: max(limit - 3, 1)] + "..."

    def _json_or_raise(self, response: requests.Response, *, action: str) -> Dict[str, Any]:
        try:
            return response.json()
        except Exception as exc:
            content_type = self._preview_text(response.headers.get("content-type"), limit=96) or "unknown"
            body_preview = self._preview_text(response.text) or "<empty>"
            raise RuntimeError(
                f"Feishu {action} returned HTTP {response.status_code} "
                f"with non-JSON body (content-type={content_type}): {body_preview}"
            ) from exc

    def _json_or_error(self, response: requests.Response, *, action: str) -> Dict[str, Any]:
        try:
            data = response.json()
        except Exception:
            data = {
                "error": f"Feishu {action} returned HTTP {response.status_code} with non-JSON body",
                "http_status": response.status_code,
                "content_type": response.headers.get("content-type"),
                "body_preview": self._preview_text(response.text) or "<empty>",
            }
        if isinstance(data, dict):
            data.setdefault("http_status", response.status_code)
            data.setdefault("content_type", response.headers.get("content-type"))
        return data

    def get_tenant_token(self) -> Optional[str]:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        resp = requests.post(
            url,
            json={"app_id": self.app_id, "app_secret": self.app_secret},
            timeout=20,
        )
        data = self._json_or_raise(resp, action="tenant token")
        print(
            "[Feishu] tenant_token resp:",
            {
                "http_status": resp.status_code,
                "code": data.get("code"),
                "msg": data.get("msg"),
                "expire": data.get("expire"),
                "tenant_access_token": self._mask_secret(data.get("tenant_access_token")),
            },
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Feishu tenant token returned HTTP {resp.status_code}: "
                f"code={data.get('code')} msg={self._preview_text(data.get('msg')) or '<empty>'}"
            )
        if data.get("code") != 0:
            raise RuntimeError(
                f"Feishu tenant token rejected credentials or app access: "
                f"code={data.get('code')} msg={self._preview_text(data.get('msg')) or '<empty>'}"
            )
        token = str(data.get("tenant_access_token") or "").strip()
        if not token:
            raise RuntimeError(
                "Feishu tenant token response succeeded but tenant_access_token was empty."
            )
        return token

    def _get_fields_meta(self, token: str) -> Dict[str, int]:
        """
        返回 field_name -> type
        常见 type：
          1 Text
          2 Number
          5 DateTime
          7 Checkbox
        """
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/fields"
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(url, headers=headers, timeout=20)
        meta = self._json_or_raise(r, action="field metadata")
        if r.status_code != 200:
            raise RuntimeError(
                f"Feishu field metadata returned HTTP {r.status_code}: "
                f"code={meta.get('code')} msg={self._preview_text(meta.get('msg')) or '<empty>'}"
            )
        if meta.get("code") != 0:
            raise RuntimeError(
                f"Feishu field metadata rejected app/table access: "
                f"code={meta.get('code')} msg={self._preview_text(meta.get('msg')) or '<empty>'}"
            )
        mp: Dict[str, int] = {}
        for it in meta["data"]["items"]:
            mp[it["field_name"]] = it.get("type")
        return mp

    def _to_bool(self, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        if s in ("1", "true", "yes", "y", "是", "on", "checked", "红票", "red"):
            return True
        if s in ("0", "false", "no", "n", "否", "off", "unchecked", ""):
            return False
        try:
            return float(s) != 0
        except Exception:
            return False

    def _to_number(self, v: Any) -> Optional[float]:
        """
        解析失败返回 None（表示丢字段）
        """
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip()
        if s == "":
            return None
        if s.lower() in ("null", "none", "nan", "n/a", "na", "-", "—", "--"):
            return None
        s = s.replace(",", "").replace(" ", "")
        # 从字符串抓第一个数字片段
        m = re.search(r"-?\d+(?:\.\d+)?", s)
        if not m:
            return None
        try:
            return float(m.group(0))
        except Exception:
            return None

    def _to_ts_ms(self, v: Any) -> Optional[int]:
        """
        Date/Datetime：必须 unix ms
        解析失败返回 None（表示丢字段）
        """
        if v is None:
            return None
        if isinstance(v, (int, float)):
            x = float(v)
            # 10位秒 -> ms
            if x < 10_000_000_000:
                return int(x * 1000)
            return int(x)

        s = str(v).strip()
        if s == "":
            return None

        # 只处理常见 YYYY-MM-DD / YYYY/MM/DD / YYYY.MM.DD
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y-%m-%d %H:%M:%S"):
            try:
                import datetime as _dt
                dt = _dt.datetime.strptime(s, fmt)
                return int(dt.timestamp() * 1000)
            except Exception:
                pass

        # 兜底：20240112
        if re.fullmatch(r"\d{8}", s):
            try:
                import datetime as _dt
                dt = _dt.datetime.strptime(s, "%Y%m%d")
                return int(dt.timestamp() * 1000)
            except Exception:
                return None

        return None

    def add_record(self, token: str, fields: Dict[str, Any]) -> Tuple[bool, Any]:
        # 1) 拉字段类型
        try:
            field_types = self._get_fields_meta(token)
        except Exception as e:
            return False, {"stage": "fetch_fields_meta_failed", "error": str(e)}

        # 2) 按类型强转 & 丢掉不可用字段
        TYPE_TEXT = 1
        TYPE_NUMBER = 2
        TYPE_DATETIME = 5
        TYPE_CHECKBOX = 7

        normalized: Dict[str, Any] = {}
        dropped: Dict[str, Any] = {}

        for k, v in fields.items():
            if k not in field_types:
                # 飞书没有这个列名，直接丢
                dropped[k] = v
                continue

            t = field_types.get(k)

            # None -> 空字符串（对 text 友好）
            if v is None:
                v = ""

            if t == TYPE_NUMBER:
                num = self._to_number(v)
                if num is None:
                    dropped[k] = v
                else:
                    normalized[k] = num

            elif t == TYPE_CHECKBOX:
                normalized[k] = self._to_bool(v)

            elif t == TYPE_DATETIME:
                ts = self._to_ts_ms(v)
                if ts is None:
                    dropped[k] = v
                else:
                    normalized[k] = ts

            else:
                # text / select 等：统一转字符串（dict/list -> json）
                if isinstance(v, (dict, list)):
                    normalized[k] = json.dumps(v, ensure_ascii=False)
                else:
                    normalized[k] = "" if v is None else v

        if dropped:
            # 打印被丢掉的字段，方便你定位到底哪个值异常
            print("[Feishu] dropped fields (invalid or not exist):", list(dropped.keys()))

        # 3) 真正写入
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"fields": normalized}

        resp = requests.post(url, headers=headers, json=payload, timeout=20)
        data = self._json_or_error(resp, action="add_record")

        print("[Feishu] add_record status:", resp.status_code)
        print("[Feishu] add_record resp:", data)

        ok = (resp.status_code in (200, 201)) and (data.get("code") == 0)
        return ok, data

    def get_record(self, token: str, record_id: str) -> Tuple[bool, Any]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{record_id}"
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, timeout=20)
        data = self._json_or_error(resp, action="get_record")

        print("[Feishu] get_record status:", resp.status_code)
        print("[Feishu] get_record resp:", data)

        ok = resp.status_code == 200 and data.get("code") == 0
        return ok, data
