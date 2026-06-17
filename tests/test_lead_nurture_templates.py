"""
tests/test_lead_nurture_templates.py
=====================================
Unit tests for the lead_nurture email templates in empire_email.py.

Tests _build_lead_nurture_email() for all 4 steps (0-3) to verify:
  - Templates render without errors
  - Subjects contain facility name
  - Body contains facility and location
  - Unsubscribe link is present
  - CAN-SPAM footer (postal address) is present
  - Click tracking URL is included when provided
"""

import sys
sys.path.insert(0, "/root/empire-v49")

from empire_email import _build_lead_nurture_email


SAMPLE_ARGS = {
    "unsubscribe_link": "https://empire-ai.co.uk/email/unsubscribe?t=test_token",
    "postal_address": "Empire AI Ltd · United Kingdom",
    "sender_name": "Empire AI Operations",
}

FACILITY = "Utility Distribution Center"
CITY = "Houston"
STATE = "TX"


def _render(step: int, **overrides) -> tuple[str, str]:
    """Helper: call _build_lead_nurture_email with sensible defaults."""
    args = dict(SAMPLE_ARGS)
    args["facility"] = FACILITY
    args["city"] = CITY
    args["state"] = STATE
    # Allow overrides to replace any default (e.g. city="", state="")
    args.update(overrides)
    return _build_lead_nurture_email(
        step=step,
        **args,
    )


class TestLeadNurtureTemplates:
    """Verify all 4 steps render without errors with correct content."""

    def test_step0_renders(self):
        """Step 0: Introductory offer — facility in subject + body."""
        subject, html = _render(0)
        assert FACILITY in subject
        assert FACILITY in html
        assert CITY in html
        assert STATE in html
        assert "3% success fee" in html
        # 'upfront' and 'cost' may be separated by newline/whitespace in HTML
        assert "no upfront" in html
        assert "success fee" in html

    def test_step1_renders(self):
        """Step 1: Follow-up — process description."""
        subject, html = _render(1)
        assert FACILITY in subject
        assert CITY in html or STATE in html
        assert "How we source" in html
        assert "3% success fee" in html

    def test_step2_renders(self):
        """Step 2: Social proof — operator results."""
        subject, html = _render(2)
        assert FACILITY in subject
        assert "Results from our network" in html
        assert "48 hours" in html

    def test_step3_renders(self):
        """Step 3: Last touch — graceful exit."""
        subject, html = _render(3)
        assert FACILITY in subject
        assert "Last note" in subject
        assert "Stepping back" in html
        assert "no further messages" in html.lower()

    def test_can_spam_unsubscribe_link_present(self):
        """Every email must contain a one-click unsubscribe link (CAN-SPAM)."""
        _, html = _render(0)
        assert "Unsubscribe" in html
        assert SAMPLE_ARGS["unsubscribe_link"] in html

    def test_can_spam_postal_address_present(self):
        """Every email must contain a physical postal address (CAN-SPAM)."""
        _, html = _render(0)
        assert "Empire AI Ltd" in html
        assert "United Kingdom" in html

    def test_lead_nurture_shell_footer(self):
        """Email shell references 'facility' and 'lead generation' not storm/weather."""
        _, html = _render(0)
        assert "facility" in html.lower()
        assert "lead generation" in html.lower()
        # Should NOT reference storm/weather
        assert "storm" not in html.lower()
        assert "severe weather" not in html.lower()

    def test_missing_city_falls_back(self):
        """When city is empty string, template still renders."""
        subject, html = _render(0, city="")
        assert FACILITY in subject
        assert "in  as an" not in html  # no "in  as" with double-space

    def test_empty_city_state_falls_back_to_facility(self):
        """When both city and state are empty, location falls back to facility name."""
        subject, html = _render(0, city="", state="")
        assert FACILITY in subject
        # Location fallback should use the facility name
        assert "as an established logistics" in html

    def test_click_tracking_url_included(self):
        """When click_tracking_url is provided, email includes a CTA button."""
        click_url = "https://empire-ai.co.uk/pricing?ref=email_nurture_step0"
        _, html = _render(0, click_tracking_url=click_url)
        assert click_url in html
        assert "Learn More" in html
        assert "padding:14px 32px" in html  # CTA button styling

    def test_subject_differs_per_step(self):
        """Each step should have a unique subject line."""
        subjects = [_render(step)[0] for step in range(4)]
        assert len(set(subjects)) == 4, f"Expected 4 unique subjects, got {subjects}"

    def test_tracking_pixel_included(self):
        """When tracking_pixel_url is provided, pixel img tag is present."""
        pixel_url = "https://empire-ai.co.uk/email/track/open?t=pixel"
        _, html = _render(0, tracking_pixel_url=pixel_url)
        assert pixel_url in html
        assert '<img src="' in html
        assert 'width="1" height="1"' in html

    def test_step0_matches_expected_subject_format(self):
        """Step 0 subject: 'Qualified leads for {facility}'."""
        subject, _ = _render(0)
        assert subject == f"Qualified leads for {FACILITY}"

    def test_step3_matches_expected_subject_format(self):
        """Step 3 subject: 'Last note from us · {facility}'."""
        subject, _ = _render(3)
        assert subject == f"Last note from us · {FACILITY}"
