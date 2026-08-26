"""Shared like/dislike helpers used by both main.py (newspaper articles,
post_kind='article') and explore.py (post_kind='explore'). See the
`reactions` table in database.py for the schema and design notes."""


def reaction_counts(conn, post_kind, post_id):
    row = conn.execute(
        "SELECT "
        "SUM(CASE WHEN reaction = 'like' THEN 1 ELSE 0 END) AS likes, "
        "SUM(CASE WHEN reaction = 'dislike' THEN 1 ELSE 0 END) AS dislikes "
        "FROM reactions WHERE post_kind = ? AND post_id = ?",
        (post_kind, post_id),
    ).fetchone()
    return int(row["likes"] or 0), int(row["dislikes"] or 0)


def my_reaction(conn, post_kind, post_id, user):
    """Returns 'like', 'dislike', or None. None for a signed-out user too."""
    if not user:
        return None
    row = conn.execute(
        "SELECT reaction FROM reactions WHERE post_kind = ? AND post_id = ? AND user_id = ?",
        (post_kind, post_id, user["id"]),
    ).fetchone()
    return row["reaction"] if row else None


def toggle_reaction(conn, post_kind, post_id, user_id, reaction):
    """Sets the user's reaction, toggling off if they clicked the same one
    again. Caller is responsible for the require_user / not-your-own-post
    checks and for conn.commit(). Returns the resulting reaction ('like',
    'dislike', or None if it was just removed)."""
    existing = conn.execute(
        "SELECT reaction FROM reactions WHERE post_kind = ? AND post_id = ? AND user_id = ?",
        (post_kind, post_id, user_id),
    ).fetchone()
    if existing and existing["reaction"] == reaction:
        conn.execute(
            "DELETE FROM reactions WHERE post_kind = ? AND post_id = ? AND user_id = ?",
            (post_kind, post_id, user_id),
        )
        return None
    conn.execute(
        "INSERT INTO reactions (post_kind, post_id, user_id, reaction) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (post_kind, post_id, user_id) DO UPDATE SET "
        "reaction = excluded.reaction, created_at = datetime('now')",
        (post_kind, post_id, user_id, reaction),
    )
    return reaction