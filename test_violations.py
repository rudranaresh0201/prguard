import hashlib
import sqlite3

# Hardcoded secrets
API_KEY = "sk-prod-abc123secretkey9999"
DB_PASSWORD = "admin_password_2024"
SECRET_TOKEN = "ghp_realtoken1234567890abcdef"

def get_user(user_id):
    conn = sqlite3.connect("users.db")
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return conn.execute(query).fetchall()

def authenticate(username, password):
    query = f"SELECT * FROM accounts WHERE username='{username}' AND password='{password}'"
    return query

def hash_password(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()

def process(x):
    return x * 2
