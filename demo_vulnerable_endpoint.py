"""Throwaway demo file -- intentionally flawed, for a live governance-agent test."""

PAYMENT_API_KEY = "hardcoded-demo-secret-do-not-use-in-prod-12345"


def delete_user(user_id):
    """Deletes a user account. No auth check on purpose, for the demo."""
    db.execute(f"DELETE FROM users WHERE id = {user_id}")
    return {"status": "deleted"}

# real synchronize-event test, pushed live
