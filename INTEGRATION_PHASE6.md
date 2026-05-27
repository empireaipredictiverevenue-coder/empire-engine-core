EMPIRE V49 · PHASE 6 INTEGRATION
==================================
The Sovereign Console + Brain Learning Loop. Voice/text command bar that
sits inside the existing Empire UI. Type or speak → Claude routes →
operator confirms (for destructive) → action fires.

THIS IS PART 1 OF THE "BEAT THE COMPETITORS" PUSH
─────────────────────────────────────────────────
After this, two more things ship:

  Part 2: Bridge (full-screen voice-first experience) · next session
  Part 3: Pulse (the insight layer that shows ROI per dimension) · later


───────────────────────────────────────────────────────────────────────────────
WHAT'S NEW IN PHASE 6
───────────────────────────────────────────────────────────────────────────────

  empire_brain_memory.py     pgvector-backed memory of past decisions
                             → record_decision() on every brain call
                             → retrieve_similar() before each new call
                             → attach_outcome() when claims resolve
                             → few-shot context injected into brain prompt

  empire_brain_learning.py   Nightly threshold auto-tuner
                             → analyzes outcomes by (city, severity, asset band)
                             → finds optimal urgency floor per bucket
                             → writes to brain_config table
                             → brain reads tuned thresholds at runtime

  empire_console.py          Voice + text command bar (Cmd+K)
                             → 17 registered actions
                             → 9 informational (instant execute)
                             → 8 destructive (require confirmation)
                             → role-based action filtering
                             → Web Speech API voice input
                             → cinematic Empire-brand UI


───────────────────────────────────────────────────────────────────────────────
WHY THE CONSOLE IS SAFE BY DESIGN
───────────────────────────────────────────────────────────────────────────────

The console is the most dangerous module in the build. A misheard voice
command could approve a payout, send 500 SMSes, or invite the wrong
person to your team. Safety is baked in at four layers:

  1. BOUNDED ACTION SET · the LLM CAN'T invent new actions. It can only
     pick from the 17 registered ones. Inventing a freeform action returns
     {action: null, explanation: "..."}.

  2. SCHEMA-VALIDATED PARAMS · each action declares its param types and
     required fields. Missing/wrong params fail before execution.

  3. ROLE FILTERING · the LLM only sees actions allowed for the operator's
     role. A viewer can't even ASK the system to approve a payout — the
     option doesn't appear in its action menu.

  4. MANDATORY CONFIRMATION · every destructive action returns a preview
     card showing the action name, parameters, and a Confirm button.
     The operator must click/press Enter. There is NO direct-fire path
     for destructive actions, regardless of how confident the LLM is.

This matches how Cursor, Linear, and Notion handle destructive AI actions.


───────────────────────────────────────────────────────────────────────────────
SUPABASE SCHEMA · already in deploy/schema.sql
───────────────────────────────────────────────────────────────────────────────

Phase 5 tables (brain_memory + brain_config + match_brain_memory RPC) are
already in the master schema.sql. The console doesn't add new tables — it
only READs existing ones and CALLs existing endpoints.


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py — Phase 5 (brain learning)
───────────────────────────────────────────────────────────────────────────────

Add the imports:

    from empire_brain_memory   import BrainMemory, render_few_shot
    from empire_brain_learning import BrainLearning, asset_to_band

Initialize after the other engines:

    brain_memory = BrainMemory(
        get_db=          get_db,
        openai_key=      os.environ.get("OPENAI_API_KEY", ""),
        embedding_model="text-embedding-3-small",
    )

    brain_learning = BrainLearning(get_db=get_db)

In the @app.on_event("startup") handler, add:

    # Phase 5 · nightly brain tuner
    asyncio.create_task(brain_learning.nightly_tune_loop())

In the brain evaluation path (inside _subconscious_cycle, just before
calling Claude), inject memory:

    # Phase 5 · pull similar past leads for few-shot calibration
    similar = await brain_memory.retrieve_similar(
        address=     p["address"],
        city=        p["city"],
        severity=    severity,
        asset_value= asset_val_num,
        urgency_signal=alert.get("event", ""),
        k=5,
    )
    memory_context = render_few_shot(similar)

    # Pull the tuned urgency floor for this bucket
    urgency_floor = await brain_learning.get_urgency_floor(
        city=        p["city"],
        severity=    severity,
        asset_value= asset_val_num,
    )

    # Include memory_context in the brain prompt's user message
    prompt = build_brain_prompt(
        target= p,
        alert=  alert,
        memory_context= memory_context,        # NEW
        urgency_floor=  urgency_floor,         # NEW · was hardcoded BRAIN_MIN_URGENCY
    )

    # ... call Claude as before ...

AFTER Claude returns the analysis, record the decision:

    memory_id = await brain_memory.record_decision(
        lead_id=     str(p.get("id", "")),
        decision=    analysis["decision"],
        urgency=     analysis.get("urgency", 0),
        reasoning=   analysis.get("reasoning", ""),
        address=     p["address"],
        city=        p["city"],
        severity=    severity,
        asset_value= asset_val_num,
    )

In your existing /api/v1/record-outcome endpoint, after persisting the
claim_outcomes row, link it back to brain_memory:

    await brain_memory.attach_outcome(
        lead_id=    outcome.get("lead_id"),
        outcome=    outcome["outcome"],
        actual_fee= float(outcome.get("actual_fee") or 0),
    )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP IN hub.py — Phase 6 (Sovereign Console)
───────────────────────────────────────────────────────────────────────────────

Add the imports:

    from empire_console import (
        SovereignConsole,
        register_console_routes,
        CONSOLE_CLIENT_JS,
    )

Initialize:

    console = SovereignConsole(
        anthropic_key= os.environ.get("ANTHROPIC_API_KEY", ""),
        get_db=        get_db,
        model=         "claude-sonnet-4-6",   # or your preferred model
    )

    register_console_routes(
        app,
        console=      console,
        require_auth= require_auth,
        get_db=       get_db,
    )


───────────────────────────────────────────────────────────────────────────────
WIRE-UP — inject the Cmd+K bar into every operator page
───────────────────────────────────────────────────────────────────────────────

In empire_layout.py, find the `_shell_js()` function. AT THE END of the
returned string, before the closing `"""`, add:

    """ + CONSOLE_CLIENT_JS

So the bottom of `_shell_js()` looks like:

    def _shell_js() -> str:
        """JavaScript for live clock + AGI status + ticker refresh."""
        return """
        <script>
        (function() { ... existing code ... })();
        </script>
        """ + CONSOLE_CLIENT_JS    # ← NEW

Then at the TOP of empire_layout.py, add the import:

    from empire_console import CONSOLE_CLIENT_JS

Now every page rendered through base_layout() has the Cmd+K bar.


───────────────────────────────────────────────────────────────────────────────
ENVIRONMENT VARIABLES
───────────────────────────────────────────────────────────────────────────────

Phase 5 requires:

    OPENAI_API_KEY              for embeddings (Phase 5 memory) +
                                Whisper voicemail transcription (Phase 4)

Phase 6 requires:

    ANTHROPIC_API_KEY           (already set · the console uses Claude)

No new variables. Both phases reuse keys you already have.


───────────────────────────────────────────────────────────────────────────────
SAMPLE COMMANDS TO TRY
───────────────────────────────────────────────────────────────────────────────

After deploy, sign in, press Cmd+K (or Ctrl+K on Windows/Linux) and try:

  INFORMATIONAL (execute immediately):
    "show me hottest leads in Dallas"
    "what's our funnel for the last 14 days"
    "show today's summary"
    "any anomalies?"
    "show pending payouts"
    "top contractors"
    "search for warehouse leads"
    "audit log last 50 actions"

  DESTRUCTIVE (preview + confirm):
    "approve the Houston contractor application abc-123"
    "pause SMS for +12145559999"
    "trigger dispatch for lead xyz-456 with urgency 9"
    "approve payout for settlement sig_abc"
    "invite operator@example.com as John Smith"

The natural language is forgiving — Claude maps "pause SMS for Acme",
"halt the SMS to phone 214 555 9999", and "stop messaging that Dallas
warehouse" to the same `pause_sms_sequence` action.


───────────────────────────────────────────────────────────────────────────────
VOICE INPUT
───────────────────────────────────────────────────────────────────────────────

Click the 🎙 voice button OR speak after pressing Cmd+K. The browser's
built-in Web Speech API transcribes locally — no audio sent to a third
party. Transcript appears in the input, you can edit before pressing Enter.

Works in:
  ✓ Chrome / Edge (most reliable)
  ✓ Safari (iOS + macOS)
  ✗ Firefox (no Web Speech API support)


───────────────────────────────────────────────────────────────────────────────
TEST PROTOCOL
───────────────────────────────────────────────────────────────────────────────

1. Sign in as owner
2. Press Cmd+K → console opens
3. Type "show today's summary"
4. ✓ Stats card appears (strikes, brain decisions, dispatches, fees)
5. Type "show pending payouts"
6. ✓ List of payouts appears
7. Type "invite test@example.com as Test Operator"
8. ✓ Confirmation card appears with action + params + Confirm/Cancel
9. Click Confirm
10. ✓ Status shows "✓ Done" · check Supabase for new operator row

Sign in as a viewer-role operator:
11. Press Cmd+K → type "approve payout for settlement xyz"
12. ✓ Status shows "requires owner role" · action did NOT fire


───────────────────────────────────────────────────────────────────────────────
WHAT'S COMING NEXT
───────────────────────────────────────────────────────────────────────────────

Phase 7 · Bridge view
  Full-screen voice-first experience at /bridge. Big mic button,
  continuous listening, streaming responses. Like Hermes' interface
  but powered by Claude.

Phase 8 · Pulse view
  The insight layer at /view/pulse. Per-niche, per-corridor,
  per-contractor, per-channel, per-hour ROI breakdown. The dashboard
  no competitor has because they don't have the underlying data model.

Phase 9 · Brain personality
  Operator-configurable brain persona. Conservative / aggressive /
  balanced. Memory of operator preferences. Per-niche brain instances.


THE EMPIRE NOW HAS A VOICE. SHIP IT.
Voice Bridge Fixed: Hub.py routes mapped to vonage_answer_webhook. PM2 empire-hub operational on port 8000.
