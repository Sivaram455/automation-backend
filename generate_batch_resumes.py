import requests
import json
import time

BASE_URL = "http://127.0.0.1:8000"

def generate_resumes():
    print("Logging in as admin...")
    login_data = {
        "username": "admin@jobpull.io",
        "password": "admin123"
    }
    try:
        response = requests.post(f"{BASE_URL}/auth/login", data=login_data)
        response.raise_for_status()
        token = response.json()["access_token"]
        print("Successfully logged in.\n")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        print("Starting batch resume generation for multiple candidates!")
        print("Our system will grab their top job matches and craft individual resumes for each job...")
        print("This may take 10-30 seconds depending on how many candidates exist...\n")
        
        start_time = time.time()
        
        res = requests.post(f"{BASE_URL}/resume/generate-batch-for-candidates", headers=headers)
        res.raise_for_status()
        
        duration = time.time() - start_time
        result = res.json()
        print(f"Batch mapping complete in {duration:.1f} seconds!")
        
        # Display the output cleanly
        for candidate_data in result.get("details", []):
            print(f"\n==========================================")
            print(f"👔 CANDIDATE: {candidate_data['candidate_name']}")
            print(f"==========================================")
            for resume in candidate_data.get("resumes_generated", []):
                print(f"\n   📍 Tailored for: {resume['job_title']} at {resume['company']}")
                if "error" in resume:
                    print(f"      [ERROR] {resume['error']}")
                else:
                    print(f"      [GENERATED PREVIEW]")
                    # indentation for the excerpt
                    print(f"      {resume['resume_excerpt']}")
            
        print("\n\n" + result.get("message", ""))
        
    except requests.exceptions.ConnectionError:
        print(f"Error: Could not connect to the backend server at {BASE_URL}. Make sure it is running.")
    except Exception as e:
        print(f"An error occurred: {e}")
        if 'res' in locals() and res.status_code != 200:
            print(res.text)

if __name__ == "__main__":
    generate_resumes()
