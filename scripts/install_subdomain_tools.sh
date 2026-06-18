#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# install_subdomain_tools.sh — Install Go + All Subdomain Recon Tools
# ═══════════════════════════════════════════════════════════════════════════
# Installs:
#   - Go 1.22+ (from golang.org)
#   - subfinder     (passive subdomain enumeration)
#   - dnsx          (DNS resolution + validation)
#   - httpx         (HTTP probing + tech detection)
#   - nuclei        (template-based vulnerability scanner)
#   - naabu         (port scanning)
#   - subjack       (subdomain takeover detection)
#   - waybackurls    (historical URL discovery)
#   - unfurl        (URL parsing)
#
# Usage:
#   sudo ./scripts/install_subdomain_tools.sh
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[*]${NC} $1"; }
ok()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

# ── Detect OS + Arch ────────────────────────────────────────────────────
OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  ARCH_GO="amd64" ;;
    aarch64|arm64) ARCH_GO="arm64" ;;
    *)       err "Unsupported arch: $ARCH"; exit 1 ;;
esac

# ── 1. Install Go if missing ───────────────────────────────────────────
install_go() {
    if command -v go &>/dev/null; then
        local v
        v=$(go version | grep -oP 'go\K[0-9]+\.[0-9]+')
        info "Go already installed: $(go version)"
        return 0
    fi

    info "Installing Go 1.22.3 (${OS}_${ARCH_GO})..."

    local tarball="go1.22.3.${OS}-${ARCH_GO}.tar.gz"
    local url="https://go.dev/dl/${tarball}"

    curl -fsSL --max-time 120 --connect-timeout 15 "$url" -o "/tmp/${tarball}"
    curl -fsSL --max-time 30 "${url}.sha256" -o "/tmp/${tarball}.sha256" 2>/dev/null || \
        warn "No checksum file available — skipping verification"
    if [[ -f "/tmp/${tarball}.sha256" ]]; then
        (cd /tmp && sha256sum --quiet --check "${tarball}.sha256") || {
            err "Go tarball checksum mismatch! Aborting for safety."
            rm -f "/tmp/${tarball}" "/tmp/${tarball}.sha256"
            exit 1
        }
        ok "Go tarball checksum verified"
    fi
    tar -C /usr/local -xzf "/tmp/${tarball}"
    rm -f "/tmp/${tarball}" "/tmp/${tarball}.sha256"

    # Ensure /usr/local/go/bin is in PATH for this script
    export PATH="/usr/local/go/bin:${HOME}/go/bin:${PATH}"

    if command -v go &>/dev/null; then
        ok "Go installed: $(go version)"
    else
        err "Go installation failed"
        exit 1
    fi
}

# ── 2. Install Go-based tools ──────────────────────────────────────────
install_tool() {
    local name="$1" pkg="$2"
    info "Installing ${name}..."
    if command -v "$name" &>/dev/null; then
        ok "${name} already installed: $($name -version 2>/dev/null || $name --version 2>/dev/null || echo 'present')"
        return 0
    fi
    go install -v "${pkg}" 2>&1 | tail -1 || {
        warn "${name} install failed (non-critical, continuing)"
        return 1
    }
    if command -v "$name" &>/dev/null; then
        ok "${name} installed"
    else
        warn "${name} installed but not in PATH — check ~/go/bin"
    fi
}

# ── MAIN ────────────────────────────────────────────────────────────────
main() {
    if [[ $EUID -eq 0 ]]; then
        warn "Running as root. Go will be installed system-wide."
    fi

    echo "╔═══════════════════════════════════════════════════════════════╗"
    echo "║       Subdomain Tools Installer                              ║"
    echo "╚═══════════════════════════════════════════════════════════════╝"
    echo

    # Step 1: Install Go
    install_go

    # Ensure ~/go/bin exists
    mkdir -p "${HOME}/go/bin"
    export PATH="${HOME}/go/bin:/usr/local/go/bin:${PATH}"

    # Step 2: Install system deps (jq for crt.sh, libpcap for naabu)
    echo
    info "Installing system dependencies..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq 2>/dev/null || true
        apt-get install -y -qq jq libpcap-dev 2>/dev/null && \
            ok "System deps installed (jq, libpcap-dev)" || \
            warn "System dep install had issues — check manually if needed"
    else
        warn "apt-get not available — install jq + libpcap-dev manually"
    fi

    # Step 3: Install tools
    echo
    info "Installing subdomain recon tools..."
    echo

    install_tool "subfinder"   "github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest"
    install_tool "dnsx"        "github.com/projectdiscovery/dnsx/cmd/dnsx@latest"
    install_tool "httpx"       "github.com/projectdiscovery/httpx/cmd/httpx@latest"
    install_tool "nuclei"      "github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest"
    install_tool "naabu"       "github.com/projectdiscovery/naabu/v2/cmd/naabu@latest"
    install_tool "subjack"     "github.com/haccer/subjack@latest"
    install_tool "waybackurls" "github.com/tomnomnom/waybackurls@latest"
    install_tool "unfurl"      "github.com/tomnomnom/unfurl@latest"

    # Step 3: Verify all installed
    echo
    info "Verifying installations..."
    echo

    local all_ok=true
    for tool in subfinder dnsx httpx nuclei naabu subjack waybackurls unfurl; do
        if command -v "$tool" &>/dev/null; then
            ok "${tool}: found"
        else
            err "${tool}: NOT FOUND in PATH"
            all_ok=false
        fi
    done

    # Step 4: Update system PATH
    echo
    info "Adding ~/go/bin to system PATH..."
    local profile_file="/root/.bashrc"
    if ! grep -q 'export PATH="${HOME}/go/bin' "$profile_file" 2>/dev/null; then
        cat >> "$profile_file" << 'EOF'

# ── Go / Subdomain Tools ──────────────────────────────────────────
export PATH="${HOME}/go/bin:/usr/local/go/bin:${PATH}"
EOF
        ok "PATH updated in ${profile_file}"
    else
        info "PATH already configured"
    fi

    # Step 5: Download nuclei templates
    echo
    if command -v nuclei &>/dev/null; then
        info "Downloading nuclei templates (first run)..."
        local nuc_out
        nuc_out=$(nuclei -update-templates 2>&1) || {
            warn "Nuclei template download failed: $(echo "$nuc_out" | tail -1)"
        }
        ok "Nuclei ready"
    fi

    # ── Summary ─────────────────────────────────────────────────────
    echo
    echo -e "${GREEN}╔═══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  INSTALLATION COMPLETE                                       ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════════════════╝${NC}"
    echo

    local installed=0 missing=0
    for tool in subfinder dnsx httpx nuclei naabu subjack waybackurls unfurl; do
        if command -v "$tool" &>/dev/null; then
            ((installed++))
        else
            ((missing++))
        fi
    done

    echo "  Installed: ${installed}/8"
    echo "  Missing:   ${missing}"
    echo
    echo "  Run the validation workflow:"
    echo "    ./scripts/subdomain_validate.sh example.com"
    echo "    ./scripts/subdomain_validate.sh example.com --aggressive"
    echo "    ./scripts/subdomain_validate.sh example.com --monitor"
    echo
    echo "  Re-login or source ~/.bashrc to pick up PATH changes."
}

main "$@"
