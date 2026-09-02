import sys, requests, json, time

if len(sys.argv) < 2:
    print("Usage: python test_apinex_live.py <
sk-apxe925955c1c06dd1eb829da88d31152500d80bda6107b001>")
    sys.exit(1)

key = sys.argv[1]
url = "https://api.apinex.bond/v1/chat/completions"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
payload = {"model": "gpt-5.6-sol", "messages": [{"role": "user", "content": "VPS Log Test"}], "max_tokens": 20}

print(f"🚀 Requesting...")
start = time.time()
try:
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    print(f"Status: {r.status_code} | Latency: {int((time.time()-start)*1000)}ms")
    print(json.dumps(r.json(), indent=2))
except Exception as e:
    print(f"Error: {e}")
