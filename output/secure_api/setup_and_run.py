import os
import json
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "http://127.0.0.1:8000"
USERNAME = "admin"
PASSWORD = os.environ.get("SETUP_TEST_PASSWORD", "CHANGE_ME_IMMEDIATELY")
# WARNING: Was hardcoded "test_password". Rotated 2026-08-30. Set SETUP_TEST_PASSWORD env var.


def request(method, url, data=None, headers=None):
    body = None

    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")

    req = urllib.request.Request(
        url=url,
        data=body,
        method=method,
        headers=headers or {},
    )

    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            raw = response.read().decode("utf-8")
            try:
                return response.status, json.loads(raw)
            except json.JSONDecodeError:
                return response.status, raw

    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw

        return exc.code, payload

    except Exception as exc:
        return None, {"error": str(exc)}


print("===== Atlas Secure API Test =====")
print(f"Base URL: {BASE_URL}")

# 1. Create user.
# /users/ expects query parameters, not form body.
print("\n[1] Creating user...")

create_url = (
    BASE_URL
    + "/users/"
    + "?"
    + urllib.parse.urlencode(
        {
            "username": USERNAME,
            "password": PASSWORD,
        }
    )
)

status, result = request("POST", create_url)

print(f"HTTP {status}")
print(result)

# 2. Login.
# /token uses OAuth2PasswordRequestForm.
print("\n[2] Logging in...")

status, result = request(
    "POST",
    BASE_URL + "/token",
    {
        "username": USERNAME,
        "password": PASSWORD,
    },
    {
        "Content-Type": "application/x-www-form-urlencoded",
    },
)

print(f"HTTP {status}")
print(result)

if status != 200 or not isinstance(result, dict):
    print("\nLOGIN FAILED")
    raise SystemExit(1)

token = result.get("access_token")

if not token:
    print("\nLOGIN FAILED: access_token missing")
    raise SystemExit(1)

print("\n[3] Token received successfully.")

# 3. Authenticated request.
print("\n[4] Getting current user...")

status, result = request(
    "GET",
    BASE_URL + "/users/me",
    headers={
        "Authorization": f"Bearer {token}",
    },
)

print(f"HTTP {status}")
print(result)

if status == 200:
    print("\n================================")
    print("SECURE API TEST: SUCCESS")
    print("================================")
else:
    print("\n================================")
    print("SECURE API TEST: FAILED")
    print("================================")
    raise SystemExit(1)
