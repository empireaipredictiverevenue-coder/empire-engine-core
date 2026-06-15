Empire AI · Carrier Outreach · Send List
==========================================

5 draft emails are ready for your review. Each is in
/root/empire-v49/carrier_outreach_drafts/<carrier>.txt

| # | Carrier   | File                       | To                              |
|---|-----------|----------------------------|---------------------------------|
| 1 | State Farm    | state_farm.txt        | partners@statefarm.com          |
| 2 | Allstate      | allstate.txt          | vendorpartners@allstate.com     |
| 3 | USAA          | usaa.txt              | partnerships@usaa.com           |
| 4 | Liberty Mutual| liberty_mutual.txt    | partners@libertymutual.com      |
| 5 | Farmers       | farmers.txt           | partners@farmers.com            |

BEFORE SENDING:
- The email addresses are educated guesses. Real partnership teams
  often have specific aliases (e.g. apidev@allstate.com, integrations@
  statefarm.com). Worth a 30-second search on LinkedIn or the
  carrier's developer portal before sending.
- "We're the operator" — the drafts are signed "Phil, Empire AI" with
  phil@empire-ai.co.uk. If you'd rather send from a personal account,
  copy-paste the body into your own email client.
- The drafts were auto-revised to say "validated the 3% fee model
  end-to-end with first fee events recorded this week (testing through
  a mock carrier API)" rather than "first paid fee event" — this is
  more accurate. The real fee events are in the database but they
  came from the mock carrier, not real insurance money.

AFTER SENDING:
- When a carrier responds, the response will go to your email.
- If they offer a partner program, that's a real revenue event. The
  /api/v1/fee/claim-settled endpoint is already wired to receive the
  webhook (or a polling loop can be added).
- If they pass, we still have a working system. The mock carrier
  remains as a dev tool.

SENDING INSTRUCTIONS:
The drafts are plain text. To send, either:
  (a) Open each .txt file, copy the body, paste into your email
      client, and send.
  (b) Configure SMTP creds in /root/.env and have the email engine
      send them (next step if you want automation).

STATUS: 5 DRAFTS READY · 0 SENT
