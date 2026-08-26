"""Reporting + moderation for J.

- Any signed-in user can report a post (explore post or newspaper
  article). One report per user per post.
- Moderators see all pending reports under "Reported Posts" and can:
    - Cancel the report (no action taken), or
    - Warn the author: the moderator writes a reason, which is emailed
      to the author. The moderator is never shown who the recipient is.
- Email sending is stubbed for now (stored + logged, not actually sent).
  Swap send_warning_email() for a real SMTP call when credentials exist.
- Ban Polls: a moderator can start a public vote on de-anonymizing the
  author of a reported anonymous post, citing a reason everyone can see.
  Anyone signed in gets one irreversible vote, yes or no. Reaching the
  vote conditions (see K_RATIO / TURNOUT_RATIO below) never reveals
  identity by itself — it only unlocks a "Reveal identity" button for
  moderators. A moderator must actively click it, and the click is
  re-checked against the conditions server-side regardless of what the
  frontend shows. If either condition isn't met, reveal is refused.
"""

import os
import smtplib
from email.message import EmailMessage

from fastapi import APIRouter, Form, HTTPException, Depends

from auth import require_user, get_current_user
from database import get_conn

router = APIRouter()

SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
# What shows up in the recipient's inbox as the sender name + address.
SMTP_FROM = os.environ.get("SMTP_FROM", SMTP_USER)


def require_moderator(request_user: dict = Depends(require_user)):
    if not request_user.get("is_moderator"):
        raise HTTPException(403, "Moderators only")
    return request_user


def _post_and_author(conn, post_kind, post_id):
    if post_kind == "explore":
        row = conn.execute(
            "SELECT explore_posts.*, users.email AS author_email FROM explore_posts "
            "JOIN users ON explore_posts.user_id = users.id WHERE explore_posts.id = ?",
            (post_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT posts.*, users.email AS author_email FROM posts "
            "JOIN users ON posts.user_id = users.id WHERE posts.id = ?",
            (post_id,),
        ).fetchone()
    return row


def send_warning_email(to_email: str, reason: str):
    """Sends the warning over SMTP (Gmail by default — see backend/.env).
    Callers never see to_email, so nothing else about the calling code
    needs to change. Falls back to logging only if SMTP isn't configured,
    so local dev without credentials still works without crashing."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[stub email — SMTP not configured] To: {to_email}\nSubject: Warning about your post on J\n\n{reason}")
        return

    msg = EmailMessage()
    msg["Subject"] = "Warning about your post on J"
    msg["From"] = SMTP_FROM
    msg["To"] = to_email
    msg.set_content(
        "A moderator has issued a warning about one of your posts on J.\n\n"
        f"Reason given:\n{reason}\n\n"
        "This is an automated message — please don't reply to this address."
    )

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.send_message(msg)
    except Exception as e:
        # Don't let a mail failure break the moderation action itself —
        # the warning is already recorded in the DB regardless. Just log it.
        print(f"[email send failed] To: {to_email} — {e}\nReason was:\n{reason}")


# ---------- reporting (any signed-in user) ----------

@router.post("/reports")
def create_report(
    post_kind: str = Form(...),
    post_id: int = Form(...),
    user: dict = Depends(require_user),
):
    if post_kind not in {"explore", "article"}:
        raise HTTPException(400, "post_kind must be 'explore' or 'article'")
    with get_conn() as conn:
        post = _post_and_author(conn, post_kind, post_id)
        if not post:
            raise HTTPException(404, "Post not found")
        try:
            conn.execute(
                "INSERT INTO reports (post_kind, post_id, reported_by_user_id) VALUES (?, ?, ?)",
                (post_kind, post_id, user["id"]),
            )
            conn.commit()
        except Exception:
            raise HTTPException(400, "You've already reported this post")
    return {"ok": True}


# ---------- moderator queue ----------

@router.get("/moderation/reported")
def list_reported(moderator: dict = Depends(require_moderator)):
    """All pending reports, oldest first, with the reported content
    attached so moderators can review inline."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT reports.*, reporter.name AS reported_by_name "
            "FROM reports JOIN users AS reporter ON reports.reported_by_user_id = reporter.id "
            "WHERE reports.status = 'pending' ORDER BY reports.created_at ASC"
        ).fetchall()

        result = []
        for r in rows:
            post = _post_and_author(conn, r["post_kind"], r["post_id"])
            item = dict(r)
            if post:
                item["post_title"] = post["title"]
                item["post_body"] = post["body"]
                item["post_type"] = post["type"] if r["post_kind"] == "explore" else "article"
                item["post_exists"] = True
                item["post_is_anonymous"] = bool(post["is_anonymous"])
            else:
                item["post_title"] = "(post deleted)"
                item["post_body"] = ""
                item["post_type"] = r["post_kind"]
                item["post_exists"] = False
                item["post_is_anonymous"] = False
            result.append(item)
        return result


@router.post("/moderation/reports/{report_id}/cancel")
def cancel_report(report_id: int, moderator: dict = Depends(require_moderator)):
    with get_conn() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            raise HTTPException(404, "Not found")
        if report["status"] != "pending":
            raise HTTPException(400, f"Report already {report['status']}")
        conn.execute("UPDATE reports SET status = 'cancelled' WHERE id = ?", (report_id,))
        conn.commit()
    return {"ok": True}


@router.post("/moderation/reports/{report_id}/warn")
def warn_author(
    report_id: int,
    reason: str = Form(...),
    moderator: dict = Depends(require_moderator),
):
    if not reason.strip():
        raise HTTPException(400, "Give a reason before warning")
    with get_conn() as conn:
        report = conn.execute("SELECT * FROM reports WHERE id = ?", (report_id,)).fetchone()
        if not report:
            raise HTTPException(404, "Not found")
        if report["status"] != "pending":
            raise HTTPException(400, f"Report already {report['status']}")

        post = _post_and_author(conn, report["post_kind"], report["post_id"])
        if not post:
            raise HTTPException(404, "The reported post no longer exists")

        conn.execute(
            "INSERT INTO warnings (report_id, target_user_id, moderator_id, reason) VALUES (?, ?, ?, ?)",
            (report_id, post["user_id"], moderator["id"], reason),
        )
        conn.execute("UPDATE reports SET status = 'warned' WHERE id = ?", (report_id,))
        conn.commit()

        send_warning_email(post["author_email"], reason)

    return {"ok": True}


# ---------- ban polls (moderator-started, public vote) ----------

K_RATIO = 5.0          # x/y must be >= this (y = 0 auto-passes)
TURNOUT_RATIO = 0.65   # x+y must be >= this fraction of all registered users


def _total_users(conn):
    return conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]


def _poll_counts(conn, poll_id):
    yes = conn.execute(
        "SELECT COUNT(*) AS n FROM ban_poll_votes WHERE poll_id = ? AND vote = 'yes'", (poll_id,)
    ).fetchone()["n"]
    no = conn.execute(
        "SELECT COUNT(*) AS n FROM ban_poll_votes WHERE poll_id = ? AND vote = 'no'", (poll_id,)
    ).fetchone()["n"]
    return yes, no


def _conditions_met(poll, yes, no, total_users):
    total_votes = yes + no
    turnout_met = total_users > 0 and total_votes >= poll["turnout_ratio"] * total_users
    ratio_met = (no == 0 and yes > 0) or (no > 0 and (yes / no) >= poll["k_ratio"])
    return turnout_met and ratio_met


def _poll_to_dict(conn, poll):
    yes, no = _poll_counts(conn, poll["id"])
    total_users = _total_users(conn)
    post = _post_and_author(conn, poll["post_kind"], poll["post_id"])
    d = dict(poll)
    d["yes_votes"] = yes
    d["no_votes"] = no
    d["total_users"] = total_users
    d["conditions_met"] = poll["status"] == "open" and _conditions_met(poll, yes, no, total_users)
    d["post_title"] = post["title"] if post else "(post deleted)"
    d["post_body"] = post["body"] if post else ""
    d["post_type"] = (post["type"] if poll["post_kind"] == "explore" else "article") if post else poll["post_kind"]
    # The target's identity is only ever included once resolved.
    d.pop("target_user_id", None)
    return d


@router.post("/moderation/ban-polls")
def start_ban_poll(
    post_kind: str = Form(...),
    post_id: int = Form(...),
    reason: str = Form(...),
    moderator: dict = Depends(require_moderator),
):
    if post_kind not in {"explore", "article"}:
        raise HTTPException(400, "post_kind must be 'explore' or 'article'")
    if not reason.strip():
        raise HTTPException(400, "Give a reason for the ban poll")
    with get_conn() as conn:
        post = _post_and_author(conn, post_kind, post_id)
        if not post:
            raise HTTPException(404, "Post not found")
        if not post["is_anonymous"]:
            raise HTTPException(400, "Ban polls are only for anonymous posts — a named post has no identity to reveal")
        cur = conn.execute(
            "INSERT INTO ban_polls (post_kind, post_id, target_user_id, started_by_id, reason, k_ratio, turnout_ratio) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (post_kind, post_id, post["user_id"], moderator["id"], reason, K_RATIO, TURNOUT_RATIO),
        )
        conn.commit()
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (cur.lastrowid,)).fetchone()
        return _poll_to_dict(conn, poll)


@router.get("/moderation/ban-polls")
def list_ban_polls(user: dict | None = Depends(get_current_user)):
    """Public — anyone can see open and resolved ban polls, including
    logged-out visitors, since the resolution announcement is public."""
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM ban_polls ORDER BY created_at DESC").fetchall()
        result = []
        for p in rows:
            d = _poll_to_dict(conn, p)
            if user:
                my_vote = conn.execute(
                    "SELECT vote FROM ban_poll_votes WHERE poll_id = ? AND user_id = ?", (p["id"], user["id"])
                ).fetchone()
                d["my_vote"] = my_vote["vote"] if my_vote else None
            else:
                d["my_vote"] = None
            result.append(d)
        return result


@router.get("/moderation/ban-polls/{poll_id}")
def get_ban_poll(poll_id: int, user: dict | None = Depends(get_current_user)):
    with get_conn() as conn:
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (poll_id,)).fetchone()
        if not poll:
            raise HTTPException(404, "Not found")
        d = _poll_to_dict(conn, poll)
        d["my_vote"] = None
        if user:
            my_vote = conn.execute(
                "SELECT vote FROM ban_poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user["id"])
            ).fetchone()
            d["my_vote"] = my_vote["vote"] if my_vote else None
        return d


@router.post("/moderation/ban-polls/{poll_id}/vote")
def vote_ban_poll(
    poll_id: int,
    vote: str = Form(...),
    user: dict = Depends(require_user),
):
    """One vote per signed-in user, irreversible. Auto-resolves — and
    reveals identity publicly — the instant the conditions are met."""
    if vote not in {"yes", "no"}:
        raise HTTPException(400, "vote must be 'yes' or 'no'")
    with get_conn() as conn:
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (poll_id,)).fetchone()
        if not poll:
            raise HTTPException(404, "Not found")
        if poll["status"] != "open":
            raise HTTPException(400, "This ban poll is already resolved")
        already = conn.execute(
            "SELECT 1 FROM ban_poll_votes WHERE poll_id = ? AND user_id = ?", (poll_id, user["id"])
        ).fetchone()
        if already:
            raise HTTPException(400, "You've already voted on this poll — votes can't be changed")
        conn.execute(
            "INSERT INTO ban_poll_votes (poll_id, user_id, vote) VALUES (?, ?, ?)",
            (poll_id, user["id"], vote),
        )
        conn.commit()
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (poll_id,)).fetchone()
        return _poll_to_dict(conn, poll)


@router.post("/moderation/ban-polls/{poll_id}/reveal")
def reveal_ban_poll(poll_id: int, moderator: dict = Depends(require_moderator)):
    """Moderator-triggered reveal. Only succeeds if both resolution
    conditions are actually met at the moment of the click — the frontend
    disables the button until then, but this is re-checked server-side
    regardless, since conditions are never enough on their own to trigger
    a reveal automatically."""
    with get_conn() as conn:
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (poll_id,)).fetchone()
        if not poll:
            raise HTTPException(404, "Not found")
        if poll["status"] != "open":
            raise HTTPException(400, "This ban poll is already resolved")

        yes, no = _poll_counts(conn, poll_id)
        total_users = _total_users(conn)
        if not _conditions_met(poll, yes, no, total_users):
            raise HTTPException(400, "Conditions for de-anonymization aren't met yet")

        target = conn.execute("SELECT * FROM users WHERE id = ?", (poll["target_user_id"],)).fetchone()
        conn.execute(
            "UPDATE ban_polls SET status = 'resolved', resolved_at = datetime('now'), revealed_name = ? WHERE id = ?",
            (target["name"], poll_id),
        )
        conn.commit()
        poll = conn.execute("SELECT * FROM ban_polls WHERE id = ?", (poll_id,)).fetchone()
        return _poll_to_dict(conn, poll)


@router.get("/moderation/ban-polls/announcements")
def list_announcements():
    """Public feed of resolved ban polls — the automatic public
    announcement text is built on the frontend from this data:
    'The Ban Poll No. {id} resulted in de-anonymization of {revealed_name}.'"""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, revealed_name, resolved_at FROM ban_polls WHERE status = 'resolved' ORDER BY resolved_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]