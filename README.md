# Project: ncs-license-finder
## Created By: brian.dean on 2026-07-16
### Description: Connects to a list of Cisco NCS (IOS-XR) nodes via SSH, runs
### "show license platform summary" on each, parses the entitlement
### counts, and prints per-node results plus grand totals.

### Usage:
###     python3 ncs540_license_summary.py -i ips.txt
### 
###     ips.txt should contain one IP or hostname per line, e.g.:
###         172.25.0.85
###         172.25.0.89
###         10.10.0.59
###         # lines starting with # are ignored, blank lines are skipped

### Requires:
###     pip install netmiko --break-system-packages

### Notes:
###     - Credentials are prompted for interactively (not stored/echoed).
###     - If your devices use SSH keys instead of a password, see the
###       NOTE in get_connection() below.
###     - Each device is tried independently; a failure on one host
###       does not stop the rest from being processed.
