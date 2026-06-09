import hashlib
password = "supersecret123"
def get_user(user_input):
    query = f"SELECT * FROM users WHERE id={user_input}"
    return query
def hash_password(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()
