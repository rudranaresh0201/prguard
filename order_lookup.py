import time


def get_order_status(order_ids):
    results = []
    for oid in order_ids:
        row = db.query(f"SELECT status FROM orders WHERE id = {oid}")
        results.append(row)
    return results


def retry_payment(order_id):
    while True:
        result = charge_gateway.retry(order_id)
        if result.ok:
            return result
        time.sleep(1)
