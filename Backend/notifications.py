"""Notifications for J256.

By design, a notification says only "someone replied to one of your
discussions/comments" — never which one, never who, never what was said.
See the notifications table in database.py for the full reasoning: this
mirrors the same anonymity guarantee anonymous posts already have (their
is_mine is forced False even for the author's own session), extended to
this feature so a glance at someone's notifications — on a shared device,
over their shoulder, or by anyone who's ever logged into the account —
can't be used to match a notification against the public feed and
deanonymize them. There is deliberately no way to click a notification
through to the post that caused it.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth import require_user
from database import get_conn

router = APIRouter()

# The only text a person ever sees — generic on purpose. Keep this in
# sync with the CHECK constraint on notifications.kind in database.py.
KIND_TEXT = {
    "reply_to_post": "Someone replied to one of your discussions.",
    "reply_to_reply": "Someone replied to one of your comments.",
}


def create_notification(conn, user_id: int, kind: str):
    """Callers (explore.py) are responsible for conn.commit() — this just
    queues the insert in the same transaction as whatever triggered it."""
    conn.execute(
        "INSERT INTO notifications (user_id, kind) VALUES (?, ?)",
        (user_id, kind),
    )


def _to_dict(row):
    return {
        "id": row["id"],
        "text": KIND_TEXT.get(row["kind"], "You have new activity."),
        "is_read": bool(row["is_read"]),
        "created_at": row["created_at"],
    }


@router.get("/notifications")
def list_notifications(user: dict = Depends(require_user)):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
            (user["id"],),
        ).fetchall()
    return [_to_dict(r) for r in rows]


@router.get("/notifications/unread-count")
def unread_count(user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM notifications WHERE user_id = ? AND is_read = 0",
            (user["id"],),
        ).fetchone()
    return {"count": row["n"]}


@router.post("/notifications/read-all")
def mark_all_read(user: dict = Depends(require_user)):
    """Marking individually isn't offered — there's nothing to click
    through to per-notification anyway, so "I've seen my notifications"
    is the only meaningful read state."""
    with get_conn() as conn:
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE user_id = ? AND is_read = 0",
            (user["id"],),
        )
        conn.commit()
    return {"ok": True}