from __future__ import annotations

from contextlib import contextmanager
import html
import json
import os
import sys
import textwrap
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


def fmt_day_label(value: Any) -> str:
    if value in (None, ""):
        return "-"
    text = str(value)
    return text[5:10] if len(text) >= 10 and text[4] == "-" and text[7] == "-" else text


def short_text(value: Any, limit: int = 160) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def compact_label(value: Any) -> str:
    text = str(value or "").replace("_", " ").strip()
    if not text:
        return "-"
    chars: List[str] = []
    for idx, char in enumerate(text):
        if idx and char.isupper() and text[idx - 1].islower():
            chars.append(" ")
        chars.append(char)
    compact = "".join(chars).strip()
    return compact[:1].upper() + compact[1:]


def risk_reason_label(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    normalized = "".join(char for char in text.lower() if char.isalnum())
    mapping = {
        "amountmismatchwithexpected": "Amount gap",
        "amountmismatch": "Amount gap",
        "sellernamemismatch": "Seller mismatch",
        "buyernamemismatch": "Buyer mismatch",
        "invoicedateearlierthanpo": "Invoice date before PO",
        "missingpo": "Missing PO",
        "purchaseordermissing": "Missing PO",
        "duplicateinvoice": "Possible duplicate",
        "duplicaterecord": "Possible duplicate",
        "taxidmismatch": "Tax ID mismatch",
    }
    if normalized in mapping:
        return mapping[normalized]
    lowered = text.lower()
    if "amount mismatch" in lowered:
        return "Amount gap"
    if "seller" in lowered and "mismatch" in lowered:
        return "Seller mismatch"
    if "buyer" in lowered and "mismatch" in lowered:
        return "Buyer mismatch"
    if "date" in lowered and "po" in lowered:
        return "Invoice date before PO"
    if "duplicate" in lowered:
        return "Possible duplicate"
    return compact_label(text)


def summarize_risk_reason(reason: Any, *, limit: int = 160, max_parts: int = 3) -> str:
    parts: List[str] = []

    def push(text: Any) -> None:
        label = risk_reason_label(text)
        if label != "-" and label not in parts and len(parts) < max_parts:
            parts.append(label)

    def walk(value: Any) -> None:
        if len(parts) >= max_parts or value in (None, ""):
            return
        decoded = decode_json(value)
        if isinstance(decoded, list):
            for item in decoded:
                if len(parts) >= max_parts:
                    break
                walk(item)
            return
        if isinstance(decoded, dict):
            for key in ("summary", "reason", "message", "rule", "type", "code"):
                if key in decoded:
                    walk(decoded.get(key))
                    if len(parts) >= max_parts:
                        break
            if not parts:
                push(json.dumps(decoded, ensure_ascii=False))
            return
        push(decoded)

    walk(reason)
    if not parts:
        return "-"
    return short_text("; ".join(parts), limit=limit)


def runtime_error_summary(error: Exception) -> str:
    text = str(error or "").strip()
    lower = text.lower()
    if "mysql" in lower and ("can't connect" in lower or "10061" in text or "connection refused" in lower):
        return "MySQL is not reachable on the configured host and port."
    if "httpconnectionpool" in lower or "connection refused" in lower:
        return "A local dependency is not reachable on its configured endpoint."
    if "smtp" in lower:
        return "SMTP is not reachable with the current configuration."
    return short_text(text, limit=180)


def clean_status_text(value: Any) -> str:
    text = str(value or "").replace("\r", " ").replace("\n", " ").strip()
    return " ".join(text.split())


def summarize_connector_status(name: str, status: str, message: Any, detail: Any) -> tuple[str, str]:
    raw_message = clean_status_text(message)
    raw_detail = clean_status_text(detail)
    combined = f"{raw_message} {raw_detail}".lower()
    key = str(name or "").strip().lower()
    connection_issue = any(
        token in combined
        for token in (
            "connection refused",
            "10061",
            "max retries exceeded",
            "failed to establish a new connection",
            "timed out",
            "timeout",
            "can't connect",
            "cannot connect",
            "unreachable",
        )
    )
    auth_issue = any(token in combined for token in ("401", "403", "unauthorized", "forbidden", "invalid credentials"))
    not_found_issue = "404" in combined or "not found" in combined
    missing_config = any(token in combined for token in ("not configured", "missing", "not set", "empty"))

    if status == "OK":
        ok_message = {
            "ocr": "Local OCR endpoint is reachable.",
            "dify": "Dify endpoint is responding.",
            "feishu": "Feishu integration settings look healthy.",
            "smtp": "SMTP transport is reachable.",
        }.get(key, "Service is responding normally.")
        ok_detail = {
            "ocr": raw_detail or raw_message or "Ready for extraction requests.",
            "dify": raw_detail or raw_message or "Ready for workflow calls.",
            "feishu": raw_detail or raw_message or "Ready for sync and alert traffic.",
            "smtp": raw_detail or raw_message or "Ready for outbound mail delivery.",
        }.get(key, raw_detail or raw_message or "No extra detail.")
        return ok_message, short_text(ok_detail, limit=96)

    if missing_config:
        config_detail = {
            "feishu": "Add the app id, secret, app token, and table id before syncing records.",
            "smtp": "Add the mail host, port, credentials, and sender settings.",
            "dify": "Add the base URL, workflow id, and API key.",
            "ocr": "Set the local OCR base URL and bring the service online.",
        }.get(key, "Add the required connection settings.")
        return "Configuration is incomplete.", config_detail

    if key == "ocr":
        if connection_issue:
            return "OCR service is offline.", "Start the local OCR service or container, then refresh the page."
        return "OCR health check did not pass.", short_text(raw_message or raw_detail or "Check the local OCR endpoint.", limit=96)

    if key == "dify":
        if auth_issue:
            return "Dify credentials were rejected.", "Verify the API key and workflow id configured for this workspace."
        if not_found_issue:
            return "Dify endpoint responded, but the target route was not found.", "Confirm the base URL and workflow id."
        if connection_issue:
            return "Dify endpoint is unreachable.", "Check outbound network access and the configured base URL."
        return "Dify health check did not pass.", short_text(raw_message or raw_detail or "Review the Dify configuration.", limit=96)

    if key == "feishu":
        if auth_issue:
            return "Feishu credentials were rejected.", "Recheck the app credentials and target table permissions."
        if not_found_issue:
            return "Feishu target resource was not found.", "Verify the app token and table id."
        if connection_issue:
            return "Feishu API is unreachable.", "Check outbound network access or proxy settings from this machine."
        return "Feishu health check did not pass.", short_text(raw_message or raw_detail or "Review the Feishu configuration.", limit=96)

    if key == "smtp":
        if auth_issue:
            return "SMTP credentials were rejected.", "Recheck the username, password, and encryption mode."
        if connection_issue:
            return "SMTP server is unreachable.", "Verify the host, port, and TLS or SSL settings."
        return "SMTP health check did not pass.", short_text(raw_message or raw_detail or "Review the SMTP configuration.", limit=96)

    if connection_issue:
        return "Service is unreachable.", "Check the configured host, port, and local runtime status."

    return raw_message or "Health check did not pass.", short_text(raw_detail or raw_message or "Review the connector configuration.", limit=96)


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


def render_html(markup: str) -> None:
    st.markdown(textwrap.dedent(markup).strip(), unsafe_allow_html=True)


def join_html_fragments(fragments: List[str]) -> str:
    return "".join(textwrap.dedent(fragment).strip() for fragment in fragments if str(fragment).strip())


def control_row(spec: List[float], gap: str = "small") -> List[Any]:
    return st.columns(spec, gap=gap)


def control_group_label(label: str, hint: str = "", badges_html: str = "") -> None:
    render_html(
        f"""
        <div class="control-field-head">
          <div>
            <div class="control-field-label">{esc(label)}</div>
            {'<div class="control-field-hint">' + esc(hint) + '</div>' if hint else ''}
          </div>
          <div class="control-field-meta">{badges_html}</div>
        </div>
        """
    )


@contextmanager
def control_shell(
    shell_class: str,
    *,
    kicker: str = "",
    title: str = "",
    copy: str = "",
    badges_html: str = "",
) -> Any:
    render_html(
        f"""
        <div class="control-shell {html.escape(shell_class, quote=True)}">
          <div class="control-shell-head">
            <div>
              {'<div class="control-shell-kicker">' + esc(kicker) + '</div>' if kicker else ''}
              {'<div class="control-shell-title">' + esc(title) + '</div>' if title else ''}
              {'<div class="control-shell-copy">' + esc(copy) + '</div>' if copy else ''}
            </div>
            <div class="control-shell-meta">{badges_html}</div>
          </div>
          <div class="control-shell-body">
        """
    )
    try:
        yield
    finally:
        render_html("</div></div>")


@contextmanager
def toolbar_shell(kicker: str, title: str, copy: str, badges_html: str = "") -> Any:
    with control_shell("control-shell-toolbar", kicker=kicker, title=title, copy=copy, badges_html=badges_html):
        yield


@contextmanager
def filter_shell(kicker: str, title: str, copy: str, badges_html: str = "") -> Any:
    with control_shell("control-shell-filter", kicker=kicker, title=title, copy=copy, badges_html=badges_html):
        yield


@contextmanager
def action_button_row(kicker: str, title: str, copy: str, badges_html: str = "") -> Any:
    with control_shell("control-shell-actions", kicker=kicker, title=title, copy=copy, badges_html=badges_html):
        yield


@contextmanager
def form_shell(kicker: str, title: str, copy: str, badges_html: str = "") -> Any:
    with control_shell("control-shell-form", kicker=kicker, title=title, copy=copy, badges_html=badges_html):
        yield


@contextmanager
def tab_shell(shell_class: str = "control-shell-tabs") -> Any:
    render_html(f'<div class="tab-shell {html.escape(shell_class, quote=True)}">')
    try:
        yield
    finally:
        render_html("</div>")


@contextmanager
def control_field(label: str, hint: str = "", badges_html: str = "", field_class: str = "") -> Any:
    if field_class:
        render_html(f'<div class="control-field-marker {html.escape(field_class, quote=True)}"></div>')
    try:
        control_group_label(label, hint, badges_html)
        yield
    finally:
        pass


def inject_theme() -> None:
    st.markdown(
        """
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Sora:wght@500;600;700&family=Manrope:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap');
        :root{
          --bg:#06111c; --panel:rgba(10,21,36,.74); --line:rgba(142,188,255,.16);
          --text:#ebf2fc; --muted:#93a7c3; --cyan:#7fe4ff; --teal:#5de1ca;
          --amber:#f0ba68; --red:#ff7c99; --blue:#90afff; --shadow:0 22px 62px rgba(0,0,0,.34);
        }
        .stApp{
          background:
            radial-gradient(circle at 18% 10%, rgba(127,228,255,.11), transparent 22%),
            radial-gradient(circle at 82% 14%, rgba(144,175,255,.10), transparent 24%),
            radial-gradient(circle at 50% 100%, rgba(93,225,202,.08), transparent 28%),
            linear-gradient(160deg, var(--bg) 0%, #091624 42%, #040a13 100%);
          color:var(--text);
          font-family:"Manrope","Segoe UI","Microsoft YaHei UI",sans-serif;
          letter-spacing:.002em;
        }
        .stApp:before{
          content:""; position:fixed; inset:0; pointer-events:none; opacity:.22;
          background-image:
            linear-gradient(rgba(123,164,220,.08) 1px, transparent 1px),
            linear-gradient(90deg, rgba(123,164,220,.08) 1px, transparent 1px);
          background-size:42px 42px;
          mask-image:radial-gradient(circle at center, rgba(0,0,0,.92), transparent 84%);
          -webkit-mask-image:radial-gradient(circle at center, rgba(0,0,0,.92), transparent 84%);
        }
        header[data-testid="stHeader"]{background:transparent;height:0;}
        [data-testid="stToolbar"], .stDeployButton, #MainMenu, footer{display:none !important;}
        .block-container{max-width:1560px;padding-top:1.1rem;padding-bottom:2.45rem;padding-left:1.35rem;padding-right:1.35rem;}
        h1,h2,h3,h4{font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;color:var(--text);letter-spacing:-.02em;}
        [data-testid="stSidebar"]{
          background:linear-gradient(180deg, rgba(8,16,28,.98), rgba(10,22,37,.96));
          border-right:1px solid var(--line);
          min-width:290px !important;
          max-width:290px !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{padding-top:.65rem;}
        [data-testid="stSidebar"] *{color:var(--text);}
        [data-testid="stSidebar"] label[data-testid="stWidgetLabel"]{display:none;}
        [data-testid="stSidebar"] .stRadio > div{gap:.5rem;}
        [data-testid="stSidebar"] .stRadio [role="radiogroup"]{display:grid;gap:.55rem;}
        [data-testid="stSidebar"] .stRadio label{
          margin:0 !important;
          padding:.82rem .92rem;
          border-radius:16px;
          border:1px solid rgba(120,166,255,.11);
          background:linear-gradient(180deg, rgba(9,20,34,.84), rgba(7,14,24,.98));
        }
        [data-testid="stSidebar"] .stRadio label:has(input:checked){
          border-color:rgba(127,228,255,.24);
          box-shadow:0 10px 28px rgba(87,217,255,.12);
          background:linear-gradient(180deg, rgba(11,28,48,.96), rgba(7,15,26,.98));
        }
        .hero-shell,.metric-card,.panel-card,.timeline-card{
          border:1px solid var(--line); background:linear-gradient(180deg,var(--panel),rgba(7,16,29,.96));
          box-shadow:var(--shadow); border-radius:24px;
        }
        .hero-shell,.metric-card,.panel-card,.timeline-card,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.hero-side{
          backdrop-filter:blur(18px);
          -webkit-backdrop-filter:blur(18px);
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
        }
        .metric-card,.panel-card,.timeline-card,.day-chip,.hero-side,.ops-chip,.flow-card,.quick-link{
          transition:transform .22s ease, border-color .22s ease, box-shadow .22s ease;
        }
        .metric-card:hover,.panel-card:hover,.timeline-card:hover,.day-chip:hover,.hero-side:hover,.ops-chip:hover,.flow-card:hover,.quick-link:hover{
          transform:translateY(-2px);
          border-color:rgba(87,217,255,.28);
          box-shadow:0 22px 58px rgba(0,0,0,.36);
        }
        .hero-shell{display:grid;grid-template-columns:1.6fr .82fr;gap:1rem;padding:1.85rem 1.85rem 1.72rem;margin-bottom:1.05rem;position:relative;overflow:hidden;}
        .hero-shell:before,.hero-shell:after{
          content:""; position:absolute; width:220px; height:220px; border-radius:999px; filter:blur(10px); animation:floatGlow 8s ease-in-out infinite;
        }
        .hero-shell:before{right:-80px; top:-80px; background:radial-gradient(circle, rgba(127,228,255,.18), transparent 68%);}
        .hero-shell:after{left:-95px; bottom:-120px; background:radial-gradient(circle, rgba(144,175,255,.14), transparent 70%);}
        @keyframes floatGlow{0%,100%{transform:translateY(0)}50%{transform:translateY(12px)}}
        .hero-kicker,.section-kicker,.hero-side-label,.metric-label,.ops-label,.briefing-kicker,.quick-link-kicker,.day-chip-label{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.74rem; letter-spacing:.14em; color:var(--cyan); font-weight:600; text-transform:uppercase;
        }
        .hero-shell h1{margin:.42rem 0 .62rem; font-size:2.7rem; line-height:1.02; max-width:15ch;}
        .hero-shell p{margin:0; color:var(--muted); max-width:58rem; line-height:1.78; font-size:1.03rem;}
        .hero-badges{display:flex; gap:.6rem; flex-wrap:wrap; margin-top:1.15rem;}
        .hero-side{background:linear-gradient(180deg, rgba(10,24,41,.68), rgba(8,18,30,.88)); border:1px solid rgba(127,228,255,.12); border-radius:22px; padding:1.3rem 1.28rem; display:flex; flex-direction:column; justify-content:space-between;}
        .hero-side-value{font-family:"Sora",sans-serif;font-size:1.95rem;font-weight:700;margin:.38rem 0 .45rem;letter-spacing:-.03em;}
        .hero-side-caption{color:var(--muted);line-height:1.6;}
        .nav-shell{display:grid;gap:.85rem;margin-bottom:.9rem;}
        .nav-brand{padding:1.1rem 1.08rem;border-radius:20px;border:1px solid rgba(127,228,255,.12);background:linear-gradient(180deg, rgba(10,24,41,.72), rgba(7,15,26,.98));}
        .nav-title{font-family:"Sora",sans-serif;font-size:1.45rem;font-weight:700;line-height:1.15;letter-spacing:-.03em;margin:.4rem 0 .38rem;}
        .nav-copy{color:var(--muted);line-height:1.6;font-size:.92rem;}
        .nav-meta{display:grid;gap:.55rem;}
        .nav-meta-row{display:flex;justify-content:space-between;gap:.8rem;padding:.68rem .76rem;border-radius:14px;background:rgba(120,166,255,.045);border:1px solid rgba(120,166,255,.08);}
        .nav-meta-row span{color:var(--muted);font-size:.9rem;}
        .nav-meta-row strong{font-weight:600;color:var(--text);}
        .section-head{display:flex;justify-content:space-between;gap:1rem;align-items:center;margin:1rem 0 .95rem;padding-top:.25rem;border-top:1px solid rgba(142,188,255,.08);}
        .section-head h3{margin:.28rem 0 0;font-size:1.18rem;}
        .section-head p{margin:0;max-width:31rem;color:var(--muted);font-size:.93rem;line-height:1.7;}
        .metric-card{padding:1.18rem 1.22rem 1.1rem; min-height:146px; display:flex; flex-direction:column; justify-content:space-between; position:relative; overflow:hidden;}
        .metric-label{color:var(--muted);}
        .metric-value{font-family:"Sora",sans-serif;font-size:1.95rem;font-weight:700;margin:.46rem 0 .28rem;letter-spacing:-.03em;}
        .metric-note{color:#bfd2ed;line-height:1.5;}
        .tone-ok{box-shadow:0 18px 52px rgba(22,132,104,.18);}
        .tone-warn{box-shadow:0 18px 52px rgba(191,121,30,.18);}
        .tone-danger{box-shadow:0 18px 52px rgba(170,58,86,.20);}
        .panel-card,.timeline-card{padding:1.1rem 1.15rem; margin-bottom:.95rem; position:relative; overflow:hidden;}
        .metric-card:before,.panel-card:before,.timeline-card:before,.signal-card:before{
          content:""; position:absolute; left:0; right:0; top:0; height:1px; background:linear-gradient(90deg, rgba(255,255,255,.12), transparent 55%);
        }
        .panel-title{font-family:"Sora",sans-serif;font-size:1rem;font-weight:600;margin-bottom:.78rem;letter-spacing:-.01em;}
        .fact-grid{display:grid;gap:.58rem;}
        .fact-row{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:1rem;padding:.68rem .76rem;border-radius:15px;background:rgba(120,166,255,.045);border:1px solid rgba(120,166,255,.08);}
        .fact-row span{color:var(--muted);}
        .fact-row strong{font-weight:600;color:var(--text);text-align:right;max-width:28ch;line-height:1.45;}
        .badge{display:inline-flex;align-items:center;justify-content:center;padding:.36rem .78rem;border-radius:999px;font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase;border:1px solid transparent;}
        .badge-ok{background:rgba(44,243,199,.14);color:#9cfce8;border-color:rgba(44,243,199,.26);}
        .badge-warn{background:rgba(255,183,74,.14);color:#ffd38c;border-color:rgba(255,183,74,.24);}
        .badge-danger{background:rgba(255,109,138,.14);color:#ffb4c1;border-color:rgba(255,109,138,.24);}
        .badge-neutral{background:rgba(120,166,255,.12);color:#b7ceff;border-color:rgba(120,166,255,.2);}
        .ops-ribbon{display:grid;grid-template-columns:repeat(auto-fit,minmax(175px,1fr));gap:.85rem;margin:.15rem 0 1.05rem;}
        .ops-chip{position:relative;overflow:hidden;padding:.96rem 1.02rem;border-radius:18px;border:1px solid rgba(120,166,255,.13);background:linear-gradient(180deg, rgba(9,22,37,.88), rgba(7,14,26,.98));}
        .ops-chip:after{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg, rgba(120,166,255,.45), rgba(87,217,255,.22));}
        .ops-ok:after{background:linear-gradient(90deg, rgba(44,243,199,.76), rgba(87,217,255,.34));}
        .ops-warn:after{background:linear-gradient(90deg, rgba(255,183,74,.86), rgba(255,122,61,.32));}
        .ops-danger:after{background:linear-gradient(90deg, rgba(255,109,138,.88), rgba(255,183,74,.28));}
        .ops-value{font-family:"Sora",sans-serif;font-size:1.38rem;font-weight:700;margin:.32rem 0 .2rem;letter-spacing:-.025em;}
        .ops-note{color:#c5d8f2;font-size:.9rem;line-height:1.45;}
        .flow-grid{display:grid;gap:.7rem;}
        .flow-card{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:.82rem;padding:.84rem .94rem;border-radius:18px;border:1px solid rgba(120,166,255,.11);background:linear-gradient(180deg, rgba(10,22,38,.8), rgba(6,14,24,.96));}
        .flow-step{width:34px;height:34px;border-radius:999px;display:flex;align-items:center;justify-content:center;font-family:"Sora",sans-serif;font-weight:700;background:rgba(120,166,255,.18);color:var(--text);}
        .flow-title{font-family:"Sora",sans-serif;font-size:.97rem;font-weight:600;}
        .flow-copy{color:var(--muted);font-size:.87rem;line-height:1.45;margin-top:.18rem;}
        .flow-tail{width:10px;height:10px;border-radius:999px;background:rgba(120,166,255,.36);box-shadow:0 0 0 6px rgba(120,166,255,.08);}
        .flow-tail-ok{background:rgba(44,243,199,.92);box-shadow:0 0 0 6px rgba(44,243,199,.10);}
        .flow-tail-warn{background:rgba(255,183,74,.92);box-shadow:0 0 0 6px rgba(255,183,74,.10);}
        .flow-tail-danger{background:rgba(255,109,138,.92);box-shadow:0 0 0 6px rgba(255,109,138,.10);}
        .quick-links{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.7rem;}
        .quick-link{text-decoration:none !important;display:block;padding:1rem 1.02rem;border-radius:18px;border:1px solid rgba(120,166,255,.12);background:linear-gradient(180deg, rgba(9,20,34,.92), rgba(7,14,24,.98));min-height:120px;}
        .quick-link-title{display:block;font-family:"Sora",sans-serif;font-size:1rem;font-weight:600;color:var(--text);margin:.4rem 0 .36rem;letter-spacing:-.01em;}
        .quick-link-copy{display:block;color:var(--muted);line-height:1.48;}
        .panel-callout{padding:1rem 1.05rem;border-radius:18px;border:1px solid rgba(127,228,255,.14);background:linear-gradient(180deg, rgba(10,24,41,.72), rgba(7,15,26,.98));margin:.15rem 0 .95rem;}
        .panel-callout-title{font-family:"Sora",sans-serif;font-size:.96rem;font-weight:600;margin-bottom:.25rem;}
        .panel-callout-copy{color:var(--muted);line-height:1.58;}
        .micro-note{color:var(--muted);font-size:.88rem;line-height:1.55;margin:.25rem 0 .7rem;}
        .command-shell,.focus-shell,.checklist-shell{
          position:relative; overflow:hidden; margin:.2rem 0 1rem; padding:1.15rem 1.18rem 1.1rem;
          border:1px solid rgba(120,166,255,.14); border-radius:24px;
          background:linear-gradient(180deg, rgba(10,24,41,.88), rgba(6,12,22,.98));
          backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
        }
        .command-shell:before,.focus-shell:before,.checklist-shell:before{
          content:""; position:absolute; left:0; right:0; top:0; height:1px;
          background:linear-gradient(90deg, rgba(255,255,255,.16), transparent 52%);
        }
        .command-shell,.focus-shell{display:grid;grid-template-columns:1.05fr .95fr;gap:1rem;align-items:start;}
        .command-kicker,.focus-kicker,.checklist-kicker{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.74rem; letter-spacing:.14em; color:var(--cyan); font-weight:600; text-transform:uppercase;
        }
        .command-title,.focus-title,.checklist-title{
          font-family:"Sora",sans-serif; font-size:1.3rem; font-weight:700; line-height:1.15;
          margin:.42rem 0 .45rem; letter-spacing:-.03em; color:var(--text);
        }
        .command-copy,.focus-copy{color:var(--muted); line-height:1.68; max-width:44rem;}
        .command-pillrow,.focus-badges{display:flex; flex-wrap:wrap; gap:.55rem; margin-top:1rem;}
        .command-stats,.focus-grid{display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:.75rem;}
        .command-stat,.focus-metric{
          position:relative; overflow:hidden; padding:.9rem .94rem; border-radius:18px;
          border:1px solid rgba(120,166,255,.12); background:rgba(7,17,29,.78);
        }
        .command-stat:before,.focus-metric:before{
          content:""; position:absolute; left:0; right:0; top:0; height:3px;
          background:linear-gradient(90deg, var(--accent), rgba(255,255,255,.08));
        }
        .command-stat-label,.focus-metric-label{color:var(--muted); font-size:.84rem; line-height:1.45;}
        .command-stat-value,.focus-metric-value{
          font-family:"Sora",sans-serif; font-size:1.42rem; font-weight:700;
          margin:.32rem 0 .22rem; letter-spacing:-.03em;
        }
        .command-stat-note,.focus-metric-note{color:#c7d8ef; font-size:.88rem; line-height:1.48;}
        .focus-note{
          margin-top:.78rem; padding:.92rem .98rem; border-radius:18px;
          border:1px solid rgba(127,228,255,.14); background:rgba(9,21,35,.78);
        }
        .focus-note-title{font-family:"Sora",sans-serif; font-size:.95rem; font-weight:600; margin-bottom:.24rem;}
        .focus-note-copy{color:var(--muted); line-height:1.58;}
        .checklist-shell{display:block;}
        .checklist-grid{display:grid; gap:.72rem; margin-top:.95rem;}
        .checklist-item{
          display:grid; grid-template-columns:34px 1fr; gap:.8rem; align-items:start;
          padding:.8rem .84rem; border-radius:18px; border:1px solid rgba(120,166,255,.12); background:rgba(7,17,29,.78);
        }
        .checklist-index{
          width:34px; height:34px; border-radius:999px; display:flex; align-items:center; justify-content:center;
          font-family:"Sora",sans-serif; font-weight:700; color:var(--text); background:rgba(120,166,255,.18);
        }
        .checklist-item-title{font-family:"Sora",sans-serif; font-size:.95rem; font-weight:600; margin-bottom:.18rem; letter-spacing:-.01em;}
        .checklist-item-copy{color:var(--muted); line-height:1.52; font-size:.9rem;}
        .dashboard-band{display:grid;grid-template-columns:1.04fr 1fr .92fr;gap:.9rem;margin-bottom:1rem;align-items:start;}
        .surface-stack{display:grid;gap:.9rem;}
        .action-row{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:.8rem;}
        .signal-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:.85rem;}
        .signal-card{padding:1.03rem 1.06rem;border-radius:22px;border:1px solid rgba(120,166,255,.13);background:linear-gradient(180deg, rgba(9,21,35,.94), rgba(6,12,22,.98));}
        .signal-top{display:flex;justify-content:space-between;gap:.75rem;align-items:flex-start;margin-bottom:.9rem;}
        .signal-label{font-family:"Sora",sans-serif;font-size:1rem;font-weight:600;letter-spacing:-.01em;}
        .signal-main{display:grid;grid-template-columns:94px 1fr;gap:1rem;align-items:center;}
        .signal-ring{position:relative;width:94px;height:94px;border-radius:999px;display:flex;align-items:center;justify-content:center;background:
          radial-gradient(circle at center, rgba(6,14,24,.96) 0 52%, transparent 53%),
          conic-gradient(var(--signal-color) calc(var(--signal-pct) * 1%), rgba(120,166,255,.12) 0);}
        .signal-ring:after{content:"";position:absolute;inset:8px;border-radius:999px;border:1px solid rgba(120,166,255,.14);background:rgba(6,14,24,.94);}
        .signal-center{position:relative;z-index:1;font-family:"Sora",sans-serif;font-size:1rem;font-weight:700;}
        .signal-value{font-family:"Sora",sans-serif;font-size:1.46rem;font-weight:700;margin-bottom:.18rem;letter-spacing:-.03em;}
        .signal-note{color:#d6e5fb;line-height:1.45;}
        .signal-detail{color:var(--muted);font-size:.84rem;line-height:1.48;margin-top:.28rem;}
        .briefing-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:.8rem;}
        .briefing-card{position:relative;overflow:hidden;padding:1rem 1.05rem;border-radius:20px;border:1px solid rgba(120,166,255,.13);background:linear-gradient(180deg, rgba(10,22,38,.88), rgba(7,14,24,.98));}
        .briefing-card:before{content:"";position:absolute;left:0;right:0;top:0;height:3px;background:linear-gradient(90deg, var(--accent), rgba(255,255,255,.08));}
        .briefing-value{font-family:"Sora",sans-serif;font-size:1.07rem;font-weight:600;line-height:1.44;margin:.45rem 0 .38rem;word-break:break-word;letter-spacing:-.01em;}
        .briefing-note{color:var(--muted);line-height:1.5;font-size:.9rem;}
        .integration-top,.timeline-top,.spotlight-top{display:flex;justify-content:space-between;gap:.75rem;align-items:start;}
        .integration-message,.timeline-body,.spotlight-reason{color:#d6e5fb;line-height:1.65;}
        .integration-detail,.timeline-meta,.spotlight-meta{color:var(--muted);font-size:.86rem;margin-top:.45rem;}
        .spotlight-vendor{color:var(--muted);}
        .spotlight-amount{font-family:"Sora",sans-serif;font-size:1.5rem;font-weight:700;margin:.75rem 0 .25rem;letter-spacing:-.03em;}
        .activity-strip{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:.8rem;margin-bottom:.6rem;}
        .day-chip{padding:.92rem 1rem;border-radius:18px;border:1px solid rgba(127,228,255,.11);background:linear-gradient(180deg, rgba(9,21,36,.84), rgba(8,15,26,.96));}
        .day-chip-value{font-family:"Sora",sans-serif;font-size:1.42rem;font-weight:700;margin:.45rem 0 .15rem;letter-spacing:-.03em;}
        .day-chip-sub{color:#b8cae3;font-size:.88rem;}
        .timeline-card{padding:1rem 1.05rem; margin-bottom:.75rem;}
        [data-testid="stWidgetLabel"] p,[data-testid="stMarkdownContainer"] p{font-size:.95rem;}
        .stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{
          background:rgba(7,18,30,.92) !important; border:1px solid rgba(120,166,255,.15) !important; border-radius:16px !important; color:var(--text) !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.02) !important;
        }
        .stButton > button,.stDownloadButton > button,.stFormSubmitButton > button{
          border:none; border-radius:16px; padding:.72rem 1rem; font-weight:700;
          background:linear-gradient(90deg, var(--cyan), var(--blue)); color:#04101d; box-shadow:0 14px 34px rgba(87,217,255,.18);
        }
        .stButton > button:hover,.stDownloadButton > button:hover,.stFormSubmitButton > button:hover{
          box-shadow:0 16px 42px rgba(87,217,255,.24);
          filter:brightness(1.03);
        }
        div[data-testid="stForm"]{
          border:1px solid rgba(120,166,255,.12);
          border-radius:22px;
          padding:1rem 1.05rem 1.1rem;
          background:linear-gradient(180deg, rgba(9,21,35,.88), rgba(6,12,22,.98));
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
        }
        .stCheckbox label,.stRadio label,.stCaption,.stMarkdown p{color:var(--muted);}
        .stTabs [data-baseweb="tab-list"]{gap:.45rem;padding:.2rem;border-radius:16px;background:rgba(8,18,31,.55);border:1px solid rgba(120,166,255,.08);}
        .stTabs [data-baseweb="tab"]{background:rgba(9,20,34,.72); border:1px solid rgba(120,166,255,.1); border-radius:13px; color:var(--text); padding:.58rem .98rem; font-weight:600;}
        .stTabs [aria-selected="true"]{background:linear-gradient(90deg, rgba(127,228,255,.16), rgba(144,175,255,.18)); border-color:rgba(127,228,255,.16);}
        .stDataFrame, .stTable{border:1px solid rgba(120,166,255,.12);border-radius:18px;overflow:hidden;}
        [data-testid="stCodeBlock"]{border:1px solid rgba(120,166,255,.12);border-radius:18px;overflow:hidden;}
        .surface-intro{
          position:relative; overflow:hidden; margin:.2rem 0 .78rem; padding:1rem 1.05rem;
          border:1px solid rgba(145,164,192,.14); border-radius:22px;
          background:linear-gradient(180deg, rgba(13,23,36,.92), rgba(10,18,29,.98));
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
        }
        .surface-intro:before{
          content:""; position:absolute; left:0; right:0; top:0; height:1px;
          background:linear-gradient(90deg, rgba(255,255,255,.16), transparent 56%);
        }
        .surface-intro-grid{display:grid; grid-template-columns:1.18fr .82fr; gap:1rem; align-items:start;}
        .surface-kicker{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.73rem; letter-spacing:.14em; color:var(--blue); font-weight:600; text-transform:uppercase;
        }
        .surface-title{
          font-family:"Sora",sans-serif; font-size:1.08rem; font-weight:600;
          letter-spacing:-.02em; margin:.38rem 0 .24rem; color:var(--text);
        }
        .surface-copy{color:var(--muted); line-height:1.62; max-width:46rem; font-size:.92rem;}
        .surface-meta{display:flex; flex-wrap:wrap; gap:.55rem; justify-content:flex-end;}
        div[data-testid="stAlert"]{
          border:1px solid rgba(145,164,192,.16);
          border-radius:18px;
          background:linear-gradient(180deg, rgba(14,24,38,.92), rgba(10,17,28,.98));
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
        }
        :root{
          --bg:#08111b; --panel:rgba(14,24,38,.86); --line:rgba(145,164,192,.14);
          --text:#f5f8ff; --muted:#9eb0c8; --cyan:#a6cbff; --teal:#92e0d1;
          --amber:#efc37f; --red:#ef8aa6; --blue:#8eb4ff; --shadow:0 18px 48px rgba(2,8,18,.34);
        }
        .stApp{
          background:
            radial-gradient(circle at 12% 0%, rgba(142,180,255,.15), transparent 22%),
            radial-gradient(circle at 100% 0%, rgba(146,224,209,.10), transparent 18%),
            linear-gradient(180deg, #0d1724 0%, #08111b 36%, #09121d 100%);
        }
        .stApp:before{
          opacity:.08;
          background:
            linear-gradient(180deg, rgba(255,255,255,.05), transparent 18%),
            radial-gradient(circle at top, rgba(255,255,255,.05), transparent 58%);
          background-size:auto;
          mask-image:none;
          -webkit-mask-image:none;
        }
        .hero-shell,.metric-card,.panel-card,.timeline-card,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.hero-side,.command-shell,.focus-shell,.checklist-shell{
          border-color:rgba(145,164,192,.14);
          box-shadow:0 18px 48px rgba(2,8,18,.30), inset 0 1px 0 rgba(255,255,255,.03);
        }
        .metric-card,.panel-card,.timeline-card,.day-chip,.hero-side,.ops-chip,.flow-card,.quick-link,.command-shell,.focus-shell,.checklist-shell{
          transition:transform .22s ease, border-color .22s ease, box-shadow .22s ease, background-color .22s ease;
        }
        .metric-card:hover,.panel-card:hover,.timeline-card:hover,.day-chip:hover,.hero-side:hover,.ops-chip:hover,.flow-card:hover,.quick-link:hover{
          transform:translateY(-1px);
          border-color:rgba(166,203,255,.24);
          box-shadow:0 18px 42px rgba(2,8,18,.34);
        }
        .hero-shell{
          background:linear-gradient(180deg, rgba(16,28,43,.92), rgba(11,20,32,.98));
          border-radius:28px;
        }
        .hero-shell:before{background:radial-gradient(circle, rgba(142,180,255,.15), transparent 70%);}
        .hero-shell:after{background:radial-gradient(circle, rgba(146,224,209,.10), transparent 72%);}
        .hero-shell h1{font-size:2.52rem; line-height:1.04; max-width:16ch;}
        .hero-shell p,.command-copy,.focus-copy,.panel-callout-copy,.ops-note,.briefing-note,.quick-link-copy,.integration-message,.timeline-body,.focus-note-copy{color:#b6c5d8;}
        .hero-kicker,.section-kicker,.hero-side-label,.metric-label,.ops-label,.briefing-kicker,.quick-link-kicker,.day-chip-label,.command-kicker,.focus-kicker,.checklist-kicker{
          letter-spacing:.12em;
          color:var(--blue);
        }
        .hero-side,.command-shell,.focus-shell,.checklist-shell,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.metric-card,.panel-card,.timeline-card,.surface-intro{
          background:linear-gradient(180deg, rgba(15,27,42,.90), rgba(10,18,29,.98));
        }
        .nav-brand{
          background:linear-gradient(180deg, rgba(16,28,43,.92), rgba(11,20,32,.98));
          border-color:rgba(145,164,192,.14);
        }
        .nav-meta-row,.fact-row,.command-stat,.focus-metric,.checklist-item{
          background:rgba(255,255,255,.028);
          border-color:rgba(145,164,192,.13);
        }
        .hero-side-caption,.nav-copy,.nav-meta-row span,.fact-row span,.surface-copy,.micro-note,.signal-detail,.integration-detail,.timeline-meta,.spotlight-meta,.day-chip-sub{color:#9eb0c8;}
        .badge{
          border-color:rgba(255,255,255,.05);
          box-shadow:inset 0 1px 0 rgba(255,255,255,.05);
        }
        .badge-ok{background:rgba(146,224,209,.10); color:#baf0e3; border-color:rgba(146,224,209,.18);}
        .badge-warn{background:rgba(239,195,127,.12); color:#f6d9a8; border-color:rgba(239,195,127,.20);}
        .badge-danger{background:rgba(239,138,166,.12); color:#f7b7c8; border-color:rgba(239,138,166,.20);}
        .badge-neutral{background:rgba(142,180,255,.12); color:#c7dbff; border-color:rgba(142,180,255,.20);}
        .stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{
          background:rgba(8,16,26,.96) !important;
          border:1px solid rgba(145,164,192,.16) !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.02), 0 0 0 1px rgba(0,0,0,.04) !important;
        }
        .stButton > button,.stDownloadButton > button,.stFormSubmitButton > button{
          background:linear-gradient(180deg, #c0d4ff, #8fb3ff);
          color:#09111b;
          box-shadow:0 12px 26px rgba(116,147,207,.22);
        }
        .stButton > button:hover,.stDownloadButton > button:hover,.stFormSubmitButton > button:hover{
          box-shadow:0 14px 30px rgba(116,147,207,.28);
          filter:brightness(1.02);
        }
        .stTabs [data-baseweb="tab-list"]{
          background:rgba(13,23,36,.72);
          border-color:rgba(145,164,192,.10);
        }
        .stTabs [data-baseweb="tab"]{
          background:rgba(255,255,255,.02);
          border-color:rgba(145,164,192,.10);
        }
        .stTabs [aria-selected="true"]{
          background:linear-gradient(180deg, rgba(142,180,255,.18), rgba(142,180,255,.08));
          border-color:rgba(142,180,255,.18);
          box-shadow:inset 0 1px 0 rgba(255,255,255,.04);
        }
        .stDataFrame,.stTable,div[data-testid="stDataFrame"],[data-testid="stCodeBlock"]{
          border-color:rgba(145,164,192,.14) !important;
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.03);
          background:linear-gradient(180deg, rgba(15,27,42,.92), rgba(10,18,29,.98));
        }
        :root{
          --bg:#f3f7fb; --panel:rgba(255,255,255,.94); --line:rgba(134,153,176,.20);
          --text:#142338; --muted:#65748a; --cyan:#4f7cff; --teal:#0f9d8a;
          --amber:#b7791f; --red:#cc5a7a; --blue:#5d7cff; --shadow:0 16px 40px rgba(24,52,92,.08);
        }
        .stApp{
          background:
            radial-gradient(circle at 0% 0%, rgba(93,124,255,.13), transparent 26%),
            radial-gradient(circle at 100% 0%, rgba(15,157,138,.08), transparent 18%),
            linear-gradient(180deg, #fbfcfe 0%, #f4f7fb 44%, #eef3f8 100%) !important;
          color:var(--text) !important;
        }
        .stApp:before{
          opacity:.36;
          background-image:
            linear-gradient(rgba(128,151,183,.05) 1px, transparent 1px),
            linear-gradient(90deg, rgba(128,151,183,.05) 1px, transparent 1px);
          background-size:64px 64px;
          mask-image:linear-gradient(rgba(0,0,0,.94), transparent 90%);
          -webkit-mask-image:linear-gradient(rgba(0,0,0,.94), transparent 90%);
        }
        h1,h2,h3,h4,.surface-title,.command-title,.focus-title,.checklist-title,.nav-title,.panel-title,.signal-label,.flow-title,.checklist-item-title{
          color:var(--text) !important;
        }
        [data-testid="stSidebar"]{
          background:linear-gradient(180deg, #fbfcfe, #f4f7fb) !important;
          border-right:1px solid rgba(134,153,176,.18) !important;
        }
        [data-testid="stSidebar"] *{color:var(--text) !important;}
        [data-testid="stSidebar"] .stRadio label{
          background:#ffffff !important;
          border:1px solid rgba(134,153,176,.16) !important;
          box-shadow:0 8px 20px rgba(24,52,92,.04) !important;
        }
        [data-testid="stSidebar"] .stRadio label:has(input:checked){
          background:linear-gradient(180deg, #f7faff, #eef4ff) !important;
          border-color:rgba(93,124,255,.28) !important;
          box-shadow:0 10px 24px rgba(79,124,255,.10) !important;
        }
        .hero-shell,.metric-card,.panel-card,.timeline-card,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.hero-side,.command-shell,.focus-shell,.checklist-shell,.surface-intro,.day-chip{
          border:1px solid rgba(134,153,176,.18) !important;
          background:linear-gradient(180deg, rgba(255,255,255,.98), rgba(248,250,253,.96)) !important;
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.92) !important;
        }
        .hero-shell{
          background:linear-gradient(135deg, #ffffff 0%, #f7faff 58%, #eef4ff 100%) !important;
          border-radius:28px;
        }
        .hero-shell:before{background:radial-gradient(circle, rgba(93,124,255,.14), transparent 70%) !important;}
        .hero-shell:after{background:radial-gradient(circle, rgba(15,157,138,.10), transparent 70%) !important;}
        .hero-shell p,.command-copy,.focus-copy,.panel-callout-copy,.ops-note,.briefing-note,.quick-link-copy,.integration-message,.timeline-body,.focus-note-copy,.signal-note{
          color:#55677f !important;
        }
        .hero-kicker,.section-kicker,.hero-side-label,.metric-label,.ops-label,.briefing-kicker,.quick-link-kicker,.day-chip-label,.command-kicker,.focus-kicker,.checklist-kicker,.surface-kicker{
          color:var(--blue) !important;
          letter-spacing:.12em;
        }
        .hero-side,.nav-brand{
          background:linear-gradient(180deg, #ffffff, #f5f8fd) !important;
        }
        .nav-brand{border-color:rgba(134,153,176,.18) !important;}
        .nav-copy,.hero-side-caption,.nav-meta-row span,.fact-row span,.surface-copy,.micro-note,.signal-detail,.integration-detail,.timeline-meta,.spotlight-meta,.day-chip-sub,.spotlight-vendor{
          color:#6d7e95 !important;
        }
        .nav-meta-row,.fact-row,.command-stat,.focus-metric,.checklist-item{
          background:rgba(93,124,255,.028) !important;
          border-color:rgba(134,153,176,.16) !important;
        }
        .metric-note,.command-stat-note,.focus-metric-note{color:#607088 !important;}
        .badge{
          box-shadow:none !important;
          border-width:1px !important;
        }
        .badge-ok{background:#e8f7f4 !important;color:#0b7d73 !important;border-color:#bde8de !important;}
        .badge-warn{background:#fbf2de !important;color:#9b6a14 !important;border-color:#ecd7a5 !important;}
        .badge-danger{background:#fdebf1 !important;color:#b5466a !important;border-color:#f3bfd0 !important;}
        .badge-neutral{background:#edf2ff !important;color:#4866c9 !important;border-color:#cdd8ff !important;}
        .ops-chip:after{opacity:.75;}
        .flow-step,.checklist-index{
          background:rgba(93,124,255,.10) !important;
          color:#3556bc !important;
        }
        .flow-tail{background:rgba(93,124,255,.45) !important;box-shadow:0 0 0 6px rgba(93,124,255,.08) !important;}
        .flow-tail-ok{background:#0f9d8a !important;box-shadow:0 0 0 6px rgba(15,157,138,.08) !important;}
        .flow-tail-warn{background:#d39a33 !important;box-shadow:0 0 0 6px rgba(211,154,51,.08) !important;}
        .flow-tail-danger{background:#cc5a7a !important;box-shadow:0 0 0 6px rgba(204,90,122,.08) !important;}
        .signal-ring{
          background:
            radial-gradient(circle at center, #ffffff 0 52%, transparent 53%),
            conic-gradient(var(--signal-color) calc(var(--signal-pct) * 1%), rgba(93,124,255,.12) 0) !important;
        }
        .signal-ring:after{
          border-color:rgba(134,153,176,.16) !important;
          background:#ffffff !important;
        }
        .spotlight-amount,.metric-value,.command-stat-value,.focus-metric-value,.hero-side-value,.ops-value,.day-chip-value,.signal-value{
          color:var(--text) !important;
        }
        .stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{
          background:#ffffff !important;
          color:var(--text) !important;
          border:1px solid rgba(134,153,176,.22) !important;
          box-shadow:0 1px 2px rgba(24,52,92,.04), inset 0 1px 0 rgba(255,255,255,.95) !important;
        }
        .stTextInput input:focus,.stNumberInput input:focus,.stTextArea textarea:focus{
          border-color:rgba(93,124,255,.34) !important;
          box-shadow:0 0 0 4px rgba(93,124,255,.10) !important;
        }
        .stButton > button,.stDownloadButton > button,.stFormSubmitButton > button{
          background:linear-gradient(180deg, #6387ff, #4d74f0) !important;
          color:#ffffff !important;
          box-shadow:0 10px 20px rgba(77,116,240,.18) !important;
        }
        .stButton > button:hover,.stDownloadButton > button:hover,.stFormSubmitButton > button:hover{
          box-shadow:0 12px 24px rgba(77,116,240,.22) !important;
          filter:brightness(1.02);
        }
        div[data-testid="stForm"],div[data-testid="stAlert"]{
          border-color:rgba(134,153,176,.18) !important;
          background:linear-gradient(180deg, #ffffff, #f8fafc) !important;
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.92) !important;
        }
        .stTabs [data-baseweb="tab-list"]{
          background:#f3f6fb !important;
          border-color:rgba(134,153,176,.14) !important;
        }
        .stTabs [data-baseweb="tab"]{
          background:transparent !important;
          border-color:transparent !important;
          color:#6b7d94 !important;
        }
        .stTabs [aria-selected="true"]{
          background:#ffffff !important;
          color:var(--text) !important;
          border-color:rgba(93,124,255,.20) !important;
          box-shadow:0 8px 18px rgba(24,52,92,.07), inset 0 1px 0 rgba(255,255,255,.96) !important;
        }
        .stDataFrame,.stTable,div[data-testid="stDataFrame"],[data-testid="stCodeBlock"]{
          border-color:rgba(134,153,176,.18) !important;
          background:#ffffff !important;
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.92) !important;
        }
        .stCheckbox label,.stRadio label,.stCaption,.stMarkdown p{color:var(--muted) !important;}
        :root{
          --bg:#f6f8fc; --panel:#ffffff; --line:rgba(15,23,42,.08);
          --text:#111827; --muted:#667085; --cyan:#5b6cff; --teal:#0f9d8a;
          --amber:#b7791f; --red:#c15372; --blue:#5b6cff;
          --shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 34px rgba(16,24,40,.06);
        }
        .stApp{
          background:
            radial-gradient(circle at 0% 0%, rgba(91,108,255,.08), transparent 24%),
            linear-gradient(180deg, #fcfdff 0%, #f7f9fc 40%, #f4f7fb 100%) !important;
        }
        .stApp:before,.hero-shell:before,.hero-shell:after{display:none !important;}
        .block-container{max-width:1520px;padding-top:1rem;padding-bottom:2rem;padding-left:1.25rem;padding-right:1.25rem;}
        .hero-shell,.metric-card,.panel-card,.timeline-card,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.hero-side,.command-shell,.focus-shell,.checklist-shell,.surface-intro,.day-chip{
          backdrop-filter:none !important;
          -webkit-backdrop-filter:none !important;
          background:#ffffff !important;
          border-color:rgba(15,23,42,.08) !important;
          box-shadow:var(--shadow), inset 0 1px 0 rgba(255,255,255,.92) !important;
        }
        .metric-card:hover,.panel-card:hover,.timeline-card:hover,.day-chip:hover,.hero-side:hover,.ops-chip:hover,.flow-card:hover,.quick-link:hover{
          transform:translateY(-1px);
          border-color:rgba(91,108,255,.16) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 18px 38px rgba(16,24,40,.08) !important;
        }
        .hero-shell,.command-shell,.focus-shell{border-radius:24px;padding:1.55rem 1.6rem 1.48rem;gap:1.2rem;}
        .hero-side,.nav-brand,.metric-card,.panel-card,.timeline-card,.signal-card,.briefing-card,.ops-chip,.flow-card,.quick-link,.surface-intro,.day-chip{border-radius:18px;}
        .hero-shell h1{font-size:2.34rem;line-height:1;max-width:14ch;letter-spacing:-.045em;}
        .hero-shell p,.command-copy,.focus-copy,.panel-callout-copy,.ops-note,.briefing-note,.quick-link-copy,.integration-message,.timeline-body,.focus-note-copy,.signal-note{color:#5f7088 !important;}
        .hero-kicker,.section-kicker,.hero-side-label,.metric-label,.ops-label,.briefing-kicker,.quick-link-kicker,.day-chip-label,.command-kicker,.focus-kicker,.checklist-kicker,.surface-kicker{
          font-family:"Manrope","Segoe UI",sans-serif !important;
          font-size:.76rem !important;
          letter-spacing:.02em !important;
          text-transform:none !important;
          color:#7f8ca1 !important;
        }
        .nav-title{font-size:1.15rem;letter-spacing:-.025em;}
        .nav-copy,.hero-side-caption,.nav-meta-row span,.fact-row span,.surface-copy,.micro-note,.signal-detail,.integration-detail,.timeline-meta,.spotlight-meta,.day-chip-sub,.spotlight-vendor{color:#74839a !important;}
        .nav-brand,.nav-meta-row,.fact-row,.command-stat,.focus-metric,.checklist-item,.focus-note{background:#fafbff !important;}
        .nav-meta-row,.fact-row,.command-stat,.focus-metric,.checklist-item,.focus-note{border-color:rgba(15,23,42,.08) !important;}
        .section-head{margin:.9rem 0 .78rem;padding-top:0;border-top:none;}
        .section-head h3{font-size:1.04rem;}
        .section-head p{font-size:.9rem;max-width:36rem;}
        .metric-card{padding:1rem 1.02rem .98rem;min-height:132px;}
        .metric-value{font-size:1.72rem;}
        .panel-card,.timeline-card{padding:1rem 1.02rem;}
        .panel-title{font-size:.96rem;}
        .panel-card:before,.timeline-card:before,.metric-card:before,.signal-card:before,.command-shell:before,.focus-shell:before,.checklist-shell:before,.surface-intro:before{
          background:linear-gradient(90deg, rgba(15,23,42,.08), transparent 58%) !important;
        }
        .ops-chip:after,.briefing-card:before,.command-stat:before,.focus-metric:before{height:2px;}
        .ops-value,.signal-value,.command-stat-value,.focus-metric-value{font-size:1.22rem;}
        .briefing-value{font-size:1rem;}
        .signal-main{grid-template-columns:78px 1fr;gap:.9rem;}
        .signal-ring{width:78px;height:78px;}
        .signal-center{font-size:.88rem;}
        .quick-link{min-height:108px;padding:.92rem .96rem;border-radius:16px;}
        .flow-card{padding:.76rem .82rem;border-radius:16px;}
        .flow-title{font-size:.94rem;}
        .surface-intro{padding:.9rem .98rem;}
        .surface-title{font-size:1rem;}
        .surface-meta,.hero-badges,.command-pillrow,.focus-badges{gap:.45rem;}
        .badge{
          padding:.28rem .58rem;
          font-size:.67rem;
          letter-spacing:.01em;
          text-transform:none !important;
          border-radius:999px;
        }
        .stButton > button,.stDownloadButton > button,.stFormSubmitButton > button{
          border-radius:14px;
          padding:.68rem .95rem;
          box-shadow:0 8px 18px rgba(77,116,240,.16) !important;
        }
        .stButton > button:hover,.stDownloadButton > button:hover,.stFormSubmitButton > button:hover{
          box-shadow:0 12px 24px rgba(77,116,240,.18) !important;
        }
        .stTextInput input,.stNumberInput input,.stTextArea textarea,.stSelectbox [data-baseweb="select"] > div{border-radius:14px !important;}
        div[data-testid="stForm"]{padding:.95rem 1rem 1rem;border-radius:18px;}
        .stTabs [data-baseweb="tab-list"]{background:#f8fafc !important;padding:.18rem;border-radius:14px;}
        .stTabs [data-baseweb="tab"]{padding:.54rem .88rem;font-weight:600;}
        .stTabs [aria-selected="true"]{
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 10px 22px rgba(16,24,40,.06) !important;
        }
        .stDataFrame,.stTable,div[data-testid="stDataFrame"],[data-testid="stCodeBlock"]{border-radius:18px !important;}
        .hero-shell{
          position:relative;
          background:
            linear-gradient(135deg, rgba(255,255,255,.98) 0%, rgba(248,250,255,.98) 58%, rgba(241,245,255,.98) 100%) !important;
          border:1px solid rgba(91,108,255,.12) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 22px 46px rgba(16,24,40,.08) !important;
        }
        .hero-shell:before,.hero-shell:after{
          display:block !important;
          content:"";
          position:absolute;
          border-radius:999px;
          pointer-events:none;
        }
        .hero-shell:before{
          width:280px;height:280px;right:-110px;top:-130px;
          background:radial-gradient(circle, rgba(91,108,255,.12), transparent 70%);
        }
        .hero-shell:after{
          width:220px;height:220px;left:-90px;bottom:-120px;
          background:radial-gradient(circle, rgba(15,157,138,.08), transparent 72%);
        }
        .hero-kicker{
          display:inline-flex;
          align-items:center;
          gap:.35rem;
          padding:.34rem .62rem;
          border-radius:999px;
          background:#eef2ff;
          border:1px solid #d7e1ff;
          color:#445fc4 !important;
          font-weight:700;
        }
        .hero-shell h1{max-width:13ch;}
        .hero-badges{margin-top:1rem;}
        .hero-badges .badge{
          box-shadow:0 4px 10px rgba(16,24,40,.04);
          background:#ffffff !important;
        }
        .hero-side{
          background:
            linear-gradient(180deg, rgba(255,255,255,.92), rgba(247,249,255,.98)) !important;
          border:1px solid rgba(91,108,255,.10) !important;
          justify-content:flex-start;
          gap:.4rem;
        }
        .hero-side-value{font-size:1.68rem;}
        .section-head{
          position:relative;
          margin:1rem 0 .82rem;
          padding-bottom:.1rem;
        }
        .section-head:after{
          content:"";
          position:absolute;
          left:0;
          right:0;
          bottom:-.2rem;
          height:1px;
          background:linear-gradient(90deg, rgba(15,23,42,.08), transparent 34%);
        }
        .metric-card{overflow:hidden;}
        .metric-card:after{
          content:"";
          position:absolute;
          left:1rem;
          right:calc(100% - 5rem);
          top:0;
          height:3px;
          border-radius:999px;
          background:var(--tone-color, #5b6cff);
        }
        .metric-card-neutral{--tone-color:#5b6cff;background:linear-gradient(180deg, #ffffff, #fbfcff) !important;}
        .metric-card-ok{--tone-color:#0f9d8a;background:linear-gradient(180deg, #ffffff, #f5fcfa) !important;}
        .metric-card-warn{--tone-color:#b7791f;background:linear-gradient(180deg, #ffffff, #fffbf5) !important;}
        .metric-card-danger{--tone-color:#c15372;background:linear-gradient(180deg, #ffffff, #fff7f9) !important;}
        .metric-note{max-width:24ch;}
        .panel-card,.timeline-card,.signal-card,.briefing-card,.surface-intro,.command-shell,.focus-shell,.checklist-shell{
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 24px rgba(16,24,40,.05) !important;
        }
        .panel-card-ok{border-color:rgba(15,157,138,.12) !important;background:linear-gradient(180deg, #ffffff, #f7fcfb) !important;}
        .panel-card-warn{border-color:rgba(183,121,31,.14) !important;background:linear-gradient(180deg, #ffffff, #fffaf3) !important;}
        .panel-card-danger{border-color:rgba(193,83,114,.14) !important;background:linear-gradient(180deg, #ffffff, #fff7fa) !important;}
        .panel-card:hover,.signal-card:hover,.briefing-card:hover,.command-shell:hover,.focus-shell:hover,.surface-intro:hover{
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 18px 32px rgba(16,24,40,.07) !important;
        }
        .command-shell,.focus-shell{
          background:
            linear-gradient(180deg, rgba(255,255,255,.98), rgba(249,251,255,.98)) !important;
          border-color:rgba(91,108,255,.10) !important;
        }
        .command-stat,.focus-metric{
          background:#ffffff !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.92), 0 8px 18px rgba(16,24,40,.04);
        }
        .focus-note{
          background:linear-gradient(180deg, #f8faff, #f4f7ff) !important;
          border-color:rgba(91,108,255,.10) !important;
        }
        .ops-chip{
          background:
            linear-gradient(180deg, rgba(255,255,255,.99), rgba(248,250,253,.98)) !important;
        }
        .ops-chip:after{opacity:1;}
        .quick-link{
          position:relative;
          overflow:hidden;
          background:linear-gradient(180deg, #ffffff, #f9fbff) !important;
        }
        .quick-link:after{
          content:">";
          position:absolute;
          top:.88rem;
          right:.92rem;
          color:#9aa6b8;
          font-size:.94rem;
          transition:transform .2s ease, color .2s ease;
        }
        .quick-link:hover:after{
          transform:translate(2px,-2px);
          color:#5b6cff;
        }
        .flow-card{
          background:linear-gradient(180deg, #ffffff, #fbfcff) !important;
          grid-template-columns:auto 1fr auto;
        }
        .flow-step{
          box-shadow:inset 0 1px 0 rgba(255,255,255,.94);
          border:1px solid rgba(91,108,255,.08);
        }
        .signal-card{
          background:
            linear-gradient(180deg, rgba(255,255,255,.99), rgba(249,251,255,.98)) !important;
        }
        .briefing-card{
          background:
            linear-gradient(180deg, rgba(255,255,255,.99), rgba(251,252,255,.98)) !important;
        }
        .surface-intro{
          background:
            linear-gradient(180deg, rgba(255,255,255,.98), rgba(251,252,255,.98)) !important;
          border-color:rgba(91,108,255,.10) !important;
        }
        .surface-meta .badge{background:#f8faff !important;}
        .fact-row strong,.flow-title,.signal-label,.briefing-value,.panel-title{color:#122033 !important;}
        .timeline-top strong{color:#122033;}
        .integration-message,.integration-detail,.timeline-body,.timeline-meta,.signal-detail,.signal-note,.briefing-note,.focus-copy,.focus-note-copy,.command-copy,.command-stat-note,.metric-note,.ops-note,.flow-copy,.surface-copy,.panel-callout-copy,.hero-side-caption,.hero-shell p{
          overflow-wrap:anywhere;
          word-break:break-word;
        }
        .streamlit-expanderHeader,.stExpander summary{
          font-weight:600 !important;
          color:#1b2b42 !important;
        }
        .stExpander{
          border:1px solid rgba(15,23,42,.08) !important;
          border-radius:18px !important;
          background:#ffffff !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 10px 22px rgba(16,24,40,.05) !important;
        }
        .stApp{
          background:
            radial-gradient(circle at 16% 8%, rgba(91,108,255,.08), transparent 26%),
            radial-gradient(circle at 88% 6%, rgba(15,157,138,.05), transparent 22%),
            linear-gradient(180deg, #f4f7fb 0%, #f7f9fc 46%, #f4f7fb 100%) !important;
        }
        .stApp:before{
          opacity:.1;
          background-image:
            linear-gradient(rgba(148,163,184,.1) 1px, transparent 1px),
            linear-gradient(90deg, rgba(148,163,184,.1) 1px, transparent 1px);
          background-size:72px 72px;
        }
        .block-container{
          max-width:1600px;
          padding-top:.78rem;
          padding-left:1.28rem;
          padding-right:1.28rem;
        }
        [data-testid="stSidebar"]{
          background:linear-gradient(180deg, #f7f9fc 0%, #eef3fb 100%) !important;
          border-right:1px solid rgba(15,23,42,.08) !important;
          min-width:252px !important;
          max-width:252px !important;
        }
        [data-testid="stSidebar"] [data-testid="stVerticalBlock"]{padding-top:.42rem !important;}
        [data-testid="stSidebar"] *{color:#142033 !important;}
        [data-testid="stSidebar"] .stRadio label{
          background:#ffffff !important;
          border:1px solid rgba(15,23,42,.08) !important;
          padding:.66rem .72rem !important;
          border-radius:14px !important;
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 10px 20px rgba(16,24,40,.04);
        }
        [data-testid="stSidebar"] .stRadio label:has(input:checked){
          background:linear-gradient(180deg, #ffffff, #f6f8ff) !important;
          border-color:rgba(91,108,255,.18) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 24px rgba(91,108,255,.12) !important;
        }
        [data-testid="stSidebar"] .stRadio > div{gap:.34rem !important;}
        [data-testid="stSidebar"] .stRadio [role="radiogroup"]{gap:.4rem !important;}
        .nav-shell{gap:.72rem;margin-bottom:.82rem;}
        .nav-brand{
          background:linear-gradient(180deg, #ffffff, #f9fbff) !important;
          border:1px solid rgba(15,23,42,.08) !important;
          padding:.92rem .9rem !important;
          border-radius:20px !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 28px rgba(16,24,40,.05) !important;
        }
        .nav-title{font-size:1.36rem;line-height:1.06;}
        .nav-copy{font-size:.9rem;line-height:1.48;color:#5c6d84 !important;}
        .nav-meta{gap:.42rem !important;}
        .nav-meta-row{
          background:#ffffff !important;
          border:1px solid rgba(15,23,42,.08) !important;
          padding:.58rem .7rem !important;
          border-radius:12px !important;
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 8px 18px rgba(16,24,40,.04) !important;
        }
        .hero-shell{
          grid-template-columns:minmax(0, 1.7fr) 292px !important;
          gap:.92rem !important;
          padding:1.18rem 1.24rem 1.08rem !important;
          margin-bottom:.72rem !important;
          border-radius:24px !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 20px 40px rgba(16,24,40,.07) !important;
        }
        .hero-shell:before{
          width:320px;
          height:320px;
          right:-120px;
          top:-120px;
          background:radial-gradient(circle, rgba(91,108,255,.16), transparent 68%) !important;
        }
        .hero-shell:after{
          width:260px;
          height:260px;
          left:-80px;
          bottom:-130px;
          background:radial-gradient(circle, rgba(15,157,138,.08), transparent 72%) !important;
        }
        .hero-shell h1{
          font-size:2.34rem !important;
          max-width:11.5ch !important;
          line-height:.96 !important;
          margin:.34rem 0 .42rem !important;
        }
        .hero-shell p{
          font-size:.9rem !important;
          max-width:30rem !important;
          color:#5c6d84 !important;
          line-height:1.42 !important;
        }
        .hero-kicker{
          padding:.24rem .5rem !important;
          font-size:.66rem !important;
          letter-spacing:.01em !important;
        }
        .hero-badges{margin-top:.62rem !important;gap:.4rem !important;}
        .hero-side{
          padding:.88rem .9rem .84rem !important;
          border-radius:18px !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 6px 16px rgba(16,24,40,.05) !important;
        }
        .hero-side-label{color:#7b8ba1 !important;}
        .hero-side-value{
          font-size:1.46rem !important;
          line-height:1.1 !important;
          margin:.18rem 0 .2rem !important;
        }
        .hero-side-caption{color:#5f7086 !important;font-size:.82rem !important;line-height:1.38 !important;}
        .surface-intro,.panel-card,.metric-card,.signal-card,.briefing-card,.command-shell,.focus-shell,.checklist-shell,.stExpander{
          border-radius:20px !important;
          border:1px solid rgba(15,23,42,.08) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 30px rgba(16,24,40,.06) !important;
        }
        .surface-intro,.panel-card,.metric-card,.signal-card,.briefing-card,.command-shell,.focus-shell,.checklist-shell{
          background:linear-gradient(180deg, #ffffff, #fbfcff) !important;
        }
        .surface-intro{padding:.82rem .92rem !important;}
        .surface-title{font-size:1rem !important;color:#142033 !important;}
        .surface-copy{font-size:.9rem !important;color:#5f7086 !important;line-height:1.42 !important;}
        .panel-title{font-size:1.02rem !important;margin-bottom:.56rem !important;}
        .command-shell-compact,
        .focus-shell-compact{
          display:block !important;
          padding:.9rem .96rem .88rem !important;
          gap:.72rem !important;
          margin:.12rem 0 .72rem !important;
          border-radius:20px !important;
        }
        .command-top,
        .focus-top{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.72rem;
        }
        .command-summary,
        .focus-summary{
          min-width:0;
          flex:1 1 auto;
        }
        .command-shell-compact .command-title,
        .focus-shell-compact .focus-title{
          font-size:1.08rem !important;
          margin:.18rem 0 .2rem !important;
          line-height:1.08 !important;
        }
        .command-shell-compact .command-copy,
        .focus-shell-compact .focus-copy{
          font-size:.84rem !important;
          line-height:1.38 !important;
          max-width:none !important;
        }
        .command-shell-compact .command-pillrow,
        .focus-shell-compact .focus-badges{
          margin-top:0 !important;
          justify-content:flex-end;
          align-items:flex-start;
          flex:0 0 auto;
          max-width:42%;
        }
        .command-shell-compact .command-stats,
        .focus-shell-compact .focus-grid{
          grid-template-columns:repeat(4,minmax(0,1fr)) !important;
          gap:.58rem !important;
          margin-top:.68rem;
        }
        .command-shell-compact .command-stat,
        .focus-shell-compact .focus-metric{
          padding:.66rem .72rem !important;
          border-radius:14px !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.92), 0 6px 14px rgba(16,24,40,.035) !important;
        }
        .command-shell-compact .command-stat-label,
        .focus-shell-compact .focus-metric-label{
          font-size:.74rem !important;
          line-height:1.28 !important;
        }
        .command-shell-compact .command-stat-value,
        .focus-shell-compact .focus-metric-value{
          font-size:1.04rem !important;
          margin:.18rem 0 .12rem !important;
          line-height:1.06 !important;
        }
        .command-shell-compact .command-stat-note,
        .focus-shell-compact .focus-metric-note{
          font-size:.74rem !important;
          line-height:1.25 !important;
          color:#718198 !important;
        }
        .focus-note-inline{
          margin-top:.58rem !important;
          padding:.58rem .72rem !important;
          border-radius:14px !important;
          display:flex;
          align-items:flex-start;
          gap:.48rem;
        }
        .focus-note-inline .focus-note-title{
          margin:0 !important;
          font-size:.78rem !important;
          line-height:1.3 !important;
          flex:none;
        }
        .focus-note-inline .focus-note-copy{
          font-size:.78rem !important;
          line-height:1.34 !important;
        }
        .surface-intro-compact{
          padding:.62rem .78rem !important;
          margin:.06rem 0 .58rem !important;
          border-radius:16px !important;
        }
        .surface-intro-compact .surface-intro-grid{
          grid-template-columns:minmax(0,1fr) auto !important;
          gap:.7rem !important;
          align-items:flex-start !important;
        }
        .surface-intro-compact .surface-kicker{
          margin-bottom:.08rem !important;
          font-size:.66rem !important;
        }
        .surface-intro-compact .surface-title{
          font-size:.92rem !important;
          line-height:1.12 !important;
        }
        .surface-intro-compact .surface-copy{
          margin-top:.14rem !important;
          font-size:.8rem !important;
          line-height:1.32 !important;
        }
        .surface-intro-compact .surface-meta{
          justify-content:flex-end;
          align-items:flex-start;
        }
        .dense-section-head{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.72rem;
          margin:.52rem 0 .42rem;
        }
        .dense-section-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.9rem;
          font-weight:600;
          line-height:1.14;
          color:#15253a;
        }
        .dense-section-copy{
          margin-top:.14rem;
          color:#66768c;
          font-size:.78rem;
          line-height:1.32;
        }
        .dense-section-meta{
          display:flex;
          flex-wrap:wrap;
          gap:.36rem;
          justify-content:flex-end;
        }
        .panel-card-compact{
          padding:.82rem .86rem !important;
          margin-bottom:.62rem !important;
          border-radius:16px !important;
        }
        .panel-card-compact .panel-title{
          font-size:.92rem !important;
          margin-bottom:.42rem !important;
        }
        .fact-row-compact{
          padding:.5rem .58rem !important;
          gap:.62rem !important;
          border-radius:12px !important;
        }
        .fact-row-compact span,
        .fact-row-compact strong{
          font-size:.79rem !important;
          line-height:1.28 !important;
        }
        .timeline-card-compact{
          padding:.82rem .88rem !important;
          margin-bottom:.52rem !important;
          border-radius:16px !important;
        }
        .timeline-card-compact .timeline-meta{
          margin-top:.22rem !important;
          font-size:.75rem !important;
        }
        .timeline-card-compact .timeline-body{
          margin-top:.22rem !important;
          font-size:.83rem !important;
          line-height:1.4 !important;
        }
        .metric-card-compact{
          min-height:104px !important;
          padding:.78rem .84rem .74rem !important;
          border-radius:16px !important;
        }
        .metric-card-compact .metric-label{
          font-size:.78rem !important;
        }
        .metric-card-compact .metric-value{
          font-size:1.46rem !important;
          margin:.26rem 0 .14rem !important;
        }
        .metric-card-compact .metric-note{
          font-size:.76rem !important;
          line-height:1.28 !important;
        }
        .quick-link-compact{
          min-height:88px !important;
          padding:.74rem .8rem !important;
          border-radius:16px !important;
        }
        .quick-link-compact .quick-link-title{
          margin:.28rem 0 .2rem !important;
          font-size:.92rem !important;
        }
        .quick-link-compact .quick-link-copy{
          font-size:.79rem !important;
          line-height:1.3 !important;
        }
        .control-shell{
          margin:.14rem 0 .72rem;
          padding:.84rem .9rem .88rem;
          border-radius:20px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 28px rgba(16,24,40,.05);
        }
        .control-shell-head{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.72rem;
          margin-bottom:.72rem;
        }
        .control-shell-kicker{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.69rem;
          letter-spacing:.06em;
          font-weight:700;
          text-transform:uppercase;
          color:#5b6cff;
        }
        .control-shell-title{
          margin-top:.16rem;
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.98rem;
          font-weight:600;
          line-height:1.12;
          color:#15253a;
        }
        .control-shell-copy{
          margin-top:.18rem;
          color:#66768c;
          font-size:.8rem;
          line-height:1.35;
          max-width:48rem;
        }
        .control-shell-meta{
          display:flex;
          flex-wrap:wrap;
          justify-content:flex-end;
          gap:.36rem;
          align-items:flex-start;
        }
        .control-shell-body{
          display:grid;
          gap:.68rem;
        }
        .control-shell-toolbar{
          padding:.78rem .84rem .84rem;
          border-radius:18px;
        }
        .control-shell-toolbar .control-shell-head{
          margin-bottom:.58rem;
        }
        .control-shell-filter .control-shell-copy,
        .control-shell-actions .control-shell-copy,
        .control-shell-form .control-shell-copy{
          max-width:none;
        }
        .control-field{
          height:100%;
          padding:.68rem .72rem .72rem;
          border-radius:18px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:inset 0 1px 0 rgba(255,255,255,.92), 0 10px 22px rgba(16,24,40,.04);
        }
        .control-field-body{
          display:grid;
          gap:.38rem;
        }
        .control-field-head{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.55rem;
          margin-bottom:.12rem;
        }
        .control-field-marker{display:none !important;}
        .control-field-label{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.82rem;
          font-weight:600;
          line-height:1.16;
          color:#1b2b42;
        }
        .control-field-hint{
          margin-top:.14rem;
          color:#738198;
          font-size:.75rem;
          line-height:1.32;
        }
        .control-field-meta{
          display:flex;
          flex-wrap:wrap;
          justify-content:flex-end;
          gap:.3rem;
          align-items:flex-start;
        }
        .control-field .stTextInput,
        .control-field .stNumberInput,
        .control-field .stTextArea,
        .control-field .stSelectbox,
        .control-field .stCheckbox,
        .control-field .stButton,
        .control-field .stFormSubmitButton{
          margin:0 !important;
        }
        .control-field [data-testid="stWidgetLabel"]{
          display:none !important;
        }
        .control-field .stTextInput input,
        .control-field .stNumberInput input,
        .control-field .stTextArea textarea,
        .control-field .stSelectbox [data-baseweb="select"] > div{
          background:#ffffff !important;
          border:1px solid rgba(15,23,42,.10) !important;
          border-radius:14px !important;
          color:#142338 !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.9), 0 1px 2px rgba(16,24,40,.04) !important;
        }
        .control-field .stTextInput input,
        .control-field .stNumberInput input,
        .control-field .stSelectbox [data-baseweb="select"] > div{
          min-height:48px !important;
        }
        .control-field .stTextInput input::placeholder,
        .control-field .stNumberInput input::placeholder,
        .control-field .stTextArea textarea::placeholder{
          color:#8b98ab !important;
        }
        .control-field .stTextInput input:focus,
        .control-field .stNumberInput input:focus,
        .control-field .stTextArea textarea:focus{
          border-color:rgba(91,108,255,.28) !important;
          box-shadow:0 0 0 4px rgba(91,108,255,.10), inset 0 1px 0 rgba(255,255,255,.92) !important;
        }
        .control-field .stTextArea textarea{
          min-height:176px !important;
          line-height:1.5 !important;
          padding-top:.72rem !important;
        }
        .control-field-toggle{
          display:flex;
          flex-direction:column;
          justify-content:space-between;
        }
        .control-field-toggle .stCheckbox{
          padding-top:.22rem;
        }
        .control-field-toggle .stCheckbox label{
          display:inline-flex !important;
          align-items:center;
          gap:.46rem;
          width:max-content;
          padding:.38rem .54rem !important;
          border-radius:999px;
          border:1px solid rgba(15,23,42,.10);
          background:#f8fbff;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.9);
        }
        .control-field-toggle .stCheckbox label:has(input:checked){
          background:#edf3ff;
          border-color:rgba(91,108,255,.22);
          box-shadow:0 8px 18px rgba(91,108,255,.10);
        }
        .control-field-toggle .stCheckbox p{
          color:#223248 !important;
          font-size:.86rem !important;
          font-weight:600 !important;
        }
        .control-field .stButton > button,
        .control-field .stFormSubmitButton > button{
          min-height:48px !important;
          border-radius:14px !important;
          font-weight:700 !important;
          box-shadow:0 10px 22px rgba(77,116,240,.14) !important;
        }
        .control-field-action .stButton > button{
          background:linear-gradient(180deg, #ffffff, #f7f9ff) !important;
          color:#2741ad !important;
          border:1px solid rgba(91,108,255,.14) !important;
          box-shadow:0 8px 18px rgba(16,24,40,.05) !important;
        }
        .control-field-primary .stButton > button,
        .control-field-submit .stFormSubmitButton > button,
        .control-shell-actions .stButton > button{
          background:linear-gradient(180deg, #6f88ff, #4f6ef7) !important;
          color:#ffffff !important;
          border:1px solid rgba(79,110,247,.18) !important;
        }
        .control-field-primary .stButton > button:hover,
        .control-field-submit .stFormSubmitButton > button:hover,
        .control-shell-actions .stButton > button:hover{
          box-shadow:0 14px 28px rgba(79,110,247,.20) !important;
        }
        .control-field-link{
          padding:.58rem .62rem .62rem;
        }
        .control-field-link .quick-link{
          min-height:48px !important;
          padding:.72rem .78rem !important;
          border-radius:14px !important;
          box-shadow:none !important;
        }
        .control-shell-form{
          padding:.82rem .88rem .9rem;
        }
        .control-shell-form div[data-testid="stForm"]{
          border:1px solid rgba(15,23,42,.08) !important;
          border-radius:18px !important;
          background:linear-gradient(180deg, #ffffff, #fbfcff) !important;
          box-shadow:inset 0 1px 0 rgba(255,255,255,.92), 0 10px 22px rgba(16,24,40,.04) !important;
          padding:.26rem .28rem .32rem !important;
        }
        .control-shell-form .control-field{
          box-shadow:none !important;
          background:#fbfcff !important;
        }
        .tab-shell{
          margin:.22rem 0 .5rem;
        }
        .tab-shell .stTabs [data-baseweb="tab-list"]{
          background:#f8fafc !important;
          border:1px solid rgba(15,23,42,.08) !important;
          border-radius:16px !important;
          padding:.18rem !important;
          gap:.32rem !important;
        }
        .tab-shell .stTabs [data-baseweb="tab"]{
          min-height:40px !important;
          border-radius:12px !important;
          padding:.48rem .86rem !important;
          font-weight:600 !important;
          color:#5f7086 !important;
          background:transparent !important;
          border:1px solid transparent !important;
        }
        .tab-shell .stTabs [aria-selected="true"]{
          color:#15253a !important;
          background:#ffffff !important;
          border-color:rgba(91,108,255,.12) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 10px 22px rgba(16,24,40,.06) !important;
        }
        .sidebar-control-label{
          margin:.12rem 0 .44rem;
        }
        .sidebar-control-label .control-field-label{
          font-size:.8rem;
        }
        [data-testid="stSidebar"] .stRadio label{
          min-height:52px;
          align-items:center !important;
        }
        .machine-trace-shell{
          margin:.12rem 0 .4rem;
        }
        .machine-trace-grid{
          display:grid;
          grid-template-columns:repeat(2,minmax(0,1fr));
          gap:.72rem;
        }
        .machine-trace-panel{
          border:1px solid rgba(15,23,42,.08);
          border-radius:18px;
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 24px rgba(16,24,40,.05);
          overflow:hidden;
        }
        .machine-trace-top{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.55rem;
          padding:.74rem .82rem .54rem;
          border-bottom:1px solid rgba(15,23,42,.07);
          background:#fbfcff;
        }
        .machine-trace-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.88rem;
          font-weight:600;
          line-height:1.16;
          color:#15253a;
        }
        .machine-trace-pre{
          margin:0;
          padding:.78rem .82rem .86rem;
          background:#f8fafc;
          color:#223248;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.75rem;
          line-height:1.42;
          max-height:260px;
          overflow:auto;
          white-space:pre-wrap;
          overflow-wrap:anywhere;
        }
        .trace-shell{
          border:1px solid rgba(15,23,42,.08);
          border-radius:18px;
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 24px rgba(16,24,40,.05);
          overflow:hidden;
        }
        .trace-shell-top{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.6rem;
          padding:.76rem .82rem .58rem;
          border-bottom:1px solid rgba(15,23,42,.07);
          background:#fbfcff;
        }
        .trace-shell-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.88rem;
          font-weight:600;
          line-height:1.16;
          color:#15253a;
        }
        .trace-shell-copy{
          margin-top:.16rem;
          color:#6d7e95;
          font-size:.77rem;
          line-height:1.34;
        }
        .trace-shell-meta{
          display:flex;
          flex-wrap:wrap;
          justify-content:flex-end;
          gap:.34rem;
        }
        .trace-shell-pre{
          margin:0;
          padding:.78rem .82rem .86rem;
          background:#f8fafc;
          color:#223248;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.75rem;
          line-height:1.42;
          overflow:auto;
          white-space:pre-wrap;
          overflow-wrap:anywhere;
        }
        .trace-shell-ok{border-color:rgba(15,157,138,.14);background:linear-gradient(180deg, #ffffff, #f7fcfb);}
        .trace-shell-warn{border-color:rgba(183,121,31,.14);background:linear-gradient(180deg, #ffffff, #fffaf3);}
        .trace-shell-danger{border-color:rgba(193,83,114,.14);background:linear-gradient(180deg, #ffffff, #fff7fa);}
        .trace-shell-neutral{border-color:rgba(91,108,255,.12);background:linear-gradient(180deg, #ffffff, #f8faff);}
        .trace-disclosure{
          margin:.56rem 0 .82rem;
          border:1px solid rgba(15,23,42,.08);
          border-radius:18px;
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 10px 22px rgba(16,24,40,.04);
          overflow:hidden;
        }
        .trace-disclosure summary{
          list-style:none;
          cursor:pointer;
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:.7rem;
          padding:.76rem .82rem;
          color:#223248;
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.88rem;
          font-weight:600;
          line-height:1.18;
          background:linear-gradient(180deg, #ffffff, #fbfcff);
        }
        .trace-disclosure summary::-webkit-details-marker{display:none;}
        .trace-disclosure summary:after{
          content:"+";
          color:#7d8aa0;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.94rem;
          line-height:1;
        }
        .trace-disclosure[open] summary:after{content:"-";}
        .trace-disclosure-body{
          padding:0 .82rem .82rem;
          border-top:1px solid rgba(15,23,42,.07);
          background:#fcfdff;
        }
        .ops-notice{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.78rem;
          margin:.18rem 0 .76rem;
          padding:.76rem .84rem;
          border-radius:16px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 8px 18px rgba(16,24,40,.04);
        }
        .ops-notice-main{
          display:grid;
          gap:.16rem;
        }
        .ops-notice-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.9rem;
          font-weight:600;
          line-height:1.16;
          color:#15253a;
        }
        .ops-notice-copy{
          color:#66768c;
          font-size:.8rem;
          line-height:1.36;
        }
        .ops-notice-meta{
          display:flex;
          flex-wrap:wrap;
          justify-content:flex-end;
          gap:.34rem;
          align-items:flex-start;
        }
        .ops-notice-ok{border-color:rgba(15,157,138,.14);background:linear-gradient(180deg, #ffffff, #f7fcfb);}
        .ops-notice-warn{border-color:rgba(183,121,31,.14);background:linear-gradient(180deg, #ffffff, #fffaf3);}
        .ops-notice-danger{border-color:rgba(193,83,114,.14);background:linear-gradient(180deg, #ffffff, #fff7fa);}
        .ops-notice-neutral{border-color:rgba(91,108,255,.12);background:linear-gradient(180deg, #ffffff, #f8faff);}
        .empty-state-card{
          display:grid;
          gap:.22rem;
          margin:.2rem 0 .82rem;
          padding:.94rem .98rem;
          border-radius:18px;
          border:1px dashed rgba(134,153,176,.28);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 10px 22px rgba(16,24,40,.04);
        }
        .empty-state-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.92rem;
          font-weight:600;
          line-height:1.18;
          color:#15253a;
        }
        .empty-state-copy{
          color:#66768c;
          font-size:.82rem;
          line-height:1.38;
        }
        .empty-state-meta{
          display:flex;
          flex-wrap:wrap;
          gap:.34rem;
          margin-top:.26rem;
        }
        .empty-state-ok{border-color:rgba(15,157,138,.18);background:linear-gradient(180deg, #ffffff, #f7fcfb);}
        .empty-state-warn{border-color:rgba(183,121,31,.18);background:linear-gradient(180deg, #ffffff, #fffaf3);}
        .empty-state-danger{border-color:rgba(193,83,114,.18);background:linear-gradient(180deg, #ffffff, #fff7fa);}
        .empty-state-neutral{border-color:rgba(91,108,255,.16);background:linear-gradient(180deg, #ffffff, #f8faff);}
        .recovery-queue-shell{
          margin:.08rem 0 .68rem;
          border:1px solid rgba(15,23,42,.08);
          border-radius:18px;
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 26px rgba(16,24,40,.05);
          overflow:hidden;
        }
        .recovery-queue-head{
          display:grid;
          grid-template-columns:82px minmax(180px,1.1fr) minmax(140px,.86fr) 108px minmax(220px,1.2fr) 118px;
          gap:0;
          padding:.68rem .82rem;
          border-bottom:1px solid rgba(15,23,42,.07);
          background:#fbfcff;
        }
        .recovery-queue-th{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.7rem;
          font-weight:600;
          letter-spacing:.03em;
          text-transform:uppercase;
          color:#8290a5;
        }
        .recovery-queue-scroll{
          overflow:auto;
        }
        .recovery-queue-table{
          width:100%;
          border-collapse:separate;
          border-spacing:0;
        }
        .recovery-queue-table tbody td{
          padding:.74rem .82rem;
          border-bottom:1px solid rgba(15,23,42,.06);
          vertical-align:top;
          background:#ffffff;
        }
        .recovery-queue-table tbody tr:hover td{background:#fcfdff;}
        .recovery-queue-id{
          display:inline-flex;
          align-items:center;
          padding:.18rem .5rem;
          border-radius:999px;
          border:1px solid rgba(91,108,255,.14);
          background:#f5f7ff;
          color:#4866c9;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.72rem;
          line-height:1.2;
          white-space:nowrap;
        }
        .recovery-queue-title{
          color:#15253a;
          font-size:.86rem;
          font-weight:600;
          line-height:1.26;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .recovery-queue-sub{
          margin-top:.18rem;
          color:#728198;
          font-size:.76rem;
          line-height:1.3;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .recovery-queue-error{
          color:#223248;
          font-size:.8rem;
          line-height:1.38;
          display:-webkit-box;
          -webkit-line-clamp:2;
          -webkit-box-orient:vertical;
          overflow:hidden;
          overflow-wrap:anywhere;
        }
        .queue-grid-shell{
          margin:.08rem 0 .58rem;
          padding:.84rem .9rem .82rem;
          border-radius:18px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 12px 26px rgba(16,24,40,.05);
        }
        .queue-grid-top{
          display:flex;
          justify-content:space-between;
          gap:.9rem;
          align-items:flex-start;
        }
        .queue-grid-kicker{
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.7rem;
          letter-spacing:.06em;
          font-weight:700;
          text-transform:uppercase;
          color:#5b6cff;
        }
        .queue-grid-title{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:1rem;
          font-weight:600;
          line-height:1.14;
          color:#142033;
          margin-top:.24rem;
        }
        .queue-grid-copy{
          margin-top:.24rem;
          color:#5f7086;
          font-size:.88rem;
          line-height:1.38;
          max-width:40rem;
        }
        .queue-grid-badges{
          display:flex;
          flex-wrap:wrap;
          gap:.38rem;
          justify-content:flex-end;
        }
        .queue-grid-note{
          margin-top:.46rem;
          color:#738198;
          font-size:.8rem;
          line-height:1.35;
        }
        .queue-focus-note{
          margin:.14rem 0 .46rem;
          color:#738198;
          font-size:.8rem;
          line-height:1.35;
          text-align:right;
        }
        .queue-slice-summary{
          margin:.14rem 0 .46rem;
          color:#66768c;
          font-size:.81rem;
          line-height:1.4;
        }
        .queue-slice-summary strong{
          color:#15253a;
          font-weight:700;
        }
        .queue-table-shell{
          overflow:hidden;
          border-radius:20px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 28px rgba(16,24,40,.05);
        }
        .queue-table-scroll{
          max-width:100%;
          overflow:auto;
        }
        .queue-table{
          width:100%;
          min-width:1240px;
          border-collapse:separate;
          border-spacing:0;
          table-layout:fixed;
        }
        .queue-table thead th{
          position:sticky;
          top:0;
          z-index:2;
          padding:.72rem .8rem;
          border-bottom:1px solid rgba(15,23,42,.08);
          background:#f8faff;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.69rem;
          font-weight:700;
          letter-spacing:.05em;
          text-transform:uppercase;
          text-align:left;
          white-space:nowrap;
        }
        .queue-th-primary{color:#51617a;}
        .queue-th-secondary{color:#8a98ab;}
        .queue-table thead th.queue-th-numeric{text-align:right;}
        .queue-table tbody td{
          position:relative;
          padding:.76rem .8rem;
          vertical-align:top;
          border-bottom:1px solid rgba(15,23,42,.06);
          background:#ffffff;
          transition:background .18s ease, border-color .18s ease;
        }
        .queue-table tbody tr:last-child td{border-bottom:none;}
        .queue-table tbody tr:hover td{background:#fcfdff;}
        .queue-table tbody tr.queue-row-risk td{background:linear-gradient(180deg, #ffffff, #fff8fb);}
        .queue-table tbody tr.queue-row-selected td{
          background:linear-gradient(180deg, #f7faff, #fcfdff);
          border-bottom-color:rgba(91,108,255,.16);
        }
        .queue-table tbody tr.queue-row-selected.queue-row-risk td{
          background:linear-gradient(180deg, #f7faff, #fff7fa);
        }
        .queue-table tbody tr.queue-row-selected td:first-child{
          padding-left:1.02rem;
        }
        .queue-table tbody tr.queue-row-selected td:first-child:before{
          content:"";
          position:absolute;
          left:.3rem;
          top:.72rem;
          bottom:.72rem;
          width:3px;
          border-radius:999px;
          background:#5b6cff;
        }
        .queue-cell-title{
          color:#15253a;
          font-size:.9rem;
          font-weight:600;
          line-height:1.28;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .queue-cell-sub{
          margin-top:.2rem;
          color:#76859a;
          font-size:.76rem;
          line-height:1.3;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .queue-cell-code{
          display:inline-flex;
          max-width:100%;
          align-items:center;
          padding:.16rem .4rem;
          border-radius:999px;
          border:1px solid rgba(91,108,255,.12);
          background:#f5f7ff;
          color:#223248;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.77rem;
          line-height:1.2;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .queue-id-chip{
          display:inline-flex;
          align-items:center;
          padding:.1rem 0;
          color:#60718a;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.8rem;
          font-weight:600;
          line-height:1.2;
        }
        .queue-cell-number{
          text-align:right;
        }
        .queue-cell-number .queue-cell-title,
        .queue-cell-number .queue-cell-sub{
          white-space:nowrap;
          text-overflow:clip;
          font-variant-numeric:tabular-nums;
        }
        .queue-cell-diff-danger .queue-cell-title{color:#b4234d;}
        .queue-cell-diff-warn .queue-cell-title{color:#b7791f;}
        .queue-cell-diff-ok .queue-cell-title{color:#0f766e;}
        .queue-pill{
          display:inline-flex;
          align-items:center;
          justify-content:center;
          padding:.2rem .48rem;
          border-radius:999px;
          border:1px solid transparent;
          font-size:.7rem;
          font-weight:700;
          line-height:1.15;
          letter-spacing:.03em;
          white-space:nowrap;
          text-transform:uppercase;
        }
        .queue-pill-ok{
          border-color:rgba(15,157,138,.18);
          background:#eefaf7;
          color:#0f766e;
        }
        .queue-pill-warn{
          border-color:rgba(183,121,31,.18);
          background:#fff8eb;
          color:#9a6700;
        }
        .queue-pill-danger{
          border-color:rgba(193,83,114,.18);
          background:#fff1f5;
          color:#b4234d;
        }
        .queue-pill-neutral{
          border-color:rgba(91,108,255,.16);
          background:#f1f4ff;
          color:#455ed4;
        }
        .ledger-shell{
          overflow:hidden;
          border-radius:20px;
          border:1px solid rgba(15,23,42,.08);
          background:linear-gradient(180deg, #ffffff, #fbfcff);
          box-shadow:0 1px 2px rgba(16,24,40,.04), 0 14px 28px rgba(16,24,40,.05);
        }
        .ledger-scroll{
          max-width:100%;
          overflow:auto;
        }
        .ledger-table{
          width:100%;
          min-width:1080px;
          border-collapse:separate;
          border-spacing:0;
          table-layout:fixed;
        }
        .ledger-table thead th{
          position:sticky;
          top:0;
          z-index:2;
          padding:.72rem .8rem;
          border-bottom:1px solid rgba(15,23,42,.08);
          background:#f8faff;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.69rem;
          font-weight:700;
          letter-spacing:.05em;
          text-transform:uppercase;
          text-align:left;
          white-space:nowrap;
          color:#7a899d;
        }
        .ledger-table thead th.ledger-th-numeric{text-align:right;}
        .ledger-table tbody td{
          padding:.76rem .8rem;
          vertical-align:top;
          border-bottom:1px solid rgba(15,23,42,.06);
          background:#ffffff;
        }
        .ledger-table tbody tr:last-child td{border-bottom:none;}
        .ledger-table tbody tr:hover td{background:#fcfdff;}
        .ledger-cell-title{
          color:#15253a;
          font-size:.88rem;
          font-weight:600;
          line-height:1.28;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .ledger-cell-sub{
          margin-top:.22rem;
          color:#76859a;
          font-size:.76rem;
          line-height:1.3;
          white-space:nowrap;
          overflow:hidden;
          text-overflow:ellipsis;
        }
        .ledger-cell-number{
          text-align:right;
        }
        .ledger-cell-number .ledger-cell-title,
        .ledger-cell-number .ledger-cell-sub{
          font-variant-numeric:tabular-nums;
        }
        .ledger-chip{
          display:inline-flex;
          align-items:center;
          padding:.16rem .42rem;
          border-radius:999px;
          border:1px solid rgba(91,108,255,.12);
          background:#f5f7ff;
          color:#223248;
          font-family:"IBM Plex Mono","Consolas",monospace;
          font-size:.74rem;
          line-height:1.2;
          white-space:nowrap;
        }
        .mesh-grid{
          display:grid !important;
          grid-template-columns:repeat(auto-fit, minmax(240px, 1fr));
          gap:.62rem !important;
        }
        .mesh-card{
          position:relative;
          overflow:hidden;
          padding:.78rem .82rem .74rem !important;
          border-radius:18px !important;
          border:1px solid rgba(15,23,42,.08) !important;
          background:linear-gradient(180deg, #ffffff, #fbfcff) !important;
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 10px 22px rgba(16,24,40,.05) !important;
        }
        .mesh-card:before{
          content:"";
          position:absolute;
          left:0;
          top:0;
          bottom:0;
          width:3px;
          background:var(--accent, #5b6cff);
        }
        .mesh-card-top{
          display:flex;
          align-items:flex-start;
          justify-content:space-between;
          gap:.6rem;
          margin-bottom:.42rem;
        }
        .mesh-card-name{
          font-family:"Sora","Segoe UI","Microsoft YaHei UI",sans-serif;
          font-size:.95rem;
          font-weight:600;
          line-height:1.18;
          color:#15253a;
        }
        .mesh-card-status{
          display:flex;
          align-items:center;
          gap:.36rem;
          margin-top:.18rem;
          font-size:.73rem;
          font-weight:700;
          color:#7a889d;
          text-transform:uppercase;
          letter-spacing:.04em;
        }
        .mesh-card-dot{
          width:8px;
          height:8px;
          border-radius:999px;
          background:var(--accent, #5b6cff);
          box-shadow:0 0 0 4px color-mix(in srgb, var(--accent, #5b6cff) 14%, white);
          flex:none;
        }
        .mesh-card-summary{
          color:#223248;
          font-size:.88rem;
          line-height:1.34;
          min-height:2.35em;
        }
        .mesh-card-hint{
          margin-top:.32rem;
          color:#6b7a90;
          font-size:.78rem;
          line-height:1.34;
          min-height:2.2em;
        }
        .mesh-card-ok{--accent:#0f9d8a;background:linear-gradient(180deg, #ffffff, #f5fcfa) !important;}
        .mesh-card-warn{--accent:#b7791f;background:linear-gradient(180deg, #ffffff, #fffaf3) !important;}
        .mesh-card-danger{--accent:#c15372;background:linear-gradient(180deg, #ffffff, #fff7fa) !important;}
        .mesh-card-neutral{--accent:#5b6cff;background:linear-gradient(180deg, #ffffff, #f8faff) !important;}
        .integration-message{
          font-size:.96rem !important;
          line-height:1.5 !important;
          color:#223248 !important;
        }
        .integration-detail,.signal-note,.signal-detail,.briefing-note,.metric-note,.ops-note,.flow-copy,.command-copy,.command-stat-note,.focus-copy,.focus-note-copy,.hero-side-caption,.nav-copy{
          color:#5f7086 !important;
        }
        .flow-grid{gap:.62rem !important;}
        .flow-card{
          padding:.74rem .82rem !important;
          border:1px solid rgba(15,23,42,.07) !important;
          border-radius:16px !important;
          background:#ffffff !important;
          box-shadow:0 1px 2px rgba(16,24,40,.03), 0 8px 18px rgba(16,24,40,.04) !important;
        }
        .flow-step{
          width:32px !important;
          height:32px !important;
          background:#eef2ff !important;
          color:#4660d6 !important;
          border:1px solid rgba(91,108,255,.14) !important;
          box-shadow:none !important;
        }
        .flow-title{font-size:.95rem !important;color:#15253a !important;}
        .flow-copy{font-size:.84rem !important;line-height:1.35 !important;max-width:48rem;}
        .flow-tail{width:10px !important;height:10px !important;}
        .panel-card-warn{
          background:linear-gradient(180deg, #fffdf9, #fff8ef) !important;
          border-color:rgba(183,121,31,.14) !important;
        }
        .metric-card{
          min-height:140px !important;
          padding:1.08rem 1.08rem 1rem !important;
        }
        .metric-value{font-size:1.86rem !important;}
        .badge{
          font-size:.67rem !important;
          padding:.28rem .56rem !important;
        }
        .section-head{margin:.9rem 0 .72rem !important;}
        .section-head h3{font-size:1.04rem !important;}
        .section-head p{font-size:.88rem !important;color:#5f7086 !important;}
        ::-webkit-scrollbar{width:10px;height:10px;}
        ::-webkit-scrollbar-thumb{background:rgba(120,144,177,.36);border-radius:999px;}
        ::-webkit-scrollbar-track{background:rgba(224,231,240,.72);}
        @media (max-width: 1200px){.hero-shell{grid-template-columns:1fr !important;}}
        @media (max-width: 1180px){
          .dashboard-band,.command-shell,.focus-shell,.surface-intro-grid{grid-template-columns:1fr}
          .command-shell-compact .command-stats,.focus-shell-compact .focus-grid{grid-template-columns:repeat(2,minmax(0,1fr)) !important;}
          .machine-trace-grid{grid-template-columns:1fr;}
          .recovery-queue-head{
            grid-template-columns:82px minmax(180px,1fr) minmax(180px,1fr) 108px;
          }
          .recovery-queue-head .recovery-queue-th:nth-child(3),
          .recovery-queue-head .recovery-queue-th:nth-child(5){display:none;}
          .recovery-queue-table tbody td:nth-child(3),
          .recovery-queue-table tbody td:nth-child(5){display:none;}
        }
        @media (max-width: 980px){
          .hero-shell{grid-template-columns:1fr}
          .section-head{display:block}
          .command-stats,.focus-grid{grid-template-columns:1fr}
          .surface-meta{justify-content:flex-start}
          .command-top,.focus-top,.dense-section-head{display:block;}
          .command-shell-compact .command-pillrow,.focus-shell-compact .focus-badges{max-width:none;justify-content:flex-start;margin-top:.48rem !important;}
          .command-shell-compact .command-stats,.focus-shell-compact .focus-grid{grid-template-columns:1fr !important;}
          .ops-notice{display:grid;}
          .recovery-queue-head{
            display:none;
          }
          .recovery-queue-table tbody tr{
            display:grid;
            grid-template-columns:1fr;
          }
          .recovery-queue-table tbody td{
            display:block !important;
            border-bottom:none;
            padding:.28rem .82rem;
          }
          .recovery-queue-table tbody td:first-child{padding-top:.76rem;}
          .recovery-queue-table tbody td:last-child{
            padding-bottom:.82rem;
            border-bottom:1px solid rgba(15,23,42,.06);
          }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def hero(title: str, subtitle: str, side_note: str, badges_html: str) -> None:
    render_html(
        f"""
        <div class="hero-shell">
          <div>
            <div class="hero-kicker">Finance operations</div>
            <h1>{esc(title)}</h1>
            <p>{esc(subtitle)}</p>
            <div class="hero-badges">{badges_html}</div>
          </div>
          <div class="hero-side">
            <div class="hero-side-label">Workspace</div>
            <div class="hero-side-value">{esc(side_note)}</div>
            <div class="hero-side-caption">Risk routing, sync recovery, and reviewer sign-off in one finance workspace.</div>
          </div>
        </div>
        """
    )


def section_title(title: str, subtitle: str) -> None:
    render_html(
        f"""
        <div class="section-head">
          <div><div class="section-kicker">Overview</div><h3>{esc(title)}</h3></div>
          <p>{esc(subtitle)}</p>
        </div>
        """
    )


def ops_ribbon(items: List[Dict[str, Any]]) -> None:
    cards = []
    for item in items:
        cards.append(
            f"""
            <div class="ops-chip ops-{esc(item.get('tone') or 'neutral')}">
              <div class="ops-label">{esc(item.get("label"))}</div>
              <div class="ops-value">{esc(item.get("value"))}</div>
              <div class="ops-note">{esc(item.get("note"))}</div>
            </div>
            """
        )
    render_html(f"<div class='ops-ribbon'>{join_html_fragments(cards)}</div>")


def quick_links_panel(title: str, links: List[Dict[str, str]]) -> None:
    cards = []
    for link in links:
        cards.append(
            f"""
            <a class="quick-link" href="{html.escape(str(link.get('href') or '#'), quote=True)}" target="{html.escape(str(link.get('target') or '_self'), quote=True)}">
              <div class="quick-link-kicker">{esc(link.get("kicker") or "Open")}</div>
              <span class="quick-link-title">{esc(link.get("title"))}</span>
              <span class="quick-link-copy">{esc(link.get("copy"))}</span>
            </a>
            """
        )
    render_html(
        f"""
        <div class="panel-card">
          <div class="panel-title">{esc(title)}</div>
          <div class="quick-links">{join_html_fragments(cards)}</div>
        </div>
        """
    )


def workflow_panel(title: str, stages: List[Dict[str, str]]) -> None:
    cards = []
    for idx, stage in enumerate(stages, start=1):
        cards.append(
            f"""
            <div class="flow-card">
              <div class="flow-step">{idx}</div>
              <div>
                <div class="flow-title">{esc(stage.get("title"))}</div>
                <div class="flow-copy">{esc(stage.get("copy"))}</div>
              </div>
              <div class="flow-tail flow-tail-{esc(stage.get('tone') or 'neutral')}"></div>
            </div>
            """
        )
    render_html(
        f"""
        <div class="panel-card">
          <div class="panel-title">{esc(title)}</div>
          <div class="flow-grid">{join_html_fragments(cards)}</div>
        </div>
        """
    )


def callout_panel(title: str, copy: str) -> None:
    render_html(
        f"""
        <div class="panel-callout">
          <div class="panel-callout-title">{esc(title)}</div>
          <div class="panel-callout-copy">{esc(copy)}</div>
        </div>
        """
    )


def command_panel(
    kicker: str,
    title: str,
    copy: str,
    stats: List[Dict[str, Any]],
    pills_html: str = "",
    compact: bool = False,
) -> None:
    cards = []
    for item in stats:
        cards.append(
            f"""
            <div class="command-stat" style="--accent:{html.escape(tone_color(str(item.get('tone') or 'neutral')), quote=True)};">
              <div class="command-stat-label">{esc(item.get("label"))}</div>
              <div class="command-stat-value">{esc(item.get("value"))}</div>
              <div class="command-stat-note">{esc(item.get("note"))}</div>
            </div>
            """
        )
    shell_class = "command-shell command-shell-compact" if compact else "command-shell"
    top_class = "command-top" if compact else ""
    summary_class = "command-summary" if compact else ""
    render_html(
        f"""
        <div class="{shell_class}">
          <div class="{top_class}">
            <div class="{summary_class}">
            <div class="command-kicker">{esc(kicker)}</div>
            <div class="command-title">{esc(title)}</div>
            <div class="command-copy">{esc(copy)}</div>
            </div>
            {'<div class="command-pillrow">' + pills_html + '</div>' if pills_html else ''}
          </div>
          <div class="command-stats">{join_html_fragments(cards)}</div>
        </div>
        """
    )


def focus_panel(
    kicker: str,
    title: str,
    copy: str,
    badges_html: str,
    metrics: List[Dict[str, Any]],
    note_title: str,
    note_copy: str,
    compact: bool = False,
) -> None:
    cards = []
    for item in metrics:
        cards.append(
            f"""
            <div class="focus-metric" style="--accent:{html.escape(tone_color(str(item.get('tone') or 'neutral')), quote=True)};">
              <div class="focus-metric-label">{esc(item.get("label"))}</div>
              <div class="focus-metric-value">{esc(item.get("value"))}</div>
              <div class="focus-metric-note">{esc(item.get("note"))}</div>
            </div>
            """
        )
    shell_class = "focus-shell focus-shell-compact" if compact else "focus-shell"
    top_class = "focus-top" if compact else ""
    summary_class = "focus-summary" if compact else ""
    note_class = "focus-note focus-note-inline" if compact else "focus-note"
    render_html(
        f"""
        <div class="{shell_class}">
          <div class="{top_class}">
            <div class="{summary_class}">
            <div class="focus-kicker">{esc(kicker)}</div>
            <div class="focus-title">{esc(title)}</div>
            <div class="focus-copy">{esc(copy)}</div>
          </div>
            <div class="focus-badges">{badges_html}</div>
          </div>
          <div class="focus-grid">{join_html_fragments(cards)}</div>
          <div class="{note_class}">
            <div class="focus-note-title">{esc(note_title)}</div>
            <div class="focus-note-copy">{esc(note_copy)}</div>
          </div>
        </div>
        """
    )


def checklist_panel(kicker: str, title: str, items: List[Dict[str, str]]) -> None:
    rows = []
    for idx, item in enumerate(items, start=1):
        rows.append(
            f"""
            <div class="checklist-item">
              <div class="checklist-index">{idx}</div>
              <div>
                <div class="checklist-item-title">{esc(item.get("title"))}</div>
                <div class="checklist-item-copy">{esc(item.get("copy"))}</div>
              </div>
            </div>
            """
        )
    render_html(
        f"""
        <div class="checklist-shell">
          <div class="checklist-kicker">{esc(kicker)}</div>
          <div class="checklist-title">{esc(title)}</div>
          <div class="checklist-grid">{join_html_fragments(rows)}</div>
        </div>
        """
    )


def surface_intro(kicker: str, title: str, copy: str, badges_html: str = "", compact: bool = False) -> None:
    shell_class = "surface-intro surface-intro-compact" if compact else "surface-intro"
    render_html(
        f"""
        <div class="{shell_class}">
          <div class="surface-intro-grid">
            <div>
              <div class="surface-kicker">{esc(kicker)}</div>
              <div class="surface-title">{esc(title)}</div>
              <div class="surface-copy">{esc(copy)}</div>
            </div>
            <div class="surface-meta">{badges_html}</div>
          </div>
        </div>
        """
    )


def dense_section_header(title: str, copy: str = "", badges_html: str = "") -> None:
    render_html(
        f"""
        <div class="dense-section-head">
          <div>
            <div class="dense-section-title">{esc(title)}</div>
            {'<div class="dense-section-copy">' + esc(copy) + '</div>' if copy else ''}
          </div>
          <div class="dense-section-meta">{badges_html}</div>
        </div>
        """
    )


def format_trace_payload(payload: Any) -> str:
    decoded = decode_json(payload)
    if isinstance(decoded, (dict, list)):
        try:
            return json.dumps(decoded, ensure_ascii=False, indent=2, default=str)
        except Exception:
            return json.dumps(str(decoded), ensure_ascii=False, indent=2)
    text = str(decoded or "").strip()
    return text or "-"


def trace_shell(
    title: str,
    payload: Any,
    *,
    tone: str = "neutral",
    copy: str = "",
    badges_html: str = "",
    max_height: int = 260,
) -> str:
    return textwrap.dedent(
        f"""
        <div class="trace-shell trace-shell-{esc(tone)}">
          <div class="trace-shell-top">
            <div>
              <div class="trace-shell-title">{esc(title)}</div>
              {'<div class="trace-shell-copy">' + esc(copy) + '</div>' if copy else ''}
            </div>
            <div class="trace-shell-meta">{badges_html}</div>
          </div>
          <pre class="trace-shell-pre" style="max-height:{int(max_height)}px;">{html.escape(format_trace_payload(payload))}</pre>
        </div>
        """
    ).strip()


def ops_notice_bar(title: str, copy: str, tone: str = "neutral", badges_html: str = "") -> None:
    render_html(
        f"""
        <div class="ops-notice ops-notice-{esc(tone)}">
          <div class="ops-notice-main">
            <div class="ops-notice-title">{esc(title)}</div>
            <div class="ops-notice-copy">{esc(copy)}</div>
          </div>
          <div class="ops-notice-meta">{badges_html}</div>
        </div>
        """
    )


def empty_state_card(title: str, copy: str, tone: str = "neutral", badges_html: str = "") -> None:
    render_html(
        f"""
        <div class="empty-state-card empty-state-{esc(tone)}">
          <div class="empty-state-title">{esc(title)}</div>
          <div class="empty-state-copy">{esc(copy)}</div>
          <div class="empty-state-meta">{badges_html}</div>
        </div>
        """
    )


def push_flash_notice(title: str, copy: str, tone: str = "neutral", badges_html: str = "") -> None:
    st.session_state["ops_flash_notice"] = {
        "title": str(title),
        "copy": str(copy),
        "tone": str(tone or "neutral"),
        "badges_html": str(badges_html or ""),
    }


def consume_flash_notice() -> None:
    payload = st.session_state.pop("ops_flash_notice", None)
    if payload:
        ops_notice_bar(
            str(payload.get("title") or "Notice"),
            str(payload.get("copy") or ""),
            str(payload.get("tone") or "neutral"),
            str(payload.get("badges_html") or ""),
        )


def render_failed_sync_queue(rows: List[Dict[str, Any]], max_height: int = 280) -> None:
    body_rows = []
    for row in rows:
        invoice_id = safe_int(row.get("invoice_id"))
        document = str(row.get("invoice_number") or row.get("invoice_code") or "-")
        document_note = str(row.get("invoice_code") or "-")
        seller = str(row.get("seller_name") or "-")
        po_number = str(row.get("purchase_order_no") or "-")
        last_error = summarize_sync_error(row.get("sync_error"), limit=140)
        updated_at = fmt_dt(row.get("updated_at"))
        body_rows.append(
            f"""
            <tr>
              <td>
                <div class="recovery-queue-id">#{invoice_id}</div>
              </td>
              <td>
                <div class="recovery-queue-title" title="{esc(seller)}">{esc(seller)}</div>
                <div class="recovery-queue-sub">Seller</div>
              </td>
              <td>
                <div class="recovery-queue-title" title="{esc(document)}">{esc(document)}</div>
                <div class="recovery-queue-sub">Code {esc(document_note)}</div>
              </td>
              <td>
                <div class="recovery-queue-title" title="{esc(po_number)}">{esc(po_number)}</div>
                <div class="recovery-queue-sub">Purchase order</div>
              </td>
              <td>
                <div class="recovery-queue-error" title="{esc(last_error)}">{esc(last_error)}</div>
                <div class="recovery-queue-sub">Last connector response</div>
              </td>
              <td>
                <div class="recovery-queue-title">{esc(updated_at)}</div>
                <div class="recovery-queue-sub">Updated</div>
              </td>
            </tr>
            """
        )
    render_html(
        f"""
        <div class="recovery-queue-shell">
          <div class="recovery-queue-head">
            <div class="recovery-queue-th">Invoice</div>
            <div class="recovery-queue-th">Seller</div>
            <div class="recovery-queue-th">Document</div>
            <div class="recovery-queue-th">PO</div>
            <div class="recovery-queue-th">Last Error</div>
            <div class="recovery-queue-th">Updated</div>
          </div>
          <div class="recovery-queue-scroll" style="max-height:{int(max_height)}px;">
            <table class="recovery-queue-table">
              <tbody>{join_html_fragments(body_rows)}</tbody>
            </table>
          </div>
        </div>
        """
    )


def render_machine_trace_view(invoice: Dict[str, Any]) -> None:
    trace_pairs = [
        (
            "Raw OCR JSON",
            invoice.get("raw_ocr_json") or {},
            "neutral",
            "Raw extraction payload captured from the OCR stage.",
        ),
        (
            "LLM Parsed JSON",
            invoice.get("llm_json") or {},
            "ok",
            "Structured output used for downstream review and writeback.",
        ),
    ]
    cards = []
    for label, payload, tone, copy in trace_pairs:
        cards.append(
            trace_shell(
                label,
                payload,
                tone=tone,
                copy=copy,
                badges_html=badge(label.replace(" JSON", ""), tone),
                max_height=260,
            )
        )
    render_html(f"<div class='machine-trace-shell'><div class='machine-trace-grid'>{join_html_fragments(cards)}</div></div>")


def queue_grid_header(kicker: str, title: str, copy: str, note: str, badges_html: str = "") -> None:
    render_html(
        f"""
        <div class="queue-grid-shell">
          <div class="queue-grid-top">
            <div>
              <div class="queue-grid-kicker">{esc(kicker)}</div>
              <div class="queue-grid-title">{esc(title)}</div>
              <div class="queue-grid-copy">{esc(copy)}</div>
            </div>
            <div class="queue-grid-badges">{badges_html}</div>
          </div>
          <div class="queue-grid-note">{esc(note)}</div>
        </div>
        """
    )


def tone_color(tone: str) -> str:
    palette = {
        "ok": "#0f9d8a",
        "warn": "#b7791f",
        "danger": "#c15372",
        "neutral": "#5b6cff",
    }
    return palette.get(str(tone or "neutral"), "#5b6cff")


def clamp_percent(value: float) -> int:
    try:
        return max(0, min(int(round(float(value) * 100)), 100))
    except Exception:
        return 0


def signal_board(title: str, items: List[Dict[str, Any]]) -> None:
    cards = []
    for item in items:
        tone = str(item.get("tone") or "neutral")
        cards.append(
            f"""
            <div class="signal-card">
              <div class="signal-top">
                <div>
                  <div class="quick-link-kicker">{esc(item.get("kicker") or "Signal")}</div>
                  <div class="signal-label">{esc(item.get("label"))}</div>
                </div>
                {badge(item.get("status") or item.get("value"), tone)}
              </div>
              <div class="signal-main">
                <div class="signal-ring" style="--signal-pct:{clamp_percent(safe_float(item.get('ratio')))};--signal-color:{html.escape(tone_color(tone), quote=True)};">
                  <div class="signal-center">{clamp_percent(safe_float(item.get("ratio")))}%</div>
                </div>
                <div>
                  <div class="signal-value">{esc(item.get("value"))}</div>
                  <div class="signal-note">{esc(item.get("note"))}</div>
                  <div class="signal-detail">{esc(item.get("detail"))}</div>
                </div>
              </div>
            </div>
            """
        )
    render_html(
        f"""
        <div class="panel-card">
          <div class="panel-title">{esc(title)}</div>
          <div class="signal-grid">{join_html_fragments(cards)}</div>
        </div>
        """
    )


def briefing_board(title: str, items: List[Dict[str, Any]]) -> None:
    cards = []
    for item in items:
        tone = str(item.get("tone") or "neutral")
        cards.append(
            f"""
            <div class="briefing-card" style="--accent:{html.escape(tone_color(tone), quote=True)};">
              <div class="briefing-kicker">{esc(item.get("kicker") or "Briefing")}</div>
              <div class="briefing-value">{esc(item.get("value"))}</div>
              <div class="briefing-note">{esc(item.get("note"))}</div>
            </div>
            """
        )
    render_html(
        f"""
        <div class="panel-card">
          <div class="panel-title">{esc(title)}</div>
          <div class="briefing-grid">{join_html_fragments(cards)}</div>
        </div>
        """
    )


def render_runtime_unavailable(
    *,
    title: str,
    subtitle: str,
    side_note: str,
    badges_html: str,
    summary_title: str,
    summary_copy: str,
    steps_title: str,
    steps: List[Dict[str, Any]],
    error: Exception,
) -> None:
    summary = runtime_error_summary(error)
    hero(title, subtitle, side_note, badges_html)
    surface_intro(
        "Recovery",
        summary_title,
        summary_copy,
        badge("Data offline", "danger") + badge("UI available", "ok"),
        compact=True,
    )
    workflow_panel(
        steps_title,
        [
            {
                "title": str(step.get("value") or step.get("title") or "Step"),
                "copy": str(step.get("note") or step.get("copy") or ""),
                "tone": str(step.get("tone") or "neutral"),
            }
            for step in steps
        ],
    )
    ops_notice_bar(
        "Current blocker",
        summary,
        "warn",
        badge("Recovery needed", "danger") + badge("Raw trace available", "neutral"),
    )
    render_html(
        f"""
        <details class="trace-disclosure">
          <summary>Technical trace</summary>
          <div class="trace-disclosure-body">
            {trace_shell(
                "Runtime error trace",
                str(error) or "Unknown runtime failure",
                tone="warn",
                copy="Use the raw connector trace to confirm the blocked dependency before retrying.",
                badges_html=badge("Exception", "warn"),
                max_height=220,
            )}
          </div>
        </details>
        """
    )


def metric_card(label: str, value: str, note: str, tone: str = "neutral", compact: bool = False) -> None:
    card_class = f"metric-card metric-card-{tone} tone-{tone}"
    if compact:
        card_class += " metric-card-compact"
    render_html(
        f"""
        <div class="{card_class}">
          <div class="metric-label">{esc(label)}</div>
          <div class="metric-value">{esc(value)}</div>
          <div class="metric-note">{esc(note)}</div>
        </div>
        """
    )


def info_card(title: str, pairs: List[tuple[str, Any]], compact: bool = False) -> None:
    row_class = "fact-row fact-row-compact" if compact else "fact-row"
    card_class = "panel-card panel-card-compact" if compact else "panel-card"
    rows = "".join(
        f"<div class='{row_class}'><span>{esc(label)}</span><strong>{esc(value)}</strong></div>"
        for label, value in pairs
    )
    render_html(
        f"""
        <div class="{card_class}">
          <div class="panel-title">{esc(title)}</div>
          <div class="fact-grid">{rows}</div>
        </div>
        """
    )


def status_card(name: str, status: str, message: str, detail: str) -> None:
    tone = tone_for_status(status)
    render_html(
        f"""
        <div class="panel-card panel-card-{tone}">
          <div class="integration-top">
            <div class="panel-title">{esc(name)}</div>
            {badge(status, tone)}
          </div>
          <div class="integration-message">{esc(message)}</div>
          <div class="integration-detail">{esc(detail)}</div>
        </div>
        """
    )


def status_board(items: List[Dict[str, str]]) -> None:
    cards = []
    for item in items:
        tone = tone_for_status(item.get("status"))
        summary = short_text(clean_status_text(item.get("message")), limit=72)
        hint = short_text(clean_status_text(item.get("detail")), limit=88)
        cards.append(
            f"""
            <div class="mesh-card mesh-card-{tone}">
              <div class="mesh-card-top">
                <div class="mesh-card-name">{esc(item.get("name"))}</div>
                {badge(item.get("status"), tone)}
              </div>
              <div class="mesh-card-summary">{esc(summary)}</div>
              <div class="mesh-card-hint">{esc(hint)}</div>
            </div>
            """
        )
    render_html(f"<div class='mesh-grid'>{join_html_fragments(cards)}</div>")


def risk_spotlight_card(row: Dict[str, Any]) -> None:
    reason = row.get("risk_reason")
    if isinstance(reason, (dict, list)):
        reason = json.dumps(reason, ensure_ascii=False)
    render_html(
        f"""
        <div class="panel-card panel-card-danger">
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
        """
    )


def render_activity_strip(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        empty_state_card(
            "No recent activity yet",
            "Seven-day intake volume will appear here after new invoices land in the workspace.",
            "neutral",
            badge("Activity waiting", "neutral"),
        )
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
    render_html(f"<div class='activity-strip'>{join_html_fragments(chips)}</div>")


def summarize_event_payload(event: Dict[str, Any]) -> str:
    payload = decode_json(event.get("payload"))
    event_type = str(event.get("event_type") or "").strip().upper()

    if isinstance(payload, dict):
        if event_type == "EMAIL_ALERT":
            status = str(payload.get("status") or event.get("event_status") or "").strip()
            subject = short_text(payload.get("subject") or "Risk alert sent.", limit=84)
            recipient = payload.get("to")
            if isinstance(recipient, list):
                recipient_text = ", ".join(str(item) for item in recipient[:2] if str(item or "").strip())
            else:
                recipient_text = str(recipient or "").strip()
            summary = subject
            if recipient_text:
                prefix = f"{status.title()} to {recipient_text}." if status else f"Sent to {recipient_text}."
                summary = f"{prefix} {subject}"
            return short_text(summary, limit=140)
        if event_type == "INGEST":
            source = payload.get("source") or payload.get("source_file_path") or payload.get("file")
            if source:
                return short_text(f"Captured from {Path(str(source)).name}.", limit=140)
        if event_type == "WORK_ORDER_SUBMITTED":
            decision = str(payload.get("invoice_status") or payload.get("review_result") or "").strip()
            handler = str(payload.get("handler_user") or "").strip()
            note = str(payload.get("handler_reason") or payload.get("handling_note") or "").strip()
            parts = []
            if decision:
                parts.append(f"Decision {decision}")
            if handler:
                parts.append(f"by {handler}")
            summary = " ".join(parts).strip()
            if note:
                summary = f"{summary}. {note}" if summary else note
            if summary:
                return short_text(summary, limit=140)
        if not payload:
            return "No payload attached."
        compact = []
        for key in ("invoice_number", "invoice_code", "purchase_order_no", "status", "message", "error"):
            value = str(payload.get(key) or "").strip()
            if value:
                compact.append(f"{compact_label(key)} {value}")
            if len(compact) >= 2:
                break
        if compact:
            return short_text(". ".join(compact), limit=140)
        return short_text(json.dumps(payload, ensure_ascii=False), limit=140)

    if isinstance(payload, list):
        labels = [risk_reason_label(item) for item in payload[:3] if risk_reason_label(item) != "-"]
        if labels:
            return short_text("; ".join(labels), limit=140)
        return short_text(json.dumps(payload, ensure_ascii=False), limit=140)

    text = str(payload or "").strip()
    if not text:
        return "No payload attached."
    return short_text(text, limit=140)


def render_event_feed(events: List[Dict[str, Any]], empty_text: str, compact: bool = False) -> None:
    if not events:
        empty_state_card("Event feed is empty", empty_text, "neutral", badge("No events", "neutral"))
        return
    for event in events[:8]:
        tone = tone_for_status(event.get("event_status"))
        card_class = "timeline-card timeline-card-compact" if compact else "timeline-card"
        render_html(
            f"""
            <div class="{card_class}">
              <div class="timeline-top">
                <strong>{esc(event.get("event_type") or '-')}</strong>
                {badge(event.get("event_status") or '-', tone)}
              </div>
              <div class="timeline-meta">{esc(fmt_dt(event.get("created_at")))}</div>
              <div class="timeline-body">{esc(summarize_event_payload(event))}</div>
            </div>
            """
        )


def render_review_feed(tasks: List[Dict[str, Any]], compact: bool = False) -> None:
    if not tasks:
        empty_state_card(
            "No review decisions yet",
            "Manual reviewer actions will appear here after the first approval or rejection is submitted.",
            "warn",
            badge("Desk waiting", "warn"),
        )
        return
    for task in tasks[:6]:
        card_class = "timeline-card timeline-card-compact" if compact else "timeline-card"
        render_html(
            f"""
            <div class="{card_class}">
              <div class="timeline-top">
                <strong>{esc(task.get("handler_user") or "Pending assignment")}</strong>
                {badge(task.get("review_result") or '-', tone_for_status(task.get("review_result")))}
              </div>
              <div class="timeline-meta">{esc(fmt_dt(task.get("created_at")))}</div>
              <div class="timeline-body">{esc(task.get("handling_note") or 'No note recorded.')}</div>
            </div>
            """
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


def tone_from_ratio(value: float, *, warn_at: float = 0.25, danger_at: float = 0.5) -> str:
    if value >= danger_at:
        return "danger"
    if value >= warn_at:
        return "warn"
    return "ok"


def invoice_sync_snapshot(sync_row: Optional[Dict[str, Any]]) -> tuple[str, str]:
    if not sync_row:
        return "Not Synced", "warn"
    if sync_row.get("feishu_record_id") and not sync_row.get("sync_error"):
        return "Feishu Linked", "ok"
    return "Recovery Needed", "danger"


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
        ops_notice_bar(
            "Feishu replay completed",
            f"Synced {ok_count} row(s). No failures were reported in this pass.",
            "ok",
            badge(f"{ok_count} ok", "ok") + badge(f"{fail_count} fail", "neutral"),
        )
    elif ok_count or fail_count:
        ops_notice_bar(
            "Feishu replay finished with mixed result",
            f"Synced {ok_count} row(s) and left {fail_count} row(s) unresolved.",
            "warn",
            badge(f"{ok_count} ok", "ok") + badge(f"{fail_count} fail", "danger"),
        )
    else:
        ops_notice_bar(
            "No rows needed replay",
            "The selected scope is already in sync or has no recoverable Feishu rows right now.",
            "neutral",
            badge(str(mode or "failed").replace("_", " ").title(), "neutral"),
        )
    if details:
        render_html(
            f"""
            <details class="trace-disclosure">
              <summary>Replay response</summary>
              <div class="trace-disclosure-body">
                {trace_shell(
                    "Feishu sync result",
                    details,
                    tone="neutral",
                    copy="Raw sync response for recovery auditing and connector debugging.",
                    badges_html=badge("JSON", "neutral"),
                    max_height=180,
                )}
              </div>
            </details>
            """
        )


def fetch_recent_invoices(db: MySQLClient, limit: int = 100) -> List[Dict[str, Any]]:
    sql = """
    SELECT
      id, invoice_date, seller_name, buyer_name, invoice_code, invoice_number, purchase_order_no,
      total_amount_with_tax, expected_amount, amount_diff, risk_flag, invoice_status, risk_reason,
      notify_personal_status, notify_leader_status, created_at
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
      DATE(created_at) AS activity_date,
      COUNT(*) AS total_count,
      SUM(CASE WHEN risk_flag = 1 THEN 1 ELSE 0 END) AS risk_count
    FROM invoices
    WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 6 DAY)
    GROUP BY DATE(created_at)
    ORDER BY DATE(created_at) ASC
    """
    rows = db.fetch_all(sql)
    for row in rows:
        row["day_label"] = fmt_day_label(row.get("activity_date"))
    return rows


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
    rows = []
    for check in checks:
        status = "OK" if check.ok else "NOT READY"
        message, detail = summarize_connector_status(check.name, status, check.message, check.detail or "")
        rows.append(
            {
                "name": check.name,
                "status": status,
                "message": message,
                "detail": detail,
            }
        )
    return rows


def switch_view(view: str, **params: Any) -> None:
    st.query_params.clear()
    st.query_params["view"] = view
    for key, value in params.items():
        if value not in (None, ""):
            st.query_params[key] = str(value)
    st.rerun()


def queue_pill(text: Any, tone: str = "neutral") -> str:
    return f"<span class='queue-pill queue-pill-{esc(tone)}'>{esc(text)}</span>"


def queue_status_label(status: Any) -> str:
    mapping = {
        "Pending": "Pending",
        "Approved": "Approved",
        "Rejected": "Rejected",
        "NeedsReview": "Needs review",
    }
    text = str(status or "").strip()
    if not text:
        return "-"
    return mapping.get(text, text.replace("_", " "))


def queue_status_note(status: Any) -> str:
    mapping = {
        "pending": "Open review",
        "approved": "Ready to post",
        "rejected": "Needs correction",
        "needsreview": "Escalated",
    }
    text = str(status or "").strip().lower()
    return mapping.get(text, "Workflow status available")


def queue_diff_tone(row: Dict[str, Any]) -> str:
    diff_abs = abs(safe_float(row.get("amount_diff")))
    if diff_abs <= 0.01:
        return "ok"
    if safe_int(row.get("risk_flag")) == 1 or diff_abs >= 1000:
        return "danger"
    if diff_abs >= 100:
        return "warn"
    return "neutral"


def queue_diff_note(diff_value: float, tone: str) -> str:
    diff_abs = abs(diff_value)
    if diff_abs <= 0.01:
        return "On target"
    if tone == "danger":
        return "Review delta"
    if tone == "warn":
        return "Watch variance"
    return "Minor variance"


def queue_risk_note(reason: Any, risk_flag: bool) -> str:
    summary = summarize_risk_reason(reason, limit=48, max_parts=2)
    if summary != "-":
        return summary
    return "Variance exceeds threshold" if risk_flag else "Within policy"


def build_queue_grid_rows(rows: List[Dict[str, Any]], pinned_invoice_id: Any) -> List[Dict[str, Any]]:
    selected_id = safe_int(pinned_invoice_id)
    display_rows: List[Dict[str, Any]] = []
    for row in rows:
        invoice_id = safe_int(row.get("id"))
        invoice_no = str(row.get("invoice_number") or row.get("invoice_code") or "-")
        invoice_code = str(row.get("invoice_code") or "")
        seller = str(row.get("seller_name") or "-")
        buyer = str(row.get("buyer_name") or "-")
        po_number = str(row.get("purchase_order_no") or "-")
        amount_value = safe_float(row.get("total_amount_with_tax"))
        expected_value = safe_float(row.get("expected_amount"))
        diff_value = safe_float(row.get("amount_diff"))
        risk_flag = safe_int(row.get("risk_flag")) == 1
        status_text = queue_status_label(row.get("invoice_status"))
        status_tone = tone_for_status(row.get("invoice_status"))
        diff_tone = queue_diff_tone(row)
        invoice_date = fmt_dt(row.get("invoice_date"))
        created_note = invoice_date[:4] if invoice_date != "-" and len(invoice_date) >= 4 else "Year n/a"
        display_rows.append(
            {
                "id": invoice_id,
                "date": fmt_day_label(row.get("invoice_date")),
                "date_title": invoice_date,
                "date_note": created_note,
                "seller": seller,
                "buyer": buyer,
                "invoice_no": invoice_no,
                "invoice_note": f"Code {invoice_code}" if invoice_code and invoice_code != invoice_no else "Matched document",
                "po": po_number,
                "amount": fmt_money(amount_value),
                "expected": fmt_money(expected_value),
                "diff": fmt_money(diff_value),
                "diff_abs": abs(diff_value),
                "diff_tone": diff_tone,
                "diff_note": queue_diff_note(diff_value, diff_tone),
                "risk_flag": risk_flag,
                "risk_text": "High risk" if risk_flag else "Normal",
                "risk_note": queue_risk_note(row.get("risk_reason"), risk_flag),
                "risk_tone": "danger" if risk_flag else "ok",
                "status_text": status_text,
                "status_note": queue_status_note(row.get("invoice_status")),
                "status_tone": status_tone,
                "is_selected": invoice_id == selected_id,
            }
        )
    return display_rows


def render_queue_table(rows: List[Dict[str, Any]], max_height: int) -> None:
    body_rows = []
    for row in rows:
        row_classes = ["queue-row"]
        if row.get("risk_flag"):
            row_classes.append("queue-row-risk")
        if row.get("is_selected"):
            row_classes.append("queue-row-selected")
        diff_class = f"queue-cell-number queue-cell-diff-{esc(row.get('diff_tone') or 'neutral')}"
        body_rows.append(
            f"""
            <tr class="{' '.join(row_classes)}">
              <td>
                <div class="queue-cell-title" title="{esc(row.get('date_title'))}">{esc(row.get('date'))}</div>
                <div class="queue-cell-sub">{esc(row.get('date_note'))}</div>
              </td>
              <td>
                <div class="queue-cell-title" title="{esc(row.get('seller'))}">{esc(row.get('seller'))}</div>
              </td>
              <td>
                <div class="queue-cell-title" title="{esc(row.get('buyer'))}">{esc(row.get('buyer'))}</div>
              </td>
              <td>
                <div class="queue-cell-code" title="{esc(row.get('invoice_no'))}">{esc(row.get('invoice_no'))}</div>
                <div class="queue-cell-sub">{esc(row.get('invoice_note'))}</div>
              </td>
              <td>
                <div class="queue-cell-code" title="{esc(row.get('po'))}">{esc(row.get('po'))}</div>
                <div class="queue-cell-sub">Purchase order</div>
              </td>
              <td class="queue-cell-number">
                <div class="queue-cell-title">{esc(row.get('amount'))}</div>
                <div class="queue-cell-sub">Invoice total</div>
              </td>
              <td class="queue-cell-number">
                <div class="queue-cell-title">{esc(row.get('expected'))}</div>
                <div class="queue-cell-sub">Expected value</div>
              </td>
              <td class="{diff_class}">
                <div class="queue-cell-title">{esc(row.get('diff'))}</div>
                <div class="queue-cell-sub">{esc(row.get('diff_note'))}</div>
              </td>
              <td>
                {queue_pill(row.get('status_text'), str(row.get('status_tone') or 'neutral'))}
                <div class="queue-cell-sub">{esc(row.get('status_note'))}</div>
              </td>
              <td>
                {queue_pill(row.get('risk_text'), str(row.get('risk_tone') or 'neutral'))}
                <div class="queue-cell-sub" title="{esc(row.get('risk_note'))}">{esc(row.get('risk_note'))}</div>
              </td>
              <td>
                <div class="queue-id-chip">#{esc(row.get('id'))}</div>
                <div class="queue-cell-sub">{'Pinned' if row.get('is_selected') else 'Queue'}</div>
              </td>
            </tr>
            """
        )
    render_html(
        f"""
        <div class="queue-table-shell">
          <div class="queue-table-scroll" style="max-height:{max_height}px;">
            <table class="queue-table">
              <colgroup>
                <col style="width:78px;" />
                <col style="width:180px;" />
                <col style="width:160px;" />
                <col style="width:128px;" />
                <col style="width:110px;" />
                <col style="width:110px;" />
                <col style="width:110px;" />
                <col style="width:104px;" />
                <col style="width:92px;" />
                <col style="width:104px;" />
                <col style="width:64px;" />
              </colgroup>
              <thead>
                <tr>
                  <th class="queue-th-secondary">Date</th>
                  <th class="queue-th-primary">Seller</th>
                  <th class="queue-th-secondary">Buyer</th>
                  <th class="queue-th-primary">Invoice No.</th>
                  <th class="queue-th-secondary">PO</th>
                  <th class="queue-th-primary queue-th-numeric">Amount</th>
                  <th class="queue-th-secondary queue-th-numeric">Expected</th>
                  <th class="queue-th-primary queue-th-numeric">Diff</th>
                  <th class="queue-th-primary">Status</th>
                  <th class="queue-th-primary">Risk</th>
                  <th class="queue-th-secondary">ID</th>
                </tr>
              </thead>
              <tbody>{join_html_fragments(body_rows)}</tbody>
            </table>
          </div>
        </div>
        """
    )


def fmt_decimal(value: Any, digits: int = 2) -> str:
    if value in (None, ""):
        return "-"
    try:
        text = f"{float(value):,.{digits}f}"
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text
    except Exception:
        return str(value)


def render_line_items_table(items: List[Dict[str, Any]], max_height: int = 320) -> None:
    if not items:
        empty_state_card(
            "Line ledger unavailable",
            "No parsed line items were attached to this invoice. Review the source payload before sign-off.",
            "warn",
            badge("0 lines", "warn"),
        )
        return
    body_rows = []
    for idx, item in enumerate(items, start=1):
        name = str(item.get("item_name") or f"Line {idx}")
        spec = str(item.get("item_spec") or "No spec")
        unit = str(item.get("item_unit") or "-")
        quantity = fmt_decimal(item.get("item_quantity"), digits=4)
        unit_price = fmt_decimal(item.get("item_unit_price"), digits=4)
        amount = fmt_money(item.get("item_amount"))
        tax_rate = str(item.get("tax_rate") or "-")
        tax_amount = fmt_money(item.get("tax_amount"))
        body_rows.append(
            f"""
            <tr>
              <td>
                <div class="ledger-cell-title" title="{esc(name)}">{esc(name)}</div>
                <div class="ledger-cell-sub">Line {idx}</div>
              </td>
              <td>
                <div class="ledger-chip" title="{esc(spec)}">{esc(spec)}</div>
                <div class="ledger-cell-sub">Spec</div>
              </td>
              <td class="ledger-cell-number">
                <div class="ledger-cell-title">{esc(quantity)}</div>
                <div class="ledger-cell-sub">{esc(unit)}</div>
              </td>
              <td class="ledger-cell-number">
                <div class="ledger-cell-title">{esc(unit_price)}</div>
                <div class="ledger-cell-sub">Unit price</div>
              </td>
              <td class="ledger-cell-number">
                <div class="ledger-cell-title">{esc(amount)}</div>
                <div class="ledger-cell-sub">Line amount</div>
              </td>
              <td>
                <div class="ledger-chip">{esc(tax_rate)}</div>
                <div class="ledger-cell-sub">Tax rate</div>
              </td>
              <td class="ledger-cell-number">
                <div class="ledger-cell-title">{esc(tax_amount)}</div>
                <div class="ledger-cell-sub">Tax amount</div>
              </td>
            </tr>
            """
        )
    render_html(
        f"""
        <div class="ledger-shell">
          <div class="ledger-scroll" style="max-height:{max_height}px;">
            <table class="ledger-table">
              <colgroup>
                <col style="width:260px;" />
                <col style="width:150px;" />
                <col style="width:110px;" />
                <col style="width:120px;" />
                <col style="width:140px;" />
                <col style="width:100px;" />
                <col style="width:140px;" />
              </colgroup>
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Spec</th>
                  <th class="ledger-th-numeric">Qty</th>
                  <th class="ledger-th-numeric">Unit Price</th>
                  <th class="ledger-th-numeric">Amount</th>
                  <th>Tax</th>
                  <th class="ledger-th-numeric">Tax Amount</th>
                </tr>
              </thead>
              <tbody>{join_html_fragments(body_rows)}</tbody>
            </table>
          </div>
        </div>
        """
    )


def case_risk_summary(invoice: Dict[str, Any], fallback: str = "Review identity, delta, and routing before closing the case.") -> str:
    summary = summarize_risk_reason(invoice.get("risk_reason"), limit=220, max_parts=3)
    return summary if summary != "-" else fallback


def case_badges_html(
    invoice: Dict[str, Any],
    *,
    sync_label: str,
    sync_tone: str,
    purchase_order_no: Any = "",
    include_po: bool = True,
) -> str:
    badges_html = (
        badge(invoice.get("invoice_status") or "UNKNOWN", tone_for_status(invoice.get("invoice_status")))
        + badge("RISK" if safe_int(invoice.get("risk_flag")) == 1 else "NORMAL", "danger" if safe_int(invoice.get("risk_flag")) == 1 else "ok")
        + badge(sync_label, sync_tone)
    )
    po_text = str(purchase_order_no or invoice.get("purchase_order_no") or "").strip()
    if include_po:
        badges_html += badge(f"PO {po_text or 'N/A'}", "neutral")
    return badges_html


def render_case_brief_view(
    invoice: Dict[str, Any],
    detail: Dict[str, Any],
    *,
    purchase_order_no: str,
    unique_hash: str,
    sync_label: str,
    sync_tone: str,
    intro_copy: str,
    compact: bool = False,
) -> None:
    surface_intro(
        "Case brief",
        "Identity and reconciliation",
        intro_copy,
        badge(f"{len(detail.get('items') or [])} lines", "neutral")
        + badge(sync_label, sync_tone)
        + badge(invoice.get("invoice_status") or "UNKNOWN", tone_for_status(invoice.get("invoice_status"))),
        compact=compact,
    )
    info_cols = st.columns(3, gap="small" if compact else "medium")
    with info_cols[0]:
        info_card(
            "Invoice Core",
            [
                ("Invoice code", invoice.get("invoice_code")),
                ("Invoice number", invoice.get("invoice_number")),
                ("Invoice date", fmt_dt(invoice.get("invoice_date"))[:10]),
                ("PO number", purchase_order_no),
            ],
            compact=compact,
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
            compact=compact,
        )
    with info_cols[2]:
        info_card(
            "Workflow State",
            [
                ("Sync", sync_label),
                ("Unique hash", short_text(unique_hash or "-", limit=28)),
                ("Reviews", str(len(detail.get("review_tasks") or []))),
                ("Line items", str(len(detail.get("items") or []))),
            ],
            compact=compact,
        )
    if compact:
        dense_section_header(
            "Line ledger",
            "Validate quantity, unit price, and tax before sign-off.",
            badge(f"{len(detail.get('items') or [])} lines", "neutral"),
        )
    else:
        surface_intro(
            "Line ledger",
            "Parsed line items",
            "Use the commercial breakdown to validate quantities, unit prices, and tax before approval.",
            badge(f"{len(detail.get('items') or [])} line items", "neutral"),
        )
    render_line_items_table(detail["items"] or [], max_height=280 if compact else 320)


def render_case_history_view(
    detail: Dict[str, Any],
    *,
    sync_label: str,
    sync_tone: str,
    intro_copy: str,
    compact: bool = False,
) -> None:
    surface_intro(
        "History",
        "Case timeline",
        intro_copy,
        badge(f"{len(detail.get('events') or [])} events", "neutral")
        + badge(f"{len(detail.get('review_tasks') or [])} decisions", "warn" if not detail.get("review_tasks") else "ok")
        + badge(sync_label, sync_tone),
        compact=compact,
    )
    history_cols = st.columns([1.04, 0.96], gap="small" if compact else "large")
    with history_cols[0]:
        if compact:
            dense_section_header("Event Feed", "System actions before the case reached the desk.")
        else:
            section_title("Event Feed", "What happened before the case reached the analyst desk.")
        render_event_feed(detail["events"], "No events recorded for this invoice.", compact=compact)
    with history_cols[1]:
        if compact:
            dense_section_header("Recent Decisions", "Latest manual actions already on file.")
        else:
            section_title("Recent Decisions", "Latest manual actions already recorded for this invoice.")
        render_review_feed(detail["review_tasks"], compact=compact)
        if detail.get("sync"):
            if compact:
                dense_section_header(
                    "Cloud Mirror",
                    "Latest Feishu link and replay status for this case.",
                    badge(sync_label, sync_tone),
                )
            info_card(
                "Cloud Mirror",
                [
                    ("Sync status", sync_label),
                    ("Record ID", detail["sync"].get("feishu_record_id") or "-"),
                    ("Updated", fmt_dt(detail["sync"].get("updated_at"))),
                    ("Last error", summarize_sync_error(detail["sync"].get("sync_error"))),
                ],
                compact=compact,
            )


def render_dashboard(cfg: Dict[str, Any]) -> None:
    checks = integration_status(cfg)
    try:
        db = db_client(cfg)
        metrics = fetch_metrics(db)
        feishu_sync = fetch_feishu_sync_summary(db)
        feishu_retry = feishu_retry_worker_summary(cfg)
        failed_sync_rows = fetch_recent_failed_feishu_syncs(db, limit=8)
        invoices = fetch_recent_invoices(db, limit=200)
        activity = fetch_daily_activity(db)
    except Exception as exc:
        render_runtime_unavailable(
            title="Invoice Operations Suite",
            subtitle="UI is up. Data layer offline.",
            side_note=f"Port {cfg['ui_port']} | Degraded mode",
            badges_html=badge("UI LIVE", "ok") + badge("DB OFFLINE", "danger") + badge("OCR CHECK", "warn"),
            summary_title="Dependency Recovery",
            summary_copy="Start MySQL, then refresh. Queue and audit data return automatically.",
            steps_title="Suggested Recovery Path",
            steps=[
                {
                    "kicker": "Step 1",
                    "value": "Start Docker Desktop",
                    "note": "Local demo expects MySQL and Mailpit through Docker.",
                    "tone": "warn",
                },
                {
                    "kicker": "Step 2",
                    "value": "Run start.cmd or start_demo.bat",
                    "note": "Bootstraps services and reopens the UI on port 8517.",
                    "tone": "ok",
                },
                {
                    "kicker": "Step 3",
                    "value": "Refresh This Page",
                    "note": "Refresh once the database is reachable again.",
                    "tone": "neutral",
                },
            ],
            error=exc,
        )
        surface_intro(
            "Operations center",
            "Service mesh while data is offline",
            "Connector posture is still visible so you can confirm what is ready before retrying the data layer.",
            badge(f"{sum(1 for row in checks if row['status'] == 'OK')} ready", "ok")
            + badge(f"{sum(1 for row in checks if row['status'] != 'OK')} blocked", "warn"),
            compact=True,
        )
        dense_section_header("Service Mesh", "OCR, Dify, Feishu, SMTP.")
        status_board(checks)
        return

    total_amount = sum(safe_float(row.get("total_amount_with_tax")) for row in invoices)
    risk_amount = sum(abs(safe_float(row.get("amount_diff"))) for row in invoices if safe_int(row.get("risk_flag")) == 1)
    risk_rows = sorted(
        [row for row in invoices if safe_int(row.get("risk_flag")) == 1],
        key=lambda row: abs(safe_float(row.get("amount_diff"))),
        reverse=True,
    )
    connector_ok_count = sum(1 for row in checks if row["status"] == "OK")
    connector_total = max(len(checks), 1)
    total_count = safe_int(metrics.get("total_count"))
    risk_count = safe_int(metrics.get("risk_count"))
    pending_count = safe_int(metrics.get("pending_count"))
    today_count = safe_int(metrics.get("today_count"))
    synced_count = safe_int(feishu_sync.get("synced_count"))
    failed_sync_count = safe_int(feishu_sync.get("failed_count"))
    alert_sent_count = sum(
        1
        for row in invoices
        if safe_int(row.get("risk_flag")) == 1 and str(row.get("notify_personal_status") or "").strip().lower() == "sent"
    )
    risk_ratio = (risk_count / total_count) if total_count else 0.0
    sync_ratio = (synced_count / total_count) if total_count else 0.0
    reviewed_ratio = ((total_count - pending_count) / total_count) if total_count else 0.0
    alert_ratio = (alert_sent_count / risk_count) if risk_count else 1.0

    hero(
        "Invoice Operations Suite",
        "Intake, checks, sync, review in one workspace.",
        f"Port {cfg['ui_port']} | Local workspace",
        badge("OCR LIVE", "ok") + badge("ALERT LOOP", "warn") + badge("DB WRITEBACK", "ok"),
    )
    consume_flash_notice()
    ops_ribbon(
        [
            {
                "label": "Connector Mesh",
                "value": f"{connector_ok_count}/{connector_total} Ready",
                "note": "OCR, Dify, Feishu, SMTP.",
                "tone": "ok" if connector_ok_count == connector_total else "warn",
            },
            {
                "label": "Risk Pressure",
                "value": f"{risk_ratio:.0%}" if total_count else "0%",
                "note": "Share currently flagged.",
                "tone": tone_from_ratio(risk_ratio),
            },
            {
                "label": "Open Operations",
                "value": str(pending_count),
                "note": "Cases still open.",
                "tone": "warn" if pending_count else "ok",
            },
            {
                "label": "Cloud Mirror",
                "value": f"{sync_ratio:.0%}" if total_count else "0%",
                "note": f"{failed_sync_count} row(s) need replay.",
                "tone": "danger" if failed_sync_count else ("ok" if synced_count else "warn"),
            },
        ]
    )

    cols = st.columns(4)
    with cols[0]:
        metric_card("Invoices", str(metrics["total_count"] or 0), "Total records in the workspace.")
    with cols[1]:
        metric_card("High Risk", str(metrics["risk_count"] or 0), "Invoices flagged by rules.", "danger")
    with cols[2]:
        metric_card("Pending", str(metrics["pending_count"] or 0), "Cases waiting for review.", "warn")
    with cols[3]:
        metric_card("Volume", fmt_money(total_amount), f"Risk delta {fmt_money(risk_amount)}", "ok")

    signal_board(
        "Control Signals",
        [
            {
                "kicker": "Posture",
                "label": "Risk Ratio",
                "value": f"{risk_ratio:.0%}" if total_count else "0%",
                "note": "Share of invoices flagged.",
                "detail": f"{risk_count} of {total_count} invoice(s).",
                "ratio": risk_ratio,
                "tone": tone_from_ratio(risk_ratio),
            },
            {
                "kicker": "Delivery",
                "label": "Alert Coverage",
                "value": f"{alert_ratio:.0%}" if risk_count else "Standby",
                "note": "Risk alerts already sent.",
                "detail": f"{alert_sent_count} of {risk_count} risk invoice(s).",
                "ratio": alert_ratio if risk_count else 1.0,
                "tone": "ok" if not risk_count else tone_from_ratio(1 - alert_ratio, warn_at=0.08, danger_at=0.2),
            },
            {
                "kicker": "Throughput",
                "label": "Review Closure",
                "value": f"{reviewed_ratio:.0%}" if total_count else "0%",
                "note": "Records no longer pending.",
                "detail": f"{pending_count} record(s) still open.",
                "ratio": reviewed_ratio,
                "tone": "warn" if pending_count else "ok",
            },
            {
                "kicker": "Cloud Mirror",
                "label": "Feishu Integrity",
                "value": f"{sync_ratio:.0%}" if total_count else "0%",
                "note": "Sync coverage vs. local records.",
                "detail": f"{failed_sync_count} row(s) still need replay.",
                "ratio": sync_ratio,
                "tone": "danger" if failed_sync_count else ("ok" if synced_count else "warn"),
            },
        ],
    )

    section_title("Seven-Day Activity", "Seven-day volume and risk.")
    render_activity_strip(activity)

    section_title("Operations Deck", "Core tools and topology.")
    ops_cols = st.columns([1.02, 1.0, 0.98], gap="large")
    with ops_cols[0]:
        info_card(
            "Runtime Topology",
            [
                ("UI", f"127.0.0.1:{cfg['ui_port']}"),
                ("OCR", cfg["ocr_base_url"]),
                ("Mailpit", mailpit_url()),
                ("MySQL", f"{cfg['mysql_host']}:{cfg['mysql_port']}"),
            ],
        )
    with ops_cols[1]:
        quick_links_panel(
            "Shortcuts",
            [
                {"title": "Dashboard", "copy": "Stay here.", "href": "?view=dashboard", "target": "_self", "kicker": "Workspace"},
                {"title": "Review Desk", "copy": "Open approvals.", "href": "?view=anomaly_form", "target": "_self", "kicker": "Workspace"},
                {"title": "Mailpit", "copy": "View alert mail.", "href": mailpit_url(), "target": "_blank", "kicker": "Inbox"},
                {
                    "title": "OCR Docs",
                    "copy": "Open OCR docs.",
                    "href": f"{cfg['ocr_base_url'].rstrip('/')}/docs",
                    "target": "_blank",
                    "kicker": "Service",
                },
            ],
        )
    with ops_cols[2]:
        workflow_panel(
            "Pipeline",
            [
                {"title": "OCR Intake", "copy": "Normalize and extract.", "tone": "ok"},
                {"title": "AI Parse", "copy": "Dify first, OCR fallback.", "tone": "ok" if cfg.get("dify_api_key") else "warn"},
                {"title": "Risk Routing", "copy": "Write alerts and review state.", "tone": "warn" if risk_rows else "ok"},
                {"title": "Cloud Recovery", "copy": "Replay failed Feishu syncs.", "tone": "ok" if feishu_retry["enabled"] else "warn"},
            ],
        )

    surface_intro(
        "Operations center",
        "Service mesh and recovery",
        "Keep connector posture, failed sync replay, and priority alerts in one dense control lane.",
        badge(f"{connector_ok_count}/{connector_total} ready", "ok" if connector_ok_count == connector_total else "warn")
        + badge(f"{failed_sync_count} replay", "danger" if failed_sync_count else "ok"),
        compact=True,
    )
    dense_section_header(
        "Service Mesh",
        "OCR, Dify, Feishu, SMTP.",
        badge(f"{connector_ok_count} ready", "ok") + badge(f"{connector_total - connector_ok_count} blocked", "warn" if connector_ok_count != connector_total else "neutral"),
    )
    status_board(checks)

    section_title("Review Queue", "Filter, sort, and pin a work order.")
    with filter_shell(
        "Queue filters",
        "Search, narrow, and sort",
        "Keep the working slice focused without leaving the dashboard.",
        badge("Live filters", "neutral"),
    ):
        filter_cols = control_row([1.45, 0.9, 0.6, 0.85], gap="small")
        with filter_cols[0]:
            with control_field("Search", "Seller, buyer, invoice, or PO"):
                search = st.text_input(
                    "Search seller, buyer, invoice, or PO",
                    "",
                    label_visibility="collapsed",
                    placeholder="Search seller, buyer, invoice, or PO",
                )
        with filter_cols[1]:
            with control_field("Status", "Queue state in the current slice."):
                status_filter = st.selectbox(
                    "Status",
                    ["All", "Pending", "Approved", "Rejected", "NeedsReview"],
                    index=0,
                    label_visibility="collapsed",
                )
        with filter_cols[2]:
            with control_field("Risk filter", "Limit the slice to high-risk invoices.", field_class="control-field-toggle"):
                risk_only = st.checkbox("Risk only", value=False)
        with filter_cols[3]:
            with control_field("Sort", "Choose the queue ordering."):
                sort_mode = st.selectbox(
                    "Sort",
                    ["Newest first", "Risk first", "Largest delta"],
                    index=0,
                    label_visibility="collapsed",
                )

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

    if sort_mode == "Risk first":
        filtered.sort(
            key=lambda row: (
                safe_int(row.get("risk_flag")) != 1,
                -abs(safe_float(row.get("amount_diff"))),
                str(row.get("invoice_date") or ""),
                -safe_int(row.get("id")),
            )
        )
    elif sort_mode == "Largest delta":
        filtered.sort(
            key=lambda row: (
                -abs(safe_float(row.get("amount_diff"))),
                safe_int(row.get("risk_flag")) != 1,
                str(row.get("invoice_date") or ""),
                -safe_int(row.get("id")),
            )
        )
    else:
        filtered.sort(
            key=lambda row: (
                str(row.get("invoice_date") or ""),
                safe_int(row.get("id")),
            ),
            reverse=True,
        )

    filtered_risk_count = sum(1 for row in filtered if safe_int(row.get("risk_flag")) == 1)
    filtered_pending_count = sum(1 for row in filtered if str(row.get("invoice_status") or "") == "Pending")
    filtered_total_amount = sum(safe_float(row.get("total_amount_with_tax")) for row in filtered)
    shown_rows = filtered[:120]
    pills_html = (
        badge(status_filter if status_filter != "All" else "All statuses", "neutral")
        + badge("Risk only" if risk_only else "Full mix", "danger" if risk_only else "ok")
        + badge(sort_mode, "neutral")
        + badge(short_text(keyword, limit=16) if keyword else "No search", "warn" if keyword else "neutral")
    )
    command_panel(
        "Queue workspace",
        "Live queue snapshot",
        "Matched rows update with every filter and sort change.",
        [
            {
                "label": "Matched",
                "value": str(len(filtered)),
                "note": "Rows in scope.",
                "tone": "ok" if filtered else "warn",
            },
            {
                "label": "Risk Rows",
                "value": str(filtered_risk_count),
                "note": "Flagged in slice.",
                "tone": "danger" if filtered_risk_count else "ok",
            },
            {
                "label": "Pending Rows",
                "value": str(filtered_pending_count),
                "note": "Still open.",
                "tone": "warn" if filtered_pending_count else "ok",
            },
            {
                "label": "Matched Value",
                "value": fmt_money(filtered_total_amount),
                "note": f"Today: {today_count}.",
                "tone": "neutral",
            },
        ],
        pills_html=pills_html,
    )
    queue_grid_header(
        "Queue grid",
        "Working slice",
        "Scan matched rows, then pin one invoice without leaving the dashboard.",
        f"Showing {len(shown_rows)} of {len(filtered)} matched row(s)."
        + (" Refine filters to narrow the slice further." if len(filtered) > len(shown_rows) else " The full matched slice is visible below."),
        badge(f"{len(shown_rows)} shown", "neutral")
        + badge(f"{filtered_risk_count} risk", "danger" if filtered_risk_count else "ok")
        + badge(f"{filtered_pending_count} pending", "warn" if filtered_pending_count else "ok")
        + badge(sort_mode, "neutral"),
    )

    if not filtered:
        empty_state_card(
            "No invoices match this slice",
            "Relax the search term, status filter, or risk toggle to bring more records back into the working queue.",
            "neutral",
            badge(status_filter if status_filter != "All" else "All statuses", "neutral")
            + badge("Risk only" if risk_only else "Full mix", "warn" if risk_only else "ok"),
        )
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
    queue_top_cols = st.columns([1.06, 0.94], gap="large")
    with queue_top_cols[0]:
        slice_summary_slot = st.empty()
    with queue_top_cols[1]:
        with control_field("Pinned case", "Stays in sync with the current slice and review link."):
            selected_label = st.selectbox(
                "Pinned case",
                list(option_map.keys()),
                index=default_index,
                label_visibility="collapsed",
            )
    selected_id = option_map[selected_label]
    slice_summary_slot.markdown(
        textwrap.dedent(
            f"""
            <div class="queue-slice-summary">
              Status <strong>{esc(status_filter)}</strong>
              | Risk <strong>{'On' if risk_only else 'Off'}</strong>
              | Sort <strong>{esc(sort_mode)}</strong>
              | Showing <strong>{len(shown_rows)}</strong> of <strong>{len(filtered)}</strong>
              | Pinned <strong>#{selected_id}</strong>
            </div>
            """
        ).strip(),
        unsafe_allow_html=True,
    )
    grid_max_height = min(max(240, 118 + len(shown_rows) * 44), 430)
    render_queue_table(build_queue_grid_rows(shown_rows, selected_id), grid_max_height)

    with tab_shell("control-shell-ops-tabs"):
        ops_tabs = st.tabs(["Feishu Recovery", "Priority Alerts"])
    with ops_tabs[0]:
        metric_cols = st.columns(3)
        with metric_cols[0]:
            metric_card("Synced", str(feishu_sync.get("synced_count") or 0), "Rows already synced.")
        with metric_cols[1]:
            metric_card("Pending", str(feishu_sync.get("pending_count") or 0), "Rows not pushed yet.", "warn")
        with metric_cols[2]:
            metric_card("Failed", str(feishu_sync.get("failed_count") or 0), "Rows that need replay.", "danger")
        worker_label = "Enabled" if feishu_retry["enabled"] else "Disabled"
        worker_tone = "ok" if feishu_retry["enabled"] else "warn"
        with action_button_row(
            "Replay actions",
            "Feishu recovery controls",
            "Replay failed rows or push pending rows without leaving this pane.",
            badge(worker_label, worker_tone),
        ):
            action_cols = control_row([1, 1], gap="small")
            with action_cols[0]:
                with control_field("Failed batch", "Replay recoverable rows from the failure queue.", field_class="control-field-primary"):
                    if st.button("Retry Failed Syncs", use_container_width=True):
                        run_feishu_sync_action(db, cfg, mode="failed", limit=20)
            with action_cols[1]:
                with control_field("Pending batch", "Push rows that have not reached Feishu yet.", field_class="control-field-primary"):
                    if st.button("Sync Pending Rows", use_container_width=True):
                        run_feishu_sync_action(db, cfg, mode="pending", limit=20)
        ops_notice_bar(
            "Auto-retry worker",
            f"Mode {feishu_retry['mode']} every {feishu_retry['interval_sec'] or 300}s with batch size {feishu_retry['limit'] or 20}.",
            worker_tone,
            badge(worker_label, worker_tone),
        )
        if failed_sync_rows:
            surface_intro(
                "Exception recovery",
                "Feishu sync exception queue",
                "Recent failures ready for replay.",
                badge(f"{len(failed_sync_rows)} recoverable", "danger") + badge(worker_label, worker_tone),
                compact=True,
            )
            render_failed_sync_queue(failed_sync_rows, max_height=292)
            failed_option_map = {
                (
                    f"#{row.get('invoice_id')} | "
                    f"{row.get('seller_name') or 'N/A'} | "
                    f"{row.get('invoice_number') or row.get('invoice_code') or 'N/A'}"
                ): int(row["invoice_id"])
                for row in failed_sync_rows
            }
            replay_cols = control_row([1.18, 0.82], gap="small")
            with replay_cols[0]:
                with control_field("Failed sync target", "Pick one recent failed row for focused replay."):
                    selected_failed_label = st.selectbox(
                        "Recent failed syncs",
                        list(failed_option_map.keys()),
                        key="failed-feishu-sync-select",
                        label_visibility="collapsed",
                    )
            with replay_cols[1]:
                with control_field("Replay selection", "Run recovery on the selected invoice.", field_class="control-field-primary"):
                    if st.button("Retry Selected Failed Sync", use_container_width=True):
                        run_feishu_sync_action(
                            db,
                            cfg,
                            mode="recoverable",
                            limit=1,
                            invoice_ids=[failed_option_map[selected_failed_label]],
                        )
        else:
            empty_state_card(
                "Recovery queue is clear",
                "No recent failed Feishu sync rows need replay right now.",
                "ok",
                badge(worker_label, worker_tone),
            )
    with ops_tabs[1]:
        if risk_rows:
            risk_cols = st.columns(min(3, max(len(risk_rows[:3]), 1)))
            for idx, row in enumerate(risk_rows[:3]):
                with risk_cols[idx % len(risk_cols)]:
                    risk_spotlight_card(row)
        else:
            empty_state_card(
                "No priority alerts",
                "The current queue has no high-risk invoices waiting for spotlight review.",
                "ok",
                badge("Queue stable", "ok"),
            )

    detail = fetch_invoice_detail(db, selected_id)
    if not detail:
        empty_state_card(
            "Pinned case unavailable",
            "The selected invoice detail could not be loaded. Pick another queue row or refresh the dashboard.",
            "danger",
            badge(f"#{selected_id}", "danger"),
        )
        return

    invoice = detail["invoice"]
    purchase_order_no = str(invoice.get("purchase_order_no") or "").strip()
    unique_hash = str(invoice.get("unique_hash") or "").strip()
    sync_label, sync_tone = invoice_sync_snapshot(detail.get("sync"))
    risk_reason_summary = case_risk_summary(invoice)
    selected_badges = case_badges_html(
        invoice,
        sync_label=sync_label,
        sync_tone=sync_tone,
        purchase_order_no=purchase_order_no,
    )

    command_panel(
        "Case desk",
        "Pinned case snapshot",
        risk_reason_summary,
        [
            {
                "label": "Items",
                "value": str(len(detail.get("items") or [])),
                "note": "Parsed lines ready.",
                "tone": "ok" if detail.get("items") else "warn",
            },
            {
                "label": "Alerts",
                "value": f"P {invoice.get('notify_personal_status') or 'NotSent'} | L {invoice.get('notify_leader_status') or 'NotSent'}",
                "note": "Current routing.",
                "tone": tone_for_status(invoice.get("notify_personal_status")),
            },
            {
                "label": "Feishu",
                "value": sync_label,
                "note": "Cloud mirror state.",
                "tone": sync_tone,
            },
            {
                "label": "History",
                "value": str(len(detail.get("review_tasks") or [])),
                "note": "Manual actions on file.",
                "tone": "ok" if detail.get("review_tasks") else "warn",
            },
        ],
        pills_html=selected_badges,
        compact=True,
    )
    focus_panel(
        "Pinned case",
        f"Invoice #{invoice['id']} | {invoice.get('seller_name') or 'Unknown Seller'}",
        risk_reason_summary,
        selected_badges,
        [
            {
                "label": "Invoice Date",
                "value": fmt_dt(invoice.get("invoice_date"))[:10],
                "note": "Document date extracted from OCR or AI parsing.",
                "tone": "neutral",
            },
            {
                "label": "Alert Reach",
                "value": str(invoice.get("notify_personal_status") or "NotSent"),
                "note": f"Leader route: {invoice.get('notify_leader_status') or 'NotSent'}.",
                "tone": tone_for_status(invoice.get("notify_personal_status")),
            },
            {
                "label": "Review History",
                "value": str(len(detail.get("review_tasks") or [])),
                "note": "Manual decisions already recorded for this case.",
                "tone": "warn" if not detail.get("review_tasks") else "ok",
            },
            {
                "label": "Line Items",
                "value": str(len(detail.get("items") or [])),
                "note": "Rows available for financial reconciliation.",
                "tone": "ok" if detail.get("items") else "warn",
            },
        ],
        "Next step",
        "Open Review Desk to capture the final decision. Dashboard keeps the pinned record read-only.",
        compact=True,
    )
    surface_intro(
        "Actions",
        "Quick case actions",
        "Open the review desk, check risk email, or retry sync without losing the pinned case.",
        badge(sync_label, sync_tone) + badge(f"#{invoice['id']}", "neutral"),
        compact=True,
    )
    action_cols = st.columns(3, gap="small")
    with action_cols[0]:
        if st.button("Open Review Desk", key=f"open-review-desk-{invoice['id']}", use_container_width=True):
            switch_view(
                "anomaly_form",
                invoice_id=invoice["id"],
                purchase_order_no=purchase_order_no,
                unique_hash=unique_hash,
            )
    with action_cols[1]:
        render_html(
            f"""
            <a class="quick-link quick-link-compact" href="{html.escape(mailpit_url(), quote=True)}" target="_blank">
              <div class="quick-link-kicker">Inbox</div>
              <span class="quick-link-title">Open Risk Email</span>
              <span class="quick-link-copy">Mailpit deep link.</span>
            </a>
            """
        )
    with action_cols[2]:
        retry_enabled = not detail.get("sync") or detail["sync"].get("sync_error") or not detail["sync"].get("feishu_record_id")
        if st.button(
            "Retry Feishu Sync",
            key=f"retry-feishu-pinned-{invoice['id']}",
            use_container_width=True,
            disabled=not retry_enabled,
        ):
            run_feishu_sync_action(db, cfg, mode="recoverable", limit=1, invoice_ids=[int(invoice["id"])])
            st.rerun()

    with tab_shell():
        tabs = st.tabs(["Case Brief", "History", "Machine Output"])
    with tabs[0]:
        render_case_brief_view(
            invoice,
            detail,
            purchase_order_no=purchase_order_no,
            unique_hash=unique_hash,
            sync_label=sync_label,
            sync_tone=sync_tone,
            intro_copy="Scan identity, counterparties, and line amounts before opening Review Desk.",
            compact=True,
        )
    with tabs[1]:
        render_case_history_view(
            detail,
            sync_label=sync_label,
            sync_tone=sync_tone,
            intro_copy="System events, reviewer decisions, and cloud mirror state for the pinned case.",
            compact=True,
        )
    with tabs[2]:
        surface_intro(
            "Machine trace",
            "Extraction payloads",
            "OCR and parsed JSON for audit and debugging.",
            badge("OCR JSON", "neutral") + badge("LLM JSON", "ok"),
            compact=True,
        )
        render_machine_trace_view(invoice)


def render_anomaly_form(cfg: Dict[str, Any]) -> None:
    query_invoice_id = st.query_params.get("invoice_id")
    default_invoice_id = int(query_invoice_id) if str(query_invoice_id or "").isdigit() else 1
    try:
        db = db_client(cfg)
    except Exception as exc:
        render_runtime_unavailable(
            title="Risk Review Work Order",
            subtitle="The review surface is online, but it cannot load invoice context until MySQL is reachable again.",
            side_note=f"Port {cfg['ui_port']} | Waiting for data plane",
            badges_html=badge("FORM LIVE", "ok") + badge("DB OFFLINE", "danger") + badge("WRITEBACK PAUSED", "warn"),
            summary_title="Review Desk Paused",
            summary_copy="Manual decisions can only be written back after the database connection recovers. Start the local stack, then reopen this page with the same invoice deep link.",
            steps_title="Bring Review Back Online",
            steps=[
                {
                    "kicker": "Step 1",
                    "value": "Start MySQL",
                    "note": "The review desk reads invoice facts, history, and targets from the local database.",
                    "tone": "warn",
                },
                {
                    "kicker": "Step 2",
                    "value": "Keep The Same Link",
                    "note": "The query string invoice id will still work once the backend is healthy again.",
                    "tone": "neutral",
                },
                {
                    "kicker": "Step 3",
                    "value": "Refresh and Submit",
                    "note": "After recovery, this page will return to the full writeback workflow automatically.",
                    "tone": "ok",
                },
            ],
            error=exc,
        )
        return

    hero(
        "Risk Review Work Order",
        "Resolve the exception, record the decision, and keep the audit trail clean.",
        f"Port {cfg['ui_port']} | Review workspace",
        badge("REVIEW LIVE", "warn") + badge("DB COMMIT", "ok") + badge("AUDIT EVENT", "ok"),
    )
    consume_flash_notice()

    with toolbar_shell(
        "Toolbar",
        "Case routing",
        "Keep the case ID, dashboard, and risk inbox aligned while you review.",
        badge(f"#{default_invoice_id}", "neutral"),
    ):
        top_cols = control_row([0.46, 0.22, 0.32], gap="small")
        with top_cols[0]:
            with control_field("Invoice ID", "Switch the current case without leaving Review Desk."):
                invoice_id = st.number_input(
                    "Invoice ID",
                    min_value=1,
                    step=1,
                    value=default_invoice_id,
                    label_visibility="collapsed",
                )
        with top_cols[1]:
            with control_field("Navigation", "Return to the dashboard with the same invoice in focus.", field_class="control-field-primary"):
                if st.button("Back to Dashboard", use_container_width=True):
                    switch_view("dashboard", invoice_id=int(invoice_id))
        with top_cols[2]:
            with control_field("Inbox", "Open the alert email deep link for this workflow.", field_class="control-field-link"):
                render_html(
                    f"""
                    <a class="quick-link quick-link-compact" href="{html.escape(mailpit_url(), quote=True)}" target="_blank">
                      <div class="quick-link-kicker">Inbox</div>
                      <span class="quick-link-title">Open Risk Email</span>
                      <span class="quick-link-copy">Mailpit deep link.</span>
                    </a>
                    """
                )

    detail = fetch_invoice_detail(db, int(invoice_id))
    if not detail:
        empty_state_card(
            "Invoice not found",
            "Enter a valid invoice ID to reopen the review workspace for that case.",
            "danger",
            badge(f"#{int(invoice_id)}", "danger"),
        )
        return

    invoice = detail["invoice"]
    purchase_order_no = (
        str(st.query_params.get("purchase_order_no") or st.query_params.get("po_no") or "").strip()
        or str(invoice.get("purchase_order_no") or "").strip()
    )
    unique_hash = str(st.query_params.get("unique_hash") or invoice.get("unique_hash") or "").strip()
    sync_label, sync_tone = invoice_sync_snapshot(detail.get("sync"))
    risk_reason_summary = case_risk_summary(invoice)
    review_badges = case_badges_html(
        invoice,
        sync_label=sync_label,
        sync_tone=sync_tone,
        purchase_order_no=purchase_order_no,
    )

    metric_cols = st.columns(4, gap="small")
    with metric_cols[0]:
        metric_card("Invoice Amount", fmt_money(invoice.get("total_amount_with_tax")), "Captured document total.", compact=True)
    with metric_cols[1]:
        metric_card("Expected Amount", fmt_money(invoice.get("expected_amount")), "Reference PO amount.", compact=True)
    with metric_cols[2]:
        metric_card("Delta", fmt_money(invoice.get("amount_diff")), "Current control gap.", "danger", compact=True)
    with metric_cols[3]:
        metric_card("Current Status", str(invoice.get("invoice_status") or "-"), "Updates on submit.", "warn", compact=True)
    command_panel(
        "Case desk",
        "Decision snapshot",
        risk_reason_summary,
        [
            {
                "label": "Items",
                "value": str(len(detail.get("items") or [])),
                "note": "Parsed lines ready.",
                "tone": "ok" if detail.get("items") else "warn",
            },
            {
                "label": "Alerts",
                "value": f"P {invoice.get('notify_personal_status') or 'NotSent'} | L {invoice.get('notify_leader_status') or 'NotSent'}",
                "note": "Current routing.",
                "tone": tone_for_status(invoice.get("notify_personal_status")),
            },
            {
                "label": "Feishu",
                "value": sync_label,
                "note": "Cloud mirror state.",
                "tone": sync_tone,
            },
            {
                "label": "History",
                "value": str(len(detail.get("review_tasks") or [])),
                "note": "Manual actions on file.",
                "tone": "ok" if detail.get("review_tasks") else "warn",
            },
        ],
        pills_html=
            review_badges,
        compact=True,
    )
    focus_panel(
        "Approval workspace",
        f"Invoice #{invoice['id']} | {invoice.get('seller_name') or 'Unknown Seller'}",
        risk_reason_summary,
        review_badges,
        [
            {
                "label": "Invoice Date",
                "value": fmt_dt(invoice.get("invoice_date"))[:10],
                "note": "Document date extracted from OCR or AI parsing.",
                "tone": "neutral",
            },
            {
                "label": "Alert Reach",
                "value": str(invoice.get("notify_personal_status") or "NotSent"),
                "note": f"Leader route: {invoice.get('notify_leader_status') or 'NotSent'}.",
                "tone": tone_for_status(invoice.get("notify_personal_status")),
            },
            {
                "label": "Review History",
                "value": str(len(detail.get("review_tasks") or [])),
                "note": "Manual decisions already recorded for this case.",
                "tone": "warn" if not detail.get("review_tasks") else "ok",
            },
            {
                "label": "Line Items",
                "value": str(len(detail.get("items") or [])),
                "note": "Rows available for financial reconciliation.",
                "tone": "ok" if detail.get("items") else "warn",
            },
        ],
        "Reviewer Prompt",
        "Confirm the amount gap and counterparties first, then write the handling note so the audit trail reads clearly to the next operator.",
        compact=True,
    )

    with tab_shell():
        review_tabs = st.tabs(["Case Brief", "Decision", "History"])
    with review_tabs[0]:
        render_case_brief_view(
            invoice,
            detail,
            purchase_order_no=purchase_order_no,
            unique_hash=unique_hash,
            sync_label=sync_label,
            sync_tone=sync_tone,
            intro_copy="Confirm the document, counterparties, and parsed line amounts before sign-off.",
            compact=True,
        )
    with review_tabs[1]:
        surface_intro(
            "Decision",
            "Reviewer action center",
            "Write one clear decision note so status, audit trail, and downstream routing stay aligned.",
            badge(invoice.get("invoice_status") or "UNKNOWN", tone_for_status(invoice.get("invoice_status")))
            + badge(sync_label, sync_tone)
            + badge(f"#{invoice['id']}", "neutral"),
            compact=True,
        )
        decision_cols = st.columns([0.9, 1.1], gap="small")
        with decision_cols[0]:
            checklist_panel(
                "Decision flow",
                "Approval checklist before commit",
                [
                    {
                        "title": "Validate commercial identity",
                        "copy": "Check seller, buyer, tax IDs, and PO alignment before you close the case.",
                    },
                    {
                        "title": "Explain the amount outcome",
                        "copy": "State whether the delta is accepted, rejected, or escalated in plain finance language.",
                    },
                    {
                        "title": "Close the downstream loop",
                        "copy": "Keep email routing, Feishu sync, and final invoice status telling the same story.",
                    },
                ],
            )
            info_card(
                "Writeback Targets",
                [
                    ("PO number", purchase_order_no or "-"),
                    ("Unique hash", short_text(unique_hash or "-", limit=28)),
                    ("Cloud sync", sync_label),
                    ("Current status", invoice.get("invoice_status") or "-"),
                ],
                compact=True,
            )
            render_html(
                f"""
                <div class="panel-card panel-card-compact">
                  <div class="panel-title">Risk narrative</div>
                  <div class="integration-message">{esc(risk_reason_summary)}</div>
                </div>
                """
            )
        with decision_cols[1]:
            with form_shell(
                "Decision form",
                "Reviewer note and outcome",
                "Capture owner, result, and handling note in one productized approval form.",
                badge(invoice.get("invoice_status") or "UNKNOWN", tone_for_status(invoice.get("invoice_status"))),
            ):
                with st.form("anomaly_review_form"):
                    form_cols = control_row([1, 1], gap="small")
                    with form_cols[0]:
                        with control_field("Handler", "Reviewer or operator responsible for this decision."):
                            handler_user = st.text_input(
                                "Handler",
                                value=invoice.get("handler_user") or "",
                                label_visibility="collapsed",
                                placeholder="Finance reviewer or owner",
                            )
                    with form_cols[1]:
                        with control_field("Review Result", "Choose the final workflow outcome."):
                            allowed_statuses = ["Pending", "Approved", "Rejected", "NeedsReview"]
                            current_status = invoice.get("invoice_status") or "Pending"
                            invoice_status = st.selectbox(
                                "Review Result",
                                allowed_statuses,
                                index=allowed_statuses.index(current_status) if current_status in allowed_statuses else 0,
                                label_visibility="collapsed",
                            )
                    with control_field(
                        "Handling Note",
                        "Explain the decision, remediation, or escalation outcome for audit traceability.",
                        field_class="control-field-note",
                    ):
                        handler_reason = st.text_area(
                            "Handling Note",
                            value=invoice.get("handler_reason") or "",
                            height=180,
                            label_visibility="collapsed",
                            placeholder="Write the finance rationale, follow-up action, or escalation outcome.",
                        )
                    with control_field(
                        "Submit",
                        "Write decision, status, and audit trail back to MySQL.",
                        field_class="control-field-submit",
                    ):
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
            push_flash_notice(
                "Review saved",
                "The case status, reviewer note, and audit trail were written back successfully.",
                "ok",
                badge(invoice_status, tone_for_status(invoice_status)) + badge(f"#{invoice['id']}", "neutral"),
            )
            st.rerun()
    with review_tabs[2]:
        render_case_history_view(
            detail,
            sync_label=sync_label,
            sync_tone=sync_tone,
            intro_copy="System events and reviewer decisions attached to this invoice.",
            compact=True,
        )


def run_app(default_view: str = "dashboard") -> None:
    st.set_page_config(
        page_title="Invoice Operations Suite",
        page_icon="I",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    inject_theme()
    cfg = load_cfg()

    query_view = st.query_params.get("view")
    current_view = str(query_view or default_view)

    with st.sidebar:
        render_html(
            f"""
            <div class="nav-shell">
              <div class="nav-brand">
                <div class="hero-kicker">AIOPS FOR FINANCE</div>
                <div class="nav-title">Invoice Operations Suite</div>
                <div class="nav-copy">Navigation only. Work stays on the right.</div>
              </div>
              <div class="nav-meta">
                <div class="nav-meta-row"><span>Mode</span><strong>Local demo</strong></div>
                <div class="nav-meta-row"><span>UI</span><strong>{esc(f"127.0.0.1:{cfg['ui_port']}")}</strong></div>
                <div class="nav-meta-row"><span>Inbox</span><strong>Mailpit</strong></div>
              </div>
            </div>
            """
        )
        render_html(
            """
            <div class="sidebar-control-label">
              <div class="control-field-label">Workspace</div>
              <div class="control-field-hint">Switch between dashboard and review desk.</div>
            </div>
            """
        )
        sidebar_view = st.radio(
            "Workspace",
            options=["dashboard", "anomaly_form"],
            index=0 if current_view == "dashboard" else 1,
            format_func=lambda value: "Mission Control" if value == "dashboard" else "Review Desk",
            label_visibility="collapsed",
        )
        if sidebar_view != current_view:
            switch_view(sidebar_view)
        st.caption("Queue, sync, review on the right.")
        st.markdown(f"[Open Mailpit Inbox]({mailpit_url()})")

    if current_view == "anomaly_form":
        render_anomaly_form(cfg)
    else:
        render_dashboard(cfg)


if __name__ == "__main__":
    run_app()
