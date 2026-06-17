"""
EMPIRE V49 · SHARED EMAIL VALIDATOR
====================================
Single source of truth for email validation across all bots, agents,
and scripts. Prevents garbage emails like shadow@2x.png from entering
the pipeline and triggering Gmail spam filters.

Usage:
    from bots.email_validator import is_valid_email

    if is_valid_email("user@company.com"):  # True
    if is_valid_email("shadow@2x.png"):     # False
    if is_valid_email("you@community.com"): # True (valid format, but domain signals may flag it)
"""

import re

# ── KNOWN GARBAGE DOMAINS ──────────────────────────────────────────
# Domains that are clearly not real email providers or business domains.
# These come from scraped data, test entries, or placeholder records.
_GARBAGE_DOMAINS = {
    # Image/file extensions mistaken for domains
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp", ".ico",
    ".tiff", ".tif", ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    # Placeholder/test domains
    "example.com", "domain.com", "test.com", "mail.com", "user.com",
    "yourcompany.com", "yourdomain.com", "company.com", "business.com",
    "email.com", "inbox.com", "website.com", "site.com",
    # Prospector placeholders
    "prospector.placeholder",
    # Known throwaway domains (NOT real email providers like mail.com)
    "mailinator.com", "guerrillamail.com", "tempmail.com", "throwaway.com",
    "yopmail.com", "10minutemail.com", "sharklasers.com",
}

# ── KNOWN GARBAGE LOCAL PARTS ──────────────────────────────────────
# Email local parts that are clearly not real person/business addresses.
_GARBAGE_LOCALS = {
    "user", "test", "example", "root",
    "postmaster", "mailer-daemon", "mailerdaemon", "nobody",
    "noreply", "no-reply", "donotreply", "do-not-reply",
    "invalid", "unknown", "fake", "placeholder", "delete",
}

# ── KNOWN GARBAGE FULL EMAILS ──────────────────────────────────────
# Specific emails that have been identified as garbage from scraping.
_GARBAGE_FULL = {
    "you@community.com",
}

# ── REGEX PATTERNS (pre-compiled for performance) ───────────────────
_BASIC_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

# TLD must not look like a file extension (catches shadow@2x.png)
_TLD_IS_FILE_EXT = re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|bmp|ico|tiff?|pdf|docx?|xlsx?)$", re.I)

# Suspicious local-part patterns (auto-generated, test, spam)
_SUSPICIOUS_LOCAL = re.compile(
    r"(test\d*|fake\d*|user\d{3,}|info\d+|contact\d+|nospam|spam)", re.I
)

# IP address pattern (emails to IP domains are almost always garbage)
_IP_DOMAIN_RE = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")


def is_valid_email(email, strict=True):
    """
    Validate an email address for B2B outreach quality.

    Args:
        email: The email string to validate
        strict: If True (default), applies all filters including domain
                reputation checks. If False, only basic format validation.

    Returns:
        bool: True if the email appears to be a real, deliverable address
    """
    if not email or not isinstance(email, str):
        return False

    email = email.strip()
    if not email:
        return False

    # ── Quick format check ──────────────────────────────────────
    if not _BASIC_EMAIL_RE.match(email):
        return False

    # ── Check full email blacklist ──────────────────────────────
    if email.lower() in _GARBAGE_FULL:
        return False

    # ── Split and check parts ───────────────────────────────────
    local, domain = email.rsplit("@", 1)
    local_lower = local.lower()
    domain_lower = domain.lower()

    # ── Domain checks ───────────────────────────────────────────
    # File extension as TLD (shadow@2x.png -> .png TLD)
    if _TLD_IS_FILE_EXT.search(domain_lower):
        return False

    # Known garbage domains
    if domain_lower in _GARBAGE_DOMAINS:
        return False

    # Single-label domain (user@localhost, user@company)
    if "." not in domain:
        return False

    # TLD too short (user@a.bc)
    tld = domain.rsplit(".", 1)[-1]
    if len(tld) < 2:
        return False

    if strict:
        # ── Local part checks (strict mode only) ────────────────
        if local_lower in _GARBAGE_LOCALS:
            return False

        # Local part too short (a@company.com)
        if len(local) < 2:
            return False

        # Local part too long (spammy patterns)
        if len(local) > 64:
            return False

        # No consecutive dots in local
        if ".." in local:
            return False

        # No dots at start or end of local
        if local.startswith(".") or local.endswith("."):
            return False

        # Suspicious patterns in local part (pre-compiled)
        if _SUSPICIOUS_LOCAL.search(email):
            return False
        # All-digit local part that's too long (auto-generated)
        if re.match(r"^\d{5,}@", email):
            return False

        # ── Domain quality checks (strict) ──────────────────────
        # TLD must be at least 2 chars
        if len(tld) < 2:
            return False

        # Domain shouldn't be an IP address
        if _IP_DOMAIN_RE.match(domain):
            return False

        # Domain shouldn't be a pure localhost
        if domain_lower in ("localhost", "local"):
            return False

    return True


def filter_valid_emails(emails, strict=True):
    """Filter a list of emails, returning only valid ones."""
    return [e for e in emails if is_valid_email(e, strict=strict)]


def describe_rejection(email):
    """
    Validate and return detailed rejection reason.
    Returns None if valid, or a string describing why it was rejected.
    """
    if not email or not isinstance(email, str):
        return "empty or non-string"
    email = email.strip()
    if not email:
        return "empty after strip"
    if not _BASIC_EMAIL_RE.match(email):
        return "does not match basic email pattern"
    if email.lower() in _GARBAGE_FULL:
        return "blacklisted full email"
    if "@" not in email:
        return "no @ sign"
    local, domain = email.rsplit("@", 1)
    domain_lower = domain.lower()
    if _TLD_IS_FILE_EXT.search(domain_lower):
        return f"TLD looks like a file extension: .{domain_lower.rsplit('.', 1)[-1]}"
    if domain_lower in _GARBAGE_DOMAINS:
        return f"domain '{domain}' is in garbage domain list"
    if "." not in domain:
        return "domain has no dot (single-label)"
    tld = domain.rsplit(".", 1)[-1]
    if len(tld) < 2:
        return f"TLD '{tld}' too short"
    if len(local) < 2:
        return "local part too short"
    return None  # valid
