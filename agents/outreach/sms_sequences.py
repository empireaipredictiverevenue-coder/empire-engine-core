"""
Empire AI · Predictive Revenue
Outreach Agent · SMS Sequences
================================

Eight TCPA-compliant SMS sequences, each with a fixed touch schedule
and "STOP to opt out" on every outbound message.

Sequences
---------
1. storm_strike        — storm-affected property owner, 5 touches / 7 days
2. contractor_recruit  — recruiting contractors into dispatch, 3 touches / 10 days
3. lead_nurture        — warm leads that didn't convert, 4 touches / 14 days
4. b2b_outreach        — B2B service providers, 4 touches / 10 days
5. commercial_roofing  — commercial property roof inspection, 5 touches / 7 days
6. commercial_solar    — commercial solar install, 5 touches / 7 days
7. debt_relief         — debt relief prospects, 5 touches / 7 days
8. legal_mass_tort     — legal case claimants (5 sub-niches), 4 touches / 10 days

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
        (1, 0,    "{prefix} We pay contractors a 3% referral fee on every "
                  "settled insurance claim — and your first 2 closed deals "
                  "are 100% complimentary. No fee, no contract, no call needed. "
                  "See the offer, watch the 2-min demo, and self-onboard at "
                  "empire-ai.co.uk/contractors. Reply STOP to opt out."),
        (2, 96,   "{prefix} Quick follow-up — we added a live demo on the page "
                  "so you can see the lead flow before deciding. Qualified, "
                  "storm-affected commercial properties delivered to your "
                  "dispatch queue. You only pay when the claim settles. "
                  "First 2 deals on us. empire-ai.co.uk/contractors"),
        (3, 240,  "{prefix} Closing note. If the timing's wrong, reply NOTNOW "
                  "and we'll check back next quarter. No chase. To test with "
                  "a free deal first, self-onboard at "
                  "empire-ai.co.uk/contractors — 90 seconds, no call needed. "
                  "First 2 closed deals are 100% complimentary. "
                  "Reply STOP to opt out."),
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

# ─────────────────────────────────────────────────────────────────────
# Sequence 4: b2b_outreach (Managed IT / Merchant Services / HR & Staffing, 4 touches / 10 days)
# Triggered by: B2B lead scraped with phone number AND email
# Goal: get them to reply YES and explore lead generation partnership
# ─────────────────────────────────────────────────────────────────────

B2B_OUTREACH = {
    "name": "b2b_outreach",
    "description": "4-touch sequence for B2B service providers (Managed IT, Merchant Services, HR & Staffing)",
    "triggers_on": "radar_targets with meta->>source='B2B Lead Gen' AND phone IS NOT NULL AND email IS NOT NULL",
    "step_count": 4,
    "schedule": [
        (1, 0,    "{prefix} We send qualified leads to {target_short} — "
                  "Managed IT / business service providers. Reply YES for "
                  "a free sample lead. STOP to opt out."),
        (2, 24,   "{prefix} {target_short}, you pay our 3% success fee "
                  "only on closed deals. No retainer, no minimum. "
                  "Reply YES. STOP to opt out."),
        (3, 72,   "{prefix} {target_short}, we can send a sample lead "
                  "matching your service profile today. No cost, no "
                  "obligation. Reply YES. STOP to opt out."),
        (4, 168,  "{prefix} Last note for {target_short}. If timing is "
                  "right, reply YES anytime. STOP to opt out."),
    ],
}

# ─────────────────────────────────────────────────────────────────────
# Sequence 5: commercial_roofing (Commercial Roofing, 5 touches / 7 days)
# Triggered by: radar_targets with b2b_sub_niche=Commercial Roofing
# Goal: get them to reply YES for a free commercial roof inspection
# ─────────────────────────────────────────────────────────────────────

COMMERCIAL_ROOFING = {
    "name": "commercial_roofing",
    "description": "5-touch sequence for commercial property owners — storm-triggered roof inspection angle",
    "triggers_on": "radar_targets with meta->>b2b_sub_niche='Commercial Roofing' AND phone IS NOT NULL",
    "step_count": 5,
    "schedule": [
        (1, 0,   "{prefix} Storm damage flagged at {target_short}. "
                 "We dispatch vetted commercial roof inspectors — "
                 "no cost unless claim settles. Reply YES. STOP to opt out."),
        (2, 24,  "{prefix} Commercial policies have a 72-hr filing window "
                 "after severe weather. Reply YES to dispatch an adjuster. "
                 "STOP to opt out."),
        (3, 72,  "{prefix} If the inspector finds no structural damage, "
                 "there's no charge. We only earn on settled claims. "
                 "Reply YES. STOP to opt out."),
        (4, 120, "{prefix} A $200K commercial roof settlement = "
                 "$6,000 to you, $6,000 to us. We earn what you earn. "
                 "Reply YES. STOP to opt out."),
        (5, 168, "{prefix} Final note for {target_short}. Reply YES for a "
                 "no-cost commercial roof assessment. Otherwise we won't "
                 "message again. STOP to opt out."),
    ],
}

# ─────────────────────────────────────────────────────────────────────
# Sequence 6: commercial_solar (Commercial Solar, 5 touches / 7 days)
# Triggered by: radar_targets with b2b_sub_niche=Commercial Solar
# Goal: get them to reply YES for a free solar savings estimate
# ─────────────────────────────────────────────────────────────────────

COMMERCIAL_SOLAR = {
    "name": "commercial_solar",
    "description": "5-touch sequence for commercial properties — solar federal tax credit angle",
    "triggers_on": "radar_targets with meta->>b2b_sub_niche='Commercial Solar' AND phone IS NOT NULL",
    "step_count": 5,
    "schedule": [
        (1, 0,   "{prefix} Commercial solar for {target_short} — "
                 "federal tax credits cover 30% of install. "
                 "We handle the paperwork. Reply YES. STOP to opt out."),
        (2, 24,  "{prefix} Most commercial properties in your area "
                 "qualify for solar with $0 down. PPA financing available. "
                 "Reply YES for a free savings estimate. STOP to opt out."),
        (3, 72,  "{prefix} {target_short}, commercial electricity rates "
                 "are up 22% YoY. Solar locks in your rate for 25 years. "
                 "Reply YES. STOP to opt out."),
        (4, 120, "{prefix} Other commercial properties in your area "
                 "are installing solar ahead of the 2027 tariff step-down. "
                 "Reply YES to see if you qualify. STOP to opt out."),
        (5, 168, "{prefix} Last note for {target_short}. If solar makes "
                 "sense for your property, reply YES for a free quote. "
                 "Otherwise we won't reach out again. STOP to opt out."),
    ],
}

# ─────────────────────────────────────────────────────────────────────
# Sequence 7: debt_relief (Debt Relief, 5 touches / 7 days)
# Triggered by: radar_targets with b2b_sub_niche=Debt Relief
# Goal: get them to reply YES for a free debt consultation
# ─────────────────────────────────────────────────────────────────────

DEBT_RELIEF = {
    "name": "debt_relief",
    "description": "5-touch sequence for debt relief prospects — settlement program angle",
    "triggers_on": "radar_targets with meta->>b2b_sub_niche='Debt Relief' AND phone IS NOT NULL",
    "step_count": 5,
    "schedule": [
        (1, 0,   "{prefix} Debt relief options available in your area — "
                 "we negotiate with creditors to reduce balances. "
                 "No upfront fees. Reply YES. STOP to opt out."),
        (2, 24,  "{prefix} Most clients see 40-60% reduction on "
                 "unsecured debt through our settlement program. "
                 "Free consultation. Reply YES. STOP to opt out."),
        (3, 72,  "{prefix} {target_short}, credit card interest "
                 "averages 24% APR. Our program stops interest "
                 "and consolidates debt. Reply YES. STOP to opt out."),
        (4, 120, "{prefix} Typical debt resolution takes 24-48 months. "
                 "First settlement often happens within 90 days. "
                 "No obligation to start. Reply YES. STOP to opt out."),
        (5, 168, "{prefix} Final note. If debt relief could help "
                 "your situation, reply YES for a free consultation. "
                 "Otherwise we won't reach out again. STOP to opt out."),
    ],
}


# ─────────────────────────────────────────────────────────────────────
# Sequence 8: legal_mass_tort (legal claimants, 4 touches / 10 days)
# Triggered by: radar_targets with niche in {pharma_liability, medical_device,
#               consumer_product, class_action, mass_tort} AND phone IS NOT NULL
# Goal: get them to reply YES for a free case review by the matching legal buyer
# Added 2026-06-17. 5 buyers in `buyers` table are PENDING placeholders
# (sub_niche=Pharma Liability / Medical Device / Consumer Product / Class Action /
# Mass Tort) — Phil recruits real buyers; until is_active=True and
# destination_phone is set, the lead_converter routes to this sequence
# but no real dispatch happens. Conservative TCPA angle.
# ─────────────────────────────────────────────────────────────────────

LEGAL_MASS_TORT = {
    "name": "legal_mass_tort",
    "description": "4-touch sequence for legal case claimants across 5 sub-niches (Pharma Liability, Medical Device, Consumer Product, Class Action, Mass Tort)",
    "triggers_on": "radar_targets with niche in {pharma_liability, medical_device, consumer_product, class_action, mass_tort} AND phone IS NOT NULL",
    "step_count": 4,
    "schedule": [
        (1, 0,   "{prefix} Legal case review available for {target_short}. "
                 "No cost unless you win. Reply YES. STOP to opt out."),
        (2, 48,  "{prefix} {target_short}, we work with vetted law firms. "
                 "Free case review, no obligation. Reply YES. STOP to opt out."),
        (3, 120, "{prefix} Most claimants in {state} qualify for a free case "
                 "review. Reply YES for a callback within 24 hours. STOP to opt out."),
        (4, 240, "{prefix} Last note. {target_short} — if a legal case review "
                 "could help, reply YES. Otherwise we won't message again. STOP to opt out."),
    ],
}


ALL_SEQUENCES = {
    "storm_strike":       STORM_STRIKE,
    "contractor_recruit": CONTRACTOR_RECRUIT,
    "lead_nurture":       LEAD_NURTURE,
    "b2b_outreach":       B2B_OUTREACH,
    "commercial_roofing": COMMERCIAL_ROOFING,
    "commercial_solar":   COMMERCIAL_SOLAR,
    "debt_relief":        DEBT_RELIEF,
    "legal_mass_tort":    LEGAL_MASS_TORT,
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
