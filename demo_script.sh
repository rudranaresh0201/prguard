#!/usr/bin/env bash
# Aftershock live demo — 5 repos, hub-and-spoke, plus the signing proof.
# Say the bracketed [NARRATION] lines out loud as each block runs.

BASE=https://governance-agent.onrender.com

echo "=== [NARRATION] 'Five independent repos. None of them know the others exist.' ==="
echo "=== [NARRATION] 'Watch: each one just posts to the same board.' ==="
echo ""

curl -s -X POST $BASE/cross-repo/announce -H "Content-Type: application/json" \
  -d '{"repo":"demo/payments-svc","symbol":"livedemo_charge","old_signature":"charge(amount)","new_signature":"charge(amount, currency)","summary":"currency now required","severity":"high","pr_url":"https://github.com/demo/payments-svc/pull/1"}'
echo ""
curl -s -X POST $BASE/cross-repo/announce -H "Content-Type: application/json" \
  -d '{"repo":"demo/search-svc","symbol":"livedemo_search","old_signature":"search(query)","new_signature":"search(query, filters)","summary":"filters now required","severity":"medium","pr_url":"https://github.com/demo/search-svc/pull/7"}'
echo ""
curl -s -X POST $BASE/cross-repo/announce -H "Content-Type: application/json" \
  -d '{"repo":"demo/auth-svc","symbol":"livedemo_login","old_signature":"login(user,pass)","new_signature":"login(user,pass,mfa_token)","summary":"MFA token now required","severity":"critical","pr_url":"https://github.com/demo/auth-svc/pull/3"}'
echo ""
curl -s -X POST $BASE/cross-repo/announce -H "Content-Type: application/json" \
  -d '{"repo":"demo/inventory-svc","symbol":"livedemo_reserve_stock","old_signature":"reserve_stock(sku,qty)","new_signature":"reserve_stock(sku,qty,warehouse_id)","summary":"warehouse_id now required","severity":"high","pr_url":"https://github.com/demo/inventory-svc/pull/12"}'
echo ""
curl -s -X POST $BASE/cross-repo/announce -H "Content-Type: application/json" \
  -d '{"repo":"demo/notifications-svc","symbol":"livedemo_send_email","old_signature":"send_email(to,body)","new_signature":"send_email(to,subject,body)","summary":"subject now required","severity":"low","pr_url":"https://github.com/demo/notifications-svc/pull/20"}'
echo ""

echo ""
echo "=== [NARRATION] 'Now a SIXTH repo — checkout — checks 4 symbols at once, including one nobody ever announced.' ==="
curl -s -X POST $BASE/cross-repo/check -H "Content-Type: application/json" \
  -d '{"repo":"demo/checkout-svc","symbols":["livedemo_charge","livedemo_reserve_stock","livedemo_send_email","livedemo_nonexistent"]}'
echo ""
echo "=== [NARRATION] 'Three real hits, the fake one correctly ignored. One call, three different repos worth of findings.' ==="

echo ""
echo "=== [NARRATION] 'A SEVENTH repo — mobile app — only cares about auth and search. Watch it get exactly those two.' ==="
curl -s -X POST $BASE/cross-repo/check -H "Content-Type: application/json" \
  -d '{"repo":"demo/mobile-app","symbols":["livedemo_login","livedemo_search"]}'
echo ""
echo "=== [NARRATION] 'Nothing about payments or inventory leaked in — same board, scoped results.' ==="

echo ""
echo "=== [NARRATION] 'And this isn't just trust-me — every one of those records is cryptographically signed.' ==="
curl -s $BASE/cross-repo/pubkey
echo ""
echo "=== [NARRATION] 'Fetch that public key once, and you can verify any record offline, forever, without ever calling us again.' ==="
