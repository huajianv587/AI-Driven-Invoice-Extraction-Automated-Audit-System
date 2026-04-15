from __future__ import annotations

from typing import Any


class InvalidStateTransition(ValueError):
    pass


TERMINAL_REVIEW_STATUSES = {"Approved", "Rejected"}
ALLOWED_REVIEW_STATUSES = {"Pending", "Approved", "Rejected", "NeedsReview"}
REVIEWER_ALLOWED_FROM = {"Pending", "NeedsReview", "", None}


def validate_review_transition(current_status: Any, next_status: str, actor_role: str) -> None:
    normalized_next = str(next_status or "").strip()
    normalized_current = str(current_status or "").strip()
    role = str(actor_role or "").strip().lower()
    if normalized_next not in ALLOWED_REVIEW_STATUSES:
        raise InvalidStateTransition(f"Unsupported invoice status: {normalized_next or '-'}")
    if normalized_current == normalized_next and not (role != "admin" and normalized_current in TERMINAL_REVIEW_STATUSES):
        return
    if role == "admin":
        return
    if normalized_current in TERMINAL_REVIEW_STATUSES:
        raise InvalidStateTransition("Only admins can reopen an approved or rejected invoice.")
    if normalized_current not in REVIEWER_ALLOWED_FROM:
        raise InvalidStateTransition(f"Reviewers cannot transition from {normalized_current or '-'} to {normalized_next}.")
