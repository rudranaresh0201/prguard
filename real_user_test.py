"""Real-user-style test PR -- no admin trickery, no missing-auth check this time.
Just a normal small change with one genuine issue for the bot to find."""


def get_user_profile(user_id):
    query = "SELECT * FROM users WHERE id = " + str(user_id)
    return db.execute(query)
