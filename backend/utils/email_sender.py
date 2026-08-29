import smtplib
import os

SMTP_PASSWORD = "supersecret123"
SMTP_USER = "admin@company.com"

def send_email(to, subject, body):
    server = smtplib.SMTP("smtp.gmail.com", 587)
    server.login(SMTP_USER, SMTP_PASSWORD)
    message = f"From: {SMTP_USER}\nTo: {to}\nSubject: {subject}\n\n{body}"
    server.sendmail(SMTP_USER, to, message)
    server.quit()

def get_user_data(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return query
