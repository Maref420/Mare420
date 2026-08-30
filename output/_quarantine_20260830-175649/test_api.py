import urllib.request
import urllib.parse
import json

BASE_URL = "<http://127.0.0.1:8000>"

def create_user(username, password):
    data = urllib.parse.urlencode({
        "username": username,
        "password": password
    }).encode("utf-8")
    
    req = urllib.request.Request(BASE_URL + "/users/", data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        print(f"User creation failed: {e.code} - {e.read().decode()}")
        return None
    except Exception as e:
        print(f"User creation error: {e}")
        return None

def login(username, password):
    data = urllib.parse.urlencode({
        "username": username,
        "password": password
    }).encode("utf-8")
    
    req = urllib.request.Request(BASE_URL + "/token", data=data, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Login failed: {e}")
        return None

def get_protected_resource(token, endpoint):
    req = urllib.request.Request(BASE_URL + endpoint)
    req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read())
    except Exception as e:
        print(f"Request failed: {e}")
        return None

if __name__ == "__main__":
    print("1. Creating user 'admin' with password 'test_password'...")
    create_user("admin", "test_password")
    
    print("\n2. Logging in...")
    token_data = login("admin", "test_password")
    if token_data:
        token = token_data.get("access_token")
        print("   Success! Token received.")
        
        print("\n3. Getting user info...")
        user_info = get_protected_resource(token, "/users/me")
        print(f"   {user_info}")
        
        print("\n4. Getting items...")
        items = get_protected_resource(token, "/items/")
        print(f"   {items}")
    else:
        print("Could not login.")
