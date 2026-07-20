# Project: ncs-license-finder
## Created By: brian.dean on 2026-07-16
### Description: 
Connects to a list of Cisco NCS (IOS-XR) nodes via SSH, runs
"show license platform summary" on each, parses the entitlement
counts, and prints per-node results plus grand totals.

### Usage:
    python3 ncs_lic_collection.py -i ips.txt

    ips.txt should contain one IP or hostname per line, e.g.:
        10.121.1.70
        10.10.0.61
        10.10.0.65
        # lines starting with # are ignored, blank lines are skipped

### Output:
    python3 ncs_lic_collection.py -i ips.txt
    Username: username
    Password: 
    Enable secret (press Enter to reuse password): 

    Connecting to 3 node(s)...

    [10.121.1.70] OK
    [10.10.0.61] OK
    [10.10.0.65] OK

    ====================================================================================================
    Hostname        IP              Compliance          Status
    ----------------------------------------------------------------------------------------------------
    10.121.1.70     10.121.1.70     In Compliance       OK
    10.10.0.65      10.10.0.65      In Compliance       OK
    10.10.0.61      10.10.0.61      Out of Compliance(Remaining Grace Period: 69 days, 21 hours)*** OUT OF COMPLIANCE ***
    ====================================================================================================

    Nodes queried:     3
    Nodes succeeded:   3
    Nodes failed:      0

    --- License Totals (across all reporting nodes) ---
    Entitlement                                                Last    Next   # Nodes
    ----------------------------------------------------------------------------------
    Access Advantage SW Right-to-Use v1.0 per 10G                44      44         2
    Access Essentials SW Right-to-Use v1.0 per 10G               64      64         2
    Access Essentials SIA per 10G                                64      64         2
    Access Advantage SIA per 10G                                 44      44         2
    N540-24Z8Q2C-M Base Hardware Tracking PID                     1       1         1

    --- Nodes Out of Compliance ---
    10.10.0.61 (10.10.0.61): Out of Compliance(Remaining Grace Period: 69 days, 21 hours)

### Requires:
    pip install netmiko --break-system-packages

### Notes:
    - Credentials are prompted for interactively (not stored/echoed).
    - If your devices use SSH keys instead of a password, see the
      NOTE in get_connection() below.
    - Each device is tried independently; a failure on one host
      does not stop the rest from being processed.