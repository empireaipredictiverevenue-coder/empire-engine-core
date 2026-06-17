"""
EMPIRE V49 · PRODUCT: ANALYZER AGENT
======================================
OSINT & reconnaissance Suite product. Wraps installed open-source tools
(holehe, maigret, phoneinfoga, shodan, social-analyzer, spiderfoot, recon-ng)
into a productized
API with tier-based limits, usage metering, and intelligence reports.

Tiers:
  ANALYZER_LITE       — $49/mo,  100 checks/mo, email + phone recon
  ANALYZER_GROWTH     — $149/mo, 500 checks/mo, + social presence + Google intel
  ANALYZER_ENTERPRISE — $399/mo, unlimited, + deep OSINT + Shodan scanning

Integration:
    engine = AnalyzerEngine(get_db, guard, log_usage)
    result = await engine.analyze(account_id, lead_data)
    report = await engine.report(account_id)
"""

import asyncio
import json
import logging
import os
import subprocess
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.analyzer")

# ── Tier limits (operations per month) ───────────────────────────────
_TIER_LIMITS = {
    "ANALYZER_LITE": {
        "max_ops": 100,
        "tools": ["holehe", "phoneinfoga"],
        "deep_osint": False,
        "shodan_access": False,
        "social_search": False,
    },
    "ANALYZER_GROWTH": {
        "max_ops": 500,
        "tools": ["holehe", "phoneinfoga", "maigret", "ghunt"],
        "deep_osint": False,
        "shodan_access": False,
        "social_search": True,
    },
    "ANALYZER_ENTERPRISE": {
        "max_ops": 0,  # unlimited
        "tools": ["holehe", "phoneinfoga", "maigret", "ghunt", "social-analyzer", "spiderfoot", "recon-ng", "betterleaks", "gef", "atomic-operator", "wpprobe", "xsstrike", "sstimap"],
        "deep_osint": True,
        "shodan_access": True,
        "social_search": True,
        "secrets_scan": True,
        "binary_analysis": True,
        "adversary_emulation": True,
        "wordpress_scan": True,
        "xss_scan": True,
        "ssti_scan": True,
    },
}


class AnalyzerEngine:
    """
    OSINT intelligence engine. Runs lightweight open-source tools against
    leads/contacts and returns structured intelligence reports.

    Integration with Suite Gateway:
      - guard(account_id, "analyzer") -> {"ok": bool, "tier": str, ...}
      - log_usage(account_id, "analyzer", "analyze", quantity=1)
    """

    def __init__(
        self,
        get_db: Callable,
        guard: Optional[Callable] = None,       # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,    # SuiteGuard.log_usage
    ):
        self._get_db = get_db
        self.guard = guard
        self.log_usage = log_usage
        self.stats = {
            "analyses": 0,
            "blocked": 0,
            "errors": 0,
            "tools_run": {},
        }
        # In-memory result log per account
        self._account_results: dict[str, list[dict]] = {}

    # ── ENTITLEMENT ──────────────────────────────────────────────────

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has Analyzer access."""
        if not self.guard:
            return {"ok": True, "tier": "ANALYZER_GROWTH",
                    "limits": _TIER_LIMITS["ANALYZER_GROWTH"]}
        result = self.guard(account_id, "analyzer")
        if not result.get("ok"):
            return result
        tier = result.get("tier", "ANALYZER_LITE")
        return {
            "ok": True,
            "tier": tier,
            "limits": _TIER_LIMITS.get(tier, _TIER_LIMITS["ANALYZER_LITE"]),
        }

    def _get_tier_limits(self, tier: str) -> dict:
        return _TIER_LIMITS.get(tier, _TIER_LIMITS["ANALYZER_LITE"])

    def _tool_allowed(self, tier: str, tool: str) -> bool:
        """Check if a tool is allowed for the given tier."""
        limits = self._get_tier_limits(tier)
        return tool in limits.get("tools", [])

    # ── TOOL RUNNERS ─────────────────────────────────────────────────

    async def _run_holehe(self, email: str) -> dict:
        """Check email registration on 120+ platforms using holehe."""
        result = {"tool": "holehe", "target": email, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "holehe", email, "--no-color", "--only-used",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode() if stdout else ""
            for line in output.split("\n"):
                line = line.strip()
                if "[+]" in line:
                    # [+] Email is registered on: platform
                    parts = line.split(":", 1)
                    platform = parts[1].strip() if len(parts) > 1 else line
                    result["findings"].append({
                        "type": "email_registered",
                        "platform": platform,
                        "detail": line,
                    })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["holehe"] = self.stats["tools_run"].get("holehe", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
            log.debug(f"[analyzer] holehe failed: {e}")
        return result

    async def _run_phoneinfoga(self, phone: str) -> dict:
        """Validate phone number and get carrier info."""
        result = {"tool": "phoneinfoga", "target": phone, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "phoneinfoga", "scan", "-n", phone,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode() if stdout else ""
            # Parse basic phone info
            for line in output.split("\n"):
                line = line.strip()
                if "Country:" in line or "Carrier:" in line or "Line type:" in line:
                    result["findings"].append({
                        "type": "phone_info",
                        "detail": line,
                    })
            result["count"] = len(result["findings"])
            # Fallback: basic validation even if CLI output is minimal
            if not result["findings"]:
                cleaned = phone.replace("+", "").replace("-", "").replace(" ", "")
                valid = len(cleaned) >= 10 and len(cleaned) <= 15
                result["findings"].append({
                    "type": "phone_validated",
                    "detail": f"Phone {phone}: valid={valid}, digits={len(cleaned)}",
                })
                result["count"] = 1
            self.stats["tools_run"]["phoneinfoga"] = self.stats["tools_run"].get("phoneinfoga", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_maigret(self, username: str) -> dict:
        """Search username across 3000+ sites."""
        result = {"tool": "maigret", "target": username, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "maigret", username, "--json", "--timeout", "5",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode() if stdout else ""
            if output.strip():
                try:
                    data = json.loads(output)
                    sites = data.get("sites", {}) if isinstance(data, dict) else {}
                    for site, info in sites.items():
                        if isinstance(info, dict) and info.get("status") == "found":
                            result["findings"].append({
                                "type": "social_profile",
                                "platform": site,
                                "url": info.get("url", ""),
                                "username": info.get("username", username),
                            })
                except json.JSONDecodeError:
                    pass
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["maigret"] = self.stats["tools_run"].get("maigret", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_shodan(self, query: str) -> dict:
        """Search Shodan for internet-connected devices."""
        result = {"tool": "shodan", "target": query, "findings": [], "status": "completed"}
        try:
            api_key = os.environ.get("SHODAN_API_KEY", "")
            if not api_key:
                result["status"] = "skipped"
                result["error"] = "SHODAN_API_KEY not configured"
                return result
            proc = await asyncio.create_subprocess_exec(
                "shodan", "search", "--limit", "5", query,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode() if stdout else ""
            for line in output.split("\n"):
                line = line.strip()
                if line and not line.startswith("Search Query"):
                    result["findings"].append({
                        "type": "device",
                        "detail": line[:200],
                    })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["shodan"] = self.stats["tools_run"].get("shodan", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_ghunt(self, email: str) -> dict:
        """Check Google account presence.
        Note: GHunt requires a pre-authenticated token.json cookie file at
        ~/.config/ghunt/token.json. Without it, the tool will return an error.
        """
        result = {"tool": "ghunt", "target": email, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "ghunt", "email", email, "--json",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode() if stdout else ""
            if output.strip():
                try:
                    data = json.loads(output)
                    for key, val in (data.items() if isinstance(data, dict) else {}):
                        if val:
                            result["findings"].append({
                                "type": "google_presence",
                                "key": key,
                                "detail": str(val)[:200],
                            })
                except json.JSONDecodeError:
                    pass
            # Fallback if no JSON parse
            if not result["findings"] and output.strip():
                result["findings"].append({
                    "type": "google_raw",
                    "detail": output[:300],
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["ghunt"] = self.stats["tools_run"].get("ghunt", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_social_analyzer(self, username: str) -> dict:
        """Check username presence on social media across 1000+ sites using social-analyzer."""
        result = {"tool": "social-analyzer", "target": username, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "social-analyzer", "--username", username,
                "--output", "json", "--filter", "good",
                "--mode", "fast", "--top", "50",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
            output = stdout.decode() if stdout else ""
            if output.strip():
                try:
                    data = json.loads(output)
                    entries = data if isinstance(data, list) else [data]
                    for entry in entries:
                        if isinstance(entry, dict):
                            platform = entry.get("website", entry.get("url", ""))
                            status_info = entry.get("status", "good")
                            result["findings"].append({
                                "type": "social_media_profile",
                                "platform": platform[:60],
                                "status": status_info,
                                "detail": str(entry)[:200],
                            })
                except json.JSONDecodeError:
                    # Fallback: extract lines with detected profiles
                    for line in output.split("\n"):
                        line = line.strip()
                        if line and ("detected" in line.lower() or "> " in line):
                            result["findings"].append({
                                "type": "profile_detected",
                                "detail": line[:200],
                            })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["social-analyzer"] = self.stats["tools_run"].get("social-analyzer", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_spiderfoot(self, target: str) -> dict:
        """Run SpiderFoot passive OSINT scan against a domain or IP address.
        Runs sf.py as a one-shot scan with passive modules.
        """
        result = {"tool": "spiderfoot", "target": target, "findings": [], "status": "completed"}
        try:
            spiderfoot_dir = "/tmp/spiderfoot"
            proc = await asyncio.create_subprocess_exec(
                "python3", f"{spiderfoot_dir}/sf.py",
                "-s", target,
                "-t", "INTERNET_NAME,DOMAIN_NAME,IP_ADDRESS,EMAIL_ADDRESS,SOCIAL_MEDIA,WEBSERVER_BANNER,SSL_CERTIFICATE_ISSUED,WHOIS",
                "-o", "json",
                "-q",  # quiet mode
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=spiderfoot_dir,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode() if stdout else ""
            if output.strip():
                try:
                    data = json.loads(output)
                    entries = data if isinstance(data, list) else [data]
                    for entry in entries:
                        if isinstance(entry, dict):
                            result["findings"].append({
                                "type": entry.get("type", "osint_finding"),
                                "module": entry.get("module", ""),
                                "data": str(entry.get("data", ""))[:200],
                                "confidence": entry.get("confidence", ""),
                            })
                except json.JSONDecodeError:
                    # Try line-by-line JSON (each line is a separate JSON object)
                    for line in output.split("\n"):
                        line = line.strip()
                        if line.startswith("{"):
                            try:
                                entry = json.loads(line)
                                result["findings"].append({
                                    "type": entry.get("type", "osint_finding"),
                                    "module": entry.get("module", ""),
                                    "data": str(entry.get("data", ""))[:200],
                                })
                            except json.JSONDecodeError:
                                pass
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["spiderfoot"] = self.stats["tools_run"].get("spiderfoot", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_betterleaks(self, target: str, scan_mode: str = "dir") -> dict:
        """Scan a directory or git repo for hardcoded secrets using BetterLeaks.
        Detects API keys, tokens, passwords, credentials in source code.
        scan_mode: "dir" scans a local directory, "git" scans git history.
        """
        result = {"tool": "betterleaks", "target": target, "findings": [], "status": "completed"}
        try:
            if scan_mode == "git":
                proc = await asyncio.create_subprocess_exec(
                    "betterleaks", "git", target,
                    "--report-format", "json", "--report-path", "-",
                    "-v",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            else:
                proc = await asyncio.create_subprocess_exec(
                    "betterleaks", "dir", target,
                    "--report-format", "json", "--report-path", "-",
                    "-v",
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode() if stdout else ""
            # Try to parse JSON output (--report-path - writes to stdout)
            if output.strip():
                try:
                    data = json.loads(output)
                    entries = data if isinstance(data, list) else [data]
                    for entry in entries:
                        if isinstance(entry, dict):
                            result["findings"].append({
                                "type": entry.get("rule_id", "secret_detected"),
                                "severity": "high",
                                "file": entry.get("file", ""),
                                "line": entry.get("start_line", entry.get("line", 0)),
                                "match": str(entry.get("match", ""))[:100],
                                "description": entry.get("description", entry.get("message", "")),
                            })
                except (json.JSONDecodeError, Exception):
                    # Fallback: parse line-by-line for secret mentions
                    for line in output.split("\n"):
                        line = line.strip()
                        if line and ("secret" in line.lower() or "key" in line.lower()
                                     or "token" in line.lower() or "credential" in line.lower()):
                            result["findings"].append({
                                "type": "secret_mentioned",
                                "detail": line[:200],
                            })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["betterleaks"] = self.stats["tools_run"].get("betterleaks", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_gef(self, binary_path: str) -> dict:
        """Analyze binary security protections using GDB with GEF (GDB Enhanced Features).
        Runs checksec to detect enabled security mitigations (Canary, NX, PIE, RELRO, Fortify).
        """
        result = {"tool": "gef", "target": binary_path, "findings": [], "status": "completed"}
        try:
            # Find GEF script dynamically (avoids version-locked paths)
            import glob
            gef_candidates = glob.glob(os.path.expanduser("~/.gef-*.py"))
            gef_script = gef_candidates[0] if gef_candidates else os.path.expanduser("~/.gdbinit-gef.py")
            if not os.path.isfile(gef_script):
                result["status"] = "skipped"
                result["error"] = "GEF script not found"
                return result
            proc = await asyncio.create_subprocess_exec(
                "gdb", "-nx", "-batch",
                "-ex", f"source {gef_script}",
                "-ex", "checksec",
                "-ex", "quit",
                binary_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = stdout.decode() if stdout else ""
            # Parse checksec output — it's a table with protection name + status
            for line in output.split("\n"):
                line = line.strip()
                # Match lines like: "Canary    : ✘" or "NX        : ✓"
                for prot in ["Canary", "NX", "PIE", "Fortify", "RelRO", "ASLR", "SafeSEH", "GS" ]:
                    if line.startswith(prot) and ":" in line:
                        status_char = line.split(":", 1)[1].strip()
                        enabled = "✓" in status_char or "enabled" in status_char.lower()
                        result["findings"].append({
                            "type": "binary_protection",
                            "protection": prot,
                            "enabled": enabled,
                            "detail": line,
                        })
            # Add file info from GDB
            if not result["findings"]:
                # Fallback: just note the binary was analyzed
                result["findings"].append({
                    "type": "binary_info",
                    "detail": f"Binary analyzed with GEF: {binary_path}",
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["gef"] = self.stats["tools_run"].get("gef", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_file_analysis(self, binary_path: str) -> dict:
        """Extract binary metadata using the `file` command: architecture, OS, format, linking, etc.
        Run alongside GEF checksec for complementary structural analysis.
        """
        result = {"tool": "file_analysis", "target": binary_path, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "file", "-b", "-L", binary_path,  # -b = brief (no filename), -L = follow symlinks
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            description = (stdout.decode() if stdout else "").strip()

            if description:
                result["findings"].append({
                    "type": "file_description",
                    "detail": description,
                })

                # Parse structured metadata from the description
                metadata: dict[str, str] = {}

                if "ELF" in description:
                    metadata["format"] = "ELF"
                    if "64-bit" in description:
                        metadata["architecture_width"] = "64-bit"
                    elif "32-bit" in description:
                        metadata["architecture_width"] = "32-bit"
                    metadata["endianness"] = "little-endian" if "LSB" in description else "big-endian"

                    for arch in ["x86-64", "i386", "ARM", "AArch64", "MIPS", "PowerPC", "RISC-V"]:
                        if arch in description:
                            metadata["architecture"] = arch
                            break

                    if "executable" in description:
                        metadata["type"] = "executable"
                    elif "shared object" in description.lower():
                        metadata["type"] = "shared_library"
                    elif "relocatable" in description:
                        metadata["type"] = "relocatable_object"
                    elif "core file" in description.lower():
                        metadata["type"] = "core_dump"

                    if "dynamically linked" in description:
                        metadata["linking"] = "dynamic"
                    elif "statically linked" in description:
                        metadata["linking"] = "static"

                    import re
                    m = re.search(r"interpreter\s+(\S+)", description)
                    if m:
                        metadata["interpreter"] = m.group(1)

                elif "PE" in description or "PE32" in description:
                    metadata["format"] = "PE"
                    metadata["architecture_width"] = "64-bit" if ("64-bit" in description or "PE32+" in description) else "32-bit"
                    for arch in ["x86-64", "i386", "ARM", "AArch64"]:
                        if arch in description:
                            metadata["architecture"] = arch
                            break
                    metadata["type"] = "executable" if "executable" in description else "dynamic_library"

                elif "Mach-O" in description:
                    metadata["format"] = "Mach-O"
                    metadata["architecture_width"] = "64-bit" if "64-bit" in description else "32-bit"
                    for arch in ["x86-64", "i386", "ARM", "AArch64"]:
                        if arch in description:
                            metadata["architecture"] = arch
                            break
                    if "executable" in description:
                        metadata["type"] = "executable"
                    elif "bundle" in description.lower():
                        metadata["type"] = "bundle"
                    elif "dylib" in description.lower():
                        metadata["type"] = "dynamic_library"

                elif "script" in description.lower() or "text" in description.lower():
                    for lang in ["Python", "Bash", "Perl", "Ruby", "POSIX shell", "AWK"]:
                        if lang in description:
                            metadata["scripting_language"] = lang
                            metadata["type"] = "script"
                            break

                for key, value in metadata.items():
                    result["findings"].append({
                        "type": "binary_metadata",
                        "key": key,
                        "value": value,
                    })

                # Get MIME type
                mime_proc = await asyncio.create_subprocess_exec(
                    "file", "-b", "--mime-type", binary_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                mime_stdout, _ = await asyncio.wait_for(mime_proc.communicate(), timeout=5)
                mime_type = (mime_stdout.decode() if mime_stdout else "").strip()
                if mime_type:
                    result["findings"].append({
                        "type": "binary_metadata",
                        "key": "mime_type",
                        "value": mime_type,
                    })

            result["count"] = len(result["findings"])
            self.stats["tools_run"]["file_analysis"] = self.stats["tools_run"].get("file_analysis", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_wpprobe(self, url: str) -> dict:
        """Scan a WordPress site for installed plugins and known vulnerabilities using WPProbe.
        Uses stealthy REST API enumeration to detect plugins and map CVEs.
        """
        result = {"tool": "wpprobe", "target": url, "findings": [], "status": "completed"}
        try:
            # Create a temp file for JSON output
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as tmp:
                tmp_path = tmp.name
            proc = await asyncio.create_subprocess_exec(
                "wpprobe", "scan", "-u", url,
                "-o", tmp_path, "-m", "stealthy",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            # Read JSON output file
            if os.path.isfile(tmp_path):
                with open(tmp_path, "r") as f:
                    raw = f.read()
                os.unlink(tmp_path)
                if raw.strip():
                    try:
                        data = json.loads(raw)
                        plugins = data.get("plugins", {}) if isinstance(data, dict) else {}
                        for plugin_name, plugin_data in plugins.items():
                            if isinstance(plugin_data, dict):
                                for severity in ["critical", "high", "medium", "low"]:
                                    cvss = plugin_data.get(severity, [])
                                    if cvss:
                                        for cve in cvss if isinstance(cvss, list) else [cvss]:
                                            result["findings"].append({
                                                "type": "wordpress_vulnerability",
                                                "plugin": plugin_name,
                                                "severity": severity,
                                                "cve": str(cve)[:100],
                                            })
                            else:
                                result["findings"].append({
                                    "type": "wordpress_plugin",
                                    "plugin": plugin_name,
                                    "detail": str(plugin_data)[:200],
                                })
                    except (json.JSONDecodeError, Exception):
                        pass
            # Fallback: parse stdout for any findings
            output = (stdout.decode() if stdout else "") + (stderr.decode() if stderr else "")
            detected_plugins = [line for line in output.split("\n")
                               if "plugin" in line.lower() and "detected" in line.lower()]
            for line in detected_plugins:
                result["findings"].append({
                    "type": "plugin_detected",
                    "detail": line[:200],
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["wpprobe"] = self.stats["tools_run"].get("wpprobe", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_xsstrike(self, url: str) -> dict:
        """Scan a URL for Cross-Site Scripting (XSS) vulnerabilities using XSStrike.
        Detects reflected XSS, identifies WAF presence and reflection points.
        """
        result = {"tool": "xsstrike", "target": url, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "xsstrike", "-u", url, "--skip", "--skip-dom",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode() if stdout else ""
            # Parse output for findings
            output_lines = output.split("\n")
            waf_detected = False
            for line in output_lines:
                line = line.strip()
                # XSStrike uses bracketed tags: [+] VULNERABLE, [!] Testing, [-] WAF
                if "[+]" in line:
                    # XSS vulnerability found
                    result["findings"].append({
                        "type": "xss_vulnerability",
                        "severity": "critical",
                        "detail": line,
                    })
                elif "WAF" in line and "detected" in line.lower():
                    waf_detected = True
                    result["findings"].append({
                        "type": "waf_detected",
                        "severity": "info",
                        "detail": line,
                    })
                elif "reflection" in line.lower() and "found" in line.lower():
                    result["findings"].append({
                        "type": "reflection_point",
                        "severity": "medium",
                        "detail": line,
                    })
            # If no findings, note the scan completed
            if not result["findings"] and output.strip():
                waf_note = f" (WAF detected)" if waf_detected else ""
                result["findings"].append({
                    "type": "xss_scan_complete",
                    "severity": "info",
                    "detail": f"No XSS vulnerabilities detected{waf_note}",
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["xsstrike"] = self.stats["tools_run"].get("xsstrike", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_sstimap(self, url: str) -> dict:
        """Scan a URL for Server-Side Template Injection (SSTI) vulnerabilities using SSTIMap.
        Tests Jinja2, Twig, OGNL, Freemarker, and other template engines for injection.
        """
        result = {"tool": "sstimap", "target": url, "findings": [], "status": "completed"}
        try:
            proc = await asyncio.create_subprocess_exec(
                "sstimap", "-u", url, "--no-color", "--batch",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=90)
            output = stdout.decode() if stdout else ""
            # Parse output for findings
            engine_detected = None
            for line in output.split("\n"):
                line = line.strip()
                # SSTI vulnerability confirmed
                if "[+]" in line or "VULNERABLE" in line.upper():
                    if "SSTI" in line or "injectable" in line.lower():
                        result["findings"].append({
                            "type": "ssti_vulnerability",
                            "severity": "critical",
                            "detail": line,
                        })
                # Engine detection (Jinja2, Twig, OGNL, Freemarker)
                if "plugin is testing" in line.lower() and "rendering" in line.lower():
                    # Extract engine name
                    engine_part = line.split("plugin")[0].strip() if "plugin" in line else ""
                    if engine_part and not engine_detected:
                        engine_detected = engine_part
                        result["findings"].append({
                            "type": "template_engine_tested",
                            "severity": "info",
                            "engine": engine_part,
                            "detail": line,
                        })
                # Injection point found
                if "parameter" in line.lower() and ("injectable" in line.lower() or "testing" in line.lower()):
                    result["findings"].append({
                        "type": "injection_point",
                        "severity": "medium",
                        "detail": line,
                    })
            # If no vulnerabilities found, note the scan completed
            if not result["findings"] and output.strip():
                engine_note = f" (engine: {engine_detected})" if engine_detected else ""
                result["findings"].append({
                    "type": "ssti_scan_complete",
                    "severity": "info",
                    "detail": f"No SSTI vulnerabilities detected{engine_note}",
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["sstimap"] = self.stats["tools_run"].get("sstimap", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_atomic_operator(self, query: str) -> dict:
        """Search MITRE ATT&CK techniques using Atomic Operator.
        Searches the Atomic Red Team library for adversary techniques matching a
        keyword or technique ID (e.g., T1059, "credential access", "persistence").
        """
        result = {"tool": "atomic-operator", "target": query, "findings": [], "status": "completed"}
        try:
            # Run with ATOMIC_RED_TEAM_PATH pointing to downloaded atomics
            env = {**os.environ, "ATOMIC_RED_TEAM_PATH": "/tmp/AtomicRedTeam"}
            proc = await asyncio.create_subprocess_exec(
                "atomic-operator", "search", query,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd="/tmp",
                env=env,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
            output = stdout.decode() if stdout else ""
            # Parse table output: Technique ID | Technique Name | Test | Found In
            for line in output.split("\n"):
                line = line.strip()
                # Skip headers and separators
                if not line or "Technique" in line or "---" in line or "INFO" in line or "WARNING" in line:
                    continue
                # Parse table rows
                parts = [p.strip() for p in line.split("|")]
                if len(parts) >= 2:
                    technique_id = parts[0]
                    technique_name = parts[1] if len(parts) > 1 else ""
                    test_name = parts[2] if len(parts) > 2 else ""
                    result["findings"].append({
                        "type": "mitre_technique",
                        "technique_id": technique_id,
                        "technique_name": technique_name[:100],
                        "test": test_name[:200],
                        "source": parts[3].strip() if len(parts) > 3 else "",
                    })
            if not result["findings"] and output.strip():
                # Fallback: return raw output as a finding
                result["findings"].append({
                    "type": "atomic_search_raw",
                    "detail": output[:500],
                })
            result["count"] = len(result["findings"])
            self.stats["tools_run"]["atomic-operator"] = self.stats["tools_run"].get("atomic-operator", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    async def _run_recon_ng(self, target: str) -> dict:
        """Run Recon-ng reconnaissance using recon-cli.
        Runs the whois_poc and dns_srv_spider modules on a domain.
        """
        result = {"tool": "recon-ng", "target": target, "findings": [], "status": "completed"}
        try:
            recon_dir = "/tmp/recon-ng"
            # Create workspace, add target, run modules
            cmd = (f"cd {recon_dir} && "
                   f"python3 recon-cli -w analyzer_workspace -x "
                   f"'db insert domains {target}' "
                   f"-m recon/domains-hosts/bing_domain_web -x "
                   f"-m recon/domains-hosts/google_site_web -x "
                   f"-m recon/domains-contacts/whois_pocs -x "
                   f"-m recon/contacts-domains/migrate_contacts -x")
            proc = await asyncio.create_subprocess_exec(
                "bash", "-c", cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
            output = stdout.decode() if stdout else ""
            result["findings"].append({
                "type": "recon_complete",
                "detail": output[:500],
            })
            result["count"] = 1
            self.stats["tools_run"]["recon-ng"] = self.stats["tools_run"].get("recon-ng", 0) + 1
        except Exception as e:
            result["status"] = "error"
            result["error"] = str(e)[:200]
        return result

    # ── MAIN ANALYZE METHOD ─────────────────────────────────────────

    async def analyze(self, account_id: str, lead_data: dict) -> dict:
        """
        Run OSINT analysis on a lead.

        lead_data supports:
          - email: str        — email address for holehe/ghunt
          - phone: str        — phone number for phoneinfoga
          - username: str     — username for maigret, social-analyzer
          - domain: str       — domain for shodan, spiderfoot, recon-ng (Enterprise)
          - scan_target: str  — path/URL to scan for secrets via BetterLeaks (Enterprise)
          - binary_path: str  — path to binary file for GEF binary analysis + file metadata (Enterprise)
          - atomic_query: str — MITRE ATT&CK search keyword/ID for Atomic Operator (Enterprise)
          - wp_url: str       — WordPress site URL for WPProbe scanning (Enterprise)
          - xss_url: str      — URL to scan for XSS vulnerabilities via XSStrike (Enterprise)
          - ssti_url: str     — URL to scan for SSTI vulnerabilities via SSTIMap (Enterprise)

        Tier-gated: each tool is only available on the appropriate tier.
        """
        # 1. Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "ANALYZER_LITE")
        limits = entitlement.get("limits", {})
        max_ops = limits.get("max_ops", 100)

        # 2. Check limit
        account_count = len(self._account_results.get(account_id, []))
        if max_ops > 0 and account_count >= max_ops:
            self.stats["blocked"] += 1
            return {
                "ok": False,
                "error": f"Monthly operation limit reached ({account_count}/{max_ops})",
                "account_id": account_id, "tier": tier,
                "limit": max_ops, "used": account_count,
            }

        # 3. Run applicable tools based on available data + tier
        tasks = []
        email = (lead_data.get("email") or "").strip()
        phone = (lead_data.get("phone") or "").strip()
        username = (lead_data.get("username") or "").strip()
        domain = (lead_data.get("domain") or "").strip()
        scan_target = (lead_data.get("scan_target") or "").strip()
        binary_path = (lead_data.get("binary_path") or "").strip()
        atomic_query = (lead_data.get("atomic_query") or "").strip()
        wp_url = (lead_data.get("wp_url") or "").strip()
        xss_url = (lead_data.get("xss_url") or "").strip()
        ssti_url = (lead_data.get("ssti_url") or "").strip()

        if email and self._tool_allowed(tier, "holehe"):
            tasks.append(self._run_holehe(email))
        if phone and self._tool_allowed(tier, "phoneinfoga"):
            tasks.append(self._run_phoneinfoga(phone))
        if username and self._tool_allowed(tier, "maigret"):
            tasks.append(self._run_maigret(username))
        if email and self._tool_allowed(tier, "ghunt"):
            tasks.append(self._run_ghunt(email))
        if domain and self._tool_allowed(tier, "shodan") and limits.get("shodan_access"):
            tasks.append(self._run_shodan(domain))
        if domain and self._tool_allowed(tier, "spiderfoot") and limits.get("deep_osint"):
            tasks.append(self._run_spiderfoot(domain))
        if domain and self._tool_allowed(tier, "recon-ng") and limits.get("deep_osint"):
            tasks.append(self._run_recon_ng(domain))
        if username and self._tool_allowed(tier, "social-analyzer"):
            tasks.append(self._run_social_analyzer(username))
        if scan_target and self._tool_allowed(tier, "betterleaks") and limits.get("secrets_scan"):
            # Dir mode for local paths, git mode for pre-cloned git repos
            scan_mode = "git" if scan_target.endswith(".git") else "dir"
            tasks.append(self._run_betterleaks(scan_target, scan_mode=scan_mode))
        if binary_path and self._tool_allowed(tier, "gef") and limits.get("binary_analysis"):
            tasks.append(self._run_gef(binary_path))
            tasks.append(self._run_file_analysis(binary_path))
        if atomic_query and self._tool_allowed(tier, "atomic-operator") and limits.get("adversary_emulation"):
            tasks.append(self._run_atomic_operator(atomic_query))
        if wp_url and self._tool_allowed(tier, "wpprobe") and limits.get("wordpress_scan"):
            if not wp_url.startswith("http"):
                wp_url = "https://" + wp_url
            tasks.append(self._run_wpprobe(wp_url))
        if xss_url and self._tool_allowed(tier, "xsstrike") and limits.get("xss_scan"):
            if not xss_url.startswith("http"):
                xss_url = "https://" + xss_url
            tasks.append(self._run_xsstrike(xss_url))
        if ssti_url and self._tool_allowed(tier, "sstimap") and limits.get("ssti_scan"):
            if not ssti_url.startswith("http"):
                ssti_url = "https://" + ssti_url
            tasks.append(self._run_sstimap(ssti_url))

        if not tasks:
            return {
                "ok": False,
                "error":                "No analyzable data provided. Need email, phone, username, domain, scan_target, binary_path, atomic_query, xss_url, ssti_url, or wp_url.",
                "tier": tier,
                "available_tools": limits.get("tools", []),
            }

        # 4. Run all tools in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 5. Process results
        tool_results = []
        total_findings = 0
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                tool_results.append({"tool": "unknown", "status": "error", "error": str(r)[:200]})
                self.stats["errors"] += 1
            else:
                tool_results.append(r)
                total_findings += r.get("count", 0)

        # 6. Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "analyzer", "analyze",
                               quantity=1, metadata={
                                   "tools_run": len(tool_results),
                                   "total_findings": total_findings,
                               })
            except Exception:
                pass

        self.stats["analyses"] += 1
        self._account_results.setdefault(account_id, []).append({
            "analysis_id": f"ANL-{__import__('uuid').uuid4().hex[:8].upper()}",
            "tier": tier,
            "tools_run": len(tool_results),
            "total_findings": total_findings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # 7. Generate intelligence score
        intel_score = self._compute_intel_score(tool_results)

        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "limit_used": account_count + 1 if max_ops > 0 else "unlimited",
            "limit_max": max_ops,
            "tools_run": len(tool_results),
            "total_findings": total_findings,
            "intel_score": intel_score,
            "results": tool_results,
            "analyzed_at": datetime.now(timezone.utc).isoformat(),
        }

    def _compute_intel_score(self, results: list) -> dict:
        """Compute an intelligence confidence score from tool results."""
        scores = {
            "email_verified": 0.0,
            "phone_verified": 0.0,
            "social_presence": 0.0,
            "google_presence": 0.0,
            "overall": 0.0,
        }
        total_weight = 0

        for r in results:
            tool = r.get("tool", "")
            findings = r.get("findings", [])
            count = len(findings)

            if tool == "holehe" and count > 0:
                scores["email_verified"] = min(1.0, count / 10)
                total_weight += 1
            if tool == "phoneinfoga" and count > 0:
                scores["phone_verified"] = 0.9 if any("valid" in str(f).lower() for f in findings) else 0.5
                total_weight += 1
            if tool == "maigret" and count > 0:
                scores["social_presence"] = min(1.0, count / 5)
                total_weight += 1
            if tool == "ghunt" and count > 0:
                scores["google_presence"] = min(1.0, count / 3)
                total_weight += 1
            if tool == "social-analyzer" and count > 0:
                scores["social_presence"] = min(1.0, count / 10)
                total_weight += 1
            if tool == "spiderfoot" and count > 0:
                scores["domain_intel"] = min(1.0, count / 20)
                total_weight += 1
            if tool == "recon-ng" and count > 0:
                scores["domain_intel"] = max(scores.get("domain_intel", 0), min(1.0, count / 5))
                total_weight += 1
            if tool == "betterleaks" and count > 0:
                scores["secrets_exposure"] = min(1.0, count / 3)
                total_weight += 1
            if tool == "gef" and count > 0:
                # Count how many protections are enabled — more enabled = harder target
                enabled = sum(1 for f in findings if f.get("enabled") is True)
                scores["binary_hardening"] = min(1.0, enabled / 5)
                total_weight += 1
            if tool == "file_analysis" and count > 0:
                scores["binary_metadata"] = 1.0
                total_weight += 1
            if tool == "atomic-operator" and count > 0:
                scores["adversary_intel"] = min(1.0, count / 10)
                total_weight += 1
            if tool == "wpprobe" and count > 0:
                scores["webapp_exposure"] = min(1.0, count / 5)
                total_weight += 1
            if tool == "xsstrike" and count > 0:
                scores["xss_vulnerability"] = min(1.0, count / 3)
                total_weight += 1
            if tool == "sstimap" and count > 0:
                scores["ssti_vulnerability"] = min(1.0, count / 3)
                total_weight += 1

        if total_weight > 0:
            scores["overall"] = round(
                sum(v for k, v in scores.items() if k != "overall") / total_weight, 3
            )

        return scores

    async def report(self, account_id: str) -> dict:
        """Return a summary report for the account."""
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        tier = entitlement.get("tier", "ANALYZER_LITE")
        limits = entitlement.get("limits", {})
        account_results = self._account_results.get(account_id, [])

        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "limits": limits,
            "analyses_this_month": len(account_results),
            "max_ops": limits.get("max_ops", 100),
            "usage_pct": round(
                (len(account_results) / max(limits.get("max_ops", 100), 1)) * 100, 1
            ) if limits.get("max_ops", 0) > 0 else 0,
            "last_analysis": account_results[-1] if account_results else None,
        }

    async def list_capabilities(self, account_id: str) -> dict:
        """Return available tools for the account's tier."""
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            return {"ok": False, "error": entitlement.get("error", "Access denied")}
        tier = entitlement.get("tier", "ANALYZER_LITE")
        limits = entitlement.get("limits", {})
        return {
            "ok": True,
            "account_id": account_id,
            "tier": tier,
            "tools": limits.get("tools", []),
            "shodan_access": limits.get("shodan_access", False),
            "deep_osint": limits.get("deep_osint", False),
        }

def _grade_hardening(score: float) -> str:
    """Convert hardening score (0-100) to a letter grade."""
    if score >= 90: return "A"
    if score >= 75: return "B"
    if score >= 55: return "C"
    if score >= 35: return "D"
    return "F"


    @staticmethod
    def _check_gef() -> bool:
        """Check if GDB with GEF is available. GEF is a GDB plugin, not a standalone binary."""
        try:
            r = subprocess.run(["which", "gdb"], capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                return False
            # Check that a GEF script exists
            import glob
            gef_scripts = glob.glob(os.path.expanduser("~/.gef-*.py"))
            return len(gef_scripts) > 0
        except Exception:
            return False

    async def health_check(self) -> dict:
        """Return Analyzer engine health."""
        tools_available = {}
        for tool in ["holehe", "phoneinfoga", "maigret", "ghunt", "shodan", "social-analyzer", "spiderfoot", "recon-ng", "betterleaks", "atomic-operator", "wpprobe", "xsstrike", "sstimap"]:
            try:
                r = subprocess.run(["which", tool], capture_output=True, text=True, timeout=5)
                tools_available[tool] = r.returncode == 0
            except Exception:
                tools_available[tool] = False
        # GEF is a GDB plugin, not a standalone binary — check differently
        tools_available["gef"] = self._check_gef()
        return {
            "status": "operational",
            "service": "analyzer",
            "tools": tools_available,
            "tools_online": sum(1 for v in tools_available.values() if v),
            "tools_total": len(tools_available),
            "stats": dict(self.stats),
            "tier_limits": {
                k: {"max_ops": v["max_ops"], "tools": v["tools"]}
                for k, v in _TIER_LIMITS.items()
            },
        }

    def stats_snapshot(self) -> dict:
        """Return in-memory stats snapshot."""
        total_accounts = len(self._account_results)
        total_ops = sum(len(v) for v in self._account_results.values())
        return {
            "engine": dict(self.stats),
            "accounts_active": total_accounts,
            "total_ops_metered": total_ops,
            "tier_limits": _TIER_LIMITS,
            "tiers": list(_TIER_LIMITS.keys()),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────

class AnalyzerRoutes:
    """Wire Analyzer product endpoints into the FastAPI app."""

    def __init__(self, engine: AnalyzerEngine, *, require_auth: Optional[Callable] = None):
        self.engine = engine
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Query, Request
        from fastapi.responses import JSONResponse

        @app.get("/api/v6/suite/analyzer/health")
        async def an_health(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(await self.engine.health_check())

        @app.get("/api/v6/suite/analyzer/stats")
        async def an_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.engine.stats_snapshot())

        @app.get("/api/v6/suite/analyzer/capabilities")
        async def an_capabilities(
            account_id: str = Query(..., description="Customer account ID"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.list_capabilities(account_id)
            status = 200 if result.get("ok") else 403
            return JSONResponse(result, status_code=status)

        @app.post("/api/v6/suite/analyzer/analyze")
        async def an_analyze(
            request: Request,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run OSINT analysis on a lead.
            Body: {account_id: str, lead: {email?: str, phone?: str, username?: str, domain?: str}}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            lead_data = body.get("lead", body.get("lead_data", {}))

            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(lead_data, dict) or not any(
                lead_data.get(k) for k in ["email", "phone", "username", "domain", "scan_target", "binary_path", "atomic_query", "wp_url", "xss_url", "ssti_url"]
            ):
                raise HTTPException(400,
                    "lead must have at least one of: email, phone, username, domain, scan_target, binary_path, atomic_query, xss_url, ssti_url, wp_url")

            result = await self.engine.analyze(account_id, lead_data)
            if not result.get("ok"):
                error = result.get("error", "Analysis denied")
                if "limit" in error.lower():
                    return JSONResponse(result, status_code=403)
                return JSONResponse(result, status_code=400)
            return JSONResponse(result)

        @app.get("/api/v6/suite/analyzer/report")
        async def an_report(
            account_id: str = Query(..., description="Customer account ID"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            result = await self.engine.report(account_id)
            status = 200 if result.get("ok") else 403
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/analyzer/checksec")
        async def an_checksec(
            binary_path: str = Query(..., description="Path to binary to analyze"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run GEF checksec against a binary and return per-protection hardening status."""
            if not os.path.isfile(binary_path):
                raise HTTPException(400, f"Binary not found: {binary_path}")
            # Run GEF checksec + file analysis in parallel
            gef_result, file_result = await asyncio.gather(
                self.engine._run_gef(binary_path),
                self.engine._run_file_analysis(binary_path),
            )
            # Compute hardening score (percentage of protections enabled)
            protections = [f for f in gef_result.get("findings", []) if f.get("type") == "binary_protection"]
            total = len(protections)
            enabled = sum(1 for p in protections if p.get("enabled"))
            hardening_score = round((enabled / max(total, 1)) * 100, 1)
            # Extract file metadata into a clean dict
            file_info = {}
            for f in file_result.get("findings", []):
                if f.get("type") == "file_description":
                    file_info["description"] = f["detail"]
                elif f.get("type") == "binary_metadata":
                    file_info[f["key"]] = f["value"]
            return JSONResponse({
                "ok": gef_result.get("status") == "completed",
                "tool": "gef",
                "target": binary_path,
                "hardening_score": hardening_score,
                "hardening_grade": _grade_hardening(hardening_score),
                "protections": protections,
                "total_protections": total,
                "enabled_protections": enabled,
                "file_analysis": file_info,
                "error": gef_result.get("error"),
            })

        @app.get("/api/v6/suite/analyzer/wp")
        async def an_wpscan(
            url: str = Query(..., description="WordPress site URL"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run WPProbe scan against a WordPress site and return structured results."""
            if not url.startswith("http"):
                url = "https://" + url
            result = await self.engine._run_wpprobe(url)
            if result.get("status") == "error":
                return JSONResponse({"ok": False, "error": result.get("error")}, status_code=500)
            # Organize findings into plugins list + vulnerability counts
            plugins = []
            vulns = result.get("findings", [])
            plugin_vulns = [f for f in vulns if f.get("type") == "wordpress_vulnerability"]
            plugin_entries = [f for f in vulns if f.get("type") == "wordpress_plugin"]
            # Build per-plugin summary
            seen = {}
            for p in plugin_entries:
                name = p.get("plugin", "")
                if name not in seen:
                    seen[name] = {"name": name, "version": "unknown", "cves": 0}
                detail = p.get("detail", "")
                if "version" in detail.lower() and seen[name]["version"] == "unknown":
                    import re
                    m = re.search(r"version': '([^']+)'", detail)
                    if m:
                        seen[name]["version"] = m.group(1)
            for v in plugin_vulns:
                name = v.get("plugin", "")
                if name in seen:
                    seen[name]["cves"] += 1
                else:
                    seen[name] = {"name": name, "version": "unknown", "cves": 1}
            plugins = list(seen.values())
            total_vulns = sum(p["cves"] for p in plugins)
            severity_breakdown = {"critical": 0, "high": 0, "medium": 0, "low": 0}
            for v in plugin_vulns:
                sev = v.get("severity", "").lower()
                if sev in severity_breakdown:
                    severity_breakdown[sev] += 1
            return JSONResponse({
                "ok": True,
                "target": url,
                "plugins_found": len(plugins),
                "total_vulnerabilities": total_vulns,
                "severity_breakdown": severity_breakdown,
                "plugins": plugins,
            })

        
        @app.get("/api/v6/suite/analyzer/xss")
        async def an_xss(
            url: str = Query(..., description="URL to scan for XSS vulnerabilities"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run XSStrike against a URL and return vulnerability findings."""
            if not url.startswith("http"):
                url = "https://" + url
            result = await self.engine._run_xsstrike(url)
            if result.get("status") == "error":
                return JSONResponse({"ok": False, "error": result.get("error")}, status_code=500)
            findings = result.get("findings", [])
            vulns = [f for f in findings if f.get("type") == "xss_vulnerability"]
            wafs = [f for f in findings if f.get("type") == "waf_detected"]
            refs = [f for f in findings if f.get("type") == "reflection_point"]
            return JSONResponse({
                "ok": True,
                "target": url,
                "total_vulnerabilities": len(vulns),
                "waf_detected": len(wafs) > 0,
                "reflection_points": len(refs),
                "findings_count": len(findings),
                "vulnerabilities": vulns[:20],
            })

        @app.get("/api/v6/suite/analyzer/ssti")
        async def an_ssti(
            url: str = Query(..., description="URL to scan for SSTI vulnerabilities"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Run SSTIMap against a URL and return template injection findings."""
            if not url.startswith("http"):
                url = "https://" + url
            result = await self.engine._run_sstimap(url)
            if result.get("status") == "error":
                return JSONResponse({"ok": False, "error": result.get("error")}, status_code=500)
            findings = result.get("findings", [])
            vulns = [f for f in findings if f.get("type") == "ssti_vulnerability"]
            engines = [f for f in findings if f.get("type") == "template_engine_tested"]
            points = [f for f in findings if f.get("type") == "injection_point"]
            return JSONResponse({
                "ok": True,
                "target": url,
                "total_vulnerabilities": len(vulns),
                "engines_tested": len(engines),
                "injection_points": len(points),
                "findings_count": len(findings),
                "vulnerabilities": vulns[:20],
            })

        @app.get("/api/v6/suite/analyzer/shodan")
        async def an_shodan_search(
            query: str = Query(..., description="Shodan search query (domain, IP, or keyword)"),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Search Shodan for internet-connected devices matching a query."""
            result = await self.engine._run_shodan(query)
            if result.get("status") == "error":
                return JSONResponse({"ok": False, "error": result.get("error")}, status_code=500)
            findings = result.get("findings", [])
            devices = [f for f in findings if f.get("type") == "device"]
            api_key_configured = result.get("status") != "skipped"
            return JSONResponse({
                "ok": result.get("status") == "completed",
                "target": query,
                "devices_found": len(devices),
                "findings_count": len(findings),
                "api_key_configured": api_key_configured,
                "warning": result.get("error"),
                "devices": devices[:20],
            })

        log.info("[analyzer-product] Routes registered · /api/v6/suite/analyzer/*")
