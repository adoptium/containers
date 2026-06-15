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
import unittest
from datetime import date
from unittest.mock import patch, MagicMock

from eol_checker import (
    OS_TO_PRODUCT,
    _extract_cycle,
    check_eol_configs,
    fetch_eol_date,
    get_eol_date,
)


def _mock_urlopen(response_data):
    """Create a mock for urllib.request.urlopen that returns JSON data."""
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    return mock_resp


class TestExtractCycle(unittest.TestCase):

    def test_ubuntu_image(self):
        self.assertEqual(_extract_cycle("ubuntu:26.04"), "26.04")

    def test_alpine_image(self):
        self.assertEqual(_extract_cycle("alpine:3.21"), "3.21")

    def test_ubi_image(self):
        self.assertEqual(_extract_cycle("redhat/ubi9-minimal"), "9")

    def test_ubi10_image(self):
        self.assertEqual(_extract_cycle("redhat/ubi10-minimal"), "10")

    def test_no_version(self):
        self.assertIsNone(_extract_cycle("scratch"))

    def test_windows_image(self):
        # Windows images use non-numeric tags like ltsc2022
        self.assertIsNone(_extract_cycle("mcr.microsoft.com/windows/servercore:ltsc2022"))


class TestFetchEolDate(unittest.TestCase):

    @patch("eol_checker.urllib.request.urlopen")
    def test_returns_date(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen({"eol": "2027-11-01"})
        result = fetch_eol_date("alpine", "3.23")
        self.assertEqual(result, date(2027, 11, 1))

    @patch("eol_checker.urllib.request.urlopen")
    def test_returns_none_for_bool_eol(self, mock_urlopen_fn):
        mock_urlopen_fn.return_value = _mock_urlopen({"eol": False})
        result = fetch_eol_date("alpine", "99.99")
        self.assertIsNone(result)

    @patch("eol_checker.urllib.request.urlopen")
    def test_returns_none_on_network_error(self, mock_urlopen_fn):
        mock_urlopen_fn.side_effect = Exception("network error")
        result = fetch_eol_date("alpine", "3.21")
        self.assertIsNone(result)


class TestGetEolDate(unittest.TestCase):

    @patch("eol_checker.fetch_eol_date", return_value=date(2027, 11, 1))
    def test_fetches_from_api(self, mock_fetch):
        cfg = {"os": "alpine-linux", "image": "alpine:3.23"}
        result = get_eol_date(cfg)
        self.assertEqual(result, date(2027, 11, 1))
        mock_fetch.assert_called_once_with("alpine", "3.23")

    @patch("eol_checker.fetch_eol_date", return_value=date(2029, 4, 30))
    def test_ubuntu(self, mock_fetch):
        cfg = {"os": "ubuntu", "image": "ubuntu:24.04"}
        result = get_eol_date(cfg)
        self.assertEqual(result, date(2029, 4, 30))
        mock_fetch.assert_called_once_with("ubuntu", "24.04")

    @patch("eol_checker.fetch_eol_date", return_value=date(2032, 5, 31))
    def test_ubi(self, mock_fetch):
        cfg = {"os": "ubi-minimal", "image": "redhat/ubi9-minimal"}
        result = get_eol_date(cfg)
        self.assertEqual(result, date(2032, 5, 31))
        mock_fetch.assert_called_once_with("rhel", "9")

    def test_hardcoded_eol_takes_priority(self):
        cfg = {"os": "ubuntu", "image": "ubuntu:24.04", "eol": "2030-01-01"}
        result = get_eol_date(cfg)
        self.assertEqual(result, date(2030, 1, 1))

    def test_hardcoded_eol_as_date_object(self):
        cfg = {"os": "ubuntu", "image": "ubuntu:24.04", "eol": date(2030, 1, 1)}
        result = get_eol_date(cfg)
        self.assertEqual(result, date(2030, 1, 1))

    def test_unknown_os_returns_none(self):
        cfg = {"os": "servercore", "image": "mcr.microsoft.com/windows/servercore:ltsc2022"}
        result = get_eol_date(cfg)
        self.assertIsNone(result)


class TestCheckEolConfigs(unittest.TestCase):

    @patch("eol_checker.get_eol_date")
    def test_finds_expired(self, mock_get_eol):
        mock_get_eol.side_effect = [date(2020, 1, 1), date(2099, 1, 1)]
        config = {
            "configurations": {
                "linux": [
                    {"os": "ubuntu", "image": "ubuntu:20.04", "directory": "ubuntu/focal"},
                    {"os": "ubuntu", "image": "ubuntu:24.04", "directory": "ubuntu/noble"},
                ],
            }
        }
        expired = check_eol_configs(config)
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0][0]["directory"], "ubuntu/focal")
        self.assertEqual(expired[0][1], date(2020, 1, 1))

    @patch("eol_checker.get_eol_date", return_value=None)
    def test_skips_when_no_eol(self, mock_get_eol):
        config = {
            "configurations": {
                "windows": [
                    {"os": "servercore", "image": "mcr.microsoft.com/windows/servercore:ltsc2022"},
                ],
            }
        }
        expired = check_eol_configs(config)
        self.assertEqual(len(expired), 0)


class TestEolFetchableForAllConfigs(unittest.TestCase):
    """Verify that every non-Windows config in temurin.yml can fetch an EOL date from the API."""

    @classmethod
    def setUpClass(cls):
        import yaml
        with open("config/temurin.yml") as f:
            cls.config = yaml.safe_load(f)

    def test_all_linux_and_alpine_configs_fetch_eol_from_api(self):
        """Each non-Windows config should resolve a product/cycle and get a valid date from endoflife.date."""
        missing = []
        for os_family, configurations in self.config["configurations"].items():
            if os_family == "windows":
                continue
            for cfg in configurations:
                os_name = cfg["os"]
                image = cfg["image"]
                product = OS_TO_PRODUCT.get(os_name)
                cycle = _extract_cycle(image)

                with self.subTest(image=image):
                    self.assertIsNotNone(product, f"No endoflife.date product mapping for os={os_name}")
                    self.assertIsNotNone(cycle, f"Could not extract version cycle from {image}")

                    eol = fetch_eol_date(product, cycle)
                    if eol is None:
                        missing.append(f"{image} ({cfg.get('directory', '')})")
                    else:
                        self.assertIsInstance(eol, date, f"EOL for {image} is not a date: {eol}")

        self.assertEqual(
            missing, [],
            f"Could not fetch EOL date from endoflife.date API for: {', '.join(missing)}"
        )


if __name__ == "__main__":
    unittest.main()
