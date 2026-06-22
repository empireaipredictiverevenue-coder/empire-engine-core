---
type: skill
name: social.facebook-bot
version: 1.0.0
description: Facebook Messenger chatbot — auto-reply to customer support questions, qualify and capture storm restoration leads, route to contractor dispatch
tags:
  - domain:social
  - mode:llm
  - pipeline:chatbot
timeout_seconds: 30.0
max_retries: 2
execution_mode: llm
required_params:
  - message
dependencies:
  - outreach.reply
  - outreach.sentiment
---

# social.facebook-bot

Facebook Messenger chatbot — auto-reply to customer support inquiries, qualify storm restoration leads, capture contact information, and route qualified leads to contractor dispatch.

## Overview

Intelligent Facebook Messenger chatbot for the Empire AI business page. Handles customer support inquiries and lead generation in a single conversation flow. Automatically classifies incoming messages as either support questions (answers from knowledge base / LLM) or lead interest (qualification flow). Captures lead information (location, damage type, urgency, phone/email) into Supabase and routes qualified leads to contractor dispatch.

Designed for storm restoration and contracting verticals where homeowners reach out after a storm event needing fast response.

## Capabilities

- **Intent classification** — classify incoming messages as: `support_question`, `lead_interest`, `contractor_inquiry`, `complaint`, `spam`, or `unknown`
- **Support auto-reply** — answer common questions about storm claims, restoration process, contractor matching, service areas, pricing, availability, insurance coordination
- **Lead qualification** — structured qualification flow: location → damage type → urgency → contact info (phone/email) → consent capture
- **FAQ knowledge base** — answers for: claim filing process, insurance claim tips, emergency tarping, water extraction, mold remediation, contractor vetting process, service area coverage, response times
- **Human handoff detection** — detect when the conversation exceeds bot capability, flag for Chatwoot agent review
- **Multi-turn conversation** — maintain conversation state across messages (qualifying, answering follow-ups, collecting info)
- **Business hours mode** — away message outside configured hours, collect callback info
- **Sentiment detection** — positive/negative/urgent sentiment tuning, escalation on negative sentiment
- **Contractor routing** — after lead capture, route to appropriate contractor in the area based on location + damage type
- **Language detection** — detect English vs Spanish and respond in the correct language

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `social.facebook-bot` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("social.facebook-bot", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| message | string | ✅ | Incoming Facebook Messenger message text |
| sender_name | string | — | Sender's display name (from Facebook profile) |
| conversation_history | list | — | Previous messages in this conversation: `[{"role": "user", "content": "..."}, {"role": "bot", "content": "..."}]` |
| page_id | string | — | Facebook Page ID the message was sent to |
| sender_psid | string | — | Facebook Page Scoped ID for the sender |
| language | string | — | Detected language: `en`, `es`. Default: `en` |
| business_hours | boolean | — | Whether currently within business hours. Default: `true` |
| lead_captured | boolean | — | Whether lead info has already been captured. Default: `false` |
| qualification_stage | string | — | Current stage in qualification flow: `none`, `asking_location`, `asking_damage`, `asking_urgency`, `asking_contact`, `complete` |
| location | string | — | Detected or collected location (city, state) |
| damage_type | string | — | Reported damage type: `roof`, `water`, `wind`, `hail`, `flood`, `fire`, `other` |

## Output

A structured chatbot response with:

```json
{
  "response": {
    "reply_text": "I'd be happy to help! Could you tell me what city you're in so I can connect you with a local contractor?",
    "type": "question|answer|lead_qualification|handoff|away_message",
    "confidence": 0.92
  },
  "classification": {
    "intent": "lead_interest|support_question|contractor_inquiry|complaint|spam",
    "sentiment": "positive|neutral|negative|urgent",
    "language": "en|es",
    "requires_human": false
  },
  "lead_data": {
    "captured": true,
    "name": "John Doe",
    "location": "Dallas, TX",
    "damage_type": "roof",
    "urgency": "high",
    "phone": "214-555-0100",
    "email": "john@example.com",
    "qualified": true
  },
  "actions": [
    {"type": "dispatch_contractor", "niche": "roofing", "location": "Dallas, TX", "priority": "high"},
    {"type": "send_followup_sms", "phone": "214-555-0100", "template": "lead_welcome"}
  ]
}
```

## Example

```python
# Execute the skill — incoming support question
result = registry.execute("social.facebook-bot", {
    "params": {
        "message": "How do I file a storm damage claim with my insurance?",
        "sender_name": "John Doe",
        "conversation_history": [],
        "language": "en",
        "business_hours": true,
        "lead_captured": false
    },
    "context": {"source": "facebook-messenger"}
})
print(result)

# Execute the skill — lead qualification reply
result = registry.execute("social.facebook-bot", {
    "params": {
        "message": "My roof got damaged in the hailstorm last night. Can you help?",
        "sender_name": "Jane Smith",
        "conversation_history": [
            {"role": "user", "content": "I need help with storm damage"}
        ],
        "language": "en",
        "business_hours": true,
        "lead_captured": false,
        "qualification_stage": "none"
    },
    "context": {"source": "facebook-messenger"}
})
print(result)
```
