# ── Hetzner Cloud server ───────────────────────────────────────
# The main production box. Runs Ubuntu 22.04, ssh-key auth only
# (no password), attached to the firewall above. The `user_data`
# cloud-init script is the first-boot bootstrap (apt update, base
# packages, fail2ban, log dir). Heavy stuff (Ollama, PM2, code
# clone, reverse proxy) is left to the post-provision runbook
# in DEPLOY_HETZNER.md — that way the Terraform apply stays
# fast and re-runnable, and the deploy can be re-done after
# `git pull` without re-provisioning the box.
resource "hcloud_ssh_key" "default" {
  name       = "${var.server_name}-key"
  public_key = local.ssh_public_key
  labels     = var.labels
}

resource "hcloud_server" "brain" {
  name         = var.server_name
  server_type  = var.server_type
  location     = var.server_location
  image        = var.server_image
  backups      = var.enable_backups
  ssh_keys     = [hcloud_ssh_key.default.id]
  firewall_ids = [hcloud_firewall.brain.id]
  labels       = var.labels

  # Public network: ipv4 always on (SSH + DNS A record need it).
  # ipv6 follows enable_ipv6 — when false, the AAAA record is
  # also skipped (see dns.tf count = var.enable_ipv6 ? 1 : 0).
  # Note: Hetzner Cloud basic monitoring is enabled by default on
  # all servers and isn't exposed as a writable attribute in the
  # hcloud provider, so there's no `monitoring` field here.
  public_net {
    ipv4_enabled = true
    ipv6_enabled = var.enable_ipv6
  }

  # Cloud-init: bootstrap the box. Keep this fast (~30s) and
  # idempotent so re-running `terraform apply` doesn't re-do
  # the slow install steps. See scripts/first-boot.sh.
  user_data = file("${path.module}/scripts/first-boot.sh")

  # Lifecycle: if you bump server_type or image, Terraform will
  # destroy + recreate the server. We're explicit about it so the
  # plan output screams about it instead of silently replacing
  # the box (and wiping /root/.env + private.key in the process).
  lifecycle {
    create_before_destroy = false
  }
}
