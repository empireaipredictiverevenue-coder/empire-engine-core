terraform {
  required_version = ">= 1.5.0"

  required_providers {
    # Official Hetzner Cloud provider — servers, firewalls, SSH keys, etc.
    hcloud = {
      source  = "hetznercloud/hcloud"
      version = "~> 1.45"
    }
    # Community provider for the Hetzner DNS Console (separate from hcloud).
    # Note: the official hcloud provider does NOT manage DNS (open issue #183),
    # so we need this separate provider. As of 2025-11 the germanbrew fork is
    # the de-facto standard; if Hetzner ever ships DNS in the official provider
    # we should switch.
    hetznerdns = {
      source  = "germanbrew/hetznerdns"
      version = "~> 3.0"
    }
  }
}
