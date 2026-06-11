variable "hcloud_token" {
  description = "Hetzner Cloud API token. Generate at https://console.hetzner.cloud → Project → Security → API Tokens. Required scope: Read + Write."
  type        = string
  sensitive   = true
}

variable "hetzner_dns_token" {
  description = "Hetzner DNS Console API token. Generate at https://dns.hetzner.com → API Tokens. Required scope: Read + Write."
  type        = string
  sensitive   = true
}

variable "server_name" {
  description = "Hostname for the Hetzner Cloud server (shown in the hcloud UI and used as the cloud-init hostname)."
  type        = string
  default     = "empire-brain"
}

variable "server_type" {
  description = "Hetzner Cloud server type. cx22 = 4 GB RAM, 2 vCPU (the size DEPLOY_HETZNER.md recommends for Kokoro + Ollama + PM2). cax21 is the ARM equivalent (slightly cheaper)."
  type        = string
  default     = "cx22"
}

variable "server_location" {
  description = "Hetzner Cloud location. fsn1=Falkenstein, nbg1=Nuremberg, hel1=Helsinki, ash=Ashburn VA, hil=Hillsboro OR."
  type        = string
  default     = "fsn1"
}

variable "server_image" {
  description = "OS image. DEPLOY_HETZNER.md uses ubuntu-22.04 LTS."
  type        = string
  default     = "ubuntu-22.04"
}

variable "ssh_public_key_path" {
  description = "Local path to the SSH public key to install on the server (default: ~/.ssh/id_ed25519.pub). The matching private key is what you'll use to ssh in."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}

variable "dns_zone" {
  description = "DNS zone — your registered domain (e.g. 'empire-ai.co.uk'). The zone MUST already exist in the Hetzner DNS Console (the module reads it via data source, it does not create zones)."
  type        = string
}

variable "dns_subdomain" {
  description = "Subdomain to create an A/AAAA record for (e.g. 'brain' → brain.empire-ai.co.uk). Leave empty to point the zone apex at the server."
  type        = string
  default     = "brain"
}

variable "enable_backups" {
  description = "Enable Hetzner Cloud daily backups (+20% cost). Recommended for production."
  type        = bool
  default     = true
}

# Note: Hetzner Cloud basic server monitoring is enabled by default on
# all servers and isn't exposed as a writable attribute in the hcloud
# Terraform provider, so there's no `enable_monitoring` variable to
# toggle. The AGI governor's staleness gate works against the
# /api/v1/governor/health endpoint, not Hetzner's monitoring.

variable "enable_ipv6" {
  description = "Enable IPv6 on the server (creates an AAAA record in addition to A)."
  type        = bool
  default     = true
}

variable "labels" {
  description = "Hetzner resource labels (key=value). Free-form, used for cost tracking and resource filtering in the Hetzner dashboard."
  type        = map(string)
  default = {
    project     = "empire-ai"
    environment = "production"
    managed-by  = "terraform"
  }
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into the server on port 22. Default: anywhere (lock down to your office/home IP for better security — e.g. ['203.0.113.42/32'])."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}
