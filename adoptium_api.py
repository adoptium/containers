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

import json
import urllib.request

ADOPTIUM_API_URL = "https://api.adoptium.net/v3/info/available_releases"


def _fetch_release_data():
    """Fetch release info from the Adoptium API."""
    req = urllib.request.Request(
        ADOPTIUM_API_URL,
        headers={"User-Agent": "Adoptium Dockerfile Updater"},
    )
    with urllib.request.urlopen(req) as response:
        return json.loads(response.read().decode("utf-8"))


def get_supported_versions():
    """Fetch supported versions from the Adoptium API.

    Returns all LTS versions plus any non-LTS versions between the most
    recent LTS and the most recent feature release (inclusive).

    For example, if LTS versions are [8, 11, 17, 21, 25] and the most
    recent feature release is 26, this returns [8, 11, 17, 21, 25, 26].
    """
    data = _fetch_release_data()

    lts_versions = set(data["available_lts_releases"])
    most_recent_lts = data["most_recent_lts"]
    most_recent_feature = data["most_recent_feature_release"]

    # All LTS versions + anything between latest LTS and most recent feature release
    versions = set(lts_versions)
    for v in range(most_recent_lts + 1, most_recent_feature + 1):
        if v in data["available_releases"]:
            versions.add(v)

    return sorted(versions)


def get_latest_lts():
    """Return the most recent LTS version number."""
    data = _fetch_release_data()
    return data["most_recent_lts"]
