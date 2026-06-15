#!/usr/bin/env python3
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

"""Fetch EOL dates from endoflife.date API for base images."""

import re
import sys
import urllib.request
import json
from datetime import date, datetime

ENDOFLIFE_API = "https://endoflife.date/api"

# Map os config values to endoflife.date product names
OS_TO_PRODUCT = {
    "ubuntu": "ubuntu",
    "alpine-linux": "alpine",
    "ubi-minimal": "rhel",
}

# Regex to extract version from image string (e.g. "ubuntu:26.04" -> "26.04",
# "redhat/ubi9-minimal" -> "9", "alpine:3.24" -> "3.24")
IMAGE_VERSION_PATTERNS = [
    # standard image:tag format
    re.compile(r":(\d[\d.]*)$"),
    # UBI images like redhat/ubi9-minimal -> extract major version
    re.compile(r"/ubi(\d+)"),
]


def _extract_cycle(image):
    """Extract the version/cycle string from a Docker image reference."""
    for pattern in IMAGE_VERSION_PATTERNS:
        m = pattern.search(image)
        if m:
            return m.group(1)
    return None


def fetch_eol_date(product, cycle):
    """Fetch the EOL date for a product cycle from endoflife.date.

    Returns a date object or None if the lookup fails.
    """
    url = f"{ENDOFLIFE_API}/{product}/{cycle}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Adoptium EOL Checker"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            eol = data.get("eol")
            if isinstance(eol, bool):
                # Some products return eol: false (meaning not yet EOL)
                return None
            if eol:
                return datetime.strptime(eol, "%Y-%m-%d").date()
    except Exception:
        pass
    return None


def get_eol_date(configuration):
    """Get the EOL date for a configuration entry.

    Priority:
    1. Hardcoded 'eol' field in the config (as fallback/override)
    2. Lookup from endoflife.date API based on os + image
    """
    # Check for hardcoded override first
    eol_str = configuration.get("eol")
    if eol_str:
        if isinstance(eol_str, date):
            return eol_str
        return datetime.strptime(str(eol_str), "%Y-%m-%d").date()

    os_name = configuration.get("os", "")
    image = configuration.get("image", "")

    product = OS_TO_PRODUCT.get(os_name)
    if not product:
        return None

    cycle = _extract_cycle(image)
    if not cycle:
        return None

    return fetch_eol_date(product, cycle)


def check_eol_configs(config):
    """Check all configurations for EOL status.

    Returns a list of (configuration, eol_date) tuples for entries past EOL.
    """
    today = date.today()
    expired = []

    for os_family, configurations in config.get("configurations", {}).items():
        for cfg in configurations:
            eol_date = get_eol_date(cfg)
            if eol_date and eol_date <= today:
                expired.append((cfg, eol_date))

    return expired


def print_eol_warnings(config, file=sys.stderr):
    """Print warnings for any expired distros. Returns the list of expired entries."""
    expired = check_eol_configs(config)
    if expired:
        print(f"\n⚠ {len(expired)} distro(s) past EOL:", file=file)
        for cfg, eol_date in expired:
            image = cfg.get("image", cfg.get("directory", "unknown"))
            directory = cfg.get("directory", "")
            print(f"  - {image} ({directory}) expired {eol_date}", file=file)
    return expired


if __name__ == "__main__":
    import yaml

    with open("config/temurin.yml") as f:
        config = yaml.safe_load(f)

    print("Distro EOL dates:")
    for os_family, configurations in config.get("configurations", {}).items():
        for cfg in configurations:
            image = cfg.get("image", cfg.get("directory", "unknown"))
            eol = get_eol_date(cfg)
            eol_str = str(eol) if eol else "unknown"
            print(f"  {image}: {eol_str}")

    print()
    expired = print_eol_warnings(config, file=sys.stdout)
    if not expired:
        print("All distros are within their EOL dates.")
    sys.exit(1 if expired else 0)
