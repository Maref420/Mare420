import os, sys, requests, json, time

KEY_FILE = "/root/Atlas-AI/.apinex_key"

if not os.path.exists(KEY_FILE):
    print("❌ Key file not found. Create .apinex_key first.")
    sys.exit(1)

with open(KEY_FILE, "r") as f:
    key = f.read().strip()

if not key.startswith("sk-"):
    print("❌ Invalid key format in file.")
    sys.exit(1)

url = "https://api.apinex.bond/v1/chat/completions"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
payload = {
    "model": "gpt-5.6-sol", 
    "messages": [{"role": "user", "content": "Secure Log Test v2"}], 
    "max_tokens": 30
}

print(f"🚀 Sending request securely...")
start = time.time()
try:
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    latency = int((time.time() - start) * 1000)
    
    print(f"📊 Status: {r.status_code} | ⏱️ Latency: {latency}ms")
    print("-" * 40)
    
    data = r.json()
    # Print only essential info to avoid clutter
    if r.status_code == 200:
        content = data.get('choices', [{}])[0].get('message', {}).get('content', 'No content')
        usage = data.get('usage', {})
        req_id = data.get('id', 'N/A')
        print(f"✅ Reply: {content[:50]}...")
        print(f"📈 Usage: {usage}")
        print(f"🆔 Request ID: {req_id}")
    else:
        print(f"⚠️ Error Response: {json.dumps(data, indent=2)}")

except Exception as e:
    print(f"❌ Network Error: {e}")
