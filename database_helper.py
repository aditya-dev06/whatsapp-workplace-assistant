import json
import os
import threading
from typing import Optional, Dict, Any

class DatabaseHelper:
    def __init__(self, db_path: str = "database.json"):
        self.db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), db_path))
        self.lock = threading.Lock()
        
    def _load_data(self) -> Dict[str, Any]:
        with self.lock:
            if not os.path.exists(self.db_path):
                return {"employees": {}}
            try:
                with open(self.db_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"employees": {}}

    def _save_data(self, data: Dict[str, Any]) -> bool:
        with self.lock:
            try:
                with open(self.db_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                return True
            except IOError:
                return False

    def get_employee(self, phone_number: str) -> Optional[Dict[str, Any]]:
        data = self._load_data()
        return data.get("employees", {}).get(phone_number)

    def update_employee(self, phone_number: str, employee_data: Dict[str, Any]) -> bool:
        data = self._load_data()
        if "employees" not in data:
            data["employees"] = {}
        data["employees"][phone_number] = employee_data
        return self._save_data(data)

    def apply_leave(self, phone_number: str, days: int) -> tuple[bool, Optional[int]]:
        """
        Deducts the leave days and returns (success, new_balance).
        """
        employee = self.get_employee(phone_number)
        if not employee:
            return False, None
        
        current_balance = employee.get("leave_balance", 0)
        if current_balance < days:
            return False, current_balance
        
        employee["leave_balance"] = current_balance - days
        success = self.update_employee(phone_number, employee)
        return success, employee["leave_balance"]

    def add_task(self, phone_number: str, title: str) -> tuple[bool, Optional[int]]:
        employee = self.get_employee(phone_number)
        if not employee:
            return False, None
        
        tasks = employee.get("tasks", [])
        new_id = max([t.get("id", 0) for t in tasks] + [0]) + 1
        tasks.append({"id": new_id, "title": title, "status": "pending"})
        employee["tasks"] = tasks
        
        # Proactively slightly increase stress level when adding a new pending task
        employee["stress_level"] = min(employee.get("stress_level", 0) + 1, 10)
        
        success = self.update_employee(phone_number, employee)
        return success, new_id

    def complete_task(self, phone_number: str, task_id: int) -> tuple[bool, str]:
        employee = self.get_employee(phone_number)
        if not employee:
            return False, "Employee not found."
        
        tasks = employee.get("tasks", [])
        found = False
        task_title = ""
        for task in tasks:
            if task.get("id") == task_id:
                if task.get("status") == "completed":
                    return False, f"Task '{task.get('title')}' is already completed."
                task["status"] = "completed"
                task_title = task.get("title", "")
                found = True
                break
                
        if not found:
            return False, f"Task ID {task_id} not found."
        
        # Proactively slightly decrease stress level when completing a task
        employee["stress_level"] = max(employee.get("stress_level", 0) - 1, 0)
        
        employee["tasks"] = tasks
        success = self.update_employee(phone_number, employee)
        return success, task_title

# Singleton instance
db = DatabaseHelper()
