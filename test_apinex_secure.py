import os, sys, requests, json, time

key = os.getenv("APINEX_KEY")
if not key:
    print("❌ Usage: APINEX_KEY='sk-...' python3 test_apinex_secure.py")
    sys.exit(1)

url = "https://api.apinex.bond/v1/chat/completions"
headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
payload = {
    "model": "gpt-5.6-sol", 
    "messages": [{"role": "user", "content": "Production Log Verification"}], 
    "max_tokens": 30,
    "stream": False
}

print(f"🚀 Target: {url}")
start = time.time()
try:
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    latency = int((time.time() - start) * 1000)
    
    print(f"📊 Status: {r.status_code} | ⏱️ Latency: {latency}ms")
    print("-" * 40)
    
    try:
        data = r.json()
        print(json.dumps(data, indent=2))
        
        # Quick Contract Check
        if r.status_code == 200:
            usage = data.get('usage', {})
            print(f"\n✅ SUCCESS. Usage: {usage}")
            if 'id' in data:
                print(f" Request ID: {data['id']} (Check this in dashboard)")
        else:
            err = data.get('error', {})
            print(f"\n⚠️ ERROR. Type: {err.get('type')}, Code: {err.get('code')}")
            
    except json.JSONDecodeError:
        print("Raw Text:", r.text[:200])

except Exception as e:
    print(f"❌ Network Error: {e}")
