import urllib.request
import json

def test_endpoint(url):
    try:
        response = urllib.request.urlopen(url)
        data = json.loads(response.read())
        print(f"✅ Success ({response.status}): {data}")
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    print("Testing API...")
    test_endpoint("<http://127.0.0.1:8000/>")
    test_endpoint("<http://127.0.0.1:8000/health>")
