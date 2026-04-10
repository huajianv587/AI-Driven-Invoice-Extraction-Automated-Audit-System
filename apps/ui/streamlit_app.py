from __future__ import annotations

import json
from typing import Any, Dict, Optional

import requests
import streamlit as st

from src.product.settings import get_settings


settings = get_settings()
API_BASE = settings.api_base_url.rstrip("/")


def init_state() -> None:
    st.session_state.setdefault("token", "")
    st.session_state.setdefault("current_user", None)
    st.session_state.setdefault("selected_invoice_id", None)


def api_request(method: str, path: str, *, token: str = "", timeout: int = 30, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {})
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, f"{API_BASE}{path}", headers=headers, timeout=timeout, **kwargs)
    return response


def login_view() -> None:
    st.title("Invoice Audit Platform")
    st.caption("API-driven review console for upload, task tracking, and manual review.")
    with st.form("login_form"):
        username = st.text_input("Username", value=settings.reviewer_username)
        password = st.text_input("Password", type="password", value=settings.reviewer_password)
        submitted = st.form_submit_button("Login", use_container_width=True)
    if submitted:
        response = api_request("POST", "/v1/auth/login", json={"username": username, "password": password})
        if response.status_code >= 400:
            st.error(response.text)
            return
        data = response.json()
        st.session_state["token"] = data["access_token"]
        st.session_state["current_user"] = data["user"]
        st.rerun()


def load_me(token: str) -> Optional[Dict[str, Any]]:
    response = api_request("GET", "/v1/auth/me", token=token)
    if response.status_code >= 400:
        return None
    return response.json()


def upload_tab(token: str) -> None:
    st.subheader("Upload Invoice")
    uploaded = st.file_uploader("Select invoice image or PDF", type=["png", "jpg", "jpeg", "webp", "pdf"])
    if uploaded and st.button("Submit Upload", use_container_width=True):
        files = {"file": (uploaded.name, uploaded.getvalue(), uploaded.type or "application/octet-stream")}
        response = api_request("POST", "/v1/invoices/upload", token=token, files=files, timeout=120)
        if response.status_code >= 400:
            st.error(response.text)
        else:
            data = response.json()
            st.success(f"Uploaded. task_id={data['task_id']} trace_id={data['trace_id']}")


def tasks_tab(token: str) -> None:
    st.subheader("Task Queue")
    status_filter = st.selectbox("Task status", ["", "PENDING", "RUNNING", "COMPLETED", "FAILED"], index=0)
    response = api_request("GET", "/v1/tasks", token=token, params={"status": status_filter, "limit": 200})
    if response.status_code >= 400:
        st.error(response.text)
        return
    tasks = response.json()
    st.dataframe(tasks, use_container_width=True)
    failed_ids = [row["id"] for row in tasks if row.get("processing_status") == "FAILED"]
    if failed_ids:
        task_id = st.selectbox("Retry failed task", failed_ids)
        if st.button("Retry Task", use_container_width=True):
            retry_resp = api_request("POST", f"/v1/tasks/{task_id}/retry", token=token)
            if retry_resp.status_code >= 400:
                st.error(retry_resp.text)
            else:
                st.success(f"Task {task_id} moved back to PENDING")


def invoices_tab(token: str) -> None:
    st.subheader("Invoices")
    q = st.text_input("Search seller / invoice / PO")
    review_status = st.selectbox("Review status", ["", "NEEDS_REVIEW", "APPROVED", "REJECTED", "PENDING"], index=0)
    processing_status = st.selectbox("Processing status", ["", "PENDING", "RUNNING", "COMPLETED", "FAILED"], index=0)
    response = api_request(
        "GET",
        "/v1/invoices",
        token=token,
        params={"q": q, "review_status": review_status, "processing_status": processing_status, "limit": 200},
    )
    if response.status_code >= 400:
        st.error(response.text)
        return
    invoices = response.json()
    st.dataframe(invoices, use_container_width=True)
    ids = [row["id"] for row in invoices]
    if not ids:
        return
    selected = st.selectbox("Invoice detail", ids, index=0)
    st.session_state["selected_invoice_id"] = selected
    detail_resp = api_request("GET", f"/v1/invoices/{selected}", token=token)
    if detail_resp.status_code >= 400:
        st.error(detail_resp.text)
        return
    detail = detail_resp.json()
    invoice = detail["invoice"]
    st.markdown("**Invoice Summary**")
    st.json(invoice)
    st.markdown("**Line Items**")
    st.dataframe(detail["items"], use_container_width=True)
    st.markdown("**Extractions**")
    st.json(detail["extractions"])
    st.markdown("**Events**")
    st.dataframe(detail["events"], use_container_width=True)
    st.markdown("**Notifications**")
    st.dataframe(detail["notifications"], use_container_width=True)


def review_tab(token: str) -> None:
    st.subheader("Review Desk")
    response = api_request("GET", "/v1/invoices", token=token, params={"review_status": "NEEDS_REVIEW", "limit": 200})
    if response.status_code >= 400:
        st.error(response.text)
        return
    queue = response.json()
    if not queue:
        st.info("No invoices waiting for review.")
        return
    st.dataframe(queue, use_container_width=True)
    invoice_id = st.selectbox("Pick invoice to review", [row["id"] for row in queue])
    detail_resp = api_request("GET", f"/v1/invoices/{invoice_id}", token=token)
    if detail_resp.status_code >= 400:
        st.error(detail_resp.text)
        return
    detail = detail_resp.json()
    left, right = st.columns(2)
    with left:
        st.markdown("**Invoice**")
        st.json(detail["invoice"])
        st.markdown("**Items**")
        st.dataframe(detail["items"], use_container_width=True)
    with right:
        st.markdown("**Latest Extraction**")
        latest_extraction = detail["extractions"][0] if detail["extractions"] else {}
        st.json(latest_extraction)
        note = st.text_area("Review note", height=180)
        review_status = st.selectbox("Decision", ["APPROVED", "REJECTED", "NEEDS_REVIEW"])
        if st.button("Submit Review", use_container_width=True):
            payload = {"invoice_id": invoice_id, "review_status": review_status, "note": note}
            submit_resp = api_request("POST", "/v1/reviews", token=token, json=payload, timeout=60)
            if submit_resp.status_code >= 400:
                st.error(submit_resp.text)
            else:
                st.success(f"Review submitted for invoice {invoice_id}")


def summary_cards(token: str) -> None:
    response = api_request("GET", "/v1/dashboard/summary", token=token)
    if response.status_code >= 400:
        st.warning("Dashboard summary unavailable.")
        return
    summary = response.json()
    cols = st.columns(5)
    cols[0].metric("Invoices", summary.get("total_invoices", 0))
    cols[1].metric("Pending Tasks", summary.get("pending_tasks", 0))
    cols[2].metric("Failed Tasks", summary.get("failed_tasks", 0))
    cols[3].metric("Review Queue", summary.get("review_queue", 0))
    cols[4].metric("Risk Invoices", summary.get("risk_invoices", 0))


def main() -> None:
    st.set_page_config(page_title="Invoice Audit Platform", page_icon="I", layout="wide")
    init_state()
    token = st.session_state["token"]
    if not token:
        login_view()
        return
    user = load_me(token)
    if not user:
        st.session_state["token"] = ""
        st.session_state["current_user"] = None
        st.warning("Session expired, please log in again.")
        st.rerun()
        return
    st.session_state["current_user"] = user

    with st.sidebar:
        st.markdown(f"**API**: `{API_BASE}`")
        st.markdown(f"**User**: `{user['username']}`")
        st.markdown(f"**Role**: `{user['role']}`")
        if st.button("Logout", use_container_width=True):
            st.session_state["token"] = ""
            st.session_state["current_user"] = None
            st.rerun()

    st.title("Invoice Audit Platform")
    st.caption("Closed-loop product console: upload, process, inspect, and review.")
    summary_cards(token)
    tab_upload, tab_tasks, tab_invoices, tab_review = st.tabs(["Upload", "Tasks", "Invoices", "Review"])
    with tab_upload:
        upload_tab(token)
    with tab_tasks:
        tasks_tab(token)
    with tab_invoices:
        invoices_tab(token)
    with tab_review:
        review_tab(token)


if __name__ == "__main__":
    main()
