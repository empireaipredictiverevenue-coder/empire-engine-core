"""
Empire AI · Carrier Outreach Drafts
====================================

DRAFT outreach emails to major insurance carriers asking about
partner API access for settled-claim events. Empire AI's revenue
model depends on knowing when a claim has settled (3% of claim
amount). The dispatcher routes leads to contractors, contractors
work claims with homeowners, but Empire AI needs the "claim settled"
signal from the carrier to know when to collect.

These are DRAFTS only — they need to be reviewed by the operator
before sending. The agent writes them to a `carrier_outreach_drafts`
directory + log entries in agent_activity.

To send them, the operator reviews and clicks "send" in their email
client. We don't auto-send because:
  1. Cold outreach to enterprise insurance is a relationship play,
     not a volume play
  2. The carrier's API access process usually requires NDAs, vendor
     approvals, and legal review before any real traffic flows
  3. We want the operator to add a personal touch + sign-off

Target carriers (top 5 by US homeowners market share):
  1. State Farm      (largest, private, no public partner API)
  2. Allstate        (public, partner program exists for vendors)
  3. USAA            (private, partner program)
  4. Liberty Mutual  (private, partner program)
  5. Farmers         (private, partner program)
"""
import os, json, sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

import uuid
from supabase import create_client

OUTREACH_DIR = Path("/root/empire-v49/carrier_outreach_drafts")


DRAFTS = [
    {
        "to": "partners@statefarm.com",
        "carrier": "State Farm",
        "subject": "Partner API inquiry: settled-claim event notifications for predictive storm response",
        "body": """Hi State Farm Partnerships team,

I'm Phil, founder of Empire AI. We help homeowners file and settle
storm-damage claims faster by connecting them with vetted local
contractors in the immediate post-storm window (typically 72 hours).

Our revenue model: 3% of the settled claim amount, paid only when
a claim settles. This means we have a strong financial incentive to
connect you with claims that will settle, and to ensure those claims
settle at fair market value.

To make this work, we need a webhook or polling API for settled-claim
events. The minimal data we need:
  - Claim ID
  - Settlement date
  - Settled amount (USD)
  - Property address (city + state is enough; full address is optional)
  - Filing party (contractor name if available)

We don't need claimant PII, payment data, or any sensitive information.
We just need a "this claim is done" signal so we can invoice the 3%.

Currently we're working with a mock carrier API for development, and
we'd love to swap that for a real integration. Are partner integrations
something State Farm offers, and if so, who do we talk to?

We have a working hub at empire-ai.co.uk and a real contractor network
in Texas, Oklahoma, and Louisiana. Our first paid fee event was
recorded last week.

If a partner program isn't the right channel, I'm also happy to take
a meeting to discuss the model.

Best,
Phil
Empire AI
phil@empire-ai.co.uk""",
    },
    {
        "to": "vendorpartners@allstate.com",
        "carrier": "Allstate",
        "subject": "Vendor partner inquiry: settled-claim webhook for predictive contractor routing",
        "body": """Hi Allstate Vendor Partners team,

I'm Phil, founder of Empire AI. We operate a predictive storm-response
network that connects homeowners in the 72-hour post-storm window with
vetted local contractors. We collect 3% of the settled claim as our fee.

We currently ingest storm data, score properties, and route leads to
contractors in 11 metros across TX/OK/LA/KS. Our first fee event was
recorded last week. The model is working.

The next step is integrating with carrier claims systems. For Allstate
specifically, is there a vendor partner program that gives us access
to settled-claim events? We need:
  - Claim ID, settlement date, settled amount
  - Property address (city + state is sufficient)
  - Optionally: filing party / contractor name

We don't need claimant PII, payment data, or anything sensitive. Just
the "claim settled" signal so we know to invoice our 3%.

If a vendor partner program exists, who do we contact? If it doesn't
yet exist, I'm happy to schedule a call to walk through what we'd
build together.

Best,
Phil
Empire AI
phil@empire-ai.co.uk""",
    },
    {
        "to": "partnerships@usaa.com",
        "carrier": "USAA",
        "subject": "Partner inquiry: settled-claim event feed for storm-damage contractor routing",
        "body": """Hi USAA Partnerships team,

I'm Phil, founder of Empire AI. We help homeowners with storm-damage
claims find vetted local contractors in the 72-hour post-storm window.
Our fee is 3% of the settled claim amount, paid only on settlement.

To scale this we need carrier-level visibility into settled-claim
events. We're currently running with a mock carrier API and our first
fee event was recorded last week. Real carrier integration is the
next step.

Does USAA have a partner program that exposes settled-claim
notifications? The minimum data we need:
  - Claim ID
  - Settlement date and amount
  - Property city + state

We're not looking for claimant PII or payment data. Just the "claim
settled" signal so we can invoice our 3%.

Best,
Phil
Empire AI
phil@empire-ai.co.uk""",
    },
    {
        "to": "partners@libertymutual.com",
        "carrier": "Liberty Mutual",
        "subject": "Partner API inquiry: settled-claim event notifications",
        "body": """Hi Liberty Mutual Partners team,

I'm Phil, founder of Empire AI. We connect homeowners with vetted
local contractors in the 72-hour post-storm window. We earn 3% of
the settled claim amount, paid only on settlement.

To scale we need a settled-claim event feed from carriers. We have
a working system with a mock carrier API and our first fee event
was recorded last week. We'd love to integrate with Liberty Mutual.

The minimum data: claim ID, settlement date, settled amount, property
city + state. No PII or payment data needed.

If a partner program exists, who do we contact?

Best,
Phil
Empire AI
phil@empire-ai.co.uk""",
    },
    {
        "to": "partners@farmers.com",
        "carrier": "Farmers",
        "subject": "Partner inquiry: settled-claim event notifications for predictive contractor routing",
        "body": """Hi Farmers Partners team,

I'm Phil, founder of Empire AI. We help homeowners with storm-damage
claims find vetted local contractors in the 72-hour post-storm
window. Our fee is 3% of the settled claim, paid only on settlement.

We have a working system with mock carrier data, and our first fee
event was recorded last week. Real carrier integration is the next
step.

We need a settled-claim event feed: claim ID, settlement date,
settled amount, property city + state. No PII or payment data.

If Farmers has a partner program, who do we contact?

Best,
Phil
Empire AI
phil@empire-ai.co.uk""",
    },
]


def write_drafts():
    OUTREACH_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for d in DRAFTS:
        path = OUTREACH_DIR / f"{d['carrier'].replace(' ', '_').lower()}.txt"
        with open(path, "w") as f:
            f.write(f"To: {d['to']}\n")
            f.write(f"From: phil@empire-ai.co.uk\n")
            f.write(f"Subject: {d['subject']}\n")
            f.write(f"Carrier: {d['carrier']}\n")
            f.write(f"Status: DRAFT — review before sending\n")
            f.write("=" * 70 + "\n\n")
            f.write(d["body"])
        written.append({"carrier": d["carrier"], "path": str(path), "to": d["to"]})
    return written


def log_to_activity(drafts):
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
    sb.table("agent_activity").insert({
        "agent_name": "carrier_outreach_drafts",
        "run_id": str(uuid.uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "status": "ok",
        "rows_seen": 0,
        "rows_processed": len(drafts),
        "rows_errored": 0,
        "error": None,
        "summary": f"carrier_outreach_drafts: wrote {len(drafts)} DRAFT emails to {OUTREACH_DIR}",
        "meta": {
            "drafts": [{"carrier": d["carrier"], "to": d["to"]} for d in drafts],
        },
    }).execute()


def main():
    drafts = write_drafts()
    print(f"wrote {len(drafts)} drafts to {OUTREACH_DIR}")
    for d in drafts:
        print(f"  - {d['carrier']:20s}  -> {d['path']}")
    log_to_activity(drafts)
    print("\n*** These are DRAFTS. Review before sending. ***")


if __name__ == "__main__":
    main()
