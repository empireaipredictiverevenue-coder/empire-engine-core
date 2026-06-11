# Empire AI — Hetzner Cloud Terraform module

Provisions the Hetzner Cloud server + firewall + DNS records for
[DEPLOY_HETZNER.md](../../DEPLOY_HETZNER.md). Lets you spin up a
fresh production box in **~3 minutes** without clicking through
the Hetzner dashboard.

## What this module creates

| Resource | Type | Notes |
|---|---|---|
| Server | `hcloud_server` | Ubuntu 22.04, SSH-key auth, runs `scripts/first-boot.sh` on boot |
| Firewall | `hcloud_firewall` | allows 22 (SSH, CIDR-restricted), 80, 443, ICMP, all outbound |
| SSH key | `hcloud_ssh_key` | uploads your local public key to Hetzner |
| DNS A record | `hetznerdns_record` | points `<subdomain>.<zone>` at the server's IPv4 |
| DNS AAAA record | `hetznerdns_record` | (optional) points at the server's IPv6 |

## Prerequisites

1. **Hetzner Cloud account** — https://console.hetzner.cloud
2. **Hetzner Cloud API token** (Read + Write) — Project → Security → API Tokens
3. **Hetzner DNS Console account** — https://dns.hetzner.com
4. **Domain already added as a zone** in the Hetzner DNS Console
5. **Hetzner DNS API token** — https://dns.hetzner.com → API Tokens
6. **SSH public key** on your laptop (default: `~/.ssh/id_ed25519.pub`)

## Usage

```bash
cd infra/terraform

# 1. Copy + edit the example tfvars
cp terraform.tfvars.example terraform.tfvars
$EDITOR terraform.tfvars
# At minimum: hcloud_token, hetzner_dns_token, dns_zone

# 2. Make sure terraform.tfvars is gitignored (it should already be)
echo "terraform.tfvars" >> ../../.gitignore

# 3. Init + plan + apply
terraform init
terraform plan
terraform apply

# 4. Watch the outputs — `next_steps` is the post-provision checklist
terraform output
```

After `terraform apply` returns (~3 minutes):

- The new box is running, SSH-reachable, with firewall + DNS records
- The `next_steps` output gives you the post-provision checklist
- Continue with [DEPLOY_HETZNER.md §2](../../DEPLOY_HETZNER.md#2-install-the-runtime) (Ollama, PM2, etc.)

## Variables

See [terraform.tfvars.example](terraform.tfvars.example) for a commented
template. Full schema in [variables.tf](variables.tf).

Key ones:

| Variable | Default | Notes |
|---|---|---|
| `hcloud_token` | _(required)_ | Hetzner Cloud API token (sensitive) |
| `hetzner_dns_token` | _(required)_ | Hetzner DNS API token (sensitive) |
| `server_type` | `cx22` | 4 GB RAM, 2 vCPU, ~€4.5/mo |
| `server_location` | `fsn1` | Falkenstein, Germany |
| `server_image` | `ubuntu-22.04` | LTS |
| `dns_zone` | _(required)_ | e.g. `empire-ai.co.uk` |
| `dns_subdomain` | `brain` | creates `brain.empire-ai.co.uk` |
| `enable_backups` | `true` | +20% cost |
| `enable_monitoring` | _(n/a)_ | Hetzner Cloud basic monitoring is enabled by default on all servers and isn't exposed in the provider |
| `enable_ipv6` | `true` | adds AAAA record |
| `allowed_ssh_cidrs` | `["0.0.0.0/0"]` | **lock down to your office IP for production** |

## Outputs

- `server_id`, `server_ipv4`, `server_ipv6` — Hetzner Cloud IDs/addresses
- `ssh_command` — `ssh root@<ipv4>` (copy-paste)
- `fqdn` — the FQDN the DNS records point at
- `firewall_id` — for adding/removing rules later
- `dns_records` — A + (optionally) AAAA records the module created
- `next_steps` — operator checklist (multi-line string)

## State

Terraform state is stored locally by default (`terraform.tfstate`).
For team use, move it to a Hetzner Storage Box or S3.

## Idempotency

`terraform apply` is safe to re-run for **non-destructive** changes
(firewall rules, DNS records, labels, monitoring toggle). Changes to
`server_type` / `server_image` / `server_location` will **destroy +
recreate** the server (and wipe `/root/.env` + `private.key`) — back
those up off-box first.

To re-create cleanly: `terraform destroy` then `terraform apply`.

## Cost

| Item | Cost |
|---|---|
| `cx22` server (4 GB / 2 vCPU) | ~€4.5/mo |
| Daily backups (if enabled) | +€0.9/mo |
| DNS zone | free |
| DNS records | free |
| Outbound traffic | 20 TB/mo included, then €1/TB |
| Floating IP (not used here) | €1.2/mo |

## Security notes

- The server's `root` SSH key is your local public key. Add team
  members' keys after provisioning (`ssh-copy-id`).
- Default firewall allows 22/80/443 inbound. Lock down
  `allowed_ssh_cidrs` to your office/home IP for a smaller attack
  surface.
- `fail2ban` is installed by `first-boot.sh` — defaults to 5 attempts
  per 10 min, 1-hour ban.
- `/root/.env` (with all API keys) is **not** managed by Terraform.
  Back it up off-box.
- API tokens in `terraform.tfvars` are gitignored but live in plain
  text on disk. Prefer `export HCLOUD_TOKEN=...` + `export
  HETZNER_DNS_TOKEN=...` before `terraform apply`.

## Related

- [DEPLOY_HETZNER.md](../../DEPLOY_HETZNER.md) — full deploy runbook
- [deploy/hetzner/*](../../deploy/hetzner/) — runtime scripts (PM2, etc.)
- [synthetic_brain.py](../../synthetic_brain.py) — the FastAPI app
- [bots/synthetic_brain.py](../../bots/synthetic_brain.py) — orchestrator wrapper
