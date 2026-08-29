"""Postgres-backed replacement for the old sqlite3 database.py.

Every route file in this app was written against sqlite3's interface:
conn.execute(sql, params) called directly on the connection, '?'
placeholders, sqlite3.Row's dict-style row["col"] access, and
cur.lastrowid after an INSERT. Rather than rewriting all of that across
every file, this module wraps psycopg2 so it presents the exact same
interface — the two classes below are the only new moving part; every
other file (auth.py, doubts.py, explore.py, main.py, moderation.py,
reactions.py) is unchanged and works against this wrapper as-is.

Set DATABASE_URL (Render's Postgres "Internal Database URL") as an
environment variable for this to connect. See get_conn() below.
"""

import os
import re
from contextlib import contextmanager

import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "")

# Tables whose primary key is a single auto-generated "id" column. An
# INSERT into one of these gets " RETURNING id" appended automatically,
# so cur.lastrowid keeps working exactly like it did under sqlite3
# without touching the ~10 call sites across the app that rely on it.
# Tables with composite primary keys (join/vote tables — reactions,
# doubt_votes, doubt_escalations, explore_poll_votes, ban_poll_votes)
# are deliberately left out: they have no id column, so appending
# RETURNING id to an INSERT there would error.
TABLES_WITH_ID = {
    "users", "posts", "post_attachments", "doubts", "doubt_replies",
    "explore_posts", "explore_poll_options", "explore_replies",
    "explore_attachments", "reports", "warnings", "ban_polls",
}

_INSERT_TABLE_RE = re.compile(r"^\s*INSERT\s+INTO\s+([a-zA-Z_]+)", re.IGNORECASE)


class _CursorWrapper:
    """Thin wrapper so conn.execute(...) keeps returning something with
    .fetchone() / .fetchall() / .lastrowid, exactly like sqlite3's cursor
    did. Rows come from psycopg2's RealDictCursor, which returns dict
    subclasses — row["col"], dict(row), and plain iteration all behave
    the same as sqlite3.Row did, so no route file needs to change."""

    def __init__(self, cursor, lastrowid=None):
        self._cursor = cursor
        self.lastrowid = lastrowid

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class _ConnWrapper:
    """Wraps a psycopg2 connection to expose .execute() directly on the
    connection object (every route file calls conn.execute(sql, params)
    the sqlite3 way), and translates the two SQL dialect differences
    that appear throughout the existing query strings:
      - '?' positional placeholders -> '%s' (psycopg2's style)
      - SQLite's datetime('now')    -> Postgres's NOW()
    Everything else (CHECK constraints, ON CONFLICT ... DO UPDATE SET
    col = excluded.col, partial unique indexes) is already valid
    Postgres syntax as written, so no other translation is needed."""

    def __init__(self, pg_conn):
        self._conn = pg_conn

    def execute(self, sql, params=()):
        translated = sql.replace("datetime('now')", "NOW()").replace("?", "%s")
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        table_match = _INSERT_TABLE_RE.match(translated)
        wants_id = bool(
            table_match
            and table_match.group(1).lower() in TABLES_WITH_ID
            and "returning" not in translated.lower()
        )
        if wants_id:
            translated = translated.rstrip().rstrip(";") + " RETURNING id"

        cur.execute(translated, params)

        lastrowid = None
        if wants_id:
            row = cur.fetchone()
            lastrowid = row["id"] if row else None

        return _CursorWrapper(cur, lastrowid=lastrowid)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


@contextmanager
def get_conn():
    pg_conn = psycopg2.connect(DATABASE_URL)
    wrapped = _ConnWrapper(pg_conn)
    try:
        yield wrapped
    finally:
        wrapped.close()


def _existing_columns(conn, table):
    cur = conn.execute(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?",
        (table,),
    )
    return {row["column_name"] for row in cur.fetchall()}


def _add_column_if_missing(conn, table, column, coldef):
    if column not in _existing_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                picture TEXT,
                pseudonym TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW())
            )
        """)
        # Moderation fields on users — added via migration so existing DBs
        # (with users already created) pick them up without a wipe.
        _add_column_if_missing(conn, "users", "is_moderator", "is_moderator INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "users", "strikes", "strikes INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(conn, "users", "banned", "banned INTEGER NOT NULL DEFAULT 0")
        # Verified IISER identity, linked via a second Google sign-in (see
        # auth.py verify_iiser_*) — separate from the primary sign-in email,
        # which no longer has to be @iisertvm.ac.in. NULL until verified.
        # Enforced unique via a partial index (only applies to non-NULL
        # values), so any number of unverified users (NULL) can coexist,
        # but a real iiser_email can only ever belong to one account.
        _add_column_if_missing(conn, "users", "iiser_email", "iiser_email TEXT")
        conn.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_iiser_email
            ON users(iiser_email) WHERE iiser_email IS NOT NULL
        """)
        # Set once, at IISER verification time, from the name on that
        # verified @iisertvm.ac.in Google account (see auth.py
        # verify_iiser_callback) — this is treated as the person's real
        # name, more trustworthy than whatever display name was on their
        # primary sign-in. Once true, the primary login (auth_callback)
        # stops overwriting users.name on every sign-in, so the verified
        # name sticks.
        name_verified_is_new = "name_verified" not in _existing_columns(conn, "users")
        _add_column_if_missing(conn, "users", "name_verified", "name_verified INTEGER NOT NULL DEFAULT 0")
        if name_verified_is_new:
            # One-time backfill: anyone who already has an iiser_email from
            # before this column existed was already verified — their
            # current name should be protected immediately rather than
            # getting silently overwritten on their next ordinary login.
            conn.execute(
                "UPDATE users SET name_verified = 1 WHERE iiser_email IS NOT NULL"
            )
        # Per-post random pseudonyms (2026-08-24): each anonymous post/reply
        # gets its own random name, generated once at creation and stored
        # on the row itself — not the account's fixed users.pseudonym. Two
        # anonymous posts by the same person never share a name, so the
        # name can't be used to correlate someone's posts across the feed.
        # anon_pseudonym is added to each content table below, once that
        # table exists. users.pseudonym is kept only as a migration
        # fallback for any pre-existing anonymous rows that predate this
        # column and have no per-row name of their own.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
                created_at TEXT NOT NULL DEFAULT (NOW()),
                updated_at TEXT NOT NULL DEFAULT (NOW()),
                published_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "posts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_attachments (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('image', 'video', 'file')),
                file_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (post_id) REFERENCES posts(id)
            )
        """)
        # Doubts / Opinions / Ideas — the OLDER dormant board. Left as-is;
        # not linked in the nav, unrelated to the Explore feature below.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL CHECK (category IN ('doubt', 'opinion', 'idea')),
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "doubts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_replies (
                id SERIAL PRIMARY KEY,
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "doubt_replies", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_votes (
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                PRIMARY KEY (doubt_id, user_id),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_escalations (
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                PRIMARY KEY (doubt_id, user_id),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- Explore: Poll / Discussion / Announcement, one shared feed ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_posts (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL CHECK (type IN ('poll', 'discussion', 'announcement')),
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "explore_posts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_poll_options (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (post_id) REFERENCES explore_posts(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_poll_votes (
                post_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                PRIMARY KEY (post_id, user_id),
                FOREIGN KEY (post_id) REFERENCES explore_posts(id),
                FOREIGN KEY (option_id) REFERENCES explore_poll_options(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_replies (
                id SERIAL PRIMARY KEY,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (post_id) REFERENCES explore_posts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "explore_replies", "anon_pseudonym", "anon_pseudonym TEXT")
        # Reply-to-reply nesting (2026-08-27): NULL means a top-level reply
        # to the post itself, same as every reply before this column
        # existed — so no backfill needed, old data reads correctly as-is.
        # A non-NULL value points at the explore_replies row being replied
        # to, one level deep is all the UI needs to support threading; the
        # column itself doesn't enforce a depth limit.
        _add_column_if_missing(
            conn, "explore_replies", "parent_reply_id",
            "parent_reply_id INTEGER REFERENCES explore_replies(id)",
        )
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_attachments (
                id SERIAL PRIMARY KEY,
                owner_type TEXT NOT NULL CHECK (owner_type IN ('post', 'reply')),
                owner_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('image', 'video', 'audio')),
                file_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (NOW())
            )
        """)
        # Same situation as the reactions constraint below: Postgres won't
        # widen an inline CHECK via ALTER TABLE ADD COLUMN, and this table
        # may already exist on Render with the old, narrower constraint
        # (no 'audio'). Drop and recreate under Postgres's default
        # auto-generated constraint name; a no-op once already applied.
        conn.execute("ALTER TABLE explore_attachments DROP CONSTRAINT IF EXISTS explore_attachments_kind_check")
        conn.execute(
            "ALTER TABLE explore_attachments ADD CONSTRAINT explore_attachments_kind_check "
            "CHECK (kind IN ('image', 'video', 'audio'))"
        )

        # --- Reactions: thumbs up/down on a post OR a discussion reply.
        # One reaction per user per (post_kind, post_id) — switching from
        # like to dislike replaces the row; voting again with the same
        # reaction removes it. The poster reacting on their own
        # post/reply is blocked in the route handlers. post_kind
        # disambiguates the id namespace: 'explore' and 'article' are
        # posts, 'explore_reply' is a reply on a discussion post — an
        # explore_posts.id and an explore_replies.id can collide as bare
        # integers, so post_kind is what keeps them apart.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article', 'explore_reply')),
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reaction TEXT NOT NULL CHECK (reaction IN ('like', 'dislike')),
                created_at TEXT NOT NULL DEFAULT (NOW()),
                PRIMARY KEY (post_kind, post_id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        # Postgres won't widen an inline CHECK constraint via ALTER TABLE
        # ADD COLUMN the way SQLite migrations elsewhere in this file work
        # — the table above may already exist on Render with the old,
        # narrower constraint (no 'explore_reply'), so it's dropped and
        # recreated here. Uses Postgres's default auto-generated name for
        # an inline column CHECK ({table}_{column}_check); safe to run
        # every startup since DROP ... IF EXISTS is a no-op once this has
        # already applied once.
        conn.execute("ALTER TABLE reactions DROP CONSTRAINT IF EXISTS reactions_post_kind_check")
        conn.execute(
            "ALTER TABLE reactions ADD CONSTRAINT reactions_post_kind_check "
            "CHECK (post_kind IN ('explore', 'article', 'explore_reply'))"
        )

        # --- Reporting: any signed-in user can report a post OR a
        # discussion reply (including a reply to a reply — both are just
        # rows in explore_replies, so post_kind='explore_reply' covers
        # both uniformly, same convention as reactions above). Moderators
        # review reported items and either cancel the report or warn the
        # author (an emailed message — the moderator never sees the
        # recipient's address; see moderation.py). One report per user
        # per item.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article', 'explore_reply')),
                post_id INTEGER NOT NULL,
                reported_by_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'cancelled', 'warned')),
                UNIQUE (post_kind, post_id, reported_by_user_id),
                FOREIGN KEY (reported_by_user_id) REFERENCES users(id)
            )
        """)
        # Same Postgres CHECK-widening pattern as above — this table may
        # already exist on Render with the old, narrower constraint (no
        # 'explore_reply'). No-op once already applied.
        conn.execute("ALTER TABLE reports DROP CONSTRAINT IF EXISTS reports_post_kind_check")
        conn.execute(
            "ALTER TABLE reports ADD CONSTRAINT reports_post_kind_check "
            "CHECK (post_kind IN ('explore', 'article', 'explore_reply'))"
        )
        # Warnings sent to a post's author. The moderator writes the
        # reason; the email is "sent" to the author's address, but the
        # moderator is never shown who the recipient is.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id SERIAL PRIMARY KEY,
                report_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (NOW()),
                FOREIGN KEY (report_id) REFERENCES reports(id),
                FOREIGN KEY (target_user_id) REFERENCES users(id),
                FOREIGN KEY (moderator_id) REFERENCES users(id)
            )
        """)

        # --- Ban Polls: moderator-started, public vote on de-anonymizing
        # the author of a specific anonymous post. Only started by a
        # moderator, only ever on an anonymous post (a named post has
        # nothing left to reveal). Every signed-in user gets one
        # irreversible vote. Auto-resolves the instant the conditions are
        # met: x/y >= k (or y = 0), and x+y >= ratio_threshold * T, where
        # T = total registered users at resolution time. On resolution the
        # target's identity is revealed via a permanent public announcement
        # — this is identity reveal only, not a ban.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ban_polls (
                id SERIAL PRIMARY KEY,
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article')),
                post_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                started_by_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                k_ratio REAL NOT NULL DEFAULT 5.0,
                turnout_ratio REAL NOT NULL DEFAULT 0.65,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
                created_at TEXT NOT NULL DEFAULT (NOW()),
                resolved_at TEXT,
                revealed_name TEXT,
                FOREIGN KEY (target_user_id) REFERENCES users(id),
                FOREIGN KEY (started_by_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ban_poll_votes (
                poll_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                vote TEXT NOT NULL CHECK (vote IN ('yes', 'no')),
                created_at TEXT NOT NULL DEFAULT (NOW()),
                PRIMARY KEY (poll_id, user_id),
                FOREIGN KEY (poll_id) REFERENCES ban_polls(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()