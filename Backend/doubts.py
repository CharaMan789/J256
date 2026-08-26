from fastapi import APIRouter, Form, HTTPException, Depends, Query

from auth import require_user, get_current_user
from database import get_conn
from pseudonyms import generate_pseudonym

router = APIRouter()

VALID_CATEGORIES = {"doubt", "opinion", "idea"}

DOUBT_SELECT = """
    SELECT doubts.*, users.name AS user_name, users.picture AS user_picture,
           users.pseudonym AS user_account_pseudonym
    FROM doubts JOIN users ON doubts.user_id = users.id
"""

REPLY_SELECT = """
    SELECT doubt_replies.*, users.name AS user_name, users.picture AS user_picture,
           users.pseudonym AS user_account_pseudonym
    FROM doubt_replies JOIN users ON doubt_replies.user_id = users.id
"""


def _identity(row, is_anon_key="is_anonymous"):
    is_anon = bool(row[is_anon_key])
    # Per-post random name generated at creation time — see create_doubt /
    # create_reply below. Falls back to the account pseudonym only for
    # rows that predate this column (pre-2026-08-24).
    name = row["anon_pseudonym"] or row["user_account_pseudonym"]
    return {
        "author": name if is_anon else row["user_name"],
        "author_picture": None if is_anon else row["user_picture"],
        "is_anonymous": is_anon,
    }


def _doubt_to_dict(conn, row, user):
    vote_count = conn.execute(
        "SELECT COUNT(*) AS n FROM doubt_votes WHERE doubt_id = ?", (row["id"],)
    ).fetchone()["n"]
    reply_count = conn.execute(
        "SELECT COUNT(*) AS n FROM doubt_replies WHERE doubt_id = ?", (row["id"],)
    ).fetchone()["n"]
    escalate_count = conn.execute(
        "SELECT COUNT(*) AS n FROM doubt_escalations WHERE doubt_id = ?", (row["id"],)
    ).fetchone()["n"]

    has_voted = False
    has_escalated = False
    if user:
        has_voted = conn.execute(
            "SELECT 1 FROM doubt_votes WHERE doubt_id = ? AND user_id = ?", (row["id"], user["id"])
        ).fetchone() is not None
        has_escalated = conn.execute(
            "SELECT 1 FROM doubt_escalations WHERE doubt_id = ? AND user_id = ?", (row["id"], user["id"])
        ).fetchone() is not None

    d = {
        "id": row["id"],
        "category": row["category"],
        "title": row["title"],
        "body": row["body"],
        "created_at": row["created_at"],
        "vote_count": vote_count,
        "reply_count": reply_count,
        "escalate_count": escalate_count,
        "has_voted": has_voted,
        "has_escalated": has_escalated,
        "is_mine": bool(user) and row["user_id"] == user["id"],
    }
    d.update(_identity(row))
    return d


def _reply_to_dict(row, user):
    d = {
        "id": row["id"],
        "doubt_id": row["doubt_id"],
        "body": row["body"],
        "created_at": row["created_at"],
        "is_mine": bool(user) and row["user_id"] == user["id"],
    }
    d.update(_identity(row))
    return d


@router.post("/doubts")
def create_doubt(
    category: str = Form(...),
    title: str = Form(...),
    body: str = Form(...),
    is_anonymous: bool = Form(False),
    user: dict = Depends(require_user),
):
    if category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")
    with get_conn() as conn:
        anon_pseudonym = generate_pseudonym() if is_anonymous else None
        cur = conn.execute(
            "INSERT INTO doubts (user_id, is_anonymous, category, title, body, anon_pseudonym) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user["id"], int(is_anonymous), category, title, body, anon_pseudonym),
        )
        conn.commit()
        row = conn.execute(DOUBT_SELECT + " WHERE doubts.id = ?", (cur.lastrowid,)).fetchone()
        return _doubt_to_dict(conn, row, user)


@router.get("/doubts")
def list_doubts(
    category: str | None = Query(None),
    sort: str = Query("new", pattern="^(new|top)$"),
    user: dict | None = Depends(get_current_user),
):
    query = DOUBT_SELECT
    params = []
    if category:
        if category not in VALID_CATEGORIES:
            raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")
        query += " WHERE doubts.category = ?"
        params.append(category)
    query += " ORDER BY doubts.created_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        doubts = [_doubt_to_dict(conn, r, user) for r in rows]

    if sort == "top":
        doubts.sort(key=lambda d: d["vote_count"], reverse=True)

    return doubts


@router.get("/doubts/{doubt_id}")
def get_doubt(doubt_id: int, user: dict | None = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(DOUBT_SELECT + " WHERE doubts.id = ?", (doubt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        doubt = _doubt_to_dict(conn, row, user)
        replies = conn.execute(
            REPLY_SELECT + " WHERE doubt_replies.doubt_id = ? ORDER BY doubt_replies.created_at ASC",
            (doubt_id,),
        ).fetchall()
        doubt["replies"] = [_reply_to_dict(r, user) for r in replies]
    return doubt


@router.delete("/doubts/{doubt_id}")
def delete_doubt(doubt_id: int, user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM doubts WHERE id = ?", (doubt_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        if row["user_id"] != user["id"]:
            raise HTTPException(403, "You can only delete your own post")
        conn.execute("DELETE FROM doubt_replies WHERE doubt_id = ?", (doubt_id,))
        conn.execute("DELETE FROM doubt_votes WHERE doubt_id = ?", (doubt_id,))
        conn.execute("DELETE FROM doubt_escalations WHERE doubt_id = ?", (doubt_id,))
        conn.execute("DELETE FROM doubts WHERE id = ?", (doubt_id,))
        conn.commit()
    return {"ok": True}


@router.post("/doubts/{doubt_id}/replies")
def create_reply(
    doubt_id: int,
    body: str = Form(...),
    is_anonymous: bool = Form(False),
    user: dict = Depends(require_user),
):
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM doubts WHERE id = ?", (doubt_id,)).fetchone():
            raise HTTPException(404, "Not found")
        anon_pseudonym = generate_pseudonym() if is_anonymous else None
        cur = conn.execute(
            "INSERT INTO doubt_replies (doubt_id, user_id, is_anonymous, body, anon_pseudonym) "
            "VALUES (?, ?, ?, ?, ?)",
            (doubt_id, user["id"], int(is_anonymous), body, anon_pseudonym),
        )
        conn.commit()
        row = conn.execute(REPLY_SELECT + " WHERE doubt_replies.id = ?", (cur.lastrowid,)).fetchone()
        return _reply_to_dict(row, user)


@router.post("/doubts/{doubt_id}/vote")
def toggle_vote(doubt_id: int, user: dict = Depends(require_user)):
    """Upvote-only, toggled: voting again removes your vote. No downvotes exist."""
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM doubts WHERE id = ?", (doubt_id,)).fetchone():
            raise HTTPException(404, "Not found")
        existing = conn.execute(
            "SELECT 1 FROM doubt_votes WHERE doubt_id = ? AND user_id = ?", (doubt_id, user["id"])
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM doubt_votes WHERE doubt_id = ? AND user_id = ?", (doubt_id, user["id"])
            )
            voted = False
        else:
            conn.execute(
                "INSERT INTO doubt_votes (doubt_id, user_id) VALUES (?, ?)", (doubt_id, user["id"])
            )
            voted = True
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM doubt_votes WHERE doubt_id = ?", (doubt_id,)
        ).fetchone()["n"]
    return {"has_voted": voted, "vote_count": count}


@router.post("/doubts/{doubt_id}/escalate")
def toggle_escalate(doubt_id: int, user: dict = Depends(require_user)):
    """Flag a doubt/opinion/idea as worth turning into a debate or seminar.
    Toggled, like votes. This just records interest — the actual moderator
    review queue is a separate phase."""
    with get_conn() as conn:
        if not conn.execute("SELECT 1 FROM doubts WHERE id = ?", (doubt_id,)).fetchone():
            raise HTTPException(404, "Not found")
        existing = conn.execute(
            "SELECT 1 FROM doubt_escalations WHERE doubt_id = ? AND user_id = ?", (doubt_id, user["id"])
        ).fetchone()
        if existing:
            conn.execute(
                "DELETE FROM doubt_escalations WHERE doubt_id = ? AND user_id = ?", (doubt_id, user["id"])
            )
            escalated = False
        else:
            conn.execute(
                "INSERT INTO doubt_escalations (doubt_id, user_id) VALUES (?, ?)", (doubt_id, user["id"])
            )
            escalated = True
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM doubt_escalations WHERE doubt_id = ?", (doubt_id,)
        ).fetchone()["n"]
    return {"has_escalated": escalated, "escalate_count": count}