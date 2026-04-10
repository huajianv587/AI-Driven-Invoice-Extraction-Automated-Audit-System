import json

from apps.ui.streamlit_app import main


def update_invoice_review(
    db,
    invoice_id: int,
    purchase_order_no: str,
    unique_hash: str,
    handler_user: str,
    handler_reason: str,
    invoice_status: str,
) -> None:
    review_status = invoice_status if invoice_status in {"APPROVED", "REJECTED", "NEEDS_REVIEW"} else invoice_status.upper()
    invoice_status_label = {
        "PENDING": "Pending",
        "NEEDS_REVIEW": "NeedsReview",
        "APPROVED": "Approved",
        "REJECTED": "Rejected",
    }.get(review_status, "Pending")
    db.execute(
        """
        UPDATE invoices
        SET review_status=%s,
            invoice_status=%s,
            handler_user=%s,
            handler_reason=%s,
            handled_at=UTC_TIMESTAMP(),
            updated_at=UTC_TIMESTAMP()
        WHERE id=%s
        """,
        (review_status, invoice_status_label, handler_user or None, handler_reason or None, int(invoice_id)),
    )
    db.execute(
        """
        INSERT INTO invoice_review_actions(
          invoice_id, action_type, review_status, actor_user_id, actor_username, note, payload
        )
        VALUES(%s, %s, %s, %s, %s, %s, %s)
        """,
        (
            int(invoice_id),
            "MANUAL_REVIEW",
            review_status,
            0,
            handler_user or "legacy-script",
            handler_reason or None,
            json.dumps({"purchase_order_no": purchase_order_no, "unique_hash": unique_hash}, ensure_ascii=False),
        ),
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
            review_status,
            handler_user or None,
            handler_reason or None,
            "legacy_streamlit_wrapper",
        ),
    )
    db.execute(
        "INSERT INTO invoice_events(invoice_id, event_type, event_status, payload) VALUES(%s, %s, %s, %s)",
        (
            int(invoice_id),
            "REVIEW_SUBMITTED",
            review_status,
            json.dumps({"handler_user": handler_user, "note": handler_reason}, ensure_ascii=False),
        ),
    )


def run_app(default_view: str = "dashboard") -> None:
    del default_view
    main()


if __name__ == "__main__":
    run_app()
