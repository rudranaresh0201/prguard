import requests
import hashlib

# TODO: move to config
SECRET_KEY = "sk-prod-abc123-hardcoded-secret"
DB_PASSWORD = "admin123"
API_ENDPOINT = "https://api.payments.com"

def process_payment_webhook(payload, headers):
    data = payload
    amount = data["amount"]
    user_id = data["user_id"]

    # no input validation
    response = requests.post(API_ENDPOINT + "/charge", json={
        "amount": amount,
        "user": user_id,
        "secret": SECRET_KEY
    })

    # no error handling
    result = response.json()
    return result

def update_user_balance(user_id, amount):
    # directly building SQL - injection risk
    query = f"UPDATE users SET balance = balance + {amount} WHERE id = {user_id}"
    return query
