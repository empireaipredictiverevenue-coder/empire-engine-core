from supabase import create_client
import os
from datetime import datetime, timezone, timedelta

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

r = sb.table("outreach_log").select("response_text").eq("channel", "email").gte("created_at", since).execute()
replies = [row for row in r.data if row.get("response_text")]
print(f"Email replies (last 7d): {len(replies)}")
