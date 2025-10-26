"""IngestAgent with REST endpoints for Android app"""
from uagents import Agent, Context, Model
import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Models
class NavigationLog(Model):
    client_id: str
    session_id: str
    t: int
    events: List[str]
    classes: Optional[List[str]] = []
    confidence: float

class LogResponse(Model):
    success: bool
    message: str

class EmergencyContact(Model):
    contact_id: str
    phone: str
    name: str
    relationship: str = "caretaker"

class Registration(Model):
    client_id: str
    emergency_contacts: List[EmergencyContact]

class RegistrationResponse(Model):
    success: bool
    client_id: str
    contacts_registered: int
    message: str

# Supabase
class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }

    async def insert(self, table: str, data: dict, ctx: Context):
        import aiohttp
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.url}/rest/v1/{table}",
                    json=data,
                    headers=self.headers
                ) as resp:
                    if resp.status in [200, 201]:
                        return await resp.json()
                    else:
                        ctx.logger.error(f"DB error: {await resp.text()}")
                        return None
        except Exception as e:
            ctx.logger.error(f"DB exception: {e}")
            return None

# Agent - Railway uses PORT env variable
PORT = int(os.getenv("PORT", "8001"))
agent = Agent(
    name="PathSense_Ingest",
    seed=os.getenv("AGENT_SEED"),
    port=PORT,
)

db = SupabaseClient(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
WATCHDOG_ADDRESS = os.getenv("WATCHDOG_ADDRESS")

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"IngestAgent started: {agent.address}")
    ctx.logger.info(f"REST endpoints enabled")

# REST ENDPOINT: Registration
@agent.on_rest_post("/register", Registration, RegistrationResponse)
async def handle_rest_registration(ctx: Context, req: Registration) -> RegistrationResponse:
    try:
        ctx.logger.info(f"REST Registration: {req.client_id}")
        contacts_registered = 0

        for contact in req.emergency_contacts:
            data = {
                "client_id": req.client_id,
                "contact_id": contact.contact_id,
                "contact_name": contact.name,
                "contact_phone": contact.phone,
                "contact_email": None
            }
            if await db.insert("emergency_contacts", data, ctx):
                contacts_registered += 1
                ctx.logger.info(f"Registered: {contact.phone}")

        return RegistrationResponse(
            success=True,
            client_id=req.client_id,
            contacts_registered=contacts_registered,
            message=f"Registered {contacts_registered} contacts"
        )
    except Exception as e:
        ctx.logger.error(f"Registration error: {e}")
        return RegistrationResponse(
            success=False,
            client_id=req.client_id,
            contacts_registered=0,
            message=str(e)
        )

# REST ENDPOINT: Log Ingestion
@agent.on_rest_post("/ingest", NavigationLog, LogResponse)
async def handle_rest_log(ctx: Context, req: NavigationLog) -> LogResponse:
    try:
        ctx.logger.info(f"REST Log: {req.client_id} - {req.events}")

        # Save to DB
        log_data = {
            "client_id": req.client_id,
            "session_id": req.session_id,
            "t": req.t,
            "events": req.events,
            "classes": req.classes or [],
            "confidence": req.confidence
        }
        await db.insert("navigation_logs", log_data, ctx)

        # Forward to Watchdog
        if WATCHDOG_ADDRESS:
            await ctx.send(WATCHDOG_ADDRESS, req)

        return LogResponse(success=True, message="Log processed")
    except Exception as e:
        ctx.logger.error(f"Log error: {e}")
        return LogResponse(success=False, message=str(e))

# Agent message handlers (for agent-to-agent communication)
@agent.on_message(model=Registration)
async def handle_msg_registration(ctx: Context, sender: str, msg: Registration):
    result = await handle_rest_registration(ctx, msg)
    await ctx.send(sender, result)

@agent.on_message(model=NavigationLog)
async def handle_msg_log(ctx: Context, sender: str, msg: NavigationLog):
    result = await handle_rest_log(ctx, msg)
    await ctx.send(sender, result)

if __name__ == "__main__":
    agent.run()
