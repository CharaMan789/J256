import sqlite3
from pathlib import Path
from contextlib import contextmanager

DB_PATH = Path(__file__).parent / "jamna.db"


def _add_column_if_missing(conn, table, column, coldef):
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {coldef}")


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                picture TEXT,
                pseudonym TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        # SQLite can't add a UNIQUE column via ALTER TABLE, so the
        # uniqueness is enforced with a partial index instead: it only
        # applies to non-NULL values, so any number of unverified users
        # (NULL) can coexist, but a real iiser_email can only ever belong
        # to one account.
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
        name_verified_is_new = "name_verified" not in {
            row["name"] for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now')),
                published_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "posts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS post_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('image', 'video', 'file')),
                file_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (post_id) REFERENCES posts(id)
            )
        """)
        # Doubts / Opinions / Ideas — the OLDER dormant board. Left as-is;
        # not linked in the nav, unrelated to the Explore feature below.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                category TEXT NOT NULL CHECK (category IN ('doubt', 'opinion', 'idea')),
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "doubts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "doubt_replies", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_votes (
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (doubt_id, user_id),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS doubt_escalations (
                doubt_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (doubt_id, user_id),
                FOREIGN KEY (doubt_id) REFERENCES doubts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- Explore: Poll / Discussion / Announcement, one shared feed ---
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_posts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                type TEXT NOT NULL CHECK (type IN ('poll', 'discussion', 'announcement')),
                title TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "explore_posts", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_poll_options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (post_id, user_id),
                FOREIGN KEY (post_id) REFERENCES explore_posts(id),
                FOREIGN KEY (option_id) REFERENCES explore_poll_options(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_replies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                is_anonymous INTEGER NOT NULL DEFAULT 0,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                FOREIGN KEY (post_id) REFERENCES explore_posts(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        _add_column_if_missing(conn, "explore_replies", "anon_pseudonym", "anon_pseudonym TEXT")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS explore_attachments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_type TEXT NOT NULL CHECK (owner_type IN ('post', 'reply')),
                owner_id INTEGER NOT NULL,
                kind TEXT NOT NULL CHECK (kind IN ('image', 'video')),
                file_path TEXT NOT NULL,
                original_name TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)

        # --- Reactions: thumbs up/down on a post. Anonymous — the table
        # only records who reacted for the one-reaction-per-user
        # enforcement below, it's never exposed to other users. One
        # reaction per user per post (switching from like to dislike
        # replaces the row rather than adding a second one); voting again
        # with the same reaction removes it. The poster reacting on their
        # own post is blocked in the route handlers, not here, since SQL
        # can't easily compare against explore_posts/posts.user_id across
        # both post_kinds. Covers explore posts and newspaper articles via
        # post_kind, same convention as reports above.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reactions (
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article')),
                post_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                reaction TEXT NOT NULL CHECK (reaction IN ('like', 'dislike')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (post_kind, post_id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)

        # --- Reporting: any signed-in user can report a post; moderators
        # review reported posts and either cancel the report or warn the
        # author (an emailed message — the moderator never sees the
        # recipient's address; see moderation.py). One report per user
        # per post. Covers explore posts (poll/discussion/announcement)
        # and newspaper articles via post_kind.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article')),
                post_id INTEGER NOT NULL,
                reported_by_user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'cancelled', 'warned')),
                UNIQUE (post_kind, post_id, reported_by_user_id),
                FOREIGN KEY (reported_by_user_id) REFERENCES users(id)
            )
        """)
        # Warnings sent to a post's author. The moderator writes the
        # reason; the email is "sent" to the author's address, but the
        # moderator is never shown who the recipient is.
        conn.execute("""
            CREATE TABLE IF NOT EXISTS warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_kind TEXT NOT NULL CHECK (post_kind IN ('explore', 'article')),
                post_id INTEGER NOT NULL,
                target_user_id INTEGER NOT NULL,
                started_by_id INTEGER NOT NULL,
                reason TEXT NOT NULL,
                k_ratio REAL NOT NULL DEFAULT 5.0,
                turnout_ratio REAL NOT NULL DEFAULT 0.65,
                status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved')),
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
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
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                PRIMARY KEY (poll_id, user_id),
                FOREIGN KEY (poll_id) REFERENCES ban_polls(id),
                FOREIGN KEY (user_id) REFERENCES users(id)
            )
        """)
        conn.commit()


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()