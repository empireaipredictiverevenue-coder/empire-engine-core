"""
Empire AI · Predictive Revenue
Outreach Agent
==================

Content layer of the outreach automation. Provides:
  - sms_sequences  : TCPA-compliant SMS copy for storm_strike, contractor_recruit, lead_nurture
  - voice_scripts  : phone scripts for initial_strike, followups, handoff, opt-out
  - compliance     : gates every send/call through DNC, opt-out, consent, time-of-day, rate

Runtime (NOT in this package, built separately when vonage auth is fixed):
  - dispatcher cron:  enrolls leads in sequences, fires next step on schedule
  - call router:     uses voice_scripts.get_script(name) and place_strike_call()

Everything in this package is reviewable offline. To preview a sequence:
    python3 -c "from agents.outreach import sms_sequences; print(sms_sequences.get_message('storm_strike', 1))"

To run a compliance dry-run check:
    python3 -c "from agents.outreach import compliance; print(compliance.can_send_sms('+12142277528', consent_flag=True, area_code='214'))"
"""

from . import sms_sequences
from . import voice_scripts
from . import compliance

__all__ = ["sms_sequences", "voice_scripts", "compliance"]
__version__ = "0.1.0"
