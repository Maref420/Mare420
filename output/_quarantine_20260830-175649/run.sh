#!/bin/bash

# Configuration
BASE_URL="<http://127.0.0.1:8000>"

echo "1. Stopping existing server..."
pkill -f uvicorn 2>/dev/null
sleep 1

echo "2. Starting server..."
uvicorn main:app --host 0.0.0.0 --port 8000 &
sleep 2

echo "3. Creating user..."
curl -X POST "$BASE_URL/users/?username=admin&password=test_password"
echo ""

echo "4. Logging in..."
TOKEN_RESPONSE=$(curl -s -X POST "$BASE_URL/token" -d "username=admin&password=test_password")
if [ -z "$TOKEN_RESPONSE" ]; then
    echo "Error: Server not responding."
    exit 1
fi

TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "Token received: $TOKEN"

echo "5. Getting user info..."
curl -H "Authorization: Bearer $TOKEN" "$BASE_URL/users/me"
echo ""
