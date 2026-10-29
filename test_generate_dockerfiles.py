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
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from jinja2 import Environment, FileSystemLoader
import yaml

from architecture_config import resolve_architectures
from generate_dockerfiles import add_missing_architectures


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

    def test_pending_architecture_rendering(self):
        template = self.env.get_template("ubuntu.Dockerfile.j2")
        context = {
            "version": 11,
            "image_type": "jdk",
            "java_version": "jdk-11.0.30+7",
            "os": "ubuntu",
            "arch_data": {
                "amd64": {
                    "download_url": "http://fake-url.com",
                    "checksum": "fake-checksum",
                },
                "arm64": {"pending": True},
            },
        }

        rendered_template = template.render(**context)
        pending_branch = rendered_template.split("arm64)", 1)[1].split(";;", 1)[0]

        self.assertIn(
            "This configured architecture is pending upstream binary availability",
            pending_branch,
        )
        self.assertIn(
            "retry after it is published upstream",
            pending_branch,
        )
        self.assertNotIn("ESUM=", pending_branch)
        self.assertNotIn("BINARY_URL=", pending_branch)

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
        self.assertIn("/certificates/*crt", rendered_template)
        self.assertNotIn("/certificates/*.crt", rendered_template)
        self.assertIn("cp -La /certificates/* /usr/local/share/ca-certificates/", rendered_template)
        self.assertIn("exec \"$@\"", rendered_template)


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


class TestConfiguredAlpineArchitectures(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parent
        with (root / "config" / "temurin.yml").open() as source:
            self.config = yaml.safe_load(source)
        self.env = Environment(loader=FileSystemLoader(root / "docker_templates"))

    def test_alpine_arm64_starts_at_java21_for_every_distro(self):
        for distro in self.config["configurations"]["alpine-linux"]:
            overrides = self.config["architecture_overrides"] + distro.get("architecture_overrides", [])
            for version in (8, 11, 17, 21, 25, 26, 27):
                with self.subTest(distro=distro["directory"], version=version):
                    architectures = resolve_architectures(distro["architectures"], overrides, version)
                    self.assertEqual(architectures, ["x64"] if version < 21 else ["aarch64", "x64"])

    def test_old_alpine_jdk_and_jre_do_not_render_pending_arm64(self):
        template = self.env.get_template("alpine-linux.Dockerfile.j2")
        for distro in self.config["configurations"]["alpine-linux"]:
            overrides = self.config["architecture_overrides"] + distro.get("architecture_overrides", [])
            for version in (8, 11, 17):
                architectures = resolve_architectures(distro["architectures"], overrides, version)
                arch_data = add_missing_architectures({
                    "x86_64": {"download_url": "https://example.com/java.tar.gz", "checksum": "abc"},
                }, architectures, "alpine-linux")
                for package in ("jdk", "jre"):
                    with self.subTest(distro=distro["directory"], version=version, package=package):
                        rendered = template.render(
                            base_image=distro["image"], image_type=package,
                            java_version=f"jdk-{version}", version=version,
                            arch_data=arch_data, os_family="alpine-linux", os="alpine-linux",
                        )
                        self.assertIn("x86_64)", rendered)
                        self.assertNotIn("aarch64)", rendered)
                        self.assertNotIn("pending upstream binary availability", rendered)

    def test_other_linux_distros_retain_arm64_for_older_java(self):
        for distro in self.config["configurations"]["linux"]:
            overrides = self.config["architecture_overrides"] + distro.get("architecture_overrides", [])
            for version in (8, 11, 17):
                with self.subTest(distro=distro["directory"], version=version):
                    self.assertIn("aarch64", resolve_architectures(distro["architectures"], overrides, version))


class TestAddMissingArchitectures(unittest.TestCase):
    def test_adds_pending_entries_for_every_missing_architecture(self):
        arch_data = {
            "amd64": {
                "download_url": "http://fake-url.com",
                "checksum": "fake-checksum",
            }
        }
        architectures = ["aarch64", "arm", "ppc64le", "s390x", "x64"]

        result = add_missing_architectures(arch_data, architectures, "ubuntu")

        self.assertEqual(
            set(result),
            {"amd64", "arm64", "armhf", "ppc64el", "s390x"},
        )
        self.assertEqual(result["amd64"], arch_data["amd64"])
        for architecture in ["arm64", "armhf", "ppc64el", "s390x"]:
            self.assertEqual(result[architecture], {"pending": True})
        self.assertEqual(set(arch_data), {"amd64"})


if __name__ == "__main__":
    unittest.main()
