import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def pull_jobs():
    print("Logging in as admin...")
    # Login as admin to get token
    login_data = {
        "username": "admin@jobpull.io",
        "password": "admin123"
    }
    try:
        response = requests.post(f"{BASE_URL}/auth/login", data=login_data)
        response.raise_for_status()
        token = response.json()["access_token"]
        print("Successfully logged in.")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        print("Pulling jobs based on candidate skills from multiple portals (Remotive, The Muse, Working Nomads)...")
        print("This may take a minute...")
        start_time = time.time()
        
        pull_response = requests.post(f"{BASE_URL}/jobs/pull-for-candidates", headers=headers)
        pull_response.raise_for_status()
        
        duration = time.time() - start_time
        result = pull_response.json()
        print(f"\nDone in {duration:.1f} seconds!")
        print(json.dumps(result, indent=2))
        
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the backend server at {BASE_URL}. Make sure it is running.")
    except Exception as e:
        print(f"An error occurred: {e}")
        if 'pull_response' in locals() and pull_response.status_code != 200:
            print(pull_response.text)

if __name__ == "__main__":
    pull_jobs()
