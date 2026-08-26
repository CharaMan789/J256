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
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise HTTPException(
            500,
            "Google OAuth isn't configured yet. Set GOOGLE_CLIENT_ID and "
            "GOOGLE_CLIENT_SECRET in backend/.env — see README.md.",
        )
    redirect_uri = request.url_for("auth_callback")
    return await oauth.google.authorize_redirect(request, redirect_uri)


@router.get("/auth/callback", name="auth_callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        return RedirectResponse(f"{FRONTEND_URL}/?error=login_failed")

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return RedirectResponse(f"{FRONTEND_URL}/?error=login_failed")

    email = userinfo["email"].lower()

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
            iiser_email = None
        else:
            user_id = row["id"]
            iiser_email = row["iiser_email"]
            # Keep picture fresh in case it changes on Google's side. name
            # is only kept fresh here until it's been verified — once
            # name_verified is set (via the IISER sign-in below), that
            # verified name is treated as the real one and this primary
            # login must not overwrite it again.
            if row["name_verified"]:
                conn.execute(
                    "UPDATE users SET picture = ? WHERE id = ?",
                    (picture, user_id),
                )
            else:
                conn.execute(
                    "UPDATE users SET name = ?, picture = ? WHERE id = ?",
                    (name, picture, user_id),
                )
            conn.commit()

    request.session["user_id"] = user_id

    if not iiser_email:
        # Chained straight into the second sign-in — no manual "verify"
        # button needed. If this fails/gets cancelled, verify_iiser_callback
        # still redirects to FRONTEND_URL with an error, so the person
        # always ends up signed in and on the site either way; they just
        # land on /?view=account with a retry button instead of Home.
        redirect_uri = request.url_for("verify_iiser_callback")
        return await oauth.google.authorize_redirect(
            request, redirect_uri, prompt="select_account", hd=ALLOWED_DOMAIN
        )

    return RedirectResponse(FRONTEND_URL)


@router.get("/auth/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(FRONTEND_URL)


@router.get("/auth/verify-iiser")
async def verify_iiser_start(request: Request):
    """Second, separate Google sign-in — used only to prove ownership of an
    @iisertvm.ac.in account and link it to the already-signed-in (primary)
    account. Doesn't touch the primary session/login at all. prompt=
    select_account forces Google's account chooser so the browser doesn't
    silently reuse whichever Google account is already signed in. hd (hosted
    domain) tells Google to filter/label that chooser to the IISER TVM
    Workspace domain specifically, so this screen visibly looks different
    from the first, generic sign-in."""
    if not request.session.get("user_id"):
        return RedirectResponse(f"{FRONTEND_URL}/?error=not_logged_in")
    redirect_uri = request.url_for("verify_iiser_callback")
    return await oauth.google.authorize_redirect(
        request, redirect_uri, prompt="select_account", hd=ALLOWED_DOMAIN
    )


@router.get("/auth/verify-iiser/callback", name="verify_iiser_callback")
async def verify_iiser_callback(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return RedirectResponse(f"{FRONTEND_URL}/?error=not_logged_in")

    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        return RedirectResponse(f"{FRONTEND_URL}/?view=account&error=iiser_verify_failed")

    userinfo = token.get("userinfo")
    if not userinfo or not userinfo.get("email"):
        return RedirectResponse(f"{FRONTEND_URL}/?view=account&error=iiser_verify_failed")

    iiser_email = userinfo["email"].lower()
    if not iiser_email.endswith(f"@{ALLOWED_DOMAIN}"):
        return RedirectResponse(f"{FRONTEND_URL}/?view=account&error=iiser_domain_mismatch")

    # The name on this IISER account is treated as the person's real name —
    # more trustworthy than whatever display name was set on their primary
    # sign-in (which can be any Google account). Falls back to whatever
    # name is already on file if Google doesn't return one here, so
    # verification never blanks out an existing name.
    iiser_name = userinfo.get("name")

    with get_conn() as conn:
        # One IISER email can only ever be linked to one account — this is
        # the actual anti-multi-account enforcement.
        existing = conn.execute(
            "SELECT id FROM users WHERE iiser_email = ?", (iiser_email,)
        ).fetchone()
        if existing and existing["id"] != user_id:
            return RedirectResponse(f"{FRONTEND_URL}/?view=account&error=iiser_already_linked")

        if iiser_name:
            conn.execute(
                "UPDATE users SET iiser_email = ?, name = ?, name_verified = 1 WHERE id = ?",
                (iiser_email, iiser_name, user_id),
            )
        else:
            conn.execute("UPDATE users SET iiser_email = ? WHERE id = ?", (iiser_email, user_id))
        conn.commit()

    return RedirectResponse(f"{FRONTEND_URL}/?view=account&iiser=verified")


@router.get("/auth/me")
async def me(request: Request):
    return get_current_user(request)


def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, email, name, picture, pseudonym, is_moderator, strikes, banned, "
            "iiser_email, name_verified FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    if not row:
        return None
    d = dict(row)
    d["is_moderator"] = bool(d["is_moderator"])
    d["banned"] = bool(d["banned"])
    d["name_verified"] = bool(d["name_verified"])
    return d


def require_user(request: Request):
    user = get_current_user(request)
    if not user:
        raise HTTPException(401, "Sign in with your IISER TVM Google account first")
    if user["banned"]:
        raise HTTPException(403, "Your account has been banned for violating community guidelines")
    return user