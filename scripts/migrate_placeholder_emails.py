"""
Migrate synthetic emails (slug -> phone). One-shot, idempotent.

Uses the python-postgrest upsert with a list of {id, email} dicts, batched
100 at a time. ~10 round-trips for 952 rows.
"""
import os, re
from supabase import create_client
from collections import Counter

env = open("/root/.env").read()
kv = {}
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|$)', env, re.MULTILINE | re.DOTALL):
    kv[m.group(1)] = m.group(2)
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)=([^\n#"]+)$', env, re.MULTILINE):
    k = m.group(1)
    if k not in kv:
        kv[k] = m.group(2).strip()
os.environ.update(kv)

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

OLD_PREFIX = "unknown."
OLD_SUFFIX = "@prospector.placeholder"

print("=== snapshot ===")
all_rows = []
offset = 0
batch = 1000
while True:
    r = (sb.table("contractors")
           .select("id,phone,email")
           .like("email", f"{OLD_PREFIX}%{OLD_SUFFIX}")
           .range(offset, offset + batch - 1)
           .execute())
    rows = r.data or []
    if not rows:
        break
    all_rows.extend(rows)
    if len(rows) < batch:
        break
    offset += batch
print(f"  {len(all_rows)} rows with old synthetic email")

old_dupes = Counter(row["email"] for row in all_rows)
print(f"  old-email dup groups: {len({e:n for e,n in old_dupes.items() if n>1})}")

plan = []
for row in all_rows:
    phone = (row.get("phone") or "").strip()
    digits = "".join(c for c in phone if c.isdigit())
    new_email = f"{OLD_PREFIX}{digits}{OLD_SUFFIX}" if digits else None
    plan.append({"id": row["id"], "phone": phone, "old_email": row["email"], "new_email": new_email})

new_dupes = Counter(p["new_email"] for p in plan if p["new_email"])
new_dup_groups = {e:n for e,n in new_dupes.items() if n>1}
print(f"  new-email dup groups: {len(new_dup_groups)}")
if new_dup_groups:
    print("  ABORT: new emails would still collide. Examples:")
    for e, n in list(new_dup_groups.items())[:5]:
        print(f"    {e}: {n} rows (phones below)")
        for p in plan:
            if p["new_email"] == e:
                print(f"      id={p['id'][:8]} phone={p['phone']}")
    raise SystemExit(1)

# Filter to only ones that need an update
to_update = [p for p in plan if p["new_email"] and p["new_email"] != p["old_email"]]
print(f"  to update: {len(to_update)} (others already on new scheme or no phone)")

# Upsert in batches of 100
print("=== upsert ===")
total = 0
errs = 0
for i in range(0, len(to_update), 100):
    chunk = [{"id": p["id"], "email": p["new_email"]} for p in to_update[i:i+100]]
    try:
        # upsert requires merge-duplicate handling; on id PK conflicts it overwrites
        sb.table("contractors").upsert(chunk, on_conflict="id").execute()
        total += len(chunk)
    except Exception as e:
        errs += 1
        print(f"  err chunk {i}-{i+100}: {type(e).__name__}: {e}")
    if (i // 100) % 2 == 0:
        print(f"  ...{total}/{len(to_update)}")

print(f"\nresult: updated={total} errors={errs}")

# Verify
print("\n=== verify ===")
r = sb.table("contractors").select("id", count="exact").like("email", f"{OLD_PREFIX}%{OLD_SUFFIX}").execute()
print(f"  rows still on old slug scheme: {r.count}")
# Sample 5 new ones
r = sb.table("contractors").select("id,phone,email,meta").like("email", f"{OLD_PREFIX}1%{OLD_SUFFIX}").limit(3).execute()
for row in r.data:
    print(f"  sample: {row['email']} phone={row['phone']} name={(row.get('meta') or {}).get('prospect_niche') or '?'}")
