import os

from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

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

# Every response below that either sets the session cookie or reveals who
# it belongs to (login, callback, logout, /auth/me) gets these headers.
# Without them, a shared cache sitting between the browser and this
# server — a campus wifi proxy, Render's edge, a browser's own back/
# forward cache — is technically permitted to store the response and
# replay it to a *different* person who requests the same URL shortly
# after. For /auth/callback that would replay someone else's Set-Cookie;
# for /auth/me it would replay someone else's signed-in identity straight
# into a new visitor's UI. This is a well-documented class of bug (search
# "Set-Cookie CDN cache cross-user leak") and the fix is exactly this:
# tell every cache in the path, explicitly, that these responses are
# private to the one request that produced them and must never be stored
# or reused for anyone else.
NO_STORE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, private",
    "Pragma": "no-cache",
}


def _no_store_redirect(url: str) -> RedirectResponse:
    return RedirectResponse(url, headers=NO_STORE_HEADERS)


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
    resp = await oauth.google.authorize_redirect(request, redirect_uri, hd=ALLOWED_DOMAIN)
    resp.headers.update(NO_STORE_HEADERS)
    return resp


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return _no_store_redirect(f"{FRONTEND_URL}/?error=login_failed")

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return _no_store_redirect(f"{FRONTEND_URL}/?error=login_failed")

    email = userinfo["email"].lower()

    # hd= is only a hint to Google's account picker — a person can still
    # bypass it (e.g. by hitting the OAuth URL directly), so the domain is
    # re-checked here, server-side, same as before.
    if not email.endswith(f"@{ALLOWED_DOMAIN}"):
        return _no_store_redirect(f"{FRONTEND_URL}/?error=iiser_domain_mismatch")

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
    return _no_store_redirect(FRONTEND_URL)


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return _no_store_redirect(FRONTEND_URL)


@router.get("/auth/me")
async def me(request: Request):
    return JSONResponse(content=get_current_user(request), headers=NO_STORE_HEADERS)


@router.post("/auth/onboarding/accept")
async def accept_onboarding(request: Request):
    """Records that the signed-in user has clicked through and agreed to
    the welcome/philosophy/guidelines modal. Idempotent — accepting again
    just refreshes nothing (onboarded_at is only ever set once, never
    overwritten), so a double-click or retry can't cause issues."""
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "Sign in first")
    with get_conn() as conn:
        conn.execute(
            "UPDATE users SET onboarded_at = NOW() WHERE id = ? AND onboarded_at IS NULL",
            (user_id,),
        )
        conn.commit()
    return JSONResponse(content=get_current_user(request), headers=NO_STORE_HEADERS)


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, name, picture, pseudonym, is_moderator, strikes, banned, onboarded_at "
            "FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_moderator"] = bool(d["is_moderator"])
    d["banned"] = bool(d["banned"])
    d["onboarded"] = d["onboarded_at"] is not None
    return d


def require_user(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Sign in with your IISER TVM Google account first")
    if user["banned"]:
        raise HTTPException(403, "Your account has been banned for violating community guidelines")
    return user