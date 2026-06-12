import os
from dotenv import load_dotenv
load_dotenv('/root/.env')
from supabase import create_client
sb = create_client(os.environ['SUPABASE_URL'], os.environ['SUPABASE_SERVICE_KEY'])
r = sb.table('affiliate_links').select('code,buyer_id,label').limit(5).execute()
print("=== affiliate_links ===")
for row in (r.data or []):
    print(f"  Code: {row['code']}  Label: {row.get('label','')}")
first_id = str(r.data[0]['buyer_id']) if r.data else None
print(f"\nFirst buyer_id: {first_id}")
import subprocess, json
code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', 'http://localhost:8000/portal/affiliate/login'], capture_output=True, text=True)
print(f"Login page: HTTP {code.stdout}")
if first_id:
    code = subprocess.run(['curl', '-s', '-o', '/dev/null', '-w', '%{http_code}', f'http://localhost:8000/api/v1/affiliate/{first_id}/stats'], capture_output=True, text=True)
    print(f"Stats (unauthed): HTTP {code.stdout}")
hub_token = ""
for line in open('/root/.env'):
    if line.startswith('HUB_TOKEN='):
        hub_token = line.split('=', 1)[1].strip().strip('"').strip("'")
        break
if hub_token and first_id:
    code = subprocess.run(['curl', '-s', '-o', '/tmp/stats.json', '-w', '%{http_code}', '-H', f'Authorization: Bearer {hub_token}', f'http://localhost:8000/api/v1/affiliate/{first_id}/stats'], capture_output=True, text=True)
    print(f"Stats (authed): HTTP {code.stdout}")
    if code.stdout == '200':
        d = json.load(open('/tmp/stats.json'))
        print(f"  Response: {json.dumps(d, indent=2)[:400]}")
