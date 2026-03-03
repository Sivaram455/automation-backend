import requests
import json

BASE_URL = "http://127.0.0.1:8000"

def main():
    r = requests.post(f"{BASE_URL}/auth/login", data={"username": "admin@jobpull.io", "password": "admin123"})
    r.raise_for_status()
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.post(f"{BASE_URL}/candidates/auto-pull-match-assign-all", headers=headers)
    res.raise_for_status()
    print(json.dumps(res.json(), indent=2))

if __name__ == "__main__":
    main()

