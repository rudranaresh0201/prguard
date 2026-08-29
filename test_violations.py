import hashlib

password = "supersecret123"
db_password = "admin1234"
SECRET_KEY = "jwt-secret-do-not-share"

def get_user(user_input):
    query = f"SELECT * FROM users WHERE id={user_input}"
    return query

def hash_password(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()

def process_data(x):
    return x * 2
