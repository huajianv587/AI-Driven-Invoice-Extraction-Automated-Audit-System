# src/clients/dify_client.py
from typing import Any, Dict
import os
import mimetypes
import requests


class DifyClient:
    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")

    def upload_file(self, file_path: str, user: str = "invoice-ai") -> str:
        """
        POST /v1/files/upload
        必须 multipart/form-data（不要手写 Content-Type）
        """
        url = f"{self.base_url}/files/upload"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        filename = os.path.basename(file_path)
        mime, _ = mimetypes.guess_type(file_path)
        mime = mime or "application/octet-stream"

        with open(file_path, "rb") as f:
            files = {"file": (filename, f, mime)}
            data = {"user": user}
            r = requests.post(url, headers=headers, files=files, data=data, timeout=60)

        r.raise_for_status()
        return r.json()["id"]

    def run_workflow(self, inputs: Dict[str, Any], user: str = "invoice-ai") -> Dict[str, Any]:
        url = f"{self.base_url}/workflows/run"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {"inputs": inputs, "response_mode": "blocking", "user": user}
        r = requests.post(url, headers=headers, json=payload, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"Dify {r.status_code}: {r.text}")
        return r.json()



