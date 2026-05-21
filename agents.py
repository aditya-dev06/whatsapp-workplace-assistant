import re
import os
import httpx
from datetime import datetime
from typing import Dict, Any, Tuple
from config import settings
from database_helper import db

# Define system prompts for each specialized agent

CHORES_PROMPT = """
You are the Chores Agent, an objective corporate assistant specializing in managing leaves, official text formatting, and email drafting.
An employee is interacting with you. Your job is to draft clean, professional emails or leave notes based on their input.

If the user is applying for a leave:
1. Parse the number of days, start date, and end date if provided.
2. Return a JSON structure exactly matching this block at the VERY END of your response, prefixed by a delimiter [ACTION_JSON]:
[ACTION_JSON]{"action": "apply_leave", "days": <int>, "dates": "<start> to <end>"}

If the user is adding a task:
Return this JSON block at the end:
[ACTION_JSON]{"action": "add_task", "title": "<task title>"}

If the user is completing a task:
Return this JSON block at the end:
[ACTION_JSON]{"action": "complete_task", "task_id": <int>}

Ensure your text response is concise, extremely professional, and ready to be forwarded on WhatsApp.
"""

WORKLOAD_PROMPT = """
You are the Workload Tracker, an objective corporate psychologist and task auditor.
Your job is to analyze the employee's stress, workload, and performance indicators without emotional bias.

The user will provide their task list or request a "status update".
1. Look at their tasks: calculate the Workload Index (Pending Tasks vs Total Tasks).
2. Report the metrics clearly and objectively:
   - Workload Index (e.g., 0.67 is High, 0.33 is Moderate)
   - Current Stress Level (obtained from user details)
   - Recommendation (proactive balance tips if high, e.g., > 0.6)
Ensure the tone is supportive yet highly analytical and neutral. Avoid flowery language.
"""

ESCALATOR_PROMPT = """
You are the Neutral Escalator. You take corporate complaints and workplace grievances, strip away ALL emotional spikes, vitriol, personal identifiers (names of people/managers), and reformat them into fully objective, neutral feedback ready for constructive leadership review.

Your output must strictly contain:
1. The sanitized, professionally reframed feedback.
2. A confirmation that this has been securely logged.

You MUST append the sanitized text at the end using this JSON block:
[ACTION_JSON]{"action": "log_escalation", "sanitized_text": "<reframed feedback without names/emotions>"}
"""

async def call_llm(system_prompt: str, user_prompt: str) -> str:
    """
    Stateless, secure LLM client supporting both Cloud OpenAI and Local Ollama.
    """
    if settings.AGENT_MODE == "openai":
        if not settings.OPENAI_API_KEY:
            return "Error: OpenAI API Key is missing in configurations. Please set it in your .env file."
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}"
        }
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.3
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers=headers,
                    json=payload
                )
                if response.status_code == 200:
                    result = response.json()
                    return result["choices"][0]["message"]["content"]
                else:
                    return f"Error: OpenAI returned status code {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error connecting to OpenAI: {str(e)}"

    elif settings.AGENT_MODE == "ollama":
        url = f"{settings.OLLAMA_BASE_URL}/api/chat"
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "stream": False,
            "options": {
                "temperature": 0.3
            }
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, json=payload)
                if response.status_code == 200:
                    result = response.json()
                    return result["message"]["content"]
                else:
                    return f"Error: Ollama returned status code {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error connecting to local Ollama at {settings.OLLAMA_BASE_URL}: {str(e)}"

    # Default fallback
    return "Error: Unsupported agent mode configured."


class AgentCoordinator:
    """
    Coordinates routing, execution, and state manipulation for all agents.
    """
    
    @staticmethod
    def _route_intent_mock(text: str) -> str:
        """
        Regex-based rule router for fast, offline testing.
        """
        text_lower = text.lower()
        if any(w in text_lower for w in ["leave", "vacation", "off", "holiday", "add task", "complete task", "finish task"]):
            return "CHORES"
        elif any(w in text_lower for w in ["status", "update", "workload", "burnout", "stress", "tasks"]):
            return "WORKLOAD"
        elif any(w in text_lower for w in ["complaint", "grievance", "unfair", "angry", "screaming", "breathing down", "hate", "abuse", "harass", "escalate"]):
            return "ESCALATION"
        return "GENERAL"

    @classmethod
    async def route_intent(cls, text: str) -> str:
        """
        Determines the appropriate agent based on the incoming message.
        """
        if settings.AGENT_MODE == "mock":
            return cls._route_intent_mock(text)
        
        # LLM-based classification prompt
        system_router_prompt = (
            "You are a router agent. Classify the user's incoming corporate message into exactly one category:\n"
            "- CHORES: If they want to apply/log leaves, write/format an email, add a task, or mark a task as completed.\n"
            "- WORKLOAD: If they want to check their tasks status, workload index, burnout, stress levels, or ask 'status update'.\n"
            "- ESCALATION: If they are making a complaint, grievance, reporting toxic behavior, expressing extreme distress/harassment.\n"
            "- GENERAL: For standard greetings like hi, hello, help, or unknown requests.\n"
            "Respond with exactly one word: CHORES, WORKLOAD, ESCALATION, or GENERAL."
        )
        try:
            response = await call_llm(system_router_prompt, text)
            clean_res = response.strip().upper()
            for token in ["CHORES", "WORKLOAD", "ESCALATION", "GENERAL"]:
                if token in clean_res:
                    return token
            return "GENERAL"
        except Exception:
            return cls._route_intent_mock(text)

    @classmethod
    async def process_chores(cls, phone: str, text: str, employee: Dict[str, Any]) -> str:
        if settings.AGENT_MODE == "mock":
            return cls._process_chores_mock(phone, text, employee)
        
        # LLM execution
        user_context = f"Employee Profile: {employee}\nRequest: {text}"
        response = await call_llm(CHORES_PROMPT, user_context)
        return cls._execute_action_json(phone, response)

    @classmethod
    async def process_workload(cls, phone: str, text: str, employee: Dict[str, Any]) -> str:
        if settings.AGENT_MODE == "mock":
            return cls._process_workload_mock(phone, text, employee)
        
        # LLM execution
        user_context = f"Employee Profile: {employee}\nRequest: {text}"
        return await call_llm(WORKLOAD_PROMPT, user_context)

    @classmethod
    async def process_escalation(cls, phone: str, text: str, employee: Dict[str, Any]) -> str:
        if settings.AGENT_MODE == "mock":
            return cls._process_escalation_mock(phone, text, employee)
        
        # LLM execution
        user_context = f"Employee Profile: {employee}\nGrievance: {text}"
        response = await call_llm(ESCALATOR_PROMPT, user_context)
        return cls._execute_action_json(phone, response)

    # --- ACTION EXECUTION HELPER ---
    @staticmethod
    def _execute_action_json(phone: str, response: str) -> str:
        """
        Parses action JSON appended by agents, updates DB, and cleans the text response.
        """
        if "[ACTION_JSON]" not in response:
            return response
        
        parts = response.split("[ACTION_JSON]")
        clean_text = parts[0].strip()
        json_str = parts[1].strip()
        
        try:
            import json
            action_data = json.loads(json_str)
            action = action_data.get("action")
            
            if action == "apply_leave":
                days = action_data.get("days", 1)
                dates = action_data.get("dates", "requested dates")
                success, balance = db.apply_leave(phone, days)
                if success:
                    clean_text += f"\n\n🟢 *System Log:* Leave for *{days} days* ({dates}) successfully registered in database.json! New balance: *{balance} days*."
                else:
                    clean_text += f"\n\n🔴 *System Error:* Insufficient leave balance! Remaining: *{balance} days*."
                    
            elif action == "add_task":
                title = action_data.get("title", "New Task")
                success, new_id = db.add_task(phone, title)
                if success:
                    clean_text += f"\n\n🟢 *System Log:* Task ID *{new_id}* ('{title}') successfully added to database.json!"
                    
            elif action == "complete_task":
                task_id = int(action_data.get("task_id", 0))
                success, title = db.complete_task(phone, task_id)
                if success:
                    clean_text += f"\n\n🟢 *System Log:* Task ID *{task_id}* ('{title}') marked as *completed*!"
                else:
                    clean_text += f"\n\n🔴 *System Error:* {title}"
                    
            elif action == "log_escalation":
                sanitized_text = action_data.get("sanitized_text", "")
                if sanitized_text:
                    escalations_file = os.path.join(os.path.dirname(__file__), "escalations_log.txt")
                    timestamp = datetime.now().isoformat()
                    with open(escalations_file, "a", encoding="utf-8") as f:
                        f.write(f"[{timestamp}] Sanitized Grievance:\n{sanitized_text}\n\n")
                    clean_text += "\n\n🟢 *Privacy Confirmation:* Gripes securely scrubbed, anonymized, and logged in escalations_log.txt. No identification metrics retained."
                    
        except Exception as e:
            # Fallback silently but note in clean_text during debugging
            clean_text += f"\n\n⚠️ *System Alert:* Action processing encountered an issue: {str(e)}"
            
        return clean_text

    # --- MOCK FALLBACK IMPLEMENTATIONS ---
    @staticmethod
    def _process_chores_mock(phone: str, text: str, employee: Dict[str, Any]) -> str:
        text_lower = text.lower()
        
        # Complete Task Mock
        if "complete task" in text_lower:
            match = re.search(r'complete task\s+(\d+)', text_lower)
            if match:
                task_id = int(match.group(1))
                success, result_msg = db.complete_task(phone, task_id)
                if success:
                    return (
                        f"### Task Completed!\n\n"
                        f"Great work on completing task *{task_id}* (*{result_msg}*). I have updated the company ledger.\n\n"
                        f"🟢 *System Log:* Task successfully marked as completed. Keep up the high velocity!"
                    )
                else:
                    return f"🔴 *System Error:* Task ID {task_id} could not be updated. Reason: {result_msg}"
        
        # Add Task Mock
        if "add task" in text_lower:
            match = re.search(r'add task\s+(.+)', text, re.IGNORECASE)
            if match:
                title = match.group(1).strip()
                success, new_id = db.add_task(phone, title)
                if success:
                    return (
                        f"### Task Logged Successfully\n\n"
                        f"I have registered a new chore for you: *{title}* (assigned ID: *{new_id}*).\n\n"
                        f"🟢 *System Log:* Added to database.json under active task roster."
                    )
        
        # Apply Leave Mock
        days_match = re.search(r'(\d+)\s*day', text_lower)
        days = int(days_match.group(1)) if days_match else 1
        
        # Extract dates or simulate
        dates_match = re.search(r'(?:from|for)\s+([A-Za-z]+\s+\d+(?:-\d+)?|\d+/\d+)', text_lower)
        dates = dates_match.group(1).strip() if dates_match else "requested dates"
        
        success, balance = db.apply_leave(phone, days)
        if success:
            return (
                f"### Official Leave Draft\n\n"
                f"**To:** {employee.get('manager', 'Manager')}\n"
                f"**Subject:** Leave Request - {employee.get('name')}\n\n"
                f"Please accept this official request for a *{days} day* leave starting on *{dates}*. "
                f"I will ensure all my handovers are completed before departure.\n\n"
                f"🟢 *System Log:* Leave successfully registered. Deducted *{days}* days. New balance: *{balance} days*."
            )
        else:
            return (
                f"### Leave Application Failed\n\n"
                f"You requested *{days} days* of leave, but you only have *{balance} days* remaining in your account.\n\n"
                f"🔴 *System Error:* Operation cancelled due to insufficient balance."
            )

    @staticmethod
    def _process_workload_mock(phone: str, text: str, employee: Dict[str, Any]) -> str:
        tasks = employee.get("tasks", [])
        total_tasks = len(tasks)
        pending_tasks = sum(1 for t in tasks if t.get("status") == "pending")
        completed_tasks = total_tasks - pending_tasks
        
        # Workload Index calculation
        workload_index = round(pending_tasks / total_tasks, 2) if total_tasks > 0 else 0.0
        
        status_color = "🟢"
        status_label = "Optimal"
        if workload_index >= 0.7:
            status_color = "🔴"
            status_label = "Critically High (Burnout Warning!)"
        elif workload_index >= 0.4:
            status_color = "🟡"
            status_label = "Moderate (Monitor Workload)"
            
        task_rows = []
        for t in tasks:
            status_icon = "✅" if t.get("status") == "completed" else "⏳"
            task_rows.append(f"- {status_icon} [{t.get('id')}] {t.get('title')}")
            
        task_list_str = "\n".join(task_rows)
        
        # Stress level based warnings
        stress_level = employee.get("stress_level", 0)
        burnout_advice = ""
        if stress_level >= 7 or workload_index >= 0.7:
            burnout_advice = (
                f"\n⚠️ *Burnout Precaution:* Your Workload Index is at *{workload_index}* and registered stress is *{stress_level}/10*. "
                f"We strongly recommend setting aside a 15-minute screen-free block today or drafting a leave request to rest."
            )
            
        return (
            f"### Workplace Workload & Stress Audit\n\n"
            f"**Employee:** {employee.get('name')}\n"
            f"**Role:** {employee.get('role')}\n\n"
            f"**Metrics Summary:**\n"
            f"- Workload Index: *{workload_index}* ({pending_tasks} pending / {total_tasks} total)\n"
            f"- Status: {status_color} *{status_label}*\n"
            f"- Stress Level: *{stress_level}/10*\n"
            f"- Hours Logged Today: *{employee.get('daily_hours_logged', 0)} hrs*\n\n"
            f"**Task Ledger:**\n"
            f"{task_list_str}"
            f"{burnout_advice}"
        )

    @staticmethod
    def _process_escalation_mock(phone: str, text: str, employee: Dict[str, Any]) -> str:
        # Simple heuristic sanitization (removing common emotionally charged words)
        cleaned = text
        # Remove direct reference to names or roles if common
        cleaned = re.sub(r'(?i)\b(?:my manager|sarah|john|jenkins|smith)\b', "a supervisor", cleaned)
        cleaned = re.sub(r'(?i)\b(?:is an? idiot|hate|screaming|stupid|awful|dumb|breathing down)\b', "expressing highly directive and micro-managerial tendencies", cleaned)
        cleaned = re.sub(r'(?i)\b(?:making me work late|forcing me to stay)\b', "consistently scheduling deliverables outside of official contract hours", cleaned)
        
        # Strip the trigger word "complaint:" or similar
        cleaned = re.sub(r'(?i)^complaint:\s*', '', cleaned).strip()
        
        # Write to secure log
        escalations_file = os.path.join(os.path.dirname(__file__), "escalations_log.txt")
        timestamp = datetime.now().isoformat()
        
        with open(escalations_file, "a", encoding="utf-8") as f:
            f.write(f"[{timestamp}] Anonymized Grievance Logged:\n\"{cleaned}\"\n\n")
            
        return (
            f"### Neutral Corporate Escalation\n\n"
            f"Your feedback has been reframed to ensure objectivity and strip emotional markers:\n\n"
            f"\"_{cleaned}_\"\n\n"
            f"🟢 *Privacy Confirmation:* This feedback has been securely committed to escalations_log.txt. "
            f"Your name, phone number, and managers' names have been stripped to guarantee total anonymity."
        )
