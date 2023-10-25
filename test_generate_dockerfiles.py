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
# Script that generates the `eclipse-temurin` config file for the official docker
# image github repo and the doc updates for the unofficial docker image repo.
# Process to update the official docker image repo 
# 1. Run ./update_all.sh to update all the dockerfiles in the current repo.
# 2. Submit PR to push the newly generated dockerfiles to the current repo.
# 3. After above PR is merged, git pull the latest changes.
# 4. Run this command
#

import unittest
from unittest.mock import Mock, mock_open, patch

from jinja2 import Environment, FileSystemLoader

import generate_dockerfiles


class TestHelperFunctions(unittest.TestCase):
    def test_archHelper(self):
        test_data = [
            ("aarch64", "some-os", "aarch64|arm64"),
            ("ppc64le", "some-os", "ppc64el|powerpc:common64"),
            ("s390x", "some-os", "s390x|s390:64-bit"),
            ("arm", "some-os", "armhf|arm"),
            ("x64", "alpine-linux", "amd64|x86_64"),
            ("x64", "ubuntu", "amd64|i386:x86-64"),
            ("random-arch", "some-os", "random-arch"),
        ]

        for arch, os_family, expected in test_data:
            self.assertEqual(generate_dockerfiles.archHelper(arch, os_family), expected)

    def test_osFamilyHelper(self):
        test_data = [
            ("ubuntu", "linux"),
            ("centos", "linux"),
            ("ubi9-minimal", "linux"),
            ("nanoserver", "windows"),
            ("servercore", "windows"),
            ("random-os", "random-os"),
        ]

        for os_name, expected in test_data:
            self.assertEqual(generate_dockerfiles.osFamilyHelper(os_name), expected)

    @patch("requests.get")
    def test_fetch_latest_release(self, mock_get):
        # Mocking the request.get call
        mock_response = Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [{"key": "value"}]
        mock_get.return_value = mock_response

        url = "https://api.adoptium.net/v3/assets/feature_releases/some_version/ga?page=0&image_type=some_type&page_size=1&vendor=eclipse"
        response = generate_dockerfiles.requests.get(
            url, headers=generate_dockerfiles.headers
        )
        data = response.json()
        self.assertIn("key", data[0])
        self.assertEqual(data[0]["key"], "value")

    @patch("builtins.open", new_callable=mock_open, read_data="configurations: []")
    def test_load_config(self, mock_file):
        with open("config/hotspot.yml", "r") as file:
            config = generate_dockerfiles.yaml.safe_load(file)
            self.assertIn("configurations", config)


class TestJinjaRendering(unittest.TestCase):
    def setUp(self):
        # Setup the Jinja2 environment
        self.env = Environment(loader=FileSystemLoader("docker_templates"))

    def test_armhf_ubuntu8_rendering(self):
        template_name = "ubuntu.Dockerfile.j2"
        template = self.env.get_template(template_name)

        arch_data = {}

        arch_data["armhf|arm"] = {
            "download_url": "http://fake-url.com",
            "checksum": "fake-checksum",
        }

        # The context/variables to render the template
        context = {
            "architecture": "armhf|arm",
            "os": "ubuntu",
            "version": "8",
            "arch_data": arch_data,
        }
        rendered_template = template.render(**context)

        # Expected string/partial in the rendered output
        expected_string = "# Fixes libatomic.so.1: cannot open shared object file"
        self.assertIn(expected_string, rendered_template)

    def test_version_checker(self):
        template_name = "partials/version-check.j2"
        template = self.env.get_template(template_name)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "&& echo javac --version && javac --version"
            self.assertIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "&& echo javac -version && javac -version"
            self.assertIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "&& echo javac --version && javac --version"
            self.assertNotIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "&& echo javac -version && javac -version"
            self.assertNotIn(expected_string, rendered_template)

    def test_version_checker_windows(self):
        template_name = "partials/version-check-windows.j2"
        template = self.env.get_template(template_name)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "Write-Host 'javac --version'; javac --version;"
            self.assertIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "Write-Host 'javac -version'; javac -version;"
            self.assertIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "Write-Host 'javac --version'; javac --version;"
            self.assertNotIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = "Write-Host 'javac -version'; javac -version;"
            self.assertNotIn(expected_string, rendered_template)

    def test_jdk11plus_jshell_cmd(self):
        template_name = "partials/jshell.j2"
        template = self.env.get_template(template_name)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = 'CMD ["jshell"]'
            self.assertIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "17", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = 'CMD ["jshell"]'
            self.assertNotIn(expected_string, rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            expected_string = 'CMD ["jshell"]'
            self.assertNotIn(expected_string, rendered_template)


if __name__ == "__main__":
    unittest.main()
