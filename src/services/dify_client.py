from __future__ import annotations

import json
import mimetypes
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from PIL import Image


class DifyClient:
    """
    Compatibility-focused Dify client.

    It supports:
    - file upload
    - app parameter probing
    - multiple workflow run endpoint styles
    - light polling when the initial blocking response has no outputs yet
    """

    def __init__(self, api_key: str, base_url: str = "https://api.dify.ai/v1"):
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "https://api.dify.ai/v1").rstrip("/")

    def _headers(self, json_body: bool = False) -> Dict[str, str]:
        headers = {"Authorization": f"Bearer {self.api_key}"}
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, method: str, path: str, timeout: int = 30, **kwargs) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        resp = requests.request(method=method.upper(), url=url, timeout=timeout, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"Dify {method.upper()} {path} -> http {resp.status_code}: {resp.text}")
        if not resp.content:
            return {}
        return resp.json()

    def get_parameters(self) -> Dict[str, Any]:
        return self._request("get", "/parameters", headers=self._headers(), timeout=20)

    def get_app_info(self) -> Dict[str, Any]:
        return self._request("get", "/info", headers=self._headers(), timeout=20)

    def upload_file(self, file_path: str, user: str = "local-script") -> str:
        if not os.path.exists(file_path):
            raise FileNotFoundError(file_path)

        filename = os.path.basename(file_path)
        mime, _ = mimetypes.guess_type(file_path)
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
            resp = requests.post(
                f"{self.base_url}/files/upload",
                headers=self._headers(),
                files={"file": (filename, f, mime)},
                data={"user": user},
                timeout=120,
            )

        if resp.status_code >= 400:
            raise RuntimeError(f"Dify upload http {resp.status_code}: {resp.text}")

        data = resp.json()
        file_id = data.get("id") or (data.get("file") or {}).get("id")
        if not file_id:
            raise RuntimeError(f"Dify upload succeeded but no file id was returned: {data}")
        return file_id

    @staticmethod
    def build_file_input(upload_file_id: str, file_kind: str = "image") -> Dict[str, Any]:
        return {
            "type": file_kind,
            "transfer_method": "local_file",
            "upload_file_id": upload_file_id,
        }

    @staticmethod
    def _normalize_extension(file_path: str) -> str:
        return Path(file_path).suffix.replace(".", "").upper()

    @staticmethod
    def extract_input_variables(parameters: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        variables: List[Dict[str, Any]] = []
        for item in (parameters or {}).get("user_input_form") or []:
            if not isinstance(item, dict):
                continue
            for control_type, control_cfg in item.items():
                if not isinstance(control_cfg, dict):
                    continue
                variable = str(control_cfg.get("variable") or "").strip()
                if not variable:
                    continue
                variables.append(
                    {
                        "type": control_type,
                        "variable": variable,
                        "required": bool(control_cfg.get("required")),
                        "allowed_file_types": list(control_cfg.get("allowed_file_types") or []),
                        "allowed_file_extensions": [str(ext).upper() for ext in (control_cfg.get("allowed_file_extensions") or [])],
                    }
                )
        return variables

    def pick_file_variable(
        self,
        parameters: Optional[Dict[str, Any]],
        preferred_variable: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        variables = self.extract_input_variables(parameters)
        if preferred_variable:
            for variable in variables:
                if variable.get("variable") == preferred_variable:
                    return variable
        for variable in variables:
            if variable.get("type") in {"file", "image"}:
                return variable
        return None

    def convert_image_to_pdf(self, file_path: str) -> str:
        with Image.open(file_path) as image:
            rgb = image.convert("RGB")
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                pdf_path = tmp.name
            rgb.save(pdf_path, "PDF")
        return pdf_path

    def prepare_local_file_input(
        self,
        file_path: str,
        parameters: Optional[Dict[str, Any]] = None,
        preferred_variable: Optional[str] = None,
        user: str = "local-script",
    ) -> Dict[str, Any]:
        variable_cfg = self.pick_file_variable(parameters, preferred_variable=preferred_variable)
        variable_name = preferred_variable or (variable_cfg or {}).get("variable") or "invoice"

        upload_path = file_path
        cleanup_path = None
        ext = self._normalize_extension(file_path)
        allowed_exts = set((variable_cfg or {}).get("allowed_file_extensions") or [])
        allowed_types = {str(item).lower() for item in ((variable_cfg or {}).get("allowed_file_types") or [])}

        if allowed_exts and ext not in allowed_exts and "PDF" in allowed_exts and ext in {"JPG", "JPEG", "PNG", "WEBP"}:
            upload_path = self.convert_image_to_pdf(file_path)
            cleanup_path = upload_path
            ext = "PDF"

        file_kind = "image"
        if ext == "PDF":
            file_kind = "document"
        if allowed_types:
            if "document" in allowed_types and ext == "PDF":
                file_kind = "document"
            elif "image" in allowed_types and ext in {"JPG", "JPEG", "PNG", "WEBP"}:
                file_kind = "image"

        upload_id = self.upload_file(upload_path, user=user)
        return {
            "variable_name": variable_name,
            "file_input": self.build_file_input(upload_id, file_kind=file_kind),
            "file_kind": file_kind,
            "upload_path": upload_path,
            "cleanup_path": cleanup_path,
            "allowed_file_extensions": sorted(allowed_exts),
            "allowed_file_types": sorted(allowed_types),
        }

    def get_workflow_run_detail(self, workflow_run_id: str) -> Dict[str, Any]:
        if not workflow_run_id:
            raise ValueError("workflow_run_id is empty")
        return self._request("get", f"/workflows/run/{workflow_run_id}", headers=self._headers(), timeout=30)

    def _extract_outputs(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not isinstance(payload, dict):
            return None
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        outputs = data.get("outputs")
        if isinstance(outputs, dict):
            return payload
        top_outputs = payload.get("outputs")
        if isinstance(top_outputs, dict):
            return {"data": {"outputs": top_outputs}}
        return None

    def _wait_for_outputs(self, payload: Dict[str, Any], timeout: int) -> Dict[str, Any]:
        extracted = self._extract_outputs(payload)
        if extracted is not None:
            return extracted

        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        workflow_run_id = str(data.get("workflow_run_id") or data.get("id") or "").strip()
        if not workflow_run_id:
            compact = json.dumps(payload, ensure_ascii=False)[:1000]
            raise RuntimeError(f"Dify returned no outputs and no workflow_run_id: {compact}")

        deadline = time.time() + min(timeout, 30)
        last_payload = payload
        while time.time() < deadline:
            time.sleep(1.0)
            detail = self.get_workflow_run_detail(workflow_run_id)
            last_payload = detail
            extracted = self._extract_outputs(detail)
            if extracted is not None:
                return extracted
            status = str(((detail.get("data") or {}).get("status") or detail.get("status") or "")).lower()
            if status in {"failed", "stopped", "error"}:
                compact = json.dumps(detail, ensure_ascii=False)[:1000]
                raise RuntimeError(f"Dify workflow finished without outputs: {compact}")

        compact = json.dumps(last_payload, ensure_ascii=False)[:1000]
        raise RuntimeError(f"Dify workflow timed out while waiting for outputs: {compact}")

    def run_workflow(
        self,
        workflow_id: str,
        inputs: Dict[str, Any],
        user: str = "local-script",
        timeout: int = 180,
    ) -> Dict[str, Any]:
        payload = {
            "inputs": inputs,
            "user": user,
            "response_mode": "blocking",
        }

        attempts = []
        attempts.append(("workflow-run", "/workflows/run", payload))
        if workflow_id:
            attempts.append(("workflow-run-legacy", "/workflows/run", {**payload, "workflow_id": workflow_id}))
            attempts.append(("workflow-by-id", f"/workflows/{workflow_id}/run", payload))

        errors: List[str] = []
        for attempt_name, path, body in attempts:
            try:
                result = self._request("post", path, headers=self._headers(json_body=True), json=body, timeout=timeout)
                result = self._wait_for_outputs(result, timeout=timeout)
                if isinstance(result, dict):
                    result["_attempt"] = attempt_name
                return result
            except Exception as exc:
                errors.append(f"{attempt_name}: {exc}")

        raise RuntimeError(" | ".join(errors))
