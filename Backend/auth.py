import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse

from database import get_conn
from pseudonyms import generate_pseudonym

ALLOWED_DOMAIN = os.environ.get("ALLOWED_DOMAIN", "iisertvm.ac.in")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://127.0.0.1:8123")

oauth = OAuth()
oauth.register(
    name="google",
    client_id=GOOGLE_CLIENT_ID,
    client_secret=GOOGLE_CLIENT_SECRET,
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)

router = APIRouter()


@router.get("/auth/login")
async def login(request: Request):
    """Single sign-in, restricted to the IISER TVM Google Workspace domain.
    hd (hosted domain) tells Google's account chooser to only offer
    @iisertvm.ac.in accounts — this is what used to be the *second*,
    separate verification step; now it's the only step. Google enforces
    hd on its side, but we still re-check the returned email's domain in
    auth_callback below, since hd is a hint to the picker, not a hard
    server-side guarantee."""
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            500,
            "Google OAuth isn't configured yet. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in backend/.env — see README.md.",
        )
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri, hd=ALLOWED_DOMAIN)


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return RedirectResponse(f"{FRONTEND_URL}/?error=login_failed")

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return RedirectResponse(f"{FRONTEND_URL}/?error=login_failed")

    email = userinfo["email"].lower()

    # hd= is only a hint to Google's account picker — a person can still
    # bypass it (e.g. by hitting the OAuth URL directly), so the domain is
    # re-checked here, server-side, same as before.
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return RedirectResponse(f"{FRONTEND_URL}/?error=iiser_domain_mismatch")

    name = userinfo.get("name") or email.split("@")[0]
    picture = userinfo.get("picture")

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if row is None:
            pseudonym = generate_pseudonym()
            cur = conn.execute(
                "INSERT INTO users (email, name, picture, pseudonym) VALUES (?, ?, ?, ?)",
                (email, name, picture, pseudonym),
            )
            conn.commit()
            user_id = cur.lastrowid
        else:
            user_id = row["id"]
            conn.execute(
                "UPDATE users SET name = ?, picture = ? WHERE id = ?",
                (name, picture, user_id),
            )
            conn.commit()

    request.session["user_id"] = user_id
    return RedirectResponse(FRONTEND_URL)


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(FRONTEND_URL)


@router.get("/auth/me")
async def me(request: Request):
    return get_current_user(request)


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, name, picture, pseudonym, is_moderator, strikes, banned "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_moderator"] = bool(d["is_moderator"])
    d["banned"] = bool(d["banned"])
    return d


def require_user(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Sign in with your IISER TVM Google account first")
    if user["banned"]:
        raise HTTPException(403, "Your account has been banned for violating community guidelines")
    return user