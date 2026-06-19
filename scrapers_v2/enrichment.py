import phonenumbers
from email_validator import validate_email, EmailNotValidError
from models import Lead

def enrich_lead(lead: Lead) -> Lead:
    # Phone normalization (US-focused for now)
    if lead.phone:
        try:
            parsed = phonenumbers.parse(lead.phone, "US")
            if phonenumbers.is_valid_number(parsed):
                lead.phone = phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
            else:
                lead.phone = None
        except:
            lead.phone = None

    # Email validation
    if lead.email:
        try:
            lead.email = validate_email(lead.email).email
        except EmailNotValidError:
            lead.email = None

    return lead
