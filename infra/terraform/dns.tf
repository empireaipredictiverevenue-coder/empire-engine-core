# ── Hetzner DNS Console records ────────────────────────────────
# The DNS Console is a separate API from Hetzner Cloud, hence the
# separate `hetznerdns` provider. The zone must already exist
# (Terraform reads it via the data source — we don't create zones
# from scratch because registrars/transfer flows are messy).
#
# We create an A record (and optionally AAAA) for the chosen
# subdomain pointing at the server's public IPs. The reverse
# proxy (Caddy/Nginx) needs DNS to resolve before it can
# auto-provision the Let's Encrypt cert.
data "hetznerdns_zone" "primary" {
  name = var.dns_zone
}

resource "hetznerdns_record" "brain_a" {
  zone_id = data.hetznerdns_zone.primary.id
  name    = var.dns_subdomain
  value   = hcloud_server.brain.ipv4_address
  type    = "A"
  ttl     = 300
}

# AAAA only created when IPv6 is enabled. Using `count` rather
# than `for_each` because there's at most one AAAA record per
# (subdomain, zone) tuple.
resource "hetznerdns_record" "brain_aaaa" {
  count   = var.enable_ipv6 ? 1 : 0
  zone_id = data.hetznerdns_zone.primary.id
  name    = var.dns_subdomain
  value   = hcloud_server.brain.ipv6_address
  type    = "AAAA"
  ttl     = 300
}
