from __future__ import annotations

import html
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import streamlit as st


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


from src.config import load_env, load_flat_config
from src.db.mysql_client import MySQLClient
from src.jobs.feishu_sync_job import sync_invoices_to_feishu
from src.services.integration_checks import check_dify, check_feishu, check_http_endpoint, check_smtp


load_env()


def load_cfg() -> Dict[str, Any]:
    return load_flat_config()


@st.cache_resource(show_spinner=False)
def get_db(host: str, port: int, user: str, password: str, db_name: str) -> MySQLClient:
    return MySQLClient(
        host=host,
        port=port,
        user=user,
        password=password,
        db=db_name,
        connect_timeout=10,
        autocommit=True,
    )


def db_client(cfg: Dict[str, Any]) -> MySQLClient:
    return get_db(
        cfg["mysql_host"],
        int(cfg["mysql_port"]),
        cfg["mysql_user"],
        cfg["mysql_password"],
        cfg["mysql_db"],
    )


def decode_json(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, (bytes, bytearray)):
        value = value.decode("utf-8", "ignore")
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def safe_float(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except Exception:
        return 0.0


def safe_int(value: Any) -> int:
    try:
        if value in (None, ""):
            return 0
        return int(value)
    except Exception:
        return 0


def esc(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return html.escape(str(value))


def fmt_money(value: Any) -> str:
    if value in (None, ""):
        return "-"
    try:
        return f"{float(value):,.2f}"
    except Exception:
        return str(value)


def fmt_dt(value: Any) -> str:
    if value in (None, ""):
        return "-"
    return str(value)[:19]


def mailpit_url() -> str:
    return f"http://127.0.0.1:{os.getenv('MAILPIT_WEB_PORT', '8025')}"


def tone_for_status(status: Any) -> str:
    text = str(status or "").strip().lower()
    if text in {"ok", "approved", "sent", "success"}:
        return "ok"
    if text in {"failed", "rejected", "error"}:
        return "danger"
    if text in {"needsreview", "pending", "warning", "notsent"}:
        return "warn"
    return "neutral"


def badge(text: Any, tone: str = "neutral") -> str:
    return f"<span class='badge badge-{tone}'>{esc(text)}</span>"


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Sans:wght@400;500;600&display=swap');
        :root{
          --bg:#07111d; --panel:rgba(10,22,38,.78); --line:rgba(142,188,255,.18);
          --text:#e9f3ff; --muted:#91a6c6; --cyan:#57d9ff; --teal:#2cf3c7;
          --amber:#ffb74a; --red:#ff6d8a; --blue:#78a6ff; --shadow:0 18px 52px rgba(0,0,0,.30);
        }
        .stApp{
          background:
            radial-gradient(circle at 18% 12%, rgba(87,217,255,.14), transparent 22%),
            radial-gradient(circle at 82% 18%, rgba(120,166,255,.12), transparent 24%),
            radial-gradient(circle at 50% 100%, rgba(44,243,199,.10), transparent 28%),
            linear-gradient(160deg, var(--bg) 0%, #081523 45%, #050b14 100%);
          color:var(--text);
          font-family:"IBM Plex Sans","Segoe UI","Microsoft YaHei UI",sans-serif;
        }
        .block-container{max-width:1450px;padding-top:1.2rem;padding-bottom:2rem;}
        h1,h2,h3,h4{font-family:"Space Grotesk","Segoe UI","Microsoft YaHei UI",sans-serif;color:var(--text);}
        [data-testid="stSidebar"]{
          background:linear-gradient(180deg, rgba(8,16,28,.96), rgba(10,22,37,.95));
          border-right:1px solid var(--line);
        }
        [data-testid="stSidebar"] *{color:var(--text);}
        .hero-shell,.metric-card,.panel-card,.timeline-card{
          border:1px solid var(--line); background:linear-gradient(180deg,var(--panel),rgba(7,16,29,.96));
          box-shadow:var(--shadow); border-radius:24px;
        }
        .hero-shell{display:grid;grid-template-columns:1.55fr .85fr;gap:1rem;padding:1.6rem 1.65rem;margin-bottom:1rem;position:relative;overflow:hidden;}
        .hero-shell:before,.hero-shell:after{
          content:""; position:absolute; width:220px; height:220px; border-radius:999px; filter:blur(10px); animation:floatGlow 8s ease-in-out infinite;
        }
        .hero-shell:before{right:-80px; top:-80px; background:radial-gradient(circle, rgba(87,217,255,.22), transparent 68%);}
        .hero-shell:after{left:-95px; bottom:-120px; background:radial-gradient(circle, rgba(120,166,255,.16), transparent 70%);}
        @keyframes floatGlow{0%,100%{transform:translateY(0)}50%{transform:translateY(12px)}}
        .hero-kicker,.section-kicker,.hero-side-label{font-size:.78rem; letter-spacing:.16em; color:var(--cyan); font-weight:600;}
        .hero-shell h1{margin:.35rem 0 .55rem; font-size:2.35rem; line-height:1.05;}
        .hero-shell p{margin:0; color:var(--muted); max-width:54rem; line-height:1.7;}
        .hero-badges{display:flex; gap:.55rem; flex-wrap:wrap; margin-top:1rem;}
        .hero-side{background:linear-gradient(180deg, rgba(10,24,41,.74), rgba(8,18,30,.9)); border:1px solid rgba(87,217,255,.14); border-radius:20px; padding:1.25rem;}
        .hero-side-value{font-family:"Space Grotesk",sans-serif;font-size:1.8rem;font-weight:700;margin:.35rem 0 .4rem;}
        .hero-side-caption{color:var(--muted);line-height:1.6;}
        .section-head{display:flex;justify-content:space-between;gap:1rem;align-items:end;margin:.7rem 0 .9rem;}
        .section-head h3{margin:.25rem 0 0;font-size:1.15rem;}
        .section-head p{margin:0;max-width:30rem;color:var(--muted);font-size:.92rem;line-height:1.6;}
        .metric-card{padding:1.15rem 1.2rem; min-height:138px;}
        .metric-label{color:var(--muted);font-size:.88rem;text-transform:uppercase;letter-spacing:.09em;}
        .metric-value{font-family:"Space Grotesk",sans-serif;font-size:2rem;font-weight:700;margin:.55rem 0 .35rem;}
        .metric-note{color:#bfd2ed;line-height:1.5;}
        .tone-ok{box-shadow:0 18px 52px rgba(22,132,104,.18);}
        .tone-warn{box-shadow:0 18px 52px rgba(191,121,30,.18);}
        .tone-danger{box-shadow:0 18px 52px rgba(170,58,86,.20);}
        .panel-card{padding:1.1rem 1.15rem; margin-bottom:.95rem;}
        .panel-title{font-family:"Space Grotesk",sans-serif;font-size:1rem;font-weight:600;margin-bottom:.75rem;}
        .fact-grid{display:grid;gap:.55rem;}
        .fact-row{display:flex;justify-content:space-between;gap:1rem;padding:.62rem .72rem;border-radius:14px;background:rgba(120,166,255,.05);border:1px solid rgba(120,166,255,.08);}
        .fact-row span{color:var(--muted);}
        .fact-row strong{font-weight:600;color:var(--text);text-align:right;}
        .badge{display:inline-flex;align-items:center;justify-content:center;padding:.34rem .74rem;border-radius:999px;font-size:.74rem;font-weight:700;letter-spacing:.06em;text-transform:uppercase;border:1px solid transparent;}
        .badge-ok{background:rgba(44,243,199,.14);color:#9cfce8;border-color:rgba(44,243,199,.26);}
        .badge-warn{background:rgba(255,183,74,.14);color:#ffd38c;border-color:rgba(255,183,74,.24);}
        .badge-danger{background:rgba(255,109,138,.14);color:#ffb4c1;border-color:rgba(255,109,138,.24);}
        .badge-neutral{background:rgba(120,166,255,.12);color:#b7ceff;border-color:rgba(120,166,255,.2);}
        .integration-top,.timeline-top,.spotlight-top{display:flex;justify-content:space-between;gap:.75rem;align-items:start;}
        .integration-message,.timeline-body,.spotlight-reason{color:#d6e5fb;line-height:1.65;}
        .integration-detail,.timeline-meta,.spotlight-meta{color:var(--muted);font-size:.86rem;margin-top:.45rem;}
        .spotlight-vendor{color:var(--muted);}
        .spotlight-amount{font-family:"Space Grotesk",sans-serif;font-size:1.5rem;font-weight:700;margin:.75rem 0 .25rem;}
        .activity-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.8rem;margin-bottom:.6rem;}
        .day-chip{padding:.9rem 1rem;border-radius:18px;border:1px solid rgba(87,217,255,.12);background:linear-gradient(180deg, rgba(9,21,36,.84), rgba(8,15,26,.96));}
        .day-chip-label{font-size:.8rem;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
        .day-chip-value{font-family:"Space Grotesk",sans-serif;font-size:1.45rem;font-weight:700;margin:.45rem 0 .15rem;}
        .day-chip-sub{color:#b8cae3;font-size:.88rem;}
        .timeline-card{padding:1rem 1.05rem; margin-bottom:.75rem;}
        .stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{
          background:rgba(7,18,30,.92) !important; border:1px solid rgba(120,166,255,.16) !important; border-radius:16px !important; color:var(--text) !important;
        }
        .stButton > button,.stDownloadButton > button,.stFormSubmitButton > button{
          border:none; border-radius:16px; padding:.7rem 1rem; font-weight:700;
          background:linear-gradient(90deg, var(--cyan), var(--blue)); color:#04101d; box-shadow:0 14px 34px rgba(87,217,255,.2);
        }
        .stCheckbox label,.stRadio label,.stCaption,.stMarkdown p{color:var(--muted);}
        .stTabs [data-baseweb="tab-list"]{gap:.4rem;}
        .stTabs [data-baseweb="tab"]{background:rgba(9,20,34,.9); border:1px solid rgba(120,166,255,.14); border-radius:14px; color:var(--text); padding:.55rem .95rem;}
        .stTabs [aria-selected="true"]{background:linear-gradient(90deg, rgba(87,217,255,.18), rgba(120,166,255,.2));}
        .stDataFrame, .stTable{border:1px solid rgba(120,166,255,.12);border-radius:18px;overflow:hidden;}
        @media (max-width: 980px){.hero-shell{grid-template-columns:1fr}.section-head{display:block}}
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, side_note: str, badges_html: str) -> None:
    st.markdown(
        f"""
        <div class="hero-shell">
          <div>
            <div class="hero-kicker">FINANCE AI CONTROL CENTER</div>
            <h1>{esc(title)}</h1>
            <p>{esc(subtitle)}</p>
            <div class="hero-badges">{badges_html}</div>
          </div>
          <div class="hero-side">
            <div class="hero-side-label">Delivery Build</div>
            <div class="hero-side-value">{esc(side_note)}</div>
            <div class="hero-side-caption">Live OCR, risk routing, work-order writeback, and audit traceability in one interface.</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def section_title(title: str, subtitle: str) -> None:
    st.markdown(
        f"""
        <div class="section-head">
          <div><div class="section-kicker">PRODUCT SURFACE</div><h3>{esc(title)}</h3></div>
          <p>{esc(subtitle)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_card(label: str, value: str, note: str, tone: str = "neutral") -> None:
    st.markdown(
        f"""
        <div class="metric-card tone-{tone}">
          <div class="metric-label">{esc(label)}</div>
          <div class="metric-value">{esc(value)}</div>
          <div class="metric-note">{esc(note)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def info_card(title: str, pairs: List[tuple[str, Any]]) -> None:
    rows = "".join(
        f"<div class='fact-row'><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
        for label, value in pairs
    )
    st.markdown(
        f"""
        <div class="panel-card">
          <div class="panel-title">{esc(title)}</div>
          <div class="fact-grid">{rows}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_card(name: str, status: str, message: str, detail: str) -> None:
    tone = tone_for_status(status)
    st.markdown(
        f"""
        <div class="panel-card">
          <div class="integration-top">
            <div class="panel-title">{esc(name)}</div>
            {badge(status, tone)}
          </div>
          <div class="integration-message">{esc(message)}</div>
          <div class="integration-detail">{esc(detail)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def risk_spotlight_card(row: Dict[str, Any]) -> None:
    reason = row.get("risk_reason")
    if isinstance(reason, (dict, list)):
        reason = json.dumps(reason, ensure_ascii=False)
    st.markdown(
        f"""
        <div class="panel-card">
          <div class="spotlight-top">
            <div>
              <div class="panel-title">Invoice #{safe_int(row.get("id"))}</div>
              <div class="spotlight-vendor">{esc(row.get("seller_name") or "Unknown Seller")}</div>
            </div>
            {badge('RISK', 'danger')}
          </div>
          <div class="spotlight-amount">Diff {fmt_money(row.get("amount_diff"))}</div>
          <div class="spotlight-meta">PO {esc(row.get("purchase_order_no") or 'N/A')} | Amount {fmt_money(row.get("total_amount_with_tax"))}</div>
          <div class="spotlight-reason">{esc(reason or 'Amount or metadata anomaly detected by policy engine.')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_activity_strip(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        st.info("No recent activity found yet.")
        return
    chips = []
    for row in rows:
        chips.append(
            f"""
            <div class="day-chip">
              <div class="day-chip-label">{esc(row.get("day_label"))}</div>
              <div class="day-chip-value">{safe_int(row.get("total_count"))}</div>
              <div class="day-chip-sub">risk {safe_int(row.get("risk_count"))}</div>
            </div>
            """
        )
    st.markdown(f"<div class='activity-strip'>{''.join(chips)}</div>", unsafe_allow_html=True)


def render_event_feed(events: List[Dict[str, Any]], empty_text: str) -> None:
    if not events:
        st.info(empty_text)
        return
    for event in events[:8]:
        tone = tone_for_status(event.get("event_status"))
        payload = decode_json(event.get("payload"))
        payload_text = json.dumps(payload, ensure_ascii=False) if isinstance(payload, (dict, list)) else str(payload or "")
        st.markdown(
            f"""
            <div class="timeline-card">
              <div class="timeline-top">
                <strong>{esc(event.get("event_type") or '-')}</strong>
                {badge(event.get("event_status") or '-', tone)}
              </div>
              <div class="timeline-meta">{esc(fmt_dt(event.get("created_at")))}</div>
              <div class="timeline-body">{esc(payload_text[:260] or 'No payload attached.')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_review_feed(tasks: List[Dict[str, Any]]) -> None:
    if not tasks:
        st.info("No manual review records yet.")
        return
    for task in tasks[:6]:
        st.markdown(
            f"""
            <div class="timeline-card">
              <div class="timeline-top">
                <strong>{esc(task.get("handler_user") or "Pending assignment")}</strong>
                {badge(task.get("review_result") or '-', tone_for_status(task.get("review_result")))}
              </div>
              <div class="timeline-meta">{esc(fmt_dt(task.get("created_at")))}</div>
              <div class="timeline-body">{esc(task.get("handling_note") or 'No note recorded.')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def fetch_metrics(db: MySQLClient) -> Dict[str, Any]:
    sql = """
    SELECT
      COUNT(*) AS total_count,
      SUM(CASE WHEN risk_flag = 1 THEN 1 ELSE 0 END) AS risk_count,
      SUM(CASE WHEN invoice_status = 'Pending' THEN 1 ELSE 0 END) AS pending_count,
      SUM(CASE WHEN DATE(created_at) = CURDATE() THEN 1 ELSE 0 END) AS today_count
    FROM invoices
    """
    return db.fetch_one(sql) or {"total_count": 0, "risk_count": 0, "pending_count": 0, "today_count": 0}


def fetch_feishu_sync_summary(db: MySQLClient) -> Dict[str, Any]:
    sql = """
    SELECT
      SUM(CASE WHEN s.invoice_id IS NULL THEN 1 ELSE 0 END) AS pending_count,
      SUM(CASE WHEN s.invoice_id IS NOT NULL AND (s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL) THEN 1 ELSE 0 END) AS failed_count,
      SUM(CASE WHEN s.feishu_record_id IS NOT NULL AND (s.sync_error IS NULL OR s.sync_error = '') THEN 1 ELSE 0 END) AS synced_count
    FROM invoices i
    LEFT JOIN invoice_feishu_sync s ON s.invoice_id = i.id
    """
    return db.fetch_one(sql) or {"pending_count": 0, "failed_count": 0, "synced_count": 0}


def fetch_recent_failed_feishu_syncs(db: MySQLClient, limit: int = 10) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      s.invoice_id,
      i.seller_name,
      i.invoice_code,
      i.invoice_number,
      i.purchase_order_no,
      s.sync_error,
      s.updated_at
    FROM invoice_feishu_sync s
    INNER JOIN invoices i ON i.id = s.invoice_id
    WHERE s.feishu_record_id IS NULL OR s.sync_error IS NOT NULL
    ORDER BY s.updated_at DESC, s.id DESC
    LIMIT %s
    """
    return db.fetch_all(sql, (int(limit),))


def summarize_sync_error(value: Any, limit: int = 110) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return f"{text[:limit - 3]}..."


def feishu_retry_worker_summary(cfg: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": bool(cfg.get("FEISHU_RETRY_WORKER_ENABLED")),
        "interval_sec": safe_int(cfg.get("FEISHU_RETRY_INTERVAL_SEC")),
        "mode": str(cfg.get("FEISHU_RETRY_MODE") or "failed"),
        "limit": safe_int(cfg.get("FEISHU_RETRY_BATCH_LIMIT")),
    }


def run_feishu_sync_action(
    db: MySQLClient,
    cfg: Dict[str, Any],
    *,
    mode: str = "failed",
    limit: int = 20,
    invoice_ids: Optional[List[int]] = None,
) -> None:
    ok_count, fail_count, details = sync_invoices_to_feishu(
        db,
        cfg,
        mode=mode,
        limit=limit,
        invoice_ids=invoice_ids,
    )
    if ok_count and not fail_count:
        st.success(f"Feishu sync completed. ok={ok_count}, fail={fail_count}")
    elif ok_count or fail_count:
        st.warning(f"Feishu sync finished with mixed result. ok={ok_count}, fail={fail_count}")
    else:
        st.info("No matching invoices needed Feishu sync recovery.")
    if details:
        st.caption(json.dumps(details, ensure_ascii=False))


def fetch_recent_invoices(db: MySQLClient, limit: int = 100) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      id, invoice_date, seller_name, buyer_name, invoice_code, invoice_number, purchase_order_no,
      total_amount_with_tax, expected_amount, amount_diff, risk_flag, invoice_status, risk_reason, created_at
    FROM invoices
    ORDER BY id DESC
    LIMIT %s
    """
    rows = db.fetch_all(sql, (int(limit),))
    for row in rows:
        row["risk_reason"] = decode_json(row.get("risk_reason"))
    return rows


def fetch_daily_activity(db: MySQLClient) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      DATE_FORMAT(created_at, '%%m-%%d') AS day_label,
      COUNT(*) AS total_count,
      SUM(CASE WHEN risk_flag = 1 THEN 1 ELSE 0 END) AS risk_count
    FROM invoices
    WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
    GROUP BY DATE(created_at)
    ORDER BY DATE(created_at) ASC
    """
    return db.fetch_all(sql)


def fetch_invoice_detail(db: MySQLClient, invoice_id: int) -> Optional[Dict[str, Any]]:
    invoice = db.fetch_one("SELECT * FROM invoices WHERE id=%s", (int(invoice_id),))
    if not invoice:
        return None

    items = db.fetch_all("SELECT * FROM invoice_items WHERE invoice_id=%s ORDER BY id ASC", (int(invoice_id),))
    events = db.fetch_all("SELECT * FROM invoice_events WHERE invoice_id=%s ORDER BY id DESC", (int(invoice_id),))
    sync_row = db.fetch_one("SELECT * FROM invoice_feishu_sync WHERE invoice_id=%s", (int(invoice_id),))
    review_tasks = db.fetch_all(
        """
        SELECT * FROM invoice_review_tasks
        WHERE invoice_id=%s
        ORDER BY id DESC
        """,
        (int(invoice_id),),
    )

    invoice["raw_ocr_json"] = decode_json(invoice.get("raw_ocr_json"))
    invoice["llm_json"] = decode_json(invoice.get("llm_json"))
    invoice["risk_reason"] = decode_json(invoice.get("risk_reason"))

    return {
        "invoice": invoice,
        "items": items,
        "events": events,
        "sync": sync_row,
        "review_tasks": review_tasks,
    }


def update_invoice_review(
    db: MySQLClient,
    invoice_id: int,
    purchase_order_no: str,
    unique_hash: str,
    handler_user: str,
    handler_reason: str,
    invoice_status: str,
) -> None:
    db.execute(
        """
        UPDATE invoices
        SET invoice_status=%s, handler_user=%s, handler_reason=%s, handled_at=NOW(), updated_at=NOW()
        WHERE id=%s
        """,
        (invoice_status, handler_user or None, handler_reason or None, int(invoice_id)),
    )
    db.execute(
        """
        INSERT INTO invoice_review_tasks(
          invoice_id, purchase_order_no, unique_hash, review_result, handler_user, handling_note, source_channel
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            int(invoice_id),
            purchase_order_no or None,
            unique_hash or None,
            invoice_status,
            handler_user or None,
            handler_reason or None,
            "streamlit_form",
        ),
    )
    payload = json.dumps(
        {
            "purchase_order_no": purchase_order_no,
            "unique_hash": unique_hash,
            "handler_user": handler_user,
            "handler_reason": handler_reason,
            "invoice_status": invoice_status,
        },
        ensure_ascii=False,
    )
    db.execute(
        "INSERT INTO invoice_events(invoice_id, event_type, event_status, payload) VALUES(%s, %s, %s, %s)",
        (int(invoice_id), "WORK_ORDER_SUBMITTED", invoice_status, payload),
    )


def integration_status(cfg: Dict[str, Any]) -> List[Dict[str, str]]:
    checks = [
        check_http_endpoint("OCR", f"{cfg['ocr_base_url'].rstrip('/')}/docs"),
        check_dify(cfg["dify_base_url"], cfg["dify_api_key"], cfg["dify_workflow_id"]),
        check_feishu(
            cfg["feishu_app_id"],
            cfg["feishu_app_secret"],
            cfg["bitable_app_token"],
            cfg["bitable_table_id"],
        ),
        check_smtp(
            cfg["SMTP_HOST"],
            int(cfg["SMTP_PORT"]),
            cfg["SMTP_USER"],
            cfg["SMTP_PASS"],
            bool(cfg["SMTP_USE_TLS"]),
            bool(cfg["SMTP_USE_SSL"]),
            cfg["SMTP_FROM_NAME"],
            cfg["SMTP_FROM_EMAIL"],
        ),
    ]
    return [
        {
            "name": check.name,
            "status": "OK" if check.ok else "NOT READY",
            "message": check.message,
            "detail": check.detail or "",
        }
        for check in checks
    ]


def switch_view(view: str, **params: Any) -> None:
    st.query_params.clear()
    st.query_params["view"] = view
    for key, value in params.items():
        if value not in (None, ""):
            st.query_params[key] = str(value)
    st.rerun()


def display_invoice_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    display = []
    for row in rows:
        display.append(
            {
                "ID": safe_int(row.get("id")),
                "Date": fmt_dt(row.get("invoice_date"))[:10],
                "Seller": row.get("seller_name") or "-",
                "Buyer": row.get("buyer_name") or "-",
                "Invoice No.": row.get("invoice_number") or "-",
                "PO": row.get("purchase_order_no") or "-",
                "Amount": fmt_money(row.get("total_amount_with_tax")),
                "Expected": fmt_money(row.get("expected_amount")),
                "Diff": fmt_money(row.get("amount_diff")),
                "Risk": "HIGH" if safe_int(row.get("risk_flag")) == 1 else "NORMAL",
                "Status": row.get("invoice_status") or "-",
            }
        )
    return display


def render_dashboard(cfg: Dict[str, Any]) -> None:
    db = db_client(cfg)
    metrics = fetch_metrics(db)
    feishu_sync = fetch_feishu_sync_summary(db)
    feishu_retry = feishu_retry_worker_summary(cfg)
    failed_sync_rows = fetch_recent_failed_feishu_syncs(db, limit=8)
    invoices = fetch_recent_invoices(db, limit=200)
    activity = fetch_daily_activity(db)
    checks = integration_status(cfg)

    total_amount = sum(safe_float(row.get("total_amount_with_tax")) for row in invoices)
    risk_amount = sum(abs(safe_float(row.get("amount_diff"))) for row in invoices if safe_int(row.get("risk_flag")) == 1)
    risk_rows = sorted(
        [row for row in invoices if safe_int(row.get("risk_flag")) == 1],
        key=lambda row: abs(safe_float(row.get("amount_diff"))),
        reverse=True,
    )

    hero(
        "Invoice Intelligence Console",
        "A premium operating surface for OCR ingestion, AI field extraction, risk policy detection, alert dispatch, and manual work-order resolution.",
        f"Port {cfg['ui_port']} | Local delivery mode",
        badge("OCR LIVE", "ok") + badge("ALERT LOOP", "warn") + badge("DB WRITEBACK", "ok"),
    )

    cols = st.columns(4)
    with cols[0]:
        metric_card("Invoices in Repository", str(metrics["total_count"] or 0), "Total records now visible to the finance operations team.")
    with cols[1]:
        metric_card("High-Risk Queue", str(metrics["risk_count"] or 0), "Documents that triggered amount, supplier, or workflow anomalies.", "danger")
    with cols[2]:
        metric_card("Pending Decisions", str(metrics["pending_count"] or 0), "Cases still waiting for a reviewer decision or escalation.", "warn")
    with cols[3]:
        metric_card("Tracked Volume", fmt_money(total_amount), f"Risk exposure delta {fmt_money(risk_amount)}", "ok")

    section_title("Seven-Day Activity", "Short-range operational pulse for demo and delivery reviews.")
    render_activity_strip(activity)

    left, right = st.columns([1.45, 0.95], gap="large")
    with left:
        section_title("Review Queue", "Filter the invoice stream, inspect anomalies, and open a reviewer work order.")
        filter_cols = st.columns([1.4, 0.9, 0.7])
        with filter_cols[0]:
            search = st.text_input("Search seller, buyer, or invoice number", "")
        with filter_cols[1]:
            status_filter = st.selectbox("Status", ["All", "Pending", "Approved", "Rejected", "NeedsReview"], index=0)
        with filter_cols[2]:
            risk_only = st.checkbox("Risk only", value=False)

        filtered: List[Dict[str, Any]] = []
        keyword = search.strip().lower()
        for row in invoices:
            haystack = " ".join(
                [
                    str(row.get("seller_name") or ""),
                    str(row.get("buyer_name") or ""),
                    str(row.get("invoice_number") or ""),
                    str(row.get("invoice_code") or ""),
                ]
            ).lower()
            if keyword and keyword not in haystack:
                continue
            if risk_only and safe_int(row.get("risk_flag")) != 1:
                continue
            if status_filter != "All" and str(row.get("invoice_status") or "") != status_filter:
                continue
            filtered.append(row)

        st.dataframe(display_invoice_rows(filtered[:120]), use_container_width=True)

        if not filtered:
            st.info("No invoices matched the current filters.")
            return

        option_map = {
            (
                f"#{row['id']} | {row.get('seller_name') or 'N/A'} | "
                f"{row.get('invoice_number') or 'N/A'} | {fmt_money(row.get('total_amount_with_tax'))}"
            ): row["id"]
            for row in filtered[:120]
        }
        selected_invoice_id = st.query_params.get("invoice_id")
        default_index = 0
        if str(selected_invoice_id or "").isdigit():
            desired = int(selected_invoice_id)
            ids = list(option_map.values())
            if desired in ids:
                default_index = ids.index(desired)
        selected_label = st.selectbox("Analyst focus", list(option_map.keys()), index=default_index)
        selected_id = option_map[selected_label]
    with right:
        section_title("Service Mesh", "Health posture for OCR, Dify, Feishu, and SMTP connectors.")
        status_cols = st.columns(2)
        for idx, row in enumerate(checks):
            with status_cols[idx % 2]:
                status_card(row["name"], row["status"], row["message"], row["detail"])
        st.markdown(f"[Open Mailpit Inbox]({mailpit_url()})")
        section_title("Feishu Recovery", "Recover failed sync rows or replay pending invoice records to Feishu Bitable.")
        metric_cols = st.columns(3)
        with metric_cols[0]:
            metric_card("Synced", str(feishu_sync.get("synced_count") or 0), "Rows already mirrored to Feishu.")
        with metric_cols[1]:
            metric_card("Pending", str(feishu_sync.get("pending_count") or 0), "Invoices that have not been pushed yet.", "warn")
        with metric_cols[2]:
            metric_card("Failed", str(feishu_sync.get("failed_count") or 0), "Rows eligible for compensation replay.", "danger")
        action_cols = st.columns(2)
        with action_cols[0]:
            if st.button("Retry Failed Syncs", use_container_width=True):
                run_feishu_sync_action(db, cfg, mode="failed", limit=20)
        with action_cols[1]:
            if st.button("Sync Pending Rows", use_container_width=True):
                run_feishu_sync_action(db, cfg, mode="pending", limit=20)
        worker_label = "Enabled" if feishu_retry["enabled"] else "Disabled"
        worker_tone = "ok" if feishu_retry["enabled"] else "warn"
        st.markdown(
            f"Auto-retry worker: {badge(worker_label, worker_tone)} "
            f"mode `{feishu_retry['mode']}` every `{feishu_retry['interval_sec'] or 300}s` "
            f"(batch `{feishu_retry['limit'] or 20}`).",
            unsafe_allow_html=True,
        )
        if failed_sync_rows:
            display_failed_rows = [
                {
                    "Invoice ID": row.get("invoice_id"),
                    "Seller": row.get("seller_name") or "-",
                    "Invoice No.": row.get("invoice_number") or row.get("invoice_code") or "-",
                    "PO": row.get("purchase_order_no") or "-",
                    "Last Error": summarize_sync_error(row.get("sync_error")),
                    "Updated": fmt_dt(row.get("updated_at")),
                }
                for row in failed_sync_rows
            ]
            st.dataframe(display_failed_rows, use_container_width=True)
            failed_option_map = {
                (
                    f"#{row.get('invoice_id')} | "
                    f"{row.get('seller_name') or 'N/A'} | "
                    f"{row.get('invoice_number') or row.get('invoice_code') or 'N/A'}"
                ): int(row["invoice_id"])
                for row in failed_sync_rows
            }
            selected_failed_label = st.selectbox(
                "Recent failed syncs",
                list(failed_option_map.keys()),
                key="failed-feishu-sync-select",
            )
            if st.button("Retry Selected Failed Sync", use_container_width=True):
                run_feishu_sync_action(
                    db,
                    cfg,
                    mode="recoverable",
                    limit=1,
                    invoice_ids=[failed_option_map[selected_failed_label]],
                )
        else:
            st.info("No recent failed Feishu sync rows.")
        section_title("Priority Alerts", "Most material deltas surfaced by the policy engine.")
        if risk_rows:
            for row in risk_rows[:3]:
                risk_spotlight_card(row)
        else:
            st.info("No risk invoices are currently in queue.")

    detail = fetch_invoice_detail(db, selected_id)
    if not detail:
        st.warning("Invoice detail not found.")
        return

    invoice = detail["invoice"]
    reason = invoice.get("risk_reason")
    if isinstance(reason, (dict, list)):
        reason = json.dumps(reason, ensure_ascii=False)

    section_title("Analyst Workspace", "A single record view for financial facts, policy outcomes, and machine trace data.")
    hero(
        f"Invoice #{invoice['id']} | {invoice.get('seller_name') or 'Unknown Seller'}",
        "Review invoice identity, counterparty details, amount reconciliation, and downstream handling history before approving or escalating.",
        f"Status {invoice.get('invoice_status') or '-'}",
        badge(invoice.get("invoice_status") or "UNKNOWN", tone_for_status(invoice.get("invoice_status")))
        + badge("RISK" if safe_int(invoice.get("risk_flag")) == 1 else "NORMAL", "danger" if safe_int(invoice.get("risk_flag")) == 1 else "ok")
        + badge(f"PO {invoice.get('purchase_order_no') or 'N/A'}", "neutral"),
    )

    tabs = st.tabs(["Executive View", "Line Items", "Audit Trail", "Machine Output"])
    with tabs[0]:
        info_cols = st.columns(3)
        with info_cols[0]:
            info_card(
                "Document Identity",
                [
                    ("Invoice code", invoice.get("invoice_code")),
                    ("Invoice number", invoice.get("invoice_number")),
                    ("Invoice date", fmt_dt(invoice.get("invoice_date"))[:10]),
                    ("Source file", invoice.get("source_file_path")),
                ],
            )
        with info_cols[1]:
            info_card(
                "Counterparties",
                [
                    ("Seller", invoice.get("seller_name")),
                    ("Buyer", invoice.get("buyer_name")),
                    ("Seller tax ID", invoice.get("seller_tax_id")),
                    ("Buyer tax ID", invoice.get("buyer_tax_id")),
                ],
            )
        with info_cols[2]:
            info_card(
                "Financial Control",
                [
                    ("Invoice amount", fmt_money(invoice.get("total_amount_with_tax"))),
                    ("Expected amount", fmt_money(invoice.get("expected_amount"))),
                    ("Amount diff", fmt_money(invoice.get("amount_diff"))),
                    ("Unique hash", invoice.get("unique_hash")),
                ],
            )

        action_cols = st.columns([1, 1, 1.2])
        with action_cols[0]:
            if st.button("Open Work Order", use_container_width=True):
                switch_view(
                    "anomaly_form",
                    invoice_id=invoice["id"],
                    purchase_order_no=invoice.get("purchase_order_no") or "",
                    unique_hash=invoice.get("unique_hash") or "",
                )
        with action_cols[1]:
            if st.button("Focus This Invoice", use_container_width=True):
                switch_view("dashboard", invoice_id=invoice["id"])
        with action_cols[2]:
            st.markdown(f"[Check Risk Email in Mailpit]({mailpit_url()})")

        if not detail.get("sync") or detail["sync"].get("sync_error") or not detail["sync"].get("feishu_record_id"):
            retry_label = "Retry Feishu Sync" if detail.get("sync") else "Push To Feishu"
            if st.button(retry_label, key=f"retry-feishu-{invoice['id']}", use_container_width=True):
                run_feishu_sync_action(db, cfg, mode="recoverable", limit=1, invoice_ids=[int(invoice["id"])])
                detail = fetch_invoice_detail(db, int(invoice["id"]))
                invoice = detail["invoice"]

        st.markdown(
            f"""
            <div class="panel-card">
              <div class="panel-title">Policy Narrative</div>
              <div class="integration-message">{esc(reason or 'No structured policy explanation was stored for this invoice.')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with tabs[1]:
        st.dataframe(detail["items"] or [], use_container_width=True)
    with tabs[2]:
        audit_cols = st.columns(2, gap="large")
        with audit_cols[0]:
            section_title("System Events", "The ingestion and alert timeline captured in MySQL.")
            render_event_feed(detail["events"], "No audit events recorded yet.")
        with audit_cols[1]:
            section_title("Manual Review History", "Analyst actions written back from the work-order surface.")
            render_review_feed(detail["review_tasks"])
            if detail["sync"]:
                st.markdown(
                    f"""
                    <div class="panel-card">
                      <div class="panel-title">Feishu Sync Snapshot</div>
                      <div class="integration-message">{esc(json.dumps(detail['sync'], ensure_ascii=False))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
    with tabs[3]:
        json_cols = st.columns(2)
        with json_cols[0]:
            st.markdown("**Raw OCR JSON**")
            st.code(json.dumps(invoice.get("raw_ocr_json") or {}, ensure_ascii=False, indent=2), language="json")
        with json_cols[1]:
            st.markdown("**LLM Parsed JSON**")
            st.code(json.dumps(invoice.get("llm_json") or {}, ensure_ascii=False, indent=2), language="json")


def render_anomaly_form(cfg: Dict[str, Any]) -> None:
    db = db_client(cfg)
    query_invoice_id = st.query_params.get("invoice_id")
    default_invoice_id = int(query_invoice_id) if str(query_invoice_id or "").isdigit() else 1

    hero(
        "Risk Review Work Order",
        "A dedicated analyst workspace for resolving invoice anomalies, writing the decision back to MySQL, and preserving a review trace for auditability.",
        f"Port {cfg['ui_port']} | Writeback ready",
        badge("MANUAL REVIEW", "warn") + badge("DB COMMIT", "ok") + badge("AUDIT EVENT", "ok"),
    )

    top_cols = st.columns([0.45, 0.28, 0.27])
    with top_cols[0]:
        invoice_id = st.number_input("Invoice ID", min_value=1, step=1, value=default_invoice_id)
    with top_cols[1]:
        if st.button("Back to Dashboard", use_container_width=True):
            switch_view("dashboard", invoice_id=default_invoice_id)
    with top_cols[2]:
        st.markdown(f"[Open Risk Email]({mailpit_url()})")

    detail = fetch_invoice_detail(db, int(invoice_id))
    if not detail:
        st.warning("Invoice not found. Please enter a valid invoice ID.")
        return

    invoice = detail["invoice"]
    purchase_order_no = (
        str(st.query_params.get("purchase_order_no") or st.query_params.get("po_no") or "").strip()
        or str(invoice.get("purchase_order_no") or "").strip()
    )
    unique_hash = str(st.query_params.get("unique_hash") or invoice.get("unique_hash") or "").strip()

    metric_cols = st.columns(4)
    with metric_cols[0]:
        metric_card("Invoice Amount", fmt_money(invoice.get("total_amount_with_tax")), "Captured total from OCR and structured extraction.")
    with metric_cols[1]:
        metric_card("Expected Amount", fmt_money(invoice.get("expected_amount")), "Reference amount from the linked PO or source system.")
    with metric_cols[2]:
        metric_card("Delta", fmt_money(invoice.get("amount_diff")), "Absolute mismatch currently driving the alert.", "danger")
    with metric_cols[3]:
        metric_card("Current Status", str(invoice.get("invoice_status") or "-"), "This value will update immediately after submission.", "warn")

    left, right = st.columns([1.08, 0.92], gap="large")
    with left:
        section_title("Context Panel", "Identity, counterparty, and policy fields available before approval.")
        info_cols = st.columns(2)
        with info_cols[0]:
            info_card(
                "Invoice Core",
                [
                    ("Invoice code", invoice.get("invoice_code")),
                    ("Invoice number", invoice.get("invoice_number")),
                    ("Invoice date", fmt_dt(invoice.get("invoice_date"))[:10]),
                    ("PO number", purchase_order_no),
                    ("Unique hash", unique_hash),
                ],
            )
        with info_cols[1]:
            info_card(
                "Counterparty Signals",
                [
                    ("Seller", invoice.get("seller_name")),
                    ("Buyer", invoice.get("buyer_name")),
                    ("Risk flag", "HIGH" if safe_int(invoice.get("risk_flag")) == 1 else "NORMAL"),
                    ("Personal alert", invoice.get("notify_personal_status")),
                    ("Leader alert", invoice.get("notify_leader_status")),
                ],
            )
        st.markdown("**Line Items**")
        st.dataframe(detail["items"] or [], use_container_width=True)
        section_title("Event Feed", "What happened before the case reached the analyst desk.")
        render_event_feed(detail["events"], "No events recorded for this invoice.")
    with right:
        section_title("Action Center", "Submit the analyst decision and persist the result back into the workflow.")
        st.markdown(
            f"""
            <div class="panel-card">
              <div class="panel-title">Structured Risk Narrative</div>
              <div class="integration-message">{esc(invoice.get('risk_reason') or 'No structured risk reason stored.')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.form("anomaly_review_form"):
            handler_user = st.text_input("Handler", value=invoice.get("handler_user") or "")
            allowed_statuses = ["Pending", "Approved", "Rejected", "NeedsReview"]
            current_status = invoice.get("invoice_status") or "Pending"
            invoice_status = st.selectbox(
                "Review Result",
                allowed_statuses,
                index=allowed_statuses.index(current_status) if current_status in allowed_statuses else 0,
            )
            handler_reason = st.text_area(
                "Handling Note",
                value=invoice.get("handler_reason") or "",
                height=180,
                placeholder="Explain the decision, remediation, or escalation outcome for audit traceability.",
            )
            submitted = st.form_submit_button("Submit Review Decision", use_container_width=True)

        if submitted:
            update_invoice_review(
                db=db,
                invoice_id=int(invoice_id),
                purchase_order_no=purchase_order_no,
                unique_hash=unique_hash,
                handler_user=handler_user.strip(),
                handler_reason=handler_reason.strip(),
                invoice_status=invoice_status,
            )
            st.success("Review saved successfully. The case state and audit trail were written back to MySQL.")
            st.rerun()

        section_title("Recent Decisions", "Latest manual actions already recorded for this invoice.")
        render_review_feed(detail["review_tasks"])


def run_app(default_view: str = "dashboard") -> None:
    st.set_page_config(
        page_title="Invoice Intelligence Console",
        page_icon="I",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    cfg = load_cfg()

    query_view = st.query_params.get("view")
    current_view = str(query_view or default_view)

    with st.sidebar:
        st.markdown(
            """
            <div class="panel-card">
              <div class="hero-kicker">AIOPS FOR FINANCE</div>
              <div class="panel-title">Invoice Delivery Surface</div>
              <div class="integration-message">Built for demo recording, stakeholder reviews, and local product handoff.</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        sidebar_view = st.radio(
            "Workspace",
            options=["dashboard", "anomaly_form"],
            index=0 if current_view == "dashboard" else 1,
            format_func=lambda value: "Mission Control" if value == "dashboard" else "Review Desk",
        )
        if sidebar_view != current_view:
            switch_view(sidebar_view)

        st.markdown(
            f"""
            <div class="panel-card">
              <div class="panel-title">Runtime Topology</div>
              <div class="fact-grid">
                <div class="fact-row"><span>UI</span><strong>{esc(f"127.0.0.1:{cfg['ui_port']}")}</strong></div>
                <div class="fact-row"><span>OCR</span><strong>{esc(cfg['ocr_base_url'])}</strong></div>
                <div class="fact-row"><span>Mailpit</span><strong>{esc(mailpit_url())}</strong></div>
                <div class="fact-row"><span>MySQL</span><strong>{esc(f"{cfg['mysql_host']}:{cfg['mysql_port']}")}</strong></div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(f"[Mailpit Inbox]({mailpit_url()})")

    if current_view == "anomaly_form":
        render_anomaly_form(cfg)
    else:
        render_dashboard(cfg)


if __name__ == "__main__":
    run_app()
