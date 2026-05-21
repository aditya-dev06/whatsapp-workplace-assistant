import urllib.parse
from fastapi import FastAPI, Form, Response, HTTPException
from twilio.twiml.messaging_response import MessagingResponse

from config import settings
from database_helper import db
from formatting import format_for_whatsapp
from agents import AgentCoordinator

app = FastAPI(
    title="Agentic Workplace Assistant",
    description="Secure, multi-agent WhatsApp backend simulating zero-data-retention corporate assistance.",
    version="1.0.0"
)

HELP_MENU = """
*🏢 WORKPLACE SECURE ASSISTANT*

Hello, *{name}*! Here are the commands you can text me securely:

📅 *Leave & Tasks*
• _"apply leave for 3 days from June 12-14"_ -> Logs leave.
• _"add task Review API schemas"_ -> Registers a new task.
• _"complete task <ID>"_ (e.g. _"complete task 102"_) -> Closes a task.

📊 *Workload & Stress Audit*
• _"status update"_ or _"workload"_ -> Audits your tasks, calculates stress index, and offers mental balance tips.

🛡️ *Anonymous Escalation*
• _"complaint: <grievance text>"_ -> Strips emotions and supervisor names, logging it anonymously for HR review.

❓ _Text "help" or "?" at any time to view this menu again._
"""

@app.post("/whatsapp")
async def whatsapp_webhook(
    Body: str = Form(...),
    From: str = Form(...)
):
    """
    Core Twilio WhatsApp webhook POST handler.
    Receives incoming form-urlencoded variables, verifies user, routes to agents,
    converts markdown formatting to WhatsApp and returns synchronous XML TwiML responses.
    """
    # 1. Twilio Sandbox wraps numbers as "whatsapp:+14155238886"
    sender_phone = From.strip()
    
    # 2. Authentication Gate: check against database.json
    employee = db.get_employee(sender_phone)
    
    # Initialize Twilio markup response
    twiml_resp = MessagingResponse()
    
    if not employee:
        # Strict rejection for privacy/security
        warning_msg = (
            "⚠️ *Security Notice: Access Denied.*\n\n"
            "Your phone number is not registered in our secure workplace ledger.\n"
            "Please contact IT or HR administration to register this device."
        )
        twiml_resp.message(warning_msg)
        return Response(content=str(twiml_resp), media_type="application/xml")

    # Clean the message body
    incoming_text = Body.strip()
    incoming_text_lower = incoming_text.lower()
    
    # 3. Interactive Greetings & Help Routing
    if incoming_text_lower in ["hi", "hello", "hey", "help", "?", "menu", "start"]:
        welcome_menu = HELP_MENU.format(name=employee.get("name", "Employee"))
        formatted_menu = format_for_whatsapp(welcome_menu)
        twiml_resp.message(formatted_menu)
        return Response(content=str(twiml_resp), media_type="application/xml")
    
    # 4. Multi-Agent Router Classification
    intent = await AgentCoordinator.route_intent(incoming_text)
    
    # 5. Agent Execution
    try:
        if intent == "CHORES":
            raw_reply = await AgentCoordinator.process_chores(sender_phone, incoming_text, employee)
        elif intent == "WORKLOAD":
            raw_reply = await AgentCoordinator.process_workload(sender_phone, incoming_text, employee)
        elif intent == "ESCALATION":
            raw_reply = await AgentCoordinator.process_escalation(sender_phone, incoming_text, employee)
        else:
            # Fallback to standard dialogue using mock/chores behavior
            raw_reply = (
                f"I processed your message as a general request:\n\n"
                f"\"{incoming_text}\"\n\n"
                f"For direct commands, please see the *menu* by texting *help*."
            )
            
    except Exception as e:
        raw_reply = f"⚠️ *Internal Error:* We encountered a problem processing your request: {str(e)}"

    # 6. Apply Custom WhatsApp Formatting Translation
    formatted_reply = format_for_whatsapp(raw_reply)
    
    # 7. Package in Twilio messaging XML payload
    twiml_resp.message(formatted_reply)
    
    # Return as XML Response
    return Response(content=str(twiml_resp), media_type="application/xml")


@app.get("/status")
def server_status():
    """
    Lightweight healthcheck endpoint.
    """
    return {
        "status": "online",
        "agent_mode": settings.AGENT_MODE,
        "database_connected": True
    }
