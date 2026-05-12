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

from generate_dockerfiles import resolve_architectures


class TestJinjaRendering(unittest.TestCase):
    def setUp(self):
        # Setup the Jinja2 environment
        self.env = Environment(loader=FileSystemLoader("docker_templates"))

    def test_armhf_ubuntu8_rendering(self):
        template_name = "ubuntu.Dockerfile.j2"
        template = self.env.get_template(template_name)

        arch_data = {}

        arch_data["armhf"] = {
            "download_url": "http://fake-url.com",
            "checksum": "fake-checksum",
        }

        # The context/variables to render the template
        context = {
            "architecture": "armhf",
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

    def test_binutils_inclusion(self):
        template_name = "ubuntu.Dockerfile.j2"
        template = self.env.get_template(template_name)

        # Binutils should be included for jdk images with version >= 13
        with self.subTest("jdk 13+ should include binutils"):
            context = {
                "version": 13,
                "image_type": "jdk",
                "os": "ubuntu",
                "arch_data": {},
            }
            rendered_template = template.render(**context)
            self.assertIn("binutils", rendered_template)

        # Binutils should not be included for jre images regardless of version
        with self.subTest("jre 13+ should not include binutils"):
            context = {
                "version": 13,
                "image_type": "jre",
                "os": "ubuntu",
                "arch_data": {},
            }
            rendered_template = template.render(**context)
            self.assertNotIn("binutils", rendered_template)

        # Binutils should not be included for jdk images with version < 13
        with self.subTest("jdk < 13 should not include binutils"):
            context = {
                "version": 12,
                "image_type": "jdk",
                "os": "ubuntu",
                "arch_data": {},
            }
            rendered_template = template.render(**context)
            self.assertNotIn("binutils", rendered_template)

    def test_arch_data_population(self):
        template_name = "ubuntu.Dockerfile.j2"
        template = self.env.get_template(template_name)

        # Simulate API response
        arch_data = {
            "amd64": {
                "download_url": "http://fake-url.com",
                "checksum": "fake-checksum",
            }
        }

        context = {
            "version": 11,
            "image_type": "jdk",
            "os": "ubuntu",
            "arch_data": arch_data,
        }
        rendered_template = template.render(**context)

        self.assertIn("http://fake-url.com", rendered_template)
        self.assertIn("fake-checksum", rendered_template)

    def test_entrypoint_rendering(self):
        template_name = "entrypoint.sh.j2"
        template = self.env.get_template(template_name)

        context = {
            "image_type": "jdk",
            "os": "ubuntu",
            "version": 11,
        }
        rendered_template = template.render(**context)

        # Ensure that the entrypoint script contains expected commands
        self.assertIn("update-ca-certificates", rendered_template)
        self.assertIn("exec \"$@\"", rendered_template)

    def test_entrypoint_ps1_rendering(self):
        template_name = "entrypoint.ps1.j2"
        template = self.env.get_template(template_name)

        with self.subTest("jdk 11 truststore path"):
            context = {
                "image_type": "jdk",
                "version": 11,
            }
            rendered_template = template.render(**context)

            # Equivalent of update-ca-certificates: imports from Windows cert store
            self.assertIn("Cert:\\LocalMachine\\Root", rendered_template)
            # Equivalent of exec "$@": forwards to the original command
            self.assertIn("& $args[0]", rendered_template)
            # Uses standard truststore path for JDK 11+
            self.assertIn("$env:JAVA_HOME\\lib\\security\\cacerts", rendered_template)
            # Should not use JDK8 JRE subdirectory path
            self.assertNotIn("\\jre\\lib\\security\\cacerts", rendered_template)

        with self.subTest("jdk 8 truststore path"):
            context = {
                "image_type": "jdk",
                "version": 8,
            }
            rendered_template = template.render(**context)

            # JDK8 puts its JRE in a subdirectory
            self.assertIn("$env:JAVA_HOME\\jre\\lib\\security\\cacerts", rendered_template)

        with self.subTest("jre 11 truststore path"):
            context = {
                "image_type": "jre",
                "version": 11,
            }
            rendered_template = template.render(**context)

            # JRE uses standard path
            self.assertIn("$env:JAVA_HOME\\lib\\security\\cacerts", rendered_template)
            self.assertNotIn("\\jre\\lib\\security\\cacerts", rendered_template)

    def test_servercore_entrypoint_wiring(self):
        template_name = "servercore.Dockerfile.j2"
        template = self.env.get_template(template_name)

        context = {
            "base_image": "mcr.microsoft.com/windows/servercore:ltsc2022",
            "image_type": "jdk",
            "java_version": "11.0.20+8",
            "version": 11,
            "arch_data": {
                "download_url": "http://fake-url.com",
                "checksum": "fake-checksum",
            },
            "os": "servercore",
        }
        rendered_template = template.render(**context)

        # Ensure entrypoint.ps1 is copied and set as ENTRYPOINT
        self.assertIn("COPY entrypoint.ps1", rendered_template)
        self.assertIn("ENTRYPOINT", rendered_template)
        self.assertIn("C:\\\\entrypoint.ps1", rendered_template)


class TestResolveArchitectures(unittest.TestCase):
    def setUp(self):
        self.default_archs = ["aarch64", "arm", "ppc64le", "s390x", "x64"]

    def test_no_overrides_returns_default(self):
        result = resolve_architectures(self.default_archs, None, 17)
        self.assertEqual(result, self.default_archs)

    def test_empty_overrides_returns_default(self):
        result = resolve_architectures(self.default_archs, [], 17)
        self.assertEqual(result, self.default_archs)

    def test_exact_match_full_replacement(self):
        overrides = [{"versions": "==8", "architectures": ["aarch64", "x64"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 8), ["aarch64", "x64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 11), self.default_archs)

    def test_exclude(self):
        overrides = [{"versions": ">=21", "exclude": ["arm"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 21), ["aarch64", "ppc64le", "s390x", "x64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 17), self.default_archs)

    def test_include(self):
        overrides = [{"versions": ">=17", "include": ["riscv64"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 17), ["aarch64", "arm", "ppc64le", "s390x", "x64", "riscv64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 11), self.default_archs)

    def test_include_no_duplicates(self):
        overrides = [{"versions": ">=17", "include": ["x64", "riscv64"]}]
        result = resolve_architectures(self.default_archs, overrides, 17)
        self.assertEqual(result.count("x64"), 1)
        self.assertIn("riscv64", result)

    def test_multiple_matching_overrides_applied(self):
        overrides = [
            {"versions": ">=21", "exclude": ["arm"]},
            {"versions": "<17", "exclude": ["riscv64"]},
        ]
        # version 8 matches only second rule
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 8), ["aarch64", "arm", "ppc64le", "s390x", "x64"])
        # version 17 matches neither
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 17), self.default_archs)
        # version 21 matches only first rule
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 21), ["aarch64", "ppc64le", "s390x", "x64"])

    def test_all_matching_overrides_accumulate(self):
        overrides = [
            {"versions": "==8", "exclude": ["s390x"]},
            {"versions": "<17", "exclude": ["riscv64"]},
        ]
        # version 8 matches both rules
        result = resolve_architectures(["aarch64", "arm", "ppc64le", "riscv64", "s390x", "x64"], overrides, 8)
        self.assertNotIn("s390x", result)
        self.assertNotIn("riscv64", result)
        self.assertEqual(result, ["aarch64", "arm", "ppc64le", "x64"])

    def test_not_equal(self):
        overrides = [{"versions": "!=8", "exclude": ["arm"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 11), ["aarch64", "ppc64le", "s390x", "x64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 8), self.default_archs)

    def test_less_than(self):
        overrides = [{"versions": "<11", "exclude": ["s390x"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 8), ["aarch64", "arm", "ppc64le", "x64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 11), self.default_archs)

    def test_greater_than(self):
        overrides = [{"versions": ">17", "exclude": ["arm"]}]
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 21), ["aarch64", "ppc64le", "s390x", "x64"])
        self.assertEqual(resolve_architectures(self.default_archs, overrides, 17), self.default_archs)

    def test_invalid_condition_raises(self):
        overrides = [{"versions": "~8", "exclude": ["x64"]}]
        with self.assertRaises(ValueError):
            resolve_architectures(self.default_archs, overrides, 8)


if __name__ == "__main__":
    unittest.main()
