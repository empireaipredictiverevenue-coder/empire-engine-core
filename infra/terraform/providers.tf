# Provider configurations. Tokens are read from terraform.tfvars (or
# the HCLOUD_TOKEN / HETZNER_DNS_TOKEN env vars). Sensitive variables
# should never be committed to git — use terraform.tfvars (gitignored)
# or `export HCLOUD_TOKEN=...` before `terraform apply`.
provider "hcloud" {
  token = var.hcloud_token
}

provider "hetznerdns" {
  api_token = var.hetzner_dns_token
}
