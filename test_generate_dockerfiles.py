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

import unittest
from unittest.mock import Mock, mock_open, patch

from jinja2 import Environment, FileSystemLoader


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
            self.assertIn("javac --version", rendered_template)
            self.assertIn("java --version", rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jdk"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            self.assertIn("javac -version", rendered_template)
            self.assertIn("java -version", rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "11", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            self.assertNotIn("javac --version", rendered_template)
            self.assertIn("java --version", rendered_template)

        with self.subTest():
            # The context/variables to render the template
            context = {"version": "8", "image_type": "jre"}
            rendered_template = template.render(**context)

            # Expected string/partial in the rendered output
            self.assertNotIn("javac -version", rendered_template)
            self.assertIn("java -version", rendered_template)

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
