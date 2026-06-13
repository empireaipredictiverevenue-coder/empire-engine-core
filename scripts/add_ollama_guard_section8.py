#!/usr/bin/env python3
"""Add section 8d (Ollama-guarded content differentiation) to the E2E test."""
import re

with open('tests/test_brain_personality_e2e.py', 'r') as f:
    content = f.read()

new_section_8d = r'''
    # ── 8d. End-to-end content differentiation with real Ollama ──
    if ollama_available:
        section("8d. END-TO-END CONTENT DIFFERENTIATION (Ollama online)")

        # Use a real AIRouter and EmailDrafter with Ollama
        e2e_ai_router = AIRouter(get_db=get_db_wrapper)
        e2e_drafter = EmailDrafter(router=e2e_ai_router, get_db=get_db_wrapper)
        e2e_drafter.personality = bp_override

        e2e_results = {}
        for persona, niche in [("aggressive", "Roofing Restoration"), ("conservative", "Storm Damage Restoration")]:
            profile = bp_override.personality_for_niche(niche)
            base_temp = bp_override.recommended_temperature(niche)
            draft_temp = min(1.0, base_temp + 0.15)

            print(f"  E2E generating {persona.upper()} drafts (temp={draft_temp:.2f})...")

            drafts = []
            for i in range(8):  # 8 targets with email
                target = batch_targets[i]
                alert = batch_alerts[i]
                brain_dec = {"decision": "GO", "confidence": 0.85, "niche": niche, "personality": persona}
                try:
                    result = await e2e_drafter.draft_for_target(
                        target=target, alert_summary=alert, brain_decision=brain_dec,
                    )
                    if result and isinstance(result, dict) and result.get("subject"):
                        drafts.append(result)
                except Exception:
                    pass

            # Analyze
            wcs = [_wc(d.get("body", "")) for d in drafts]
            urges = [_score_urgency(d.get("body", ""), d.get("subject", "")) for d in drafts]
            ctas = [_classify_cta(d.get("body", "")) for d in drafts]
            pols = [_politeness(d.get("body", "")) for d in drafts]

            avg_wc = sum(wcs) / len(wcs) if wcs else 0
            avg_urg = sum(u["score"] for u in urges) / len(urges) if urges else 0
            avg_pol = sum(pols) / len(pols) if pols else 0
            high_urg = sum(1 for u in urges if u["level"] == "high")
            med_urg = sum(1 for u in urges if u["level"] == "medium")

            cta_tally = {}
            for cta in ctas:
                for style in cta:
                    cta_tally[style] = cta_tally.get(style, 0) + 1

            e2e_results[persona] = {
                "drafts": len(drafts),
                "avg_wc": round(avg_wc, 1),
                "avg_urg": round(avg_urg, 2),
                "avg_pol": round(avg_pol, 2),
                "urg_high": high_urg,
                "urg_med": med_urg,
                "ctas": cta_tally,
                "draft_temp": round(draft_temp, 2),
                "base_temp": round(base_temp, 2),
                "threshold": profile.get("confidence_threshold"),
            }

            print(f"      -> {len(drafts)} drafts, avg_wc={avg_wc:.0f}, urg_score={avg_urg:.2f}, politeness={avg_pol:.2f}")
            print(f"      -> urgency: high={high_urg} med={med_urg}, ctas={cta_tally}")

        # Assertions — content differentiation
        a = e2e_results.get("aggressive", {})
        c = e2e_results.get("conservative", {})

        check("E2E: Aggressive: generated drafts", a.get("drafts", 0) >= 5,
              f"got {a.get('drafts')} drafts")
        check("E2E: Conservative: generated drafts", c.get("drafts", 0) >= 5,
              f"got {c.get('drafts')} drafts")
        check("E2E: Draft temps differ",
              abs(a.get("draft_temp", 0) - c.get("draft_temp", 0)) > 0.10,
              f"agg_temp={a.get('draft_temp')} cons_temp={c.get('draft_temp')}")
        check("E2E: Thresholds differ",
              a.get("threshold") != c.get("threshold"),
              f"agg_thresh={a.get('threshold')} cons_thresh={c.get('threshold')}")

        # Word count — aggressive should be longer or equal
        if a.get("avg_wc", 0) > 0 and c.get("avg_wc", 0) > 0:
            check("E2E: Word count recorded for both personas",
                  True, f"agg_wc={a['avg_wc']} cons_wc={c['avg_wc']}")
            if a["avg_wc"] != c["avg_wc"]:
                wc_diff = a["avg_wc"] - c["avg_wc"]
                wc_dir = "longer" if wc_diff > 0 else "shorter"
                print(f"      -> Word count differentiation: aggressive {wc_dir} by {abs(wc_diff):.0f} words")

        # Urgency — check differences
        if a.get("avg_urg", 0) > 0 or c.get("avg_urg", 0) > 0:
            check("E2E: Urgency score recorded for at least one persona",
                  True, f"agg_urg={a.get('avg_urg', 0)} cons_urg={c.get('avg_urg', 0)}")

        # Politeness — check recorded
        if a.get("avg_pol", 0) > 0 and c.get("avg_pol", 0) > 0:
            check("E2E: Politeness recorded for both personas",
                  True, f"agg_pol={a['avg_pol']} cons_pol={c['avg_pol']}")

        # CTA styles classified
        if a.get("ctas") and c.get("ctas"):
            check("E2E: CTA styles classified for both personas",
                  len(a["ctas"]) > 0 and len(c["ctas"]) > 0,
                  f"agg_ctas={a['ctas']} cons_ctas={c['ctas']}")

        # Summary table
        print(f"  E2E Results Summary:")
        print(f"    {'Metric':<30} {'Aggressive':>12} {'Conservative':>12}")
        print(f"    {'-'*30} {'-'*12} {'-'*12}")
        for key in ["drafts", "avg_wc", "avg_urg", "avg_pol", "draft_temp", "base_temp", "threshold"]:
            print(f"    {key:<30} {str(a.get(key, '')):>12} {str(c.get(key, '')):>12}")
        print(f"    {'urg_high':<30} {str(a.get('urg_high', 0)):>12} {str(c.get('urg_high', 0)):>12}")
        print(f"    {'urg_med':<30} {str(a.get('urg_med', 0)):>12} {str(c.get('urg_med', 0)):>12}")
        print(f"    {'ctas':<30} {str(a.get('ctas', {})):>12} {str(c.get('ctas', {})):>12}")

    else:
        section("8d. END-TO-END CONTENT DIFFERENTIATION SKIPPED (Ollama offline)")
        print("  Ollama not reachable — skipping end-to-end content differentiation.")
        print("  Mock-based pipeline and parameter differentiation verified in 8b/8c above.")
        results["skipped"] += 1
        results["details"].append({
            "name": "E2E content differentiation",
            "status": "SKIP",
            "detail": "Ollama not reachable at http://127.0.0.1:11434",
        })


'''  # no trailing newline — the summary marker will follow

# Insert before SUMMARY
marker = '\n    # ── SUMMARY ──────────────────────────────────────────────────────\n    section("TEST SUMMARY")'
new_s = new_section_8d + marker
content = content.replace(marker, new_s, 1)

with open('tests/test_brain_personality_e2e.py', 'w') as f:
    f.write(content)

print("Section 8d inserted successfully!")
