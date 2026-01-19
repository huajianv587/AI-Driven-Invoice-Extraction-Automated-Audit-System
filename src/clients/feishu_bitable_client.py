# src/clients/feishu_bitable_client.py
from __future__ import annotations

import requests
from typing import Dict, Any, Optional, List


class FeishuBitableClient:
    """
    Feishu Bitable(OpenAPI) client (internal app):
    - tenant token
    - list/get tables
    - list/add/update/delete records
    - small-table upsert by key fields (scan then update/add)
    """

    def __init__(self, app_id: str, app_secret: str, app_token: str, table_id: str):
        self.app_id = (app_id or "").strip()
        self.app_secret = (app_secret or "").strip()
        self.app_token = (app_token or "").strip()   # base/app token
        self.table_id = (table_id or "").strip()     # tblxxxx

    # -----------------------------
    # Auth
    # -----------------------------
    def get_tenant_token(self) -> Optional[str]:
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        try:
            resp = requests.post(
                url,
                json={"app_id": self.app_id, "app_secret": self.app_secret},
                timeout=20,
            )
            data = resp.json()
            return data.get("tenant_access_token")
        except Exception:
            return None

    # -----------------------------
    # Tables
    # -----------------------------
    def list_tables(self, token: str) -> Dict[str, Any]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        try:
            return resp.json()
        except Exception:
            return {"_http_status": resp.status_code, "_text": resp.text}

    def get_table(self, token: str, table_id: Optional[str] = None) -> Dict[str, Any]:
        tid = (table_id or self.table_id).strip()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{tid}"
        resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        try:
            return resp.json()
        except Exception:
            return {"_http_status": resp.status_code, "_text": resp.text}

    # -----------------------------
    # Records
    # -----------------------------
    def list_records(
        self,
        token: str,
        page_size: int = 100,
        page_token: Optional[str] = None,
    ) -> Dict[str, Any]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        headers = {"Authorization": f"Bearer {token}"}
        params: Dict[str, Any] = {"page_size": page_size}
        if page_token:
            params["page_token"] = page_token

        r = requests.get(url, headers=headers, params=params, timeout=20)
        try:
            return r.json()
        except Exception:
            return {"_http_status": r.status_code, "_text": r.text}

    def add_record(self, token: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records"
        payload = {"fields": fields}
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        try:
            return resp.json()
        except Exception:
            return {"_http_status": resp.status_code, "_text": resp.text}

    def update_record(self, token: str, record_id: str, fields: Dict[str, Any]) -> Dict[str, Any]:
        rid = (record_id or "").strip()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{rid}"
        payload = {"fields": fields}
        r = requests.put(
            url,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=payload,
            timeout=20,
        )
        try:
            return r.json()
        except Exception:
            return {"_http_status": r.status_code, "_text": r.text}

    def delete_record(self, token: str, record_id: str) -> Dict[str, Any]:
        rid = (record_id or "").strip()
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{self.app_token}/tables/{self.table_id}/records/{rid}"
        r = requests.delete(url, headers={"Authorization": f"Bearer {token}"}, timeout=20)
        try:
            return r.json()
        except Exception:
            return {"_http_status": r.status_code, "_text": r.text}

    # -----------------------------
    # Helpers (small tables)
    # -----------------------------
    @staticmethod
    def _norm(v: Any) -> str:
        if v is None:
            return ""
        return str(v).strip()

    def _iter_all_records(self, token: str, page_size: int = 200, max_pages: int = 50) -> List[Dict[str, Any]]:
        all_items: List[Dict[str, Any]] = []
        page_token: Optional[str] = None

        for _ in range(max_pages):
            resp = self.list_records(token, page_size=page_size, page_token=page_token)
            if resp.get("code") != 0:
                # stop if API error
                break

            data = resp.get("data") or {}
            items = data.get("items") or []
            all_items.extend(items)

            has_more = bool(data.get("has_more"))
            if not has_more:
                break

            page_token = data.get("page_token")
            if not page_token:
                break

        return all_items

    def upsert_by_key(self, token: str, fields: Dict[str, Any], key_fields: List[str]) -> Dict[str, Any]:
        """
        Upsert for small table:
        - Find record whose fields match key_fields -> update
        - Else add
        """
        # build incoming key tuple
        key_vals: List[str] = []
        for k in key_fields:
            key_vals.append(self._norm(fields.get(k)))
        key_tuple = tuple(key_vals)

        # scan all records
        items = self._iter_all_records(token, page_size=200, max_pages=50)
        for it in items:
            rid = it.get("record_id") or it.get("id")
            f = it.get("fields") or {}

            it_vals: List[str] = []
            for k in key_fields:
                it_vals.append(self._norm(f.get(k)))
            it_key = tuple(it_vals)

            if it_key == key_tuple and rid:
                return self.update_record(token, rid, fields)

        return self.add_record(token, fields)
