import os
import shutil
import uuid
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, UploadFile, File, HTTPException, Depends
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

import auth
import doubts
import explore
import moderation
from auth import require_user, get_current_user
from database import init_db, get_conn
from magazine import build_magazine_pdf
from pseudonyms import generate_pseudonym
from reactions import reaction_counts, my_reaction, toggle_reaction

BASE_DIR = Path(__file__).parent
UPLOAD_DIR = BASE_DIR.parent / "frontend" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
FRONTEND_DIR = BASE_DIR.parent / "frontend"

SESSION_SECRET = os.environ.get("SESSION_SECRET", "dev-secret-change-me-in-.env")
VALID_KINDS = {"image", "video", "file"}

app = FastAPI(title="J256 - IISER TVM community")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax")
app.include_router(auth.router)
app.include_router(doubts.router)
app.include_router(explore.router)
app.include_router(moderation.router)


@app.on_event("startup")
def startup():
    init_db()


POST_SELECT = """
    SELECT posts.*, users.name AS user_name, users.picture AS user_picture,
           users.pseudonym AS user_account_pseudonym
    FROM posts JOIN users ON posts.user_id = users.id
"""


def _attachments_for(conn, post_id):
    rows = conn.execute(
        "SELECT * FROM post_attachments WHERE post_id = ? ORDER BY uploaded_at ASC", (post_id,)
    ).fetchall()
    return [
        {
            "id": r["id"],
            "kind": r["kind"],
            "url": f"/uploads/{r['file_path']}",
            "original_name": r["original_name"],
        }
        for r in rows
    ]


def post_to_dict(conn, row, user=None) -> dict:
    is_anon = bool(row["is_anonymous"])
    # Per-article random pseudonym, generated once at submit time (see
    # submit_post below) — not the account's fixed pseudonym. Falls back
    # to the account pseudonym only for articles submitted before this
    # column existed (pre-2026-08-24).
    name = row["anon_pseudonym"] or row["user_account_pseudonym"]
    like_count, dislike_count = reaction_counts(conn, "article", row["id"])
    return {
        "id": row["id"],
        "author": name if is_anon else row["user_name"],
        "author_picture": None if is_anon else row["user_picture"],
        "is_anonymous": is_anon,
        "title": row["title"],
        "body": row["body"],
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "published_at": row["published_at"],
        "is_mine": bool(user) and row["user_id"] == user["id"],
        "attachments": _attachments_for(conn, row["id"]),
        "like_count": like_count,
        "dislike_count": dislike_count,
        "my_reaction": my_reaction(conn, "article", row["id"], user),
    }


def _get_owned_draft(conn, post_id, user):
    row = conn.execute(POST_SELECT + " WHERE posts.id = ?", (post_id,)).fetchone()
    if not row:
        raise HTTPException(404, "Not found")
    if row["user_id"] != user["id"]:
        raise HTTPException(403, "This isn't your article")
    if row["status"] != "draft":
        raise HTTPException(400, "This article has already been submitted and can't be edited")
    return row


@app.post("/posts/drafts")
def create_draft(user: dict = Depends(require_user)):
    """Start a new, empty draft. The compose page calls this once, up front,
    so attachments and autosave have somewhere to attach to right away."""
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO posts (user_id, title, body, status) VALUES (?, '', '', 'draft')",
            (user["id"],),
        )
        conn.commit()
        row = conn.execute(POST_SELECT + " WHERE posts.id = ?", (cur.lastrowid,)).fetchone()
        return post_to_dict(conn, row, user)


@app.put("/posts/{post_id}")
def save_draft(
    post_id: int,
    title: str = Form(""),
    body: str = Form(""),
    is_anonymous: bool = Form(False),
    user: dict = Depends(require_user),
):
    with get_conn() as conn:
        _get_owned_draft(conn, post_id, user)
        conn.execute(
            "UPDATE posts SET title = ?, body = ?, is_anonymous = ?, updated_at = datetime('now') WHERE id = ?",
            (title, body, int(is_anonymous), post_id),
        )
        conn.commit()
        row = conn.execute(POST_SELECT + " WHERE posts.id = ?", (post_id,)).fetchone()
        return post_to_dict(conn, row, user)


@app.post("/posts/{post_id}/submit")
def submit_post(post_id: int, user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = _get_owned_draft(conn, post_id, user)
        if not row["title"].strip() or not row["body"].strip():
            raise HTTPException(400, "Give it a title and some content before submitting")
        # Generate the per-article pseudonym here, at submit time, using
        # whatever is_anonymous was last saved on the draft — not at draft
        # creation, since the author may flip anonymous on/off repeatedly
        # while still drafting.
        anon_pseudonym = generate_pseudonym() if row["is_anonymous"] else None
        conn.execute(
            "UPDATE posts SET status = 'published', published_at = datetime('now'), "
            "updated_at = datetime('now'), anon_pseudonym = ? WHERE id = ?",
            (anon_pseudonym, post_id),
        )
        conn.commit()
        row = conn.execute(POST_SELECT + " WHERE posts.id = ?", (post_id,)).fetchone()
        return post_to_dict(conn, row, user)


@app.get("/posts/drafts")
def list_drafts(user: dict = Depends(require_user)):
    with get_conn() as conn:
        rows = conn.execute(
            POST_SELECT + " WHERE posts.user_id = ? AND posts.status = 'draft' ORDER BY posts.updated_at DESC",
            (user["id"],),
        ).fetchall()
        return [post_to_dict(conn, r, user) for r in rows]


@app.get("/posts/newspaper")
def newspaper(user: dict | None = Depends(get_current_user)):
    with get_conn() as conn:
        rows = conn.execute(
            POST_SELECT + " WHERE posts.status = 'published' ORDER BY posts.published_at DESC"
        ).fetchall()
        return [post_to_dict(conn, r, user) for r in rows]


@app.get("/posts/{post_id}")
def get_post(post_id: int, user: dict | None = Depends(get_current_user)):
    with get_conn() as conn:
        row = conn.execute(POST_SELECT + " WHERE posts.id = ?", (post_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        if row["status"] == "draft" and (not user or row["user_id"] != user["id"]):
            raise HTTPException(404, "Not found")
        return post_to_dict(conn, row, user)


@app.delete("/posts/{post_id}")
def delete_draft(post_id: int, user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = _get_owned_draft(conn, post_id, user)
        attachments = conn.execute(
            "SELECT file_path FROM post_attachments WHERE post_id = ?", (post_id,)
        ).fetchall()
        for a in attachments:
            f = UPLOAD_DIR / a["file_path"]
            if f.exists():
                f.unlink()
        conn.execute("DELETE FROM post_attachments WHERE post_id = ?", (post_id,))
        conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
        conn.commit()
    return {"ok": True}


@app.post("/posts/{post_id}/attachments")
async def add_attachment(
    post_id: int,
    kind: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
):
    if kind not in VALID_KINDS:
        raise HTTPException(400, f"kind must be one of {sorted(VALID_KINDS)}")
    with get_conn() as conn:
        _get_owned_draft(conn, post_id, user)
        ext = Path(file.filename).suffix
        stored_name = f"{uuid.uuid4().hex}{ext}"
        dest = UPLOAD_DIR / stored_name
        with dest.open("wb") as f:
            shutil.copyfileobj(file.file, f)
        cur = conn.execute(
            "INSERT INTO post_attachments (post_id, kind, file_path, original_name) VALUES (?, ?, ?, ?)",
            (post_id, kind, stored_name, file.filename),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM post_attachments WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {
        "id": row["id"],
        "kind": row["kind"],
        "url": f"/uploads/{row['file_path']}",
        "original_name": row["original_name"],
    }


@app.delete("/attachments/{attachment_id}")
def delete_attachment(attachment_id: int, user: dict = Depends(require_user)):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT post_attachments.*, posts.user_id AS owner_id, posts.status AS post_status "
            "FROM post_attachments JOIN posts ON post_attachments.post_id = posts.id "
            "WHERE post_attachments.id = ?",
            (attachment_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Not found")
        if row["owner_id"] != user["id"]:
            raise HTTPException(403, "Not yours")
        if row["post_status"] != "draft":
            raise HTTPException(400, "Can't edit a submitted article")
        f = UPLOAD_DIR / row["file_path"]
        if f.exists():
            f.unlink()
        conn.execute("DELETE FROM post_attachments WHERE id = ?", (attachment_id,))
        conn.commit()
    return {"ok": True}


@app.get("/magazine.pdf")
def magazine_pdf(download: bool = False):
    """The whole newspaper, compiled into one PDF — every published article,
    cover page, table of contents, images embedded."""
    with get_conn() as conn:
        rows = conn.execute(
            POST_SELECT + " WHERE posts.status = 'published' ORDER BY posts.published_at ASC"
        ).fetchall()
        posts = [post_to_dict(conn, r) for r in rows]

    if not posts:
        raise HTTPException(404, "No articles have been published yet")

    pdf_bytes = build_magazine_pdf(posts, UPLOAD_DIR)
    disposition = "attachment" if download else "inline"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="J256-magazine.pdf"'},
    )


@app.post("/posts/{post_id}/react")
def react_to_post(post_id: int, reaction: str = Form(...), user: dict = Depends(require_user)):
    """Thumbs up/down on a published article. One reaction per user,
    switchable, and toggles off on a repeat click of the same button.
    The author can't react to their own article."""
    if reaction not in {"like", "dislike"}:
        raise HTTPException(400, "reaction must be 'like' or 'dislike'")
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
        if not row or row["status"] != "published":
            raise HTTPException(404, "Not found")
        if row["user_id"] == user["id"]:
            raise HTTPException(400, "You can't react to your own post")
        result = toggle_reaction(conn, "article", post_id, user["id"], reaction)
        conn.commit()
        likes, dislikes = reaction_counts(conn, "article", post_id)
    return {"my_reaction": result, "like_count": likes, "dislike_count": dislikes}


# Uploaded images/videos/files
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
# Frontend (must be mounted last — it's a catch-all for "/")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")