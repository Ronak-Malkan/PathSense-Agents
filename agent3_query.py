"""QueryAgent - ASI:One chat interface for caretakers"""
from uagents import Agent, Context, Model
from ai_engine import UAgentResponse, UAgentResponseType
import os
from typing import Optional
from datetime import datetime, timezone

# Models
class CaretakerQuery(Model):
    """Ask about navigation activity"""
    query: str
    client_id: Optional[str] = None

# Supabase Client
class SupabaseClient:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json'
        }

    async def select(self, table: str, filters: dict, ctx: Context, limit: int = 10):
        import aiohttp
        try:
            params = "&".join([f"{k}=eq.{v}" for k, v in filters.items()])
            params += f"&limit={limit}&order=created_at.desc"
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.url}/rest/v1/{table}?{params}",
                    headers=self.headers
                ) as resp:
                    return await resp.json() if resp.status == 200 else []
        except: return []

# Agent
agent = Agent(
    name="PathSense_Query",
    seed=os.getenv("AGENT_SEED"),
    port=8003,
)

db = SupabaseClient(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))

@agent.on_event("startup")
async def startup(ctx: Context):
    ctx.logger.info(f"QueryAgent started: {agent.address}")
    ctx.logger.info("ASI:One chat enabled")

@agent.on_message(model=CaretakerQuery, replies=UAgentResponse)
async def handle_query(ctx: Context, sender: str, msg: CaretakerQuery):
    """Handle natural language queries from caretakers via DeltaV"""
    try:
        ctx.logger.info(f"Query: {msg.query}")

        query_lower = msg.query.lower()

        # Pattern matching for queries
        if any(word in query_lower for word in ["alert", "emergency", "danger", "problem"]):
            # Get recent alerts
            alerts = await db.select("emergency_alerts", {"client_id": msg.client_id} if msg.client_id else {}, ctx, limit=5)

            if not alerts:
                response = "✅ Great news! No recent emergency alerts. Everything is going smoothly."
            else:
                alert_list = []
                for alert in alerts[:3]:
                    time_str = datetime.fromtimestamp(alert['t'], tz=timezone.utc).strftime('%I:%M %p on %b %d')
                    alert_list.append(f"• {alert['alert_type'].replace('_', ' ').title()} at {time_str}\n  {alert['rationale']}")

                response = f"🚨 Found {len(alerts)} recent alerts:\n\n" + "\n\n".join(alert_list)

        elif any(word in query_lower for word in ["today", "recent", "last", "latest"]):
            # Get recent logs
            logs = await db.select("navigation_logs", {"client_id": msg.client_id} if msg.client_id else {}, ctx, limit=50)

            if not logs:
                response = "No recent navigation activity found."
            else:
                clear_count = sum(1 for log in logs if "CLEAR" in log.get('events', []))
                stop_count = sum(1 for log in logs if "STOP" in log.get('events', []))
                total = len(logs)

                response = f"""📊 Recent Navigation Summary:

Total logs: {total}
✅ Clear paths: {clear_count} ({clear_count*100//total if total > 0 else 0}%)
🛑 Stops: {stop_count} ({stop_count*100//total if total > 0 else 0}%)

Overall: {"Going well! Mostly clear paths." if clear_count > stop_count else "Some challenges encountered."}"""

        else:
            # General status
            alerts = await db.select("emergency_alerts", {"client_id": msg.client_id} if msg.client_id else {}, ctx, limit=1)
            logs = await db.select("navigation_logs", {"client_id": msg.client_id} if msg.client_id else {}, ctx, limit=1)

            if not logs:
                response = "No navigation data available yet."
            else:
                last_log_time = datetime.fromtimestamp(logs[0]['t'], tz=timezone.utc).strftime('%I:%M %p on %b %d')

                if alerts:
                    response = f"Last activity: {last_log_time}\n\n⚠️ There was 1 recent alert. Ask 'show recent alerts' for details."
                else:
                    response = f"Last activity: {last_log_time}\n\n✅ No recent alerts - everything looks good!"

        await ctx.send(sender, UAgentResponse(
            message=response,
            type=UAgentResponseType.FINAL
        ))

    except Exception as e:
        ctx.logger.error(f"Query error: {e}")
        await ctx.send(sender, UAgentResponse(
            message=f"Sorry, I encountered an error: {str(e)}",
            type=UAgentResponseType.ERROR
        ))

if __name__ == "__main__":
    agent.run()
