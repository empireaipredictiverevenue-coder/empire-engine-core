# Email Compliance Reference

## CAN-SPAM Act (US)

### Requirements
1. **Don't use false or misleading header information**
   - "From" must accurately identify the sender
   - "To" and routing must be accurate
   - Subject line must reflect content accurately

2. **Don't use deceptive subject lines**
   - Subject cannot mislead about the content or purpose
   - Exception: prior affirmative consent for humorous/satirical content

3. **Identify the message as an ad**
   - Clear and conspicuous disclosure that it's a commercial message
   - Exception: transactional or relationship messages
   - Exception: prior affirmative consent

4. **Tell recipients where you're located**
   - Valid physical postal address
   - Options: current street address, PO Box (USPS-registered), private mailbox (commercial mail receiving agency)

5. **Tell recipients how to opt out**
   - Clear and conspicuous explanation of how to unsubscribe
   - Must be able to opt out via email or web form
   - PROCESS THE OPT-OUT WITHIN 10 BUSINESS DAYS

6. **Honor opt-out requests promptly**
   - Cannot require more than just reply or visit single web page
   - No fee, no provision of identifying info beyond email address
   - No requirement to log in to unsubscribe
   - Once opted out, cannot sell/transfer the email address
   - 10 business days to implement

7. **Monitor what others are doing on your behalf**
   - You are responsible for third-party email senders
   - Contractual compliance requirements recommended

### Penalties
- Up to $50,120 per violation
- Separate violation for each email
- Separate violation for each day of opt-out violation
- Criminal penalties for header/spoofing violations (fines + up to 5 years prison)

## GDPR (EU/EEA)

### Key Requirements for Email Marketing

#### Lawful Basis for Processing
1. **Consent**: freely given, specific, informed, unambiguous
   - Opt-in required (pre-ticked boxes are not valid consent)
   - Must be as easy to withdraw as to give
   - Record and prove consent

2. **Legitimate Interest**: for B2B outreach to business contacts
   - Must balance against individual's rights
   - Document legitimate interest assessment (LIA)
   - Must provide opt-out at first contact

#### Rights of Individuals
- **Right to be informed**: privacy notice at data collection
- **Right of access**: copy of personal data within 30 days
- **Right to rectification**: correct inaccurate data
- **Right to erasure**: "right to be forgotten"
- **Right to restrict processing**: limit how data is used
- **Right to data portability**: receive data in machine-readable format
- **Right to object**: object to direct marketing at any time

#### Data Processing Requirements
- Data Processing Agreement (DPA) with all email service providers
- Records of processing activities
- Data Protection Impact Assessment (DPIA) for high-risk processing
- Breach notification to DPA within 72 hours

## CASL (Canada)

### Key Requirements

#### Consent Types
1. **Express Consent**: explicit opt-in, written or oral
   - Clear description of purpose
   - Sender identification
   - Prescription information (name, mailing address, phone/email/web)
   - Unsubscribe mechanism
   - Valid for: until withdrawn

2. **Implied Consent**: based on existing relationship
   - Business or personal relationship (2 years)
   - Published business contact information + message relates to business
   - Conspicuous publication + message relates to recipient's role
   - Valid for: 2 years from last purchase/inquiry/membership

#### Content Requirements
- Sender name and contact information
- Unsubscribe mechanism
- No false or misleading representation

#### Unsubscribe Requirements
- Same electronic method as message (can't require more clicks)
- Can present options (reduce frequency, change topics)
- Must be processed within 10 business days
- Must identify sender in unsubscribe process

### Penalties
- Administrative monetary penalty: up to $10M per violation
- Vicarious liability: directors/officers responsible for corporate violations

## TCPA (US - Telephone Consumer Protection Act)

### Email-Specific Considerations
- TCPA primarily covers voice/SMS/fax
- Email marketing falls under CAN-SPAM
- BUT: if email contains link to auto-dialer or uses click-to-call, TCPA may apply
- Consent for email ≠ consent for SMS/phone calls

## Compliance Checklist

### Pre-Send
- [ ] Physical postal address in footer
- [ ] One-click unsubscribe link
- [ ] Honest subject line (matches content)
- [ ] Accurate "From" name and address
- [ ] Commercial disclosure if required
- [ ] Consent recorded (for GDPR/CASL)
- [ ] Privacy policy link (for GDPR)
- [ ] Recipient time zone check (not in quiet hours)

### Post-Send
- [ ] Unsubscribe processed within 10 business days
- [ ] Hard bounces removed immediately
- [ ] Spam complaints recorded and suppressed
- [ ] Consent records maintained
- [ ] Data processing records maintained
- [ ] Opt-out list maintained and honored

### Quarterly
- [ ] Review consent records for all active lists
- [ ] Update privacy policy if data processing changed
- [ ] Verify DNS authentication records (SPF/DKIM/DMARC)
- [ ] Test unsubscribe flow end-to-end
- [ ] Review third-party processor DPAs
- [ ] Conduct deliverability audit
