from __future__ import annotations

import os
import mimetypes
import requests
from typing import Any, Dict, Optional


class DifyClient:
    """
    Stable Dify client:
    - upload_file(file_path) -> file_id
    - run_workflow(workflow_id, inputs) -> resp_json

    Supports passing File / Array[File] variable to workflow inputs.
    """

    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.dify.ai/v1").rstrip("/")

    def upload_file(self, file_path: str, user: str = "local-script") -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        url = f"{self.base_url}/files/upload"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        filename = os.path.basename(file_path)
        mime, _ = mimetypes.guess_type(file_path)

        # Windows sometimes guesses wrong mime for jpg
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".jpg", ".jpeg"]:
            mime = "image/jpeg"
        elif ext == ".png":
            mime = "image/png"
        elif ext == ".pdf":
            mime = "application/pdf"
        elif not mime:
            mime = "application/octet-stream"

        with open(file_path, "rb") as f:
            files = {"file": (filename, f, mime)}
            data = {"user": user}
            resp = requests.post(url, headers=headers, files=files, data=data, timeout=120)

        if resp.status_code >= 400:
            raise RuntimeError(f"Dify upload http {resp.status_code}: {resp.text}")

        j = resp.json()
        file_id = j.get("id") or (j.get("file") or {}).get("id")
        if not file_id:
            raise RuntimeError(f"Dify upload ok but no file_id returned: {j}")
        return file_id

    @staticmethod
    def build_file_input(upload_file_id: str, file_kind: str = "image") -> Dict[str, Any]:
        """
        Dify workflow file input format (most compatible):
        {
          "type": "image" / "file",
          "transfer_method": "local_file",
          "upload_file_id": "<file_id>"
        }
        """
        return {
            "type": file_kind,
            "transfer_method": "local_file",
            "upload_file_id": upload_file_id,
        }

    def run_workflow(
            self,
            workflow_id: str,
            inputs: Dict[str, Any],
            user: str = "local-script",
            timeout: int = 180,
    ) -> Dict[str, Any]:
        if not workflow_id:
            raise ValueError("workflow_id is empty")

        url = f"{self.base_url}/workflows/run"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        payload = {
            "workflow_id": workflow_id,
            "inputs": inputs,
            "user": user,
            "response_mode": "blocking",  # ✅关键：确保直接拿到 data.outputs
        }

        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code >= 400:
            raise RuntimeError(f"Dify workflow http {resp.status_code}: {resp.text}")

        data = resp.json()

        # ✅如果没有 outputs，把整包打印出来你才能定位是“没blocking”还是“节点失败”
        if not (data.get("data") or {}).get("outputs"):
            raise RuntimeError(f"Dify returned no outputs, resp={data}")

        return data
