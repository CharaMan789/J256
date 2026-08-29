from pathlib import Path

from fastapi import APIRouter, Form, File, UploadFile, HTTPException, Depends, Query

from auth import require_user, get_current_user
from database import get_conn
from pseudonyms import generate_pseudonym
from reactions import reaction_counts, my_reaction, toggle_reaction
from storage import upload_fileobj, delete_key, public_url

router = APIRouter()

VALID_TYPES = {"poll", "discussion", "announcement"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}

EXPLORE_SELECT = """
    SELECT explore_posts.*, users.name AS user_name, users.picture AS user_picture,
           users.pseudonym AS user_account_pseudonym
    FROM explore_posts JOIN users ON explore_posts.user_id = users.id
"""

REPLY_SELECT = """
    SELECT explore_replies.*, users.name AS user_name, users.picture AS user_picture,
           users.pseudonym AS user_account_pseudonym
    FROM explore_replies JOIN users ON explore_replies.user_id = users.id
"""


def _identity(row):
    is_anon = bool(row["is_anonymous"])
    # Per-post random name, generated once at creation (see create_poll /
    # create_discussion / create_announcement / create_reply below).
    # Falls back to the account's fixed pseudonym only for rows that
    # predate this column (pre-2026-08-24 data).
    name = row["anon_pseudonym"] or row["user_account_pseudonym"]
    return {
        "author": name if is_anon else row["user_name"],
        "author_picture": None if is_anon else row["user_picture"],
        "is_anonymous": is_anon,
    }


def _attachments_for(conn, owner_type, owner_id):
    rows = conn.execute(
        "SELECT * FROM explore_attachments WHERE owner_type = ? AND owner_id = ? ORDER BY uploaded_at ASC",
        (owner_type, owner_id),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            # file_path stores the R2 object key (not a local filesystem
            # path — the column name predates the R2 migration, kept as-is
            # so no schema/migration was needed to make this switch).
            "url": public_url(r["file_path"]),
            "original_name": r["original_name"],
        }
        for r in rows
    ]


def _save_attachments(conn, owner_type, owner_id, files):
    """files: list of UploadFile (may contain None/empty entries, which are skipped)."""
    for f in files or []:
        if not f or not f.filename:
            continue
        ext = Path(f.filename).suffix.lower()
        if ext in VIDEO_EXTENSIONS:
            kind = "video"
        elif ext in AUDIO_EXTENSIONS:
            kind = "audio"
        else:
            kind = "image"
        # Uploaded straight to R2 (Cloudflare object storage) instead of
        # local disk — survives every Render redeploy/restart/spin-down,
        # since it lives completely outside the app server's own
        # filesystem. See storage.py for why this exists.
        object_key = upload_fileobj(f.file, f.filename)
        conn.execute(
            "INSERT INTO explore_attachments (owner_type, owner_id, kind, file_path, original_name) "
            "VALUES (?, ?, ?, ?, ?)",
            (owner_type, owner_id, kind, object_key, f.filename),
        )


def _poll_result(conn, post_id, user):
    options = conn.execute(
        "SELECT * FROM explore_poll_options WHERE post_id = ? ORDER BY position ASC", (post_id,)
    ).fetchall()

    my_option_id = None
    if user:
        my_vote = conn.execute(
            "SELECT option_id FROM explore_poll_votes WHERE post_id = ? AND user_id = ?",
            (post_id, user["id"]),
        ).fetchone()
        if my_vote:
            my_option_id = my_vote["option_id"]

    result = []
    total_votes = 0
    for opt in options:
        count = conn.execute(
            "SELECT COUNT(*) AS n FROM explore_poll_votes WHERE option_id = ?", (opt["id"],)
        ).fetchone()["n"]
        total_votes += count
        result.append({
            "id": opt["id"],
            "text": opt["option_text"],
            "vote_count": count,
            "is_mine": opt["id"] == my_option_id,
        })

    return {"options": result, "total_votes": total_votes, "my_option_id": my_option_id}


def _post_to_dict(conn, row, user, include_replies=False):
    is_anon = bool(row["is_anonymous"])
    d = {
        "id": row["id"],
        "type": row["type"],
        "title": row["title"],
        "body": row["body"],
        "created_at": row["created_at"],
        # Deliberately false for anonymous posts, even to the author's own
        # session: ownership must not be discoverable by browsing the feed
        # (e.g. on a shared/borrowed login), and anonymous posts are
        # permanent — there is no author-side delete for them. See
        # delete_explore_post below for the enforced version of this rule.
        "is_mine": bool(user) and not is_anon and row["user_id"] == user["id"],
        # The post's own author line is always OP by definition.
        "is_op": True,
    }
    like_count, dislike_count = reaction_counts(conn, "explore", row["id"])
    d["like_count"] = like_count
    d["dislike_count"] = dislike_count
    d["my_reaction"] = my_reaction(conn, "explore", row["id"], user)
    d.update(_identity(row))

    if row["type"] == "poll":
        d.update(_poll_result(conn, row["id"], user))
    else:
        d["attachments"] = _attachments_for(conn, "post", row["id"])

    if row["type"] == "discussion":
        d["reply_count"] = conn.execute(
            "SELECT COUNT(*) AS n FROM explore_replies WHERE post_id = ?", (row["id"],)
        ).fetchone()["n"]
        if include_replies:
            replies = conn.execute(
                REPLY_SELECT + " WHERE explore_replies.post_id = ? ORDER BY explore_replies.created_at ASC",
                (row["id"],),
            ).fetchall()
            d["replies"] = _build_reply_tree(conn, replies, user, row["user_id"])

    return d


def _build_reply_tree(conn, rows, user, post_author_id):
    """Turns the flat, chronologically-ordered explore_replies rows for a
    post into a nested tree, one level: each reply carries a "children"
    list of the replies made directly to it. Fetched as one flat query
    (cheap, one round trip) and assembled here rather than querying per
    parent, then reassembled by parent_reply_id — O(n) either way, but
    this keeps it to a single SELECT regardless of thread depth/width."""
    by_id = {}
    roots = []
    for row in rows:
        d = _reply_to_dict(conn, row, user, post_author_id)
        d["children"] = []
        by_id[row["id"]] = d
        if row["parent_reply_id"] and row["parent_reply_id"] in by_id:
            by_id[row["parent_reply_id"]]["children"].append(d)
        else:
            roots.append(d)
    return roots


def _reply_to_dict(conn, row, user, post_author_id):
    is_anon = bool(row["is_anonymous"])
    like_count, dislike_count = reaction_counts(conn, "explore_reply", row["id"])
    d = {
        "id": row["id"],
        "post_id": row["post_id"],
        "parent_reply_id": row["parent_reply_id"],
        "body": row["body"],
        "created_at": row["created_at"],
        "is_mine": bool(user) and not is_anon and row["user_id"] == user["id"],
        # True when this reply's author is the same account that started
        # the thread — checked by user_id, not by name, so it still works
        # when the OP is replying anonymously with a different per-row
        # pseudonym than their original (possibly also anonymous) post.
        "is_op": row["user_id"] == post_author_id,
        "attachments": _attachments_for(conn, "reply", row["id"]),
        "like_count": like_count,
        "dislike_count": dislike_count,
        "my_reaction": my_reaction(conn, "explore_reply", row["id"], user),
    }
    d.update(_identity(row))
    return d


def _new_anon_pseudonym(is_anonymous):
    """Generate a fresh random pseudonym for this specific post/reply, or
    None for named content. Called once at creation time — never reused
    across posts, even by the same author."""
    return generate_pseudonym() if is_anonymous else None


@router.post("/explore/polls")
def create_poll(
    question: str = Form(...),
    options: list[str] = Form(...),
    is_anonymous: bool = Form(False),
    user: dict = Depends(require_user),
):
    cleaned = [o.strip() for o in options if o and o.strip()]
    if len(cleaned) < 2:
        raise HTTPException(400, "A poll needs at least 2 options")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO explore_posts (user_id, is_anonymous, type, title, body, anon_pseudonym) "
            "VALUES (?, ?, 'poll', ?, '', ?)",
            (user["id"], int(is_anonymous), question, _new_anon_pseudonym(is_anonymous)),
        )
        post_id = cur.lastrowid
        for i, opt in enumerate(cleaned):
            conn.execute(
                "INSERT INTO explore_poll_options (post_id, option_text, position) VALUES (?, ?, ?)",
                (post_id, opt, i),
            )
        conn.commit()
        row = conn.execute(EXPLORE_SELECT + " WHERE explore_posts.id = ?", (post_id,)).fetchone()
        return _post_to_dict(conn, row, user)


@router.post("/explore/discussions")
async def create_discussion(
    title: str = Form(...),
    body: str = Form(...),
    is_anonymous: bool = Form(False),
    files: list[UploadFile] | None = File(None),
    user: dict = Depends(require_user),
):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO explore_posts (user_id, is_anonymous, type, title, body, anon_pseudonym) "
            "VALUES (?, ?, 'discussion', ?, ?, ?)",
            (user["id"], int(is_anonymous), title, body, _new_anon_pseudonym(is_anonymous)),
        )
        post_id = cur.lastrowid
        _save_attachments(conn, "post", post_id, files)
        conn.commit()
        row = conn.execute(EXPLORE_SELECT + " WHERE explore_posts.id = ?", (post_id,)).fetchone()
        return _post_to_dict(conn, row, user)


@router.post("/explore/announcements")
async def create_announcement(
    title: str = Form(...),
    body: str = Form(...),
    is_anonymous: bool = Form(False),
    files: list[UploadFile] | None = File(None),
    user: dict = Depends(require_user),
):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO explore_posts (user_id, is_anonymous, type, title, body, anon_pseudonym) "
            "VALUES (?, ?, 'announcement', ?, ?, ?)",
            (user["id"], int(is_anonymous), title, body, _new_anon_pseudonym(is_anonymous)),
        )
        post_id = cur.lastrowid
        _save_attachments(conn, "post", post_id, files)
        conn.commit()
        row = conn.execute(EXPLORE_SELECT + " WHERE explore_posts.id = ?", (post_id,)).fetchone()
        return _post_to_dict(conn, row, user)


@router.get("/explore")
def list_explore(
    type: str | None = Query(None),
    user: dict | None = Depends(get_current_user),
):
    query = EXPLORE_SELECT
    params = []
    if type:
        if type not in VALID_TYPES:
            raise HTTPException(400, f"type must be one of {sorted(VALID_TYPES)}")
        query += " WHERE explore_posts.type = ?"
        params.append(type)
    query += " ORDER BY explore_posts.created_at DESC"

    with get_conn() as conn:
        rows = conn.execute(query, params).fetchall()
        return [_post_to_dict(conn, r, user) for r in rows]


@router.get("/explore/{post_id}")
def get_explore_post(post_id: int, user: dict | None = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(EXPLORE_SELECT + " WHERE explore_posts.id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        return _post_to_dict(conn, row, user, include_replies=True)


@router.delete("/explore/{post_id}")
def delete_explore_post(post_id: int, user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM explore_posts WHERE id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        if row["user_id"] != user["id"]:
            raise HTTPException(403, "You can only delete your own post")
        if row["is_anonymous"]:
            # Deliberate: anonymous posts are permanent. Allowing self-delete
            # here would mean the delete button itself reveals authorship to
            # anyone with access to this session (e.g. a shared/borrowed
            # login) — the same leak as an authorship list, just spread
            # across the feed instead of collected in one place. Named
            # posts keep full ownership since there's nothing to leak.
            raise HTTPException(
                400,
                "Anonymous posts can't be deleted by their author — this is by design, "
                "so ownership of an anonymous post is never discoverable by anyone with "
                "access to your account. Only moderators can remove a post.",
            )

        reply_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM explore_replies WHERE post_id = ?", (post_id,)
        ).fetchall()]

        att_rows = list(conn.execute(
            "SELECT * FROM explore_attachments WHERE owner_type = 'post' AND owner_id = ?", (post_id,)
        ).fetchall())
        if reply_ids:
            placeholders = ",".join("?" * len(reply_ids))
            att_rows += list(conn.execute(
                f"SELECT * FROM explore_attachments WHERE owner_type = 'reply' AND owner_id IN ({placeholders})",
                reply_ids,
            ).fetchall())

        for a in att_rows:
            delete_key(a["file_path"])

        conn.execute("DELETE FROM explore_attachments WHERE owner_type = 'post' AND owner_id = ?", (post_id,))
        if reply_ids:
            placeholders = ",".join("?" * len(reply_ids))
            conn.execute(
                f"DELETE FROM explore_attachments WHERE owner_type = 'reply' AND owner_id IN ({placeholders})",
                reply_ids,
            )
        conn.execute("DELETE FROM explore_replies WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM explore_poll_votes WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM explore_poll_options WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM explore_posts WHERE id = ?", (post_id,))
        conn.commit()
    return {"ok": True}


@router.post("/explore/{post_id}/vote")
def vote_poll(
    post_id: int,
    option_id: int = Form(...),
    user: dict = Depends(require_user),
):
    """Single-choice, changeable: voting for a different option replaces your previous vote."""
    with get_conn() as conn:
        post = conn.execute("SELECT * FROM explore_posts WHERE id = ?", (post_id,)).fetchone()
        if not post or post["type"] != "poll":
            raise HTTPException(404, "Not found")
        option = conn.execute(
            "SELECT * FROM explore_poll_options WHERE id = ? AND post_id = ?", (option_id, post_id)
        ).fetchone()
        if not option:
            raise HTTPException(400, "That option doesn't belong to this poll")

        conn.execute(
            "INSERT INTO explore_poll_votes (post_id, option_id, user_id) VALUES (?, ?, ?) "
            "ON CONFLICT (post_id, user_id) DO UPDATE SET "
            "option_id = excluded.option_id, created_at = datetime('now')",
            (post_id, option_id, user["id"]),
        )
        conn.commit()
        return _poll_result(conn, post_id, user)


@router.post("/explore/{post_id}/react")
def react_to_explore_post(
    post_id: int,
    reaction: str = Form(...),
    user: dict = Depends(require_user),
):
    """Thumbs up/down on a poll/discussion/announcement. One reaction per
    user, switchable, and toggles off on a repeat click of the same
    button. The author can't react to their own post — checked via
    user_id, which works the same whether the post is anonymous or not."""
    if reaction not in {"like", "dislike"}:
        raise HTTPException(400, "reaction must be 'like' or 'dislike'")
    with get_conn() as conn:
        post = conn.execute("SELECT * FROM explore_posts WHERE id = ?", (post_id,)).fetchone()
        if not post:
            raise HTTPException(404, "Not found")
        if post["user_id"] == user["id"]:
            raise HTTPException(400, "You can't react to your own post")
        result = toggle_reaction(conn, "explore", post_id, user["id"], reaction)
        conn.commit()
        likes, dislikes = reaction_counts(conn, "explore", post_id)
    return {"my_reaction": result, "like_count": likes, "dislike_count": dislikes}


@router.post("/explore/{post_id}/replies")
async def create_reply(
    post_id: int,
    body: str = Form(...),
    is_anonymous: bool = Form(False),
    parent_reply_id: int | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(require_user),
):
    with get_conn() as conn:
        post = conn.execute("SELECT * FROM explore_posts WHERE id = ?", (post_id,)).fetchone()
        if not post or post["type"] != "discussion":
            raise HTTPException(404, "Not found")
        if parent_reply_id is not None:
            parent = conn.execute(
                "SELECT id FROM explore_replies WHERE id = ? AND post_id = ?",
                (parent_reply_id, post_id),
            ).fetchone()
            if not parent:
                raise HTTPException(400, "That reply doesn't belong to this post")
        cur = conn.execute(
            "INSERT INTO explore_replies (post_id, user_id, is_anonymous, body, anon_pseudonym, parent_reply_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (post_id, user["id"], int(is_anonymous), body, _new_anon_pseudonym(is_anonymous), parent_reply_id),
        )
        reply_id = cur.lastrowid
        if file and file.filename:
            _save_attachments(conn, "reply", reply_id, [file])
        conn.commit()
        row = conn.execute(REPLY_SELECT + " WHERE explore_replies.id = ?", (reply_id,)).fetchone()
        return _reply_to_dict(conn, row, user, post["user_id"])


@router.post("/explore/replies/{reply_id}/react")
def react_to_reply(
    reply_id: int,
    reaction: str = Form(...),
    user: dict = Depends(require_user),
):
    """Thumbs up/down on a discussion reply — same rules as reacting to a
    post (one switchable reaction per user, toggles off on repeat click,
    can't react to your own reply)."""
    if reaction not in {"like", "dislike"}:
        raise HTTPException(400, "reaction must be 'like' or 'dislike'")
    with get_conn() as conn:
        reply = conn.execute("SELECT * FROM explore_replies WHERE id = ?", (reply_id,)).fetchone()
        if not reply:
            raise HTTPException(404, "Not found")
        if reply["user_id"] == user["id"]:
            raise HTTPException(400, "You can't react to your own reply")
        result = toggle_reaction(conn, "explore_reply", reply_id, user["id"], reaction)
        conn.commit()
        likes, dislikes = reaction_counts(conn, "explore_reply", reply_id)
    return {"my_reaction": result, "like_count": likes, "dislike_count": dislikes}