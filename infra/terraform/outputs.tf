# ── Useful outputs ─────────────────────────────────────────────
# These surface the IDs/IPs/commands the operator needs after
# `terraform apply` finishes. The `next_steps` output is the
# post-provision checklist that bridges to DEPLOY_HETZNER.md §2.

output "server_id" {
  description = "Hetzner Cloud server ID. Use for `hcloud server describe` or to attach/detach resources later."
  value       = hcloud_server.brain.id
}

output "server_ipv4" {
  description = "Public IPv4 address of the server. Use in DNS records, firewall rules, and ssh commands."
  value       = hcloud_server.brain.ipv4_address
}

output "server_ipv6" {
  description = "Public IPv6 address. null if IPv6 is disabled."
  value       = var.enable_ipv6 ? hcloud_server.brain.ipv6_address : null
}

output "ssh_command" {
  description = "Copy-paste SSH command to log into the new box as root."
  value       = "ssh root@${hcloud_server.brain.ipv4_address}"
}

output "fqdn" {
  description = "Fully-qualified domain name the A/AAAA records point at (e.g. brain.empire-ai.co.uk)."
  value       = local.fqdn
}

output "firewall_id" {
  description = "Hetzner Cloud firewall ID. Use to add/remove rules later (or with `hcloud firewall describe`)."
  value       = hcloud_firewall.brain.id
}

output "dns_records" {
  description = "DNS records created by this module (A and optionally AAAA)."
  value = concat(
    [
      {
        type  = "A"
        name  = local.fqdn
        value = hcloud_server.brain.ipv4_address
        ttl   = 300
      },
    ],
    var.enable_ipv6 ? [
      {
        type  = "AAAA"
        name  = local.fqdn
        value = hcloud_server.brain.ipv6_address
        ttl   = 300
      },
    ] : [],
  )
}

output "next_steps" {
  description = "Operator checklist after `terraform apply` completes. Run these from your laptop."
  value       = <<-EOT
    Provisioning complete. To finish the deploy:

    1. Wait ~30s for the first-boot cloud-init to finish (apt update, base packages).
       Watch it:  ssh root@${hcloud_server.brain.ipv4_address} 'tail -f /var/log/cloud-init-output.log'

    2. Verify DNS propagation (usually <60s):
         dig +short ${local.fqdn}
         # expect: ${hcloud_server.brain.ipv4_address}

    3. Continue with DEPLOY_HETZNER.md §2 onward (Ollama, Python, PM2, env, reverse proxy).
       The reverse proxy will auto-provision the Let's Encrypt cert once DNS resolves.

    4. End-to-end verification (from DEPLOY_HETZNER.md §6):
         curl -i https://${local.fqdn}/docs
         python3 scripts/smoke_voice_streaming.py
  EOT
}
