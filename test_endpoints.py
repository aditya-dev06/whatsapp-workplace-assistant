import time
import httpx
import json
import os
import sys

# Force standard stdout to use UTF-8 to prevent console emoji printing errors on Windows
if sys.platform.startswith("win"):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "database.json"))
ESCALATIONS_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "escalations_log.txt"))

def print_banner(title: str):
    print("=" * 60)
    print(f"[TEST] {title.upper()}")
    print("=" * 60)

def test_integration():
    # 0. Wait for server readiness check
    print_banner("Checking Server Status")
    try:
        r = httpx.get(f"{BASE_URL}/status")
        print(f"Healthcheck response: {r.status_code} - {r.json()}")
    except Exception as e:
        print(f"[ERROR] Server is not running on {BASE_URL}. Ensure uvicorn is running first!")
        print(f"Error details: {e}")
        return

    # Keep a copy of original database to restore later
    with open(DB_PATH, "r", encoding="utf-8") as f:
        original_db = f.read()

    try:
        # 1. Test Security / Unauthorized number
        print_banner("1. Testing Unauthorized Sender Protection")
        data = {
            "From": "whatsapp:+19999999999", # Unregistered number
            "Body": "hello"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response status: {r.status_code}")
        print(f"Response body:\n{r.text}")
        assert "Access Denied" in r.text
        print("[OK] Passed: Unauthorized request blocked securely.")

        # 2. Test Greeting and Menu
        print_banner("2. Testing Authorized Greeting Menu")
        data = {
            "From": "whatsapp:+1234567890", # Jane Doe
            "Body": "hello"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response body:\n{r.text}")
        assert "WORKPLACE SECURE ASSISTANT" in r.text
        print("[OK] Passed: Interactive menu returned successfully.")

        # 3. Test Leave Application (Chores Agent)
        print_banner("3. Testing Leave Application (Jane Doe)")
        data = {
            "From": "whatsapp:+1234567890", # Jane Doe (14 starting leaves)
            "Body": "apply leave for 3 days from June 12-14"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response body:\n{r.text}")
        assert "Leave successfully registered" in r.text or "Leave for *3 days*" in r.text
        
        # Verify database deduction
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db_state = json.load(f)
        jane_leave = db_state["employees"]["whatsapp:+1234567890"]["leave_balance"]
        print(f"Jane's new leave balance in DB: {jane_leave} (Expected: 11)")
        assert jane_leave == 11
        print("[OK] Passed: Leave deducted in DB and professional draft returned.")

        # 4. Test Workload & Stress Auditing (Alex Carter)
        print_banner("4. Testing Workload & Stress Audit (Alex Carter)")
        data = {
            "From": "whatsapp:+14155238886", # Alex Carter (Stress 7, tasks 1 completed, 3 pending)
            "Body": "status update"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response body:\n{r.text}")
        assert "Workload Index" in r.text
        assert "Burnout Precaution" in r.text or "Critically High" in r.text
        print("[OK] Passed: Workload index computed correctly and burnout alert triggered.")

        # 5. Test Task Completion (Rohan Sharma)
        print_banner("5. Testing Task Completion (Rohan Sharma)")
        # Rohan starts with task 301 pending
        data = {
            "From": "whatsapp:+919876543210", 
            "Body": "complete task 301"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response body:\n{r.text}")
        assert "marked as completed" in r.text
        
        # Verify database state
        with open(DB_PATH, "r", encoding="utf-8") as f:
            db_state = json.load(f)
        rohan_tasks = db_state["employees"]["whatsapp:+919876543210"]["tasks"]
        task_301 = next(t for t in rohan_tasks if t["id"] == 301)
        print(f"Task 301 status in DB: {task_301['status']} (Expected: completed)")
        assert task_301["status"] == "completed"
        print("[OK] Passed: Task completed successfully in JSON DB.")

        # 6. Test Neutral Escalation (Alex Carter)
        print_banner("6. Testing Anonymous Grievance Escalation (Alex Carter)")
        # Clear existing logs
        if os.path.exists(ESCALATIONS_PATH):
            os.remove(ESCALATIONS_PATH)
            
        data = {
            "From": "whatsapp:+14155238886",
            "Body": "complaint: My manager Jenkins is an absolute idiot and keeps screaming at me to work late!"
        }
        r = httpx.post(f"{BASE_URL}/whatsapp", data=data)
        print(f"Response body:\n{r.text}")
        assert "Privacy Confirmation" in r.text
        
        # Verify escalations log
        assert os.path.exists(ESCALATIONS_PATH)
        with open(ESCALATIONS_PATH, "r", encoding="utf-8") as f:
            logs = f.read()
        print(f"Logged Escalation Content:\n{logs}")
        assert "Jenkins" not in logs
        assert "screaming" not in logs
        print("[OK] Passed: Grievance anonymized, names stripped, and logged securely.")

        print("\n>>> ALL COMPREHENSIVE INTEGRATION TESTS PASSED SUCCESSFULLY! <<<\n")

    finally:
        # Restore original database to keep it clean
        with open(DB_PATH, "w", encoding="utf-8") as f:
            f.write(original_db)
        print("[CLEANUP] Database state restored to original settings.")

if __name__ == "__main__":
    test_integration()
