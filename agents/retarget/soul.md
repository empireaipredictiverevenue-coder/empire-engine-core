# Retarget Agent

Walks `sms_sequences` rows in `replied` state and re-enrolls soft-replies
in a follow-up sequence of the same type.

## Conservative defaults

- **target pool:** `sms_sequences` where `status='replied'`, `created_at > NOW() - 30d`, no STOP / YES replies
- **frequency:** once per source sequence (tracked in `meta.retarget_done`)
- **dedup:** no active sequence for the phone, not in DNC tables
- **what "soft" means:** NOT a STOP / unsubscribe reply AND NOT a YES / converted reply

## Cron

```
# Every 6h, offset 7min from prospector (avoids supabase contention)
7 */6 * * * /bin/bash /root/empire-v49/agents/retarget/cron.sh >> /root/empire-v49/logs/agent_retarget.log 2>&1
```

## Usage

```bash
python3 -m agents.retarget           # one run (honors agent_config.dry_run)
python3 -m agents.retarget --dry-run # score and report, don't enroll
python3 -m agents.retarget --status  # last runs + stats
```

## Config

`agent_config` row keyed `agent_name = "retarget"`:
- `enabled` (bool)
- `dry_run` (bool)
- `config_json.window_days` (int, default 30)

## What it does NOT do

- Does not modify the source sequence (audit preserved)
- Does not retarget STOP replies (marked retarget_done so never tried again)
- Does not retarget YES replies (they're already-converted, marked retarget_done)
- Does not retarget if the phone is on DNC (`sms_opt_outs`, `do_not_contact`)
- Does not retarget if the phone has any active sequence already
