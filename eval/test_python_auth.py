import hashlib
import sqlite3

JWT_SECRET = "super-secret-jwt-key-2024"

def get_user(username):
    query = f"SELECT * FROM users WHERE username='{username}'"
    conn = sqlite3.connect("users.db")
    return conn.execute(query).fetchone()

def hash_password(pwd):
    return hashlib.md5(pwd.encode()).hexdigest()

def delete_user(user_id):
    conn = sqlite3.connect("users.db")
    conn.execute(f"DELETE FROM users WHERE id={user_id}")
    conn.commit()

def calculate_discount(price, discount_percent):
    return price * (discount_percent / 100)
