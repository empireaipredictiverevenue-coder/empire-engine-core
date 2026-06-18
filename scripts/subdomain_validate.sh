#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════
# subdomain_validate.sh — Full-Spectrum Subdomain Validation Pipeline
# ═══════════════════════════════════════════════════════════════════════════
# Phases:
#   1. Passive enumeration  (subfinder + crt.sh + waybackurls)
#   2. DNS resolution        (dnsx — dedupe + resolve + CNAME capture)
#   3. HTTP probing          (httpx — status, title, tech, screenshot)
#   4. Takeover scan         (subjack + nuclei misconfig templates)
#   5. Port discovery        (naabu — non-standard web ports)
#   6. Vulnerability scan    (nuclei — filtered CVE/tech templates)
#   7. Diff & monitor        (compare against last run, alert on new)
#   8. Report                (JSON + HTML summary)
#
# Usage:
#   ./scripts/subdomain_validate.sh example.com
#   ./scripts/subdomain_validate.sh example.com --aggressive   # full port scan + all templates
#   ./scripts/subdomain_validate.sh example.com --monitor      # diff mode (compare with last run)
#   ./scripts/subdomain_validate.sh example.com --quick        # skip vuln scan, just validation## Dependencies (install via go install):
#   go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest
#   go install -v github.com/projectdiscovery/dnsx/cmd/dnsx@latest
#   go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest
#   go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest
#   go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest
#   go install -v github.com/haccer/subjack@latest
#   go install -v github.com/tomnomnom/waybackurls@latest
#   go install -v github.com/tomnomnom/unfurl@latest
#   Also need: jq (apt install jq)
#
# ═══════════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── CONFIG ──────────────────────────────────────────────────────────────
OUTPUT_BASE="${OUTPUT_DIR:-./recon}"
THREADS="${THREADS:-50}"
TIMEOUT="${TIMEOUT:-10}"
RATE_LIMIT="${RATE_LIMIT:-150}"        # requests/min for httpx/nuclei
RESOLVERS="${RESOLVERS:-/root/resolvers.txt}"

# Colors
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'  # No Color

# ── HELPER FUNCTIONS ───────────────────────────────────────────────────
info()  { echo -e "${CYAN}[*]${NC} $1"; }
ok()    { echo -e "${GREEN}[✓]${NC} $1"; }
warn()  { echo -e "${YELLOW}[!]${NC} $1"; }
err()   { echo -e "${RED}[✗]${NC} $1"; }

check_dep() {
    if ! command -v "$1" &>/dev/null; then
        err "Missing dependency: $1"
        warn "Install: go install -v github.com/projectdiscovery/$1/v2/cmd/$1@latest"
        return 1
    fi
}

banner() {
    cat << "BANNER"
╔═══════════════════════════════════════════════════════════════╗
║         Subdomain Validation Pipeline  v2.0                  ║
║     Passive → Resolve → Probe → Takeover → Scan → Report    ║
╚═══════════════════════════════════════════════════════════════╝
BANNER
}

phase_header() {
    local phase="$1" desc="$2"
    echo
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
    echo -e "${BLUE}  PHASE ${phase}: ${desc}${NC}"
    echo -e "${BLUE}══════════════════════════════════════════════════════${NC}"
}

# ── MAIN ───────────────────────────────────────────────────────────────
main() {
    local domain="" mode="standard"
    local do_vuln=true do_portscan=false do_monitor=false

    # Parse args
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --quick)     do_vuln=false ;;
            --aggressive) do_portscan=true ;;
            --monitor)   do_monitor=true ;;
            --help|-h)
                sed -n '3,22p' "$0"
                exit 0
                ;;
            *) domain="$1" ;;
        esac
        shift
    done

    if [[ -z "$domain" ]]; then
        err "No domain provided."
        echo "Usage: $0 <domain> [--quick|--aggressive|--monitor]"
        exit 1
    fi

    # ── Setup output directory ────────────────────────────────────────
    local start_time
    start_time=$(date +%s)
    local ts
    ts=$(date +%Y%m%d_%H%M%S)
    local outdir="${OUTPUT_BASE}/${domain}/${ts}"
    mkdir -p "$outdir"

    # If in monitor mode, also create a stable "latest" symlink
    if $do_monitor; then
        local monitor_dir="${OUTPUT_BASE}/${domain}/monitor"
        mkdir -p "$monitor_dir"
    fi

    local all_subs="${outdir}/01_all_subs.txt"
    local resolved="${outdir}/02_resolved.txt"
    local live_urls="${outdir}/03_live_urls.txt"
    local live_metadata="${outdir}/03_live_metadata.txt"
    local takeover_candidates="${outdir}/04_takeover_candidates.txt"
    local port_scan="${outdir}/05_portscan.txt"
    local nuclei_results="${outdir}/06_nuclei_results.txt"
    local final_report="${outdir}/report.json"

    banner
    info "Target:  ${domain}"
    info "Output:  ${outdir}"
    echo

    # ── Validate dependencies ─────────────────────────────────────────
    info "Checking dependencies..."
    local missing=0
    check_dep subfinder  || ((missing++))
    check_dep dnsx       || ((missing++))
    check_dep httpx      || ((missing++))
    check_dep subjack    || ((missing++))
    check_dep nuclei     || ((missing++))
    check_dep waybackurls || ((missing++))
    check_dep jq         || ((missing++))
    check_dep unfurl     || ((missing++))
    if [[ $missing -gt 0 ]]; then
        err "Missing $missing dependencies. Install them and re-run."
        exit 1
    fi
    ok "All core dependencies found."

    # ── PHASE 1: Passive Enumeration ─────────────────────────────────
    phase_header 1 "Passive Subdomain Enumeration"

    info "Running subfinder (passive sources)..."
    subfinder -d "$domain" -all -silent -o "${outdir}/.subfinder_raw.txt" 2>/dev/null
    local subfinder_count
    subfinder_count=$(wc -l < "${outdir}/.subfinder_raw.txt" 2>/dev/null || echo 0)
    ok "subfinder: ${subfinder_count} subdomains"

    info "Fetching crt.sh certificate transparency logs..."
    curl -s --max-time 30 --connect-timeout 10 "https://crt.sh/?q=%25.${domain}&output=json" 2>/dev/null \
        | jq -r '.[].name_value' 2>/dev/null \
        | sed 's/\*\.//g' \
        | sort -u \
        > "${outdir}/.crtsh_raw.txt" 2>/dev/null || touch "${outdir}/.crtsh_raw.txt"
    local crt_count
    crt_count=$(wc -l < "${outdir}/.crtsh_raw.txt" 2>/dev/null || echo 0)
    ok "crt.sh: ${crt_count} subdomains"

    info "Fetching waybackurls for historical URL discovery..."
    echo "$domain" | waybackurls 2>/dev/null \
        | unfurl domains 2>/dev/null \
        | grep -E "\.${domain}$" \
        | sort -u \
        > "${outdir}/.wayback_raw.txt" 2>/dev/null || touch "${outdir}/.wayback_raw.txt"
    local wayback_count
    wayback_count=$(wc -l < "${outdir}/.wayback_raw.txt" 2>/dev/null || echo 0)
    ok "waybackurls: ${wayback_count} subdomains"

    # Merge all sources, deduplicate
    sort -u "${outdir}/.subfinder_raw.txt" "${outdir}/.crtsh_raw.txt" "${outdir}/.wayback_raw.txt" \
        | grep -E "\.${domain}$" \
        | grep -vE "^\*|\s+" \
        | sed '/^$/d' \
        > "$all_subs"

    local total
    total=$(wc -l < "$all_subs")
    info "Total unique subdomains after dedup: ${total}"

    if [[ "$total" -eq 0 ]]; then
        warn "No subdomains found. Check domain or network."
        echo '{"status":"error","phase":"enumeration","reason":"no_subdomains_found"}' > "$final_report"
        exit 0
    fi

    # ── PHASE 2: DNS Resolution ──────────────────────────────────────
    phase_header 2 "DNS Resolution & CNAME Capture"

    info "Resolving ${total} subdomains with dnsx..."
    dnsx -l "$all_subs" \
        -a -aaaa -cname -resp \
        -concurrency "$THREADS" \
        -timeout "$TIMEOUT" \
        -o "${outdir}/.dnsx_verbose.txt" 2>/dev/null

    # Extract just the resolved hostnames
    awk '{print $1}' "${outdir}/.dnsx_verbose.txt" | sort -u > "$resolved"

    # Extract CNAME records (takeover candidates)
    grep -i "cname " "${outdir}/.dnsx_verbose.txt" \
        | awk '{print $1}' \
        | sort -u \
        > "${outdir}/.cname_hosts.txt" 2>/dev/null || true

    local resolved_count
    resolved_count=$(wc -l < "$resolved")
    ok "Resolved: ${resolved_count} live hosts"
    info "CNAME records found: $(wc -l < "${outdir}/.cname_hosts.txt")"

    # ── PHASE 3: HTTP Probing ────────────────────────────────────────
    phase_header 3 "HTTP Probing & Tech Detection"

    info "Probing resolved hosts with httpx..."
    httpx -l "$resolved" \
        -status-code -title -tech-detect -content-length \
        -follow-redirects -silent \
        -rate-limit "$RATE_LIMIT" \
        -threads "$THREADS" \
        -timeout "$TIMEOUT" \
        -o "$live_metadata" 2>/dev/null

    # Extract live URLs (both HTTP and HTTPS)
    awk '{print $1}' "$live_metadata" | sort -u > "$live_urls"

    local live_count
    live_count=$(wc -l < "$live_urls")
    ok "Live HTTP(S): ${live_count} endpoints"

    # Quick stats
    echo
    info "Status code breakdown:"
    awk '{print $2}' "$live_metadata" 2>/dev/null \
        | sort | uniq -c | sort -rn \
        | while read -r count code; do
            if [[ "$code" -eq 200 ]]; then echo -e "  ${GREEN}${code}${NC}: ${count}"
            elif [[ "$code" -eq 301 ]] || [[ "$code" -eq 302 ]]; then echo -e "  ${YELLOW}${code}${NC}: ${count}"
            elif [[ "$code" -eq 403 ]] || [[ "$code" -eq 401 ]]; then echo -e "  ${RED}${code}${NC}: ${count}"
            else echo -e "  ${CYAN}${code}${NC}: ${count}"
            fi
        done 2>/dev/null || true

    # ── PHASE 4: Subdomain Takeover Detection ────────────────────────
    phase_header 4 "Subdomain Takeover Detection"

    info "Running subjack on resolved hosts..."
    subjack -w "$resolved" \
        -t "$THREADS" \
        -timeout "$TIMEOUT" \
        -ssl \
        -o "${outdir}/.subjack_raw.txt" 2>/dev/null || true

    # Also run nuclei takeover templates
    info "Running nuclei takeover templates..."
    nuclei -l "$live_urls" \
        -t ~/nuclei-templates/http/takeovers/ \
        -silent \
        -rate-limit "$RATE_LIMIT" \
        -o "${outdir}/.nuclei_takeover.txt" 2>/dev/null || true

    # Merge takeover candidates
    {
        cat "${outdir}/.subjack_raw.txt" 2>/dev/null || true
        grep -iE "vulnerable|takeover|dangling" "${outdir}/.nuclei_takeover.txt" 2>/dev/null || true
    } | sort -u > "$takeover_candidates"

    local takeover_count
    takeover_count=$(wc -l < "$takeover_candidates" 2>/dev/null || echo 0)

    if [[ "$takeover_count" -gt 0 ]]; then
        warn "⚠  ${takeover_count} potential takeover(s) found!"
        cat "$takeover_candidates"
    else
        ok "No obvious subdomain takeovers detected"
    fi

    # ── PHASE 5: Port Discovery (aggressive only) ────────────────────
    if $do_portscan; then
        phase_header 5 "Port Discovery (naabu)"

        info "Scanning top 1000 ports on resolved IPs..."
        # Extract IPv4 addresses from dnsx output (format: hostname [A 1.2.3.4] [AAAA ::1])
        grep -oP '\b[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\b' \
            "${outdir}/.dnsx_verbose.txt" 2>/dev/null \
            | sort -u \
            > "${outdir}/.ips.txt" 2>/dev/null || true

        if [[ -s "${outdir}/.ips.txt" ]]; then
            naabu -l "${outdir}/.ips.txt" \
                -top-ports 1000 \
                -rate "$RATE_LIMIT" \
                -silent \
                -o "$port_scan" 2>/dev/null || true
            ok "Port scan complete: $(wc -l < "$port_scan") open ports"
        else
            warn "No IPs to scan"
        fi
    fi

    # ── PHASE 6: Vulnerability Scanning ──────────────────────────────
    if $do_vuln; then
        phase_header 6 "Targeted Vulnerability Scanning"

        # Focused template categories — noise-reduced
        local templates=(
            "cves/"
            "misconfiguration/"
            "exposed-panels/"
            "exposures/"
            "default-login/"
        )

        for t in "${templates[@]}"; do
            local template_path="${HOME}/nuclei-templates/${t}"
            if [[ -d "$template_path" ]]; then
                info "Scanning: ${t}"
                nuclei -l "$live_urls" \
                    -t "$template_path" \
                    -severity low,medium,high,critical \
                    -rate-limit "$RATE_LIMIT" \
                    -concurrency "$THREADS" \
                    -silent \
                    -o "${outdir}/.nuclei_${t//\//_}.txt" 2>/dev/null || true
            fi
        done

        # Merge all nuclei results
        cat "${outdir}"/.nuclei_*.txt 2>/dev/null | sort -u > "$nuclei_results" || true

        local vuln_count
        vuln_count=$(wc -l < "$nuclei_results" 2>/dev/null || echo 0)
        info "Nuclei findings: ${vuln_count}"

        # Severity breakdown
        if [[ -s "$nuclei_results" ]]; then
            echo
            info "Findings by severity:"
            grep -oP '\[(low|medium|high|critical)\]' "$nuclei_results" 2>/dev/null \
                | tr '[:upper:]' '[:lower:]' \
                | sort | uniq -c | sort -rn \
                | while read -r count sev; do
                    case "$sev" in
                        critical) echo -e "  ${RED}critical${NC}: ${count}" ;;
                        high)     echo -e "  ${RED}high${NC}: ${count}" ;;
                        medium)   echo -e "  ${YELLOW}medium${NC}: ${count}" ;;
                        low)      echo -e "  ${CYAN}low${NC}: ${count}" ;;
                    esac
                done 2>/dev/null || true
        fi
    fi

    # ── PHASE 7: Diff & Monitoring (monitor mode) ────────────────────
    if $do_monitor; then
        phase_header 7 "Diff Analysis (Monitor Mode)"

        local prev_subs="${monitor_dir}/latest_subs.txt"
        local new_subs="${monitor_dir}/new_subs_${ts}.txt"

        if [[ -f "$prev_subs" ]]; then
            comm -13 <(sort "$prev_subs") <(sort "$all_subs") > "$new_subs"
            local new_count
            new_count=$(wc -l < "$new_subs" 2>/dev/null || echo 0)

            if [[ "$new_count" -gt 0 ]]; then
                warn "⚠  ${new_count} new subdomain(s) since last run!"
                cat "$new_subs"
            else
                ok "No new subdomains — landscape stable"
            fi
        else
            info "No previous snapshot. Saving baseline..."
            cp "$all_subs" "$prev_subs"
        fi

        # Save snapshot for next run's diff
        cp "$all_subs" "${monitor_dir}/latest_subs.txt"
    fi

    # ── PHASE 8: Generate Report ─────────────────────────────────────
    phase_header 8 "Report Generation"

    # Build JSON report
    cat > "$final_report" << JSONEOF
{
  "scan": {
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "target": "$domain",
    "mode": "$mode",
    "duration_seconds": $(( $(date +%s) - start_time ))
  },
  "stats": {
    "subdomains_found": $total,
    "dns_resolved": $resolved_count,
    "live_http": $live_count,
    "takeover_candidates": $takeover_count,
    "vulnerabilities_found": $(wc -l < "$nuclei_results" 2>/dev/null || echo 0)
  },
  "files": {
    "all_subs": "$all_subs",
    "resolved": "$resolved",
    "live_metadata": "$live_metadata",
    "takeover_candidates": "$takeover_candidates",
    "nuclei_results": "$nuclei_results"
  }
}
JSONEOF

    ok "Report written: ${final_report}"

    # ── Summary ─────────────────────────────────────────────────────
    echo
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  SCAN COMPLETE${NC}"
    echo -e "${GREEN}══════════════════════════════════════════════════════${NC}"
    echo -e "  Target:      ${CYAN}${domain}${NC}"
    echo -e "  Subdomains:  ${total}"
    echo -e "  Resolved:    ${resolved_count}"
    echo -e "  Live HTTP:   ${live_count}"
    echo -e "  Takeovers:   ${takeover_count}"
    if [[ -s "$nuclei_results" ]]; then
        echo -e "  Findings:    $(wc -l < "$nuclei_results")"
    fi
    echo -e "  Output:      ${YELLOW}${outdir}${NC}"
    echo

    # ⚠  Alert on high-severity findings
    if [[ -s "$nuclei_results" ]]; then
        local high_crit
        high_crit=$(grep -cE '\[(high|critical)\]' "$nuclei_results" 2>/dev/null || echo 0)
        if [[ "$high_crit" -gt 0 ]]; then
            warn "⚠  ${high_crit} HIGH/CRITICAL finding(s) detected — review immediately!"
        fi
    fi

    if [[ "$takeover_count" -gt 0 ]]; then
        warn "⚠  ${takeover_count} potential subdomain takeover(s) found — claim before someone else does!"
    fi
}

# ── ENTRY POINT ─────────────────────────────────────────────────────────
main "$@"
