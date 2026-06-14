"""
Empire AI · Predictive Revenue
Outreach Agent · SMS Sequences
================================

Three TCPA-compliant SMS sequences, each with a fixed touch schedule
and a mandatory "Reply STOP to opt out" footer on every outbound message.

Sequences
---------
1. storm_strike     — sent to a verified storm-affected property owner
                       Goal: get a callback or SMS reply → contractor dispatch
                       5 touches over 7 days

2. contractor_recruit — sent to a vetted roofing/contracting business
                        Goal: get them to accept dispatch terms
                        3 touches over 10 days

3. lead_nurture     — sent to a warm lead that didn't convert on storm_strike
                      Goal: stay present, learn what they actually need
                      4 touches over 14 days

Variables (filled by personalization.py at runtime; written as {{var}} here
so you can review the message copy in isolation):
  {{business_name}}    — recipient's business / property name
  {{contact_name}}     — first name of recipient (or empty)
  {{address}}          — street address of the property
  {{city}}, {{state}}  — geographic context
  {{event}}            — storm event description ("severe hail", "tornado")
  {{severity}}         — NWS severity tier ("Severe", "Extreme", "Catastrophic")
  {{asset_value}}      — estimated asset value as plain dollar string ("$1.2M")
  {{urgency}}          — 1-10 urgency score
  {{agent_name}}       — from /root/.env EMPIRE_SMS_PREFIX or default

Compliance
----------
Every outbound message must include the EMPIRE_SMS_PREFIX + " Reply STOP
to opt out" footer. compliance.py is the gate; this module is content only.
"""

# TCPA opt-out footer — required on EVERY outbound SMS.
# Prefix is set by the runtime; keep the suffix constant.
OPTOUT_FOOTER = "Reply STOP to opt out"

# ─────────────────────────────────────────────────────────────────────
# Sequence 1: storm_strike (property owner, 5 touches / 7 days)
# Triggered by: REVENUE_FLOW.md STEP 4 (brain returns GO + urgency >= 7)
# Goal: callback OR reply → manual contractor dispatch by you
# ─────────────────────────────────────────────────────────────────────

STORM_STRIKE = {
    "name": "storm_strike",
    "description": "5-touch sequence to a verified storm-affected property owner",
    "triggers_on": "radar_targets with urgency >= 7 AND is_lead_compliant=True AND not in sms_opt_outs",
    "step_count": 5,
    "schedule": [
        # (step, hours_after_enroll, body_template)
        (1, 0,   "Storm alert: a {event} just hit {address}, {city}. "
                 "We've documented {severity} damage in your area and have "
                 "vetted contractors ready to inspect. Want a free damage "
                 "assessment? Reply YES."),
        (2, 24,  "Following up: our contractors are in {city} right now "
                 "assessing {event} damage. If you reply YES today, we can "
                 "have someone on-site within 48 hours. No cost, no "
                 "obligation. Reply YES."),
        (3, 72,  "Quick check — saw the {event} damage reports near "
                 "{address}. Still want the free damage assessment? "
                 "Reply YES or STOP to opt out."),
        (4, 120, "Last note from us. If your property at {address} has "
                 "storm damage from the {event} and you'd like help with "
                 "the insurance process, reply YES. Otherwise no further "
                 "messages."),
        (5, 168, "Closing the loop on the {event} damage program in "
                 "{city}. If you ever need help with a future claim, "
                 "save this number. Take care."),
    ],
}

# ─────────────────────────────────────────────────────────────────────
# Sequence 2: contractor_recruit (contracting business, 3 touches / 10 days)
# Triggered by: manual addition to contractors table with status='prospect'
# Goal: get them to accept dispatch terms (1 real contractor closes step 1-6 of STARTING_POINT.md)
# ─────────────────────────────────────────────────────────────────────

CONTRACTOR_RECRUIT = {
    "name": "contractor_recruit",
    "description": "3-touch sequence to recruit a vetted contractor into the dispatch network",
    "triggers_on": "contractors table insert with status='prospect' and tcpa_consent=True",
    "step_count": 3,
    "schedule": [
        (1, 0,    "Hi {{contact_name}}, this is {agent_name} from Empire AI. "
                  "We run a predictive revenue engine that sends commercial "
                  "property owners directly to vetted contractors when "
                  "{event} damage hits. We pay a referral fee on every "
                  "settled insurance claim. Interested in 5 minutes?"),
        (2, 96,   "Following up on my note. We've got {urgency}/10 urgency "
                  "storm events live in {state} right now. If you can take "
                  "5 minutes, I can show you the lead flow and the fee "
                  "structure. Reply YES for a call."),
        (3, 240,  "Last note. We're onboarding 2-3 contractors per region per "
                  "month and we'd like you in {state}. If timing's bad, no "
                  "worries — just reply NOTNOW and we'll check back in Q4."),
    ],
}

# ─────────────────────────────────────────────────────────────────────
# Sequence 3: lead_nurture (didn't convert on storm_strike, 4 touches / 14 days)
# Triggered by: storm_strike sequence ends with no reply AND not opted out
# Goal: stay present, learn what they actually need
# ─────────────────────────────────────────────────────────────────────

LEAD_NURTURE = {
    "name": "lead_nurture",
    "description": "4-touch nurture sequence for storm_strike non-responders",
    "triggers_on": "storm_strike sequence status='completed' with replies_count=0",
    "step_count": 4,
    "schedule": [
        (1, 0,   "Hi, this is {agent_name} following up. The {event} in "
                 "{city} caused more damage than initially reported. If you "
                 "later find storm damage at {address}, save this number — "
                 "we work with vetted contractors and there's no cost to you."),
        (2, 72,  "Did the {event} in {city} end up causing any roof or "
                 "window damage at {address}? Even small leaks are worth "
                 "documenting for insurance. Reply DAMAGE for a free remote "
                 "assessment."),
        (3, 168, "Quick note: insurance companies are still processing "
                 "{event} claims in {state} from earlier this season. If "
                 "you filed one, we can connect you with a contractor who "
                 "specializes in that work. Reply CLAIM."),
        (4, 336, "Last note. We've added {city} to our active monitoring "
                 "list for the next storm season. If anything comes up, "
                 "you'll hear from us. Take care."),
    ],
}

ALL_SEQUENCES = {
    "storm_strike":       STORM_STRIKE,
    "contractor_recruit": CONTRACTOR_RECRUIT,
    "lead_nurture":       LEAD_NURTURE,
}


def get_sequence(name: str) -> dict:
    """Look up a sequence by name. Raises KeyError if unknown."""
    if name not in ALL_SEQUENCES:
        raise KeyError(f"unknown sequence: {name!r}. valid: {list(ALL_SEQUENCES)}")
    return ALL_SEQUENCES[name]


def get_message(sequence_name: str, step: int) -> str:
    """Get the message body for a specific sequence + step."""
    seq = get_sequence(sequence_name)
    for s, _hours, body in seq["schedule"]:
        if s == step:
            return body
    raise KeyError(f"sequence {sequence_name!r} has no step {step}")


def list_sequences() -> list[str]:
    return list(ALL_SEQUENCES.keys())
