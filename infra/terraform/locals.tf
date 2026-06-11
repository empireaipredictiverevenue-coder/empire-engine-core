locals {
  # Expand the user-supplied SSH key path (handles the ~ shorthand) and read
  # the public key into a string. If the file doesn't exist, terraform plan
  # fails fast with a clear error from file() — no silent misconfig.
  ssh_public_key = file(pathexpand(var.ssh_public_key_path))

  # The fully-qualified domain name the A/AAAA records will point at.
  # Empty subdomain → point the zone apex (e.g. "empire-ai.co.uk").
  fqdn = var.dns_subdomain == "" ? var.dns_zone : "${var.dns_subdomain}.${var.dns_zone}"
}
