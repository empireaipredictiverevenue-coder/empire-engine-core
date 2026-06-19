from typing import Optional
import phonenumbers
from email_validator import validate_email, EmailNotValidError

def enrich_lead(lead):
    # Phone normalization
    if lead.phone:
        try:
            lead.phone = phonenumbers.format_number(
                phonenumbers.parse(lead.phone, "US"),
                phonenumbers.PhoneNumberFormat.E164
            )
        except:
            pass

    # Email validation
    if lead.email:
        try:
            lead.email = validate_email(lead.email).email
        except EmailNotValidError:
            lead.email = None

    return lead
