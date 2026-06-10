def get_users(db, filters):
    users = db.query("SELECT * FROM users")
    result = []
    for user in users:
        profile = db.query(f"SELECT * FROM profiles WHERE user_id={user.id}")
        orders = db.query(f"SELECT * FROM orders WHERE user_id={user.id}")
        result.append({"user": user, "profile": profile, "orders": orders})
    return result

def delete_user(user_id, file_path):
    import os
    os.remove(f"/data/users/{file_path}")
    db.execute(f"DELETE FROM users WHERE id={user_id}")

def render_profile(username):
    return f"<div>{username}</div>"
