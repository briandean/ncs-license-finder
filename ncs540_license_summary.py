#!/usr/bin/env python3
"""
ncs540_license_summary.py

Connects to a list of Cisco NCS540 (IOS-XR) nodes via SSH, runs
"show license platform summary" on each, parses the entitlement
counts, and prints per-node results plus grand totals.

Usage:
    python3 ncs540_license_summary.py -i ips.txt

    ips.txt should contain one IP or hostname per line, e.g.:
        172.25.0.85
        172.25.0.89
        10.10.0.59
        # lines starting with # are ignored, blank lines are skipped

Requires:
    pip install netmiko --break-system-packages

Notes:
    - Credentials are prompted for interactively (not stored/echoed).
    - If your devices use SSH keys instead of a password, see the
      NOTE in get_connection() below.
    - Each device is tried independently; a failure on one host
      does not stop the rest from being processed.
"""

import argparse
import csv
import getpass
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from netmiko import ConnectHandler
    try:
        # Newer netmiko releases
        from netmiko.exceptions import NetmikoTimeoutException as NetmikoTimeoutError
        from netmiko.exceptions import NetmikoAuthenticationException as NetmikoAuthenticationError
    except ImportError:
        # Older netmiko releases
        from netmiko import NetmikoTimeoutException as NetmikoTimeoutError
        from netmiko import NetmikoAuthenticationException as NetmikoAuthenticationError
except ImportError:
    print("This script requires netmiko. Install it with:")
    print("    pip install netmiko --break-system-packages")
    sys.exit(1)


# Entitlement lines we want to total. Matched loosely since some
# devices prefix the Feature/Area column with "FCM" and others with
# "FCM 1" -- we only care about the Entitlement text itself.
ENTITLEMENTS = [
    "Access Advantage SW Right-to-Use v1.0 per 10G",
    "Access Essentials SW Right-to-Use v1.0 per 10G",
    "Access Essentials SIA per 10G",
    "Access Advantage SIA per 10G",
    "N540-24Z8Q2C-M Base Hardware Tracking PID",
]

# Matches lines like:
#   FCM 1        Access Advantage SIA per 10G                          25   25
# or:
#   FCM          N540-24Z8Q2C-M Base Hardware Tracking PID              1    1
ENTITLEMENT_LINE_RE = re.compile(
    r"^\s*FCM(?:\s+\d+)?\s+(?P<entitlement>.+?)\s+(?P<last>\d+)\s+(?P<next>\d+)\s*$"
)

COMPLIANCE_RE = re.compile(r"(SIA Status|Upgrade License Status):\s*(?P<status>.+)")
HOSTNAME_RE = re.compile(r"^RP/\S+:(?P<hostname>\S+)#")


def parse_license_output(raw_output, fallback_name):
    """Parse 'show license platform summary' output into a dict of results."""
    hostname = fallback_name
    compliance = "Unknown"
    counts = {}

    for line in raw_output.splitlines():
        host_match = HOSTNAME_RE.match(line.strip())
        if host_match:
            hostname = host_match.group("hostname")
            continue

        comp_match = COMPLIANCE_RE.search(line)
        if comp_match:
            compliance = comp_match.group("status").strip()
            continue

        ent_match = ENTITLEMENT_LINE_RE.match(line)
        if ent_match:
            entitlement = ent_match.group("entitlement").strip()
            last_count = int(ent_match.group("last"))
            next_count = int(ent_match.group("next"))
            # Normalize entitlement text to match known list (strip stray spaces)
            counts[entitlement] = {"last": last_count, "next": next_count}

    return {
        "hostname": hostname,
        "compliance": compliance,
        "counts": counts,
    }


def get_connection_params(ip, username, password, secret):
    return {
        "device_type": "cisco_xr",
        "host": ip,
        "username": username,
        "password": password,
        "secret": secret or password,
        "fast_cli": False,
        "conn_timeout": 15,
        "banner_timeout": 15,
    }


def collect_from_device(ip, username, password, secret):
    """Connect to a single device, run the command, return parsed result."""
    result = {
        "ip": ip,
        "hostname": ip,
        "compliance": None,
        "counts": {},
        "error": None,
    }
    try:
        conn = ConnectHandler(**get_connection_params(ip, username, password, secret))
        output = conn.send_command("show license platform summary", read_timeout=30)
        conn.disconnect()

        parsed = parse_license_output(output, fallback_name=ip)
        result["hostname"] = parsed["hostname"]
        result["compliance"] = parsed["compliance"]
        result["counts"] = parsed["counts"]

    except NetmikoAuthenticationError:
        result["error"] = "Authentication failed"
    except NetmikoTimeoutError:
        result["error"] = "Connection timed out"
    except Exception as exc:  # noqa: BLE001 - report any failure, keep going
        result["error"] = f"{type(exc).__name__}: {exc}"

    return result


def read_ip_list(path):
    ips = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            ips.append(line)
    return ips


def print_report(results):
    grand_totals = {name: {"last": 0, "next": 0} for name in ENTITLEMENTS}
    node_count_with_entitlement = {name: 0 for name in ENTITLEMENTS}
    failures = []
    out_of_compliance = []

    print("\n" + "=" * 100)
    print(f"{'Hostname':<16}{'IP':<16}{'Compliance':<20}{'Status'}")
    print("-" * 100)

    for r in results:
        if r["error"]:
            failures.append(r)
            print(f"{r['hostname']:<16}{r['ip']:<16}{'N/A':<20}FAILED: {r['error']}")
            continue

        compliance = r["compliance"] or "Unknown"
        status_flag = "OK"
        if compliance and "out of compliance" in compliance.lower():
            status_flag = "*** OUT OF COMPLIANCE ***"
            out_of_compliance.append(r)

        print(f"{r['hostname']:<16}{r['ip']:<16}{compliance:<20}{status_flag}")

        for entitlement in ENTITLEMENTS:
            if entitlement in r["counts"]:
                grand_totals[entitlement]["last"] += r["counts"][entitlement]["last"]
                grand_totals[entitlement]["next"] += r["counts"][entitlement]["next"]
                node_count_with_entitlement[entitlement] += 1

    print("=" * 100)
    print(f"\nNodes queried:     {len(results)}")
    print(f"Nodes succeeded:   {len(results) - len(failures)}")
    print(f"Nodes failed:      {len(failures)}")

    print("\n--- License Totals (across all reporting nodes) ---")
    print(f"{'Entitlement':<55}{'Last':>8}{'Next':>8}{'# Nodes':>10}")
    print("-" * 82)
    for entitlement in ENTITLEMENTS:
        t = grand_totals[entitlement]
        n = node_count_with_entitlement[entitlement]
        print(f"{entitlement:<55}{t['last']:>8}{t['next']:>8}{n:>10}")

    if out_of_compliance:
        print("\n--- Nodes Out of Compliance ---")
        for r in out_of_compliance:
            print(f"  {r['hostname']} ({r['ip']}): {r['compliance']}")

    if failures:
        print("\n--- Failed Connections ---")
        for r in failures:
            print(f"  {r['ip']}: {r['error']}")

    return grand_totals, node_count_with_entitlement, failures, out_of_compliance


def write_csv(results, path):
    fieldnames = ["hostname", "ip", "compliance", "error"] + ENTITLEMENTS
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = {
                "hostname": r["hostname"],
                "ip": r["ip"],
                "compliance": r["compliance"] or "",
                "error": r["error"] or "",
            }
            for entitlement in ENTITLEMENTS:
                if entitlement in r["counts"]:
                    row[entitlement] = r["counts"][entitlement]["last"]
                else:
                    row[entitlement] = ""
            writer.writerow(row)
    print(f"\nPer-node CSV written to: {path}")


def main():
    parser = argparse.ArgumentParser(
        description="Collect and total 'show license platform summary' across NCS540 nodes."
    )
    parser.add_argument(
        "-i", "--input", required=True, help="Path to text file with one IP/hostname per line"
    )
    parser.add_argument(
        "-o", "--output-csv", default=None, help="Optional path to write per-node CSV results"
    )
    parser.add_argument(
        "-w", "--workers", type=int, default=8, help="Number of parallel SSH connections (default 8)"
    )
    args = parser.parse_args()

    ips = read_ip_list(args.input)
    if not ips:
        print(f"No IPs found in {args.input}")
        sys.exit(1)

    username = input("Username: ").strip()
    password = getpass.getpass("Password: ")
    secret = getpass.getpass("Enable secret (press Enter to reuse password): ")

    print(f"\nConnecting to {len(ips)} node(s)...\n")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_ip = {
            executor.submit(collect_from_device, ip, username, password, secret): ip
            for ip in ips
        }
        for future in as_completed(future_to_ip):
            ip = future_to_ip[future]
            result = future.result()
            results.append(result)
            status = "OK" if not result["error"] else f"FAILED ({result['error']})"
            print(f"  [{ip}] {status}")

    # Keep output order matching the input file order
    order = {ip: idx for idx, ip in enumerate(ips)}
    results.sort(key=lambda r: order.get(r["ip"], 0))

    print_report(results)

    if args.output_csv:
        write_csv(results, args.output_csv)


if __name__ == "__main__":
    main()
