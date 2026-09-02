import sys, requests, json, time, os

# Read key from environment variable to avoid history logs
key = os.getenv("TEST_API_KEY")
if not key:
    print("❌ Error: Set TEST_API_KEY env var first.")
    sys.exit(1)

url = "https://api.apinex.bond/v1/chat/completions"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
payload = {
    "model": "gpt-5.6-sol", 
    "messages": [{"role": "user", "content": "Secure VPS Test"}], 
    "max_tokens": 20
}

print(f"🚀 Sending request...")
start = time.time()
try:
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    latency = int((time.time() - start) * 1000)
    print(f"Status: {r.status_code} | Latency: {latency}ms")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
