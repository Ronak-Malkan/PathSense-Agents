"""WatchdogAgent - Monitors logs for emergencies, sends SMS alerts"""
from uagents import Agent, Context, Model
import os
from typing import List, Optional, Dict
from collections import deque, defaultdict
from datetime import datetime, timezone
import time

# Models
class NavigationLog(Model):
    client_id: str
    session_id: str
    t: int
    events: List[str]
    classes: Optional[List[str]] = []
    confidence: float

# Supabase Client
class SupabaseClient:
    def __init__(self, url: str, key: str):
        if not url or not key:
            raise ValueError(f"Supabase credentials missing! URL: {url}, KEY: {'set' if key else 'missing'}")
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
                    return await resp.json() if resp.status in [200, 201] else None
        except: return None

    async def select(self, table: str, filters: dict, ctx: Context):
        import aiohttp
        try:
            params = "&".join([f"{k}=eq.{v}" for k, v in filters.items()])
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/rest/v1/{table}?{params}",
                    headers=self.headers
                ) as resp:
                    return await resp.json() if resp.status == 200 else []
        except: return []

# Agent
agent = Agent(
    name="PathSense_Watchdog",
    seed=os.getenv("AGENT_SEED"),
    port=8002,
)

# Initialize database with error checking
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL:
    print("ERROR: SUPABASE_URL environment variable not set!")
if not SUPABASE_KEY:
    print("ERROR: SUPABASE_KEY environment variable not set!")

db = SupabaseClient(SUPABASE_URL, SUPABASE_KEY)

# Cache
logs_cache: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
stuck_alerts: Dict[str, int] = {}
danger_alerts: Dict[str, int] = {}

CLEAR_EVENTS = {"CLEAR"}
STOP_EVENTS = {"STOP"}
STUCK_ALERT_S = 100
DANGER_STOP_COUNT = 10
DANGER_WINDOW_S = 60
DEBOUNCE_S = 300

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"WatchdogAgent started: {agent.address}")

@agent.on_message(model=NavigationLog)
async def handle_log(ctx: Context, sender: str, msg: NavigationLog):
    try:
        # Add to cache
        logs_cache[msg.client_id].append({
            "t": msg.t,
            "events": msg.events,
            "confidence": msg.confidence
        })

        # Check patterns
        if await check_stuck(ctx, msg.client_id):
            ctx.logger.warning(f"🚨 STUCK ALERT: {msg.client_id[:8]}...")

        if await check_danger_surge(ctx, msg.client_id):
            ctx.logger.warning(f"⚠️ DANGER SURGE: {msg.client_id[:8]}...")

    except Exception as e:
        ctx.logger.error(f"Monitoring error: {e}")

async def check_stuck(ctx: Context, client_id: str) -> bool:
    window = list(logs_cache[client_id])
    if len(window) < 10:
        return False

    now = int(time.time())
    last_clear_time = None
    for record in reversed(window):
        if any(e in CLEAR_EVENTS for e in record["events"]):
            last_clear_time = record["t"]
            break

    stuck_duration = now - (last_clear_time or window[0]["t"])

    if stuck_duration >= STUCK_ALERT_S:
        last_alert = stuck_alerts.get(client_id, 0)
        if now - last_alert >= DEBOUNCE_S:
            await send_alert(ctx, client_id, "stuck_alert",
                           f"User stuck for {stuck_duration}s - no clear path")
            stuck_alerts[client_id] = now
            return True
    return False

async def check_danger_surge(ctx: Context, client_id: str) -> bool:
    window = list(logs_cache[client_id])
    if len(window) < 10:
        return False

    now = int(time.time())
    cutoff = now - DANGER_WINDOW_S
    stop_count = sum(1 for r in reversed(window) if r["t"] >= cutoff and any(e in STOP_EVENTS for e in r["events"]))

    if stop_count >= DANGER_STOP_COUNT:
        last_alert = danger_alerts.get(client_id, 0)
        if now - last_alert >= DEBOUNCE_S:
            await send_alert(ctx, client_id, "danger_surge_alert",
                           f"Dangerous area: {stop_count} STOPs in {DANGER_WINDOW_S}s")
            danger_alerts[client_id] = now
            return True
    return False

async def send_alert(ctx: Context, client_id: str, alert_type: str, rationale: str):
    contacts = await db.select("emergency_contacts", {"client_id": client_id}, ctx)
    if not contacts:
        ctx.logger.error(f"No contacts for {client_id}")
        return

    now = int(time.time())

    # Save alert
    await db.insert("emergency_alerts", {
        "alert_type": alert_type,
        "client_id": client_id,
        "contact_id": contacts[0]["contact_id"],
        "t": now,
        "rationale": rationale,
        "severity": "high",
        "payload": {"type": alert_type}
    }, ctx)

    # Send SMS
    sms_provider = os.getenv("SMS_PROVIDER", "console").lower()
    for contact in contacts:
        phone = contact["contact_phone"]
        message = f"""🚨 PathSense ALERT

{rationale}

Time: {datetime.fromtimestamp(now, tz=timezone.utc).strftime('%I:%M %p')}

Please check on the user immediately."""

        if sms_provider == "textbelt":
            import aiohttp
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post('https://textbelt.com/text', json={
                        'phone': phone,
                        'message': message,
                        'key': os.getenv('TEXTBELT_API_KEY', 'textbelt')
                    }) as resp:
                        result = await resp.json()
                        if result.get('success'):
                            ctx.logger.info(f"✅ SMS sent to {phone}")
            except Exception as e:
                ctx.logger.error(f"SMS error: {e}")
        else:
            ctx.logger.info(f"[CONSOLE] SMS to {phone}: {rationale}")

if __name__ == "__main__":
    agent.run()
