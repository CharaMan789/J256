"""File storage on Cloudflare R2 (S3-compatible object storage), used
instead of Render's local disk for every uploaded image/video/audio file.

Why this exists: Render's free web services run on an ephemeral
filesystem — anything written to local disk (like the old UPLOAD_DIR
approach) is lost on every redeploy, and can also be lost on the
periodic spin-down/spin-up cycle free instances go through. Files saved
here instead live in R2, completely independent of the app server's own
lifecycle, so an upload survives redeploys, restarts, and spin-downs
indefinitely.

R2's API is S3-compatible, so this uses boto3 (the standard AWS SDK)
pointed at R2's endpoint rather than AWS — no AWS account involved.

Required environment variables (set in Render's dashboard, never
committed to a file):
    R2_ACCOUNT_ID       — from the R2 API token screen
    R2_ACCESS_KEY_ID     — from the R2 API token screen
    R2_SECRET_ACCESS_KEY — from the R2 API token screen (shown once)
    R2_BUCKET_NAME        — the bucket you created
    R2_PUBLIC_URL          — the public base URL (r2.dev subdomain or
                              custom domain) files are served from
"""

import os
import uuid
from pathlib import Path

import boto3
from botocore.config import Config

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
# No trailing slash — callers below already add the "/" when joining.
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

_configured = bool(R2_ACCOUNT_ID and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET_NAME and R2_PUBLIC_URL)

_client = None
if _configured:
    _client = boto3.client(
        "s3",
        endpoint_url=f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com",
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def storage_configured() -> bool:
    return _configured


def upload_fileobj(fileobj, original_filename: str) -> str:
    """Uploads a file-like object to R2 under a random key (keeping the
    original extension), returns the object key to store in the
    database — not the full URL, so public_url() below stays the single
    place that knows how keys map to URLs. Raises RuntimeError with a
    clear message if R2 isn't configured, rather than silently writing
    nowhere."""
    if not _configured:
        raise RuntimeError(
            "File storage isn't configured. Set R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
            "R2_SECRET_ACCESS_KEY, R2_BUCKET_NAME, and R2_PUBLIC_URL in the environment."
        )
    ext = Path(original_filename).suffix
    key = f"{uuid.uuid4().hex}{ext}"
    _client.upload_fileobj(fileobj, R2_BUCKET_NAME, key)
    return key


def delete_key(key: str) -> None:
    """Best-effort delete — swallows errors so a missing/already-deleted
    object doesn't blow up a post-delete flow that's otherwise fine."""
    if not _configured or not key:
        return
    try:
        _client.delete_object(Bucket=R2_BUCKET_NAME, Key=key)
    except Exception:
        pass


def public_url(key: str) -> str:
    return f"{R2_PUBLIC_URL}/{key}"


def download_bytes(key: str) -> bytes | None:
    """Fetches an object's raw bytes from R2 — used only by the magazine
    PDF builder, which needs actual image data to embed (not just a URL)
    to lay out each page. Returns None on any failure (missing object,
    network issue) so the PDF build can skip that image gracefully
    rather than crashing the whole magazine."""
    if not _configured or not key:
        return None
    try:
        obj = _client.get_object(Bucket=R2_BUCKET_NAME, Key=key)
        return obj["Body"].read()
    except Exception:
        return None