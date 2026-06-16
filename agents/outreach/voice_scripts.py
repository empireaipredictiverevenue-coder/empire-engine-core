"""
Empire AI · Predictive Revenue
Outreach Agent · Voice Scripts
================================

Phone scripts for the voice_router.place_strike_call() path.
Each script is a dict with:
  - name
  - max_duration_seconds (Vonage call budget; auto-hangup if exceeded)
  - intro (must identify as paid commercial within first 5 seconds — TCPA)
  - main (the actual pitch)
  - if_voicemail (leave a callback message)
  - opt_out_disclosure (must be said on every call)

All scripts identify as "Empire AI" (paid commercial identifier from
the EMPIRE_SMS_PREFIX env var) within the first sentence.

Variables: same {{var}} placeholder system as sms_sequences.py.
"""

# ─────────────────────────────────────────────────────────────────────
# Script 1: initial_strike (called when brain returns GO + urgency >= 7)
# Goal: confirm the lead is reachable + wants a contractor
# ─────────────────────────────────────────────────────────────────────

INITIAL_STRIKE = {
    "name": "initial_strike",
    "max_duration_seconds": 90,
    "intro": "Hi, this is a paid call from Empire AI on behalf of our "
             "vetted contractor network. May I speak with the property "
             "owner at {address}?",
    "main": "Hi {contact_name}, my name is {agent_name} with Empire AI. "
            "We've been monitoring severe weather in {city} and our "
            "system flagged your property at {address} for {event} damage. "
            "We've already vetted contractors in {city} who can do a free "
            "on-site damage assessment. There's no cost to you — we earn "
            "a small fee only if your insurance claim settles. "
            "Want me to have someone call you back within 24 hours?",
    "if_voicemail": "Hi, this is Empire AI calling about a {event} "
                    "damage report near {address} in {city}. We're "
                    "working with vetted local contractors and we'd "
                    "like to schedule a free damage assessment. Please "
                    "call us back at {callback_number}. That's Empire AI — "
                    "press 9 to opt out of future calls.",
    "opt_out_disclosure": "To opt out of future calls from Empire AI, "
                          "press 9 at any time or tell me now.",
}

# ─────────────────────────────────────────────────────────────────────
# Script 2: no_answer_followup (called 4 hours after initial_strike if no answer)
# Goal: leave voicemail with callback number
# ─────────────────────────────────────────────────────────────────────

NO_ANSWER_FOLLOWUP = {
    "name": "no_answer_followup",
    "max_duration_seconds": 45,
    "intro": None,  # voicemail only
    "main": None,
    "if_voicemail": "Hi, this is Empire AI. We're following up on a "
                    "{event} damage report for the property at "
                    "{address} in {city}. We work with vetted local "
                    "contractors and offer a free damage assessment. "
                    "Please call us back at {callback_number}. "
                    "Reply STOP to our last text to opt out, or press 9 "
                    "during our next call.",
    "opt_out_disclosure": "Reply STOP to our last text to opt out, or "
                          "press 9 during this call.",
}

# ─────────────────────────────────────────────────────────────────────
# Script 3: callback_confirmation (when lead calls back)
# Goal: verify identity, capture best time for contractor visit
# ─────────────────────────────────────────────────────────────────────

CALLBACK_CONFIRMATION = {
    "name": "callback_confirmation",
    "max_duration_seconds": 120,
    "intro": "Hi, this is Empire AI. Thanks for returning our call about "
             "the {event} damage report for {address} in {city}.",
    "main": "Great. I just need to confirm a few things: is this still "
            "your property, and is {contact_name} the right person to "
            "have on-site? ... Perfect. We have a vetted contractor in "
            "{city} who can be on-site for a free damage assessment on "
            "{proposed_window}. Does that work, or do you need a "
            "different time?",
    "if_voicemail": None,
    "opt_out_disclosure": "If you'd rather not receive any further calls, "
                          "just say so and we'll remove you immediately.",
}

# ─────────────────────────────────────────────────────────────────────
# Script 4: contractor_handoff (3-way: you, lead, contractor)
# Goal: warm-intro the contractor to the lead
# ─────────────────────────────────────────────────────────────────────

CONTRACTOR_HANDOFF = {
    "name": "contractor_handoff",
    "max_duration_seconds": 180,
    "intro": "Hi, this is Empire AI. I have {contractor_name} from "
             "{contractor_company} on the line with us. They're the "
             "vetted contractor we mentioned for the {event} damage at "
             "{address}.",
    "main": "Perfect. {contractor_name}, I'm handing off to you — "
            "{contact_name} is expecting your call about a free damage "
            "assessment for the {event} damage at {address} in {city}. "
            "{contact_name}, I'll drop off the line now and let "
            "{contractor_name} schedule with you directly. Empire AI "
            "will follow up after the assessment to make sure everything "
            "went well.",
    "if_voicemail": None,
    "opt_out_disclosure": "If at any point you'd like to stop receiving "
                          "calls from Empire AI, just say so.",
}

# ─────────────────────────────────────────────────────────────────────
# Script 5: opt_out_confirmation (called when lead says "stop" or "remove me")
# Goal: confirm removal, set expectation, comply with TCPA immediately
# ─────────────────────────────────────────────────────────────────────

OPT_OUT_CONFIRMATION = {
    "name": "opt_out_confirmation",
    "max_duration_seconds": 30,
    "intro": "Hi, this is Empire AI. I'm calling to confirm your request "
             "to be removed from our contact list.",
    "main": "You're confirmed removed. We won't call or text this number "
            "again. Sorry for the interruption. Take care.",
    "if_voicemail": "Hi, this is Empire AI confirming your opt-out. "
                    "This number is now on our do-not-contact list. "
                    "No further calls or texts. Take care.",
    "opt_out_disclosure": "You are now on our do-not-contact list. "
                          "No further calls or texts will be made to "
                          "this number.",
}

# ─────────────────────────────────────────────────────────────────────
# Script 6: contractor_recruit (outbound call to recruit a contractor)
# Goal: 90-sec pitch, get the contractor to self-onboard at empire-ai.co.uk
# Used by: contractor_outreach agent (manual call CLI for now)
# ─────────────────────────────────────────────────────────────────────

CONTRACTOR_RECRUIT = {
    "name": "contractor_recruit",
    "max_duration_seconds": 90,
    # TCPA-required: identify as paid commercial within first 5 seconds
    "intro": "Hi {first_name}, this is a paid call from Empire AI on behalf "
             "of our contractor network. Got 30 seconds?",
    "main": "I'm calling roofers in {metro} because we just started routing "
            "storm leads into this market — and you came up as one of the "
            "top local contractors. Quick version: we send you pre-qualified "
            "storm leads, you close them, you pay us 3% only when the "
            "insurance claim settles. First 2 closed deals are 100% on us, "
            "no fee, no contract. Most contractors who try it close their "
            "first deal within 30 days. You can self-onboard in 90 seconds "
            "at empire-ai.co.uk/contractors — no call needed to sign up. "
            "Worth a look?",
    # If voicemail — leave short callback with the link. Don't repeat pitch.
    "if_voicemail": "Hi {first_name}, this is Empire AI — a quick note for "
                    "your roofing business in {metro}. We send storm leads, "
                    "you close them, 3% fee only on settled claims, first 2 "
                    "deals on us. Self-onboard at empire-ai.co.uk/contractors. "
                    "Press 9 to opt out of future calls.",
    "opt_out_disclosure": "To opt out of future calls from Empire AI, "
                          "press 9 at any time or tell me now.",
}

ALL_SCRIPTS = {
    "initial_strike":         INITIAL_STRIKE,
    "no_answer_followup":     NO_ANSWER_FOLLOWUP,
    "callback_confirmation":  CALLBACK_CONFIRMATION,
    "contractor_handoff":     CONTRACTOR_HANDOFF,
    "opt_out_confirmation":   OPT_OUT_CONFIRMATION,
    "contractor_recruit":     CONTRACTOR_RECRUIT,
}


def get_script(name: str) -> dict:
    if name not in ALL_SCRIPTS:
        raise KeyError(f"unknown script: {name!r}. valid: {list(ALL_SCRIPTS)}")
    return ALL_SCRIPTS[name]
