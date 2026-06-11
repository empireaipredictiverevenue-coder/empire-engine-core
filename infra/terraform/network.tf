# ── Hetzner Cloud firewall ──────────────────────────────────────
# One firewall per environment (rather than per-server) is the
# Hetzner-recommended pattern. The server is attached to it via
# the `firewall_ids` field on hcloud_server (see server.tf).
#
# Rules:
#   - SSH (22)      restricted to var.allowed_ssh_cidrs
#   - HTTP (80)     open to all (Caddy/Nginx ACME challenge + redirect)
#   - HTTPS (443)   open to all (Vonage's wss:// reaches the brain here)
#   - ICMP          open to all (ping/traceroute diagnostics)
#   - Outbound      all (apt, pip, npm, git — no point restricting)
resource "hcloud_firewall" "brain" {
  name   = "${var.server_name}-fw"
  labels = var.labels

  # SSH: one rule per CIDR (Hetzner's `source_ips` is a list per rule,
  # so we use `dynamic` rather than hand-writing N rules). Lock down
  # var.allowed_ssh_cidrs to a single IP for production hardening.
  dynamic "rule" {
    for_each = var.allowed_ssh_cidrs
    content {
      direction  = "in"
      protocol   = "tcp"
      port       = "22"
      source_ips = [rule.value]
    }
  }

  # HTTP — Caddy/Nginx terminate TLS, but Let's Encrypt's HTTP-01
  # challenge hits :80 and our redirect from http→https listens here.
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "80"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # HTTPS — Vonage's `stream` NCCO action opens a wss:// connection
  # to this port (via the reverse proxy, which fronts 127.0.0.1:8005).
  rule {
    direction  = "in"
    protocol   = "tcp"
    port       = "443"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # ICMP — ping + traceroute. Useful for "is the box up?" diagnostics.
  rule {
    direction  = "in"
    protocol   = "icmp"
    source_ips = ["0.0.0.0/0", "::/0"]
  }

  # Outbound: open everything. The threat model is "we trust the
  # packages we install", not "we whitelist apt mirrors". Tighter
  # egress control would be a separate (much larger) project.
  rule {
    direction       = "out"
    protocol        = "tcp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
  rule {
    direction       = "out"
    protocol        = "udp"
    port            = "any"
    destination_ips = ["0.0.0.0/0", "::/0"]
  }
}
