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

import io
import json
import os
import tempfile
import textwrap
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from adoptium_api import get_latest_lts, get_supported_versions
from dockerhub_doc_config_update import (
    find_manifest_block,
    format_ojdk_version,
    get_block_gitcommit,
    get_distro_name,
    get_dockerfile_arches,
    get_java_version,
    get_pending_arches,
    generate_manifest,
    java_version_key,
)


MOCK_API_RESPONSE = {
    "available_lts_releases": [8, 11, 17, 21, 25],
    "available_releases": [8, 11, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26],
    "most_recent_feature_release": 26,
    "most_recent_feature_version": 27,
    "most_recent_lts": 25,
    "tip_version": 27,
}


def mock_urlopen(req):
    """Mock urllib.request.urlopen to return fake API data."""
    class MockResponse:
        def read(self):
            return json.dumps(MOCK_API_RESPONSE).encode("utf-8")
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
    return MockResponse()


class TestAdoptiumAPI(unittest.TestCase):

    @patch("adoptium_api.urllib.request.urlopen", side_effect=mock_urlopen)
    def test_get_supported_versions(self, _mock):
        versions = get_supported_versions()
        self.assertEqual(versions, [8, 11, 17, 21, 25, 26])

    @patch("adoptium_api.urllib.request.urlopen", side_effect=mock_urlopen)
    def test_get_supported_versions_lts_only(self, _mock):
        """When most_recent_feature_release equals most_recent_lts, only LTS versions are returned."""
        with patch.dict(MOCK_API_RESPONSE, {"most_recent_feature_release": 25}):
            versions = get_supported_versions()
            self.assertEqual(versions, [8, 11, 17, 21, 25])

    @patch("adoptium_api.urllib.request.urlopen", side_effect=mock_urlopen)
    def test_get_supported_versions_multiple_non_lts(self, _mock):
        """When there are multiple non-LTS releases between the latest LTS and the most recent feature release."""
        with patch.dict(MOCK_API_RESPONSE, {"most_recent_feature_release": 28, "available_releases": [8, 11, 17, 21, 25, 26, 27, 28]}):
            versions = get_supported_versions()
            self.assertEqual(versions, [8, 11, 17, 21, 25, 26, 27, 28])

    @patch("adoptium_api.urllib.request.urlopen", side_effect=mock_urlopen)
    def test_get_latest_lts(self, _mock):
        self.assertEqual(get_latest_lts(), 25)


class TestFormatOjdkVersion(unittest.TestCase):

    def test_jdk8_version(self):
        self.assertEqual(format_ojdk_version("jdk8u482-b08"), "8u482-b08")

    def test_jdk11_version(self):
        self.assertEqual(format_ojdk_version("jdk-11.0.30+7"), "11.0.30_7")

    def test_jdk25_version(self):
        self.assertEqual(format_ojdk_version("jdk-25.0.2+10"), "25.0.2_10")

    def test_jdk26_ea_version(self):
        self.assertEqual(format_ojdk_version("jdk-26+35"), "26_35")


class TestGetDistroName(unittest.TestCase):

    def test_ubuntu(self):
        self.assertEqual(get_distro_name("linux", "ubuntu/noble"), "noble")

    def test_alpine(self):
        self.assertEqual(get_distro_name("alpine-linux", "alpine/3.23"), "alpine-3.23")

    def test_ubi(self):
        self.assertEqual(get_distro_name("linux", "ubi/ubi10-minimal"), "ubi10-minimal")

    def test_windows(self):
        self.assertEqual(
            get_distro_name("windows", "windows/windowsservercore-ltsc2022"),
            "windowsservercore-ltsc2022",
        )


class TestGetJavaVersion(unittest.TestCase):

    def test_extracts_version(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write("FROM ubuntu:24.04\n")
            f.write("ENV JAVA_VERSION=jdk-25.0.2+10\n")
            f.write("RUN echo hello\n")
            f.flush()
            self.assertEqual(get_java_version(f.name), "jdk-25.0.2+10")
            os.unlink(f.name)

    def test_returns_none_when_missing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write("FROM ubuntu:24.04\n")
            f.write("RUN echo hello\n")
            f.flush()
            self.assertIsNone(get_java_version(f.name))
            os.unlink(f.name)


class TestGetDockerfileArches(unittest.TestCase):

    def test_parses_ubuntu_arches(self):
        dockerfile = textwrap.dedent("""\
            FROM ubuntu:24.04
            RUN set -eux; \\
                ARCH="$(dpkg --print-architecture)"; \\
                case "${ARCH}" in \\
               amd64) \\
                 ESUM='abc123'; \\
                 ;; \\
               arm64) \\
                 ESUM='def456'; \\
                 ;; \\
               ppc64el) \\
                 ESUM='ghi789'; \\
                 ;; \\
               s390x) \\
                 ESUM='jkl012'; \\
                 ;; \\
               *) \\
                 echo "Unsupported arch: ${ARCH}"; \\
                 exit 1; \\
                 ;; \\
            esac;
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write(dockerfile)
            f.flush()
            arches = get_dockerfile_arches(f.name)
            self.assertEqual(arches, ["amd64", "arm64v8", "ppc64le", "s390x"])
            os.unlink(f.name)

    def test_parses_alpine_arches(self):
        dockerfile = textwrap.dedent("""\
            FROM alpine:3.23
            RUN set -eux; \\
                ARCH="$(apk --print-arch)"; \\
                case "${ARCH}" in \\
               x86_64) \\
                 ESUM='abc123'; \\
                 ;; \\
               aarch64) \\
                 ESUM='def456'; \\
                 ;; \\
               *) \\
                 echo "Unsupported arch: ${ARCH}"; \\
                 exit 1; \\
                 ;; \\
            esac;
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write(dockerfile)
            f.flush()
            arches = get_dockerfile_arches(f.name)
            self.assertEqual(arches, ["amd64", "arm64v8"])
            os.unlink(f.name)

    def test_parses_armhf(self):
        dockerfile = textwrap.dedent("""\
            FROM ubuntu:22.04
            RUN set -eux; \\
                case "${ARCH}" in \\
               amd64) \\
                 ;; \\
               armhf) \\
                 ;; \\
               *) \\
                 ;; \\
            esac;
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write(dockerfile)
            f.flush()
            arches = get_dockerfile_arches(f.name)
            self.assertEqual(arches, ["amd64", "arm32v7"])
            os.unlink(f.name)

    def test_staggered_release_fewer_arches(self):
        """A Dockerfile with only amd64 and arm64 (e.g. early access release)."""
        dockerfile = textwrap.dedent("""\
            FROM ubuntu:24.04
            RUN set -eux; \\
                case "${ARCH}" in \\
               amd64) \\
                 ;; \\
               arm64) \\
                 ;; \\
               *) \\
                 ;; \\
            esac;
        """)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".Dockerfile", delete=False) as f:
            f.write(dockerfile)
            f.flush()
            arches = get_dockerfile_arches(f.name)
            self.assertEqual(arches, ["amd64", "arm64v8"])
            os.unlink(f.name)

    def test_pending_arches_only_include_marked_branches(self):
        dockerfile = textwrap.dedent("""\
            # TODO: This configured architecture is pending upstream binary availability
            RUN case "${ARCH}" in
                amd64)
                    ESUM='abc';
                    ;;
                armhf)
                    # TODO: This configured architecture is pending upstream binary availability for jdk8u504-b01.
                    exit 1;
                    ;;
                arm64)
                    ESUM='def';
                    ;;
                *)
                    # TODO: This configured architecture is pending upstream binary availability
                    exit 1;
                    ;;
            esac;
        """)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "Dockerfile"
            path.write_text(dockerfile)
            self.assertEqual(get_pending_arches(path), ["arm32v7"])
            self.assertEqual(get_dockerfile_arches(path), ["amd64", "arm32v7", "arm64v8"])


class TestJavaVersionKey(unittest.TestCase):

    def test_feature_build_is_older_than_patch_release(self):
        self.assertLess(java_version_key("jdk-27+35"), java_version_key("jdk-27.0.1.0"))

    def test_build_numbers_are_numeric(self):
        self.assertLess(java_version_key("jdk-25.0.2+9"), java_version_key("jdk-25.0.2+10"))

    def test_jdk8_update_and_build_numbers(self):
        self.assertLess(java_version_key("jdk8u492-b10"), java_version_key("jdk8u502-b01"))
        self.assertLess(java_version_key("jdk8u502-b09"), java_version_key("jdk8u502-b10"))


class TestFindManifestBlock(unittest.TestCase):

    SAMPLE_MANIFEST = (
        "Tags: 25.0.2_10-jdk-noble, 25-jdk-noble\n"
        "Architectures: amd64, arm64v8\n"
        "GitCommit: abc123\n"
        "Directory: 25/jdk/ubuntu/noble\n"
        "\n"
        "Tags: 26_35-jdk-noble, 26-jdk-noble\n"
        "Architectures: amd64\n"
        "GitCommit: def456\n"
        "Directory: 26/jdk/ubuntu/noble"
    )

    def test_finds_matching_block(self):
        block = find_manifest_block(self.SAMPLE_MANIFEST, "25.0.2_10-jdk-noble, 25-jdk-noble")
        self.assertIn("GitCommit: abc123", block)

    def test_returns_none_for_no_match(self):
        block = find_manifest_block(self.SAMPLE_MANIFEST, "99-jdk-noble")
        self.assertIsNone(block)

    def test_returns_none_for_empty_manifest(self):
        self.assertIsNone(find_manifest_block("", "25-jdk-noble"))
        self.assertIsNone(find_manifest_block(None, "25-jdk-noble"))


class TestGetBlockGitcommit(unittest.TestCase):

    def test_extracts_commit(self):
        block = "Tags: 25-jdk-noble\nGitCommit: abc123def\nDirectory: 25/jdk"
        self.assertEqual(get_block_gitcommit(block), "abc123def")

    def test_returns_none_for_no_commit(self):
        block = "Tags: 25-jdk-noble\nDirectory: 25/jdk"
        self.assertIsNone(get_block_gitcommit(block))

    def test_returns_none_for_none(self):
        self.assertIsNone(get_block_gitcommit(None))


class TestGenerateManifest(unittest.TestCase):
    """Integration test using a minimal config and temp Dockerfiles."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        # Create a minimal Dockerfile
        jdk_dir = os.path.join(self.tmpdir, "25", "jdk", "ubuntu", "noble")
        os.makedirs(jdk_dir)
        with open(os.path.join(jdk_dir, "Dockerfile"), "w") as f:
            f.write(textwrap.dedent("""\
                FROM ubuntu:24.04
                ENV JAVA_VERSION=jdk-25.0.2+10
                RUN set -eux; \\
                    ARCH="$(dpkg --print-architecture)"; \\
                    case "${ARCH}" in \\
                   amd64) \\
                     ESUM='abc'; \\
                     ;; \\
                   arm64) \\
                     ESUM='def'; \\
                     ;; \\
                   *) \\
                     echo "Unsupported"; \\
                     exit 1; \\
                     ;; \\
                esac;
            """))

        self.config = {
            "configurations": {
                "linux": [{
                    "directory": "ubuntu/noble",
                    "image": "ubuntu:24.04",
                    "architectures": ["aarch64", "x64"],
                    "os": "ubuntu",
                }],
                "alpine-linux": [{
                    "directory": "alpine/3.23",
                    "image": "alpine:3.23",
                    "architectures": ["aarch64", "x64"],
                    "os": "alpine-linux",
                }],
            },
        }
        self.output_file = os.path.join(self.tmpdir, "eclipse-temurin")
        self.orig_dir = os.getcwd()
        os.chdir(self.tmpdir)

    def tearDown(self):
        os.chdir(self.orig_dir)
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("dockerhub_doc_config_update.get_supported_versions", return_value=[25])
    @patch("dockerhub_doc_config_update.get_latest_lts", return_value=25)
    @patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123")
    @patch("dockerhub_doc_config_update.fetch_official_manifest", return_value="")
    def test_generates_valid_manifest(self, _fetch, _git, _lts, _versions):
        generate_manifest(self.config, self.output_file)

        with open(self.output_file) as f:
            content = f.read()

        # Check header
        self.assertIn("# Eclipse Temurin OpenJDK images provided by the Eclipse Foundation.", content)
        self.assertIn("GitRepo: https://github.com/adoptium/containers.git", content)
        self.assertIn("Builder: buildkit", content)

        # Check tags for v25 JDK noble
        self.assertIn("Tags: 25.0.2_10-jdk-noble, 25-jdk-noble, 25-noble", content)
        self.assertIn("SharedTags: 25.0.2_10-jdk, 25-jdk, 25, latest", content)

        # Architectures come from the Dockerfile, not config
        self.assertIn("Architectures: amd64, arm64v8", content)

        # GitCommit
        self.assertIn("GitCommit: abc123", content)
        self.assertIn("Directory: 25/jdk/ubuntu/noble", content)

    @patch("dockerhub_doc_config_update.get_supported_versions", return_value=[25])
    @patch("dockerhub_doc_config_update.get_latest_lts", return_value=25)
    @patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123")
    @patch("dockerhub_doc_config_update.fetch_official_manifest", return_value="")
    def test_no_trailing_blank_lines(self, _fetch, _git, _lts, _versions):
        generate_manifest(self.config, self.output_file)

        with open(self.output_file) as f:
            content = f.read()

        # File should end with exactly one newline
        self.assertTrue(content.endswith("\n"))
        self.assertFalse(content.endswith("\n\n"))

    @patch("dockerhub_doc_config_update.get_supported_versions", return_value=[25])
    @patch("dockerhub_doc_config_update.get_latest_lts", return_value=25)
    @patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123")
    @patch("dockerhub_doc_config_update.fetch_official_manifest", return_value="")
    def test_skips_missing_dockerfiles(self, _fetch, _git, _lts, _versions):
        """Entries for os families with no Dockerfiles on disk should be skipped."""
        generate_manifest(self.config, self.output_file)

        with open(self.output_file) as f:
            content = f.read()

        # alpine-linux config exists but no Dockerfile was created for it
        self.assertNotIn("alpine-3.23", content)

    @patch("dockerhub_doc_config_update.get_supported_versions", return_value=[8])
    @patch("dockerhub_doc_config_update.get_latest_lts", return_value=8)
    @patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123")
    @patch("dockerhub_doc_config_update.fetch_official_manifest", return_value="")
    def test_jdk8_arm32_uses_standard_tags(
        self, _fetch, _git, _lts, _versions
    ):
        jdk_dir = os.path.join(self.tmpdir, "8", "jdk", "ubuntu", "noble")
        os.makedirs(jdk_dir)

        with open(os.path.join(jdk_dir, "Dockerfile"), "w") as f:
            f.write(textwrap.dedent("""\
                FROM ubuntu:24.04
                ENV JAVA_VERSION=jdk8u504-b01
                                RUN case "${ARCH}" in
                                     amd64)
                                         ;;
                                     armhf)
                                         # TODO: This configured architecture is pending upstream binary availability for jdk8u504-b01.
                                         echo "Temurin binary for armhf is not available yet"
                                         exit 1
                                         ;;
                esac;
            """))

        generate_manifest(self.config, self.output_file)

        with open(self.output_file) as f:
            content = f.read()

        blocks = content.split("\n\n")
        matching_blocks = [
            block
            for block in blocks
            if "Tags: 8u504-b01-jdk-noble, 8-jdk-noble, 8-noble" in block
        ]

        self.assertEqual(len(matching_blocks), 1)
        main_block = matching_blocks[0]
        self.assertIn(
            "SharedTags: 8u504-b01-jdk, 8-jdk, 8, latest",
            main_block,
        )
        self.assertIn("Architectures: amd64, arm32v7", main_block)
        self.assertIn("Directory: 8/jdk/ubuntu/noble", main_block)
        self.assertNotIn("Tags: 8u504-b01-jdk-noble-arm32v7", content)


class TestPublishReadiness(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmpdir.cleanup)
        original_dir = os.getcwd()
        os.chdir(self.tmpdir.name)
        self.addCleanup(os.chdir, original_dir)
        self.config = {
            "configurations": {
                "linux": [{
                    "directory": "ubuntu/noble",
                    "architectures": ["x64", "aarch64"],
                }],
                "alpine-linux": [{
                    "directory": "alpine/3.24",
                    "architectures": ["x64", "aarch64"],
                }],
            },
        }
        for package in ("jdk", "jre"):
            for directory in ("ubuntu/noble", "alpine/3.24"):
                self.write_dockerfile(package, directory)

    def write_dockerfile(
        self, package, directory, release="jdk-25.0.2+10",
        arches=("amd64", "arm64"), pending=(),
    ):
        path = Path("25") / package / directory / "Dockerfile"
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [f"ENV JAVA_VERSION={release}", 'RUN case "${ARCH}" in']
        for arch in arches:
            lines.append(f"    {arch})")
            if arch in pending:
                lines.append("        # TODO: This configured architecture is pending upstream binary availability")
                lines.append("        exit 1;")
            lines.append("        ;;")
        lines.append("esac;")
        path.write_text("\n".join(lines))
        return path

    def generate(self):
        output = io.StringIO()
        with (
            patch("dockerhub_doc_config_update.get_supported_versions", return_value=[25]),
            patch("dockerhub_doc_config_update.get_latest_lts", return_value=25),
            patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123"),
            patch("dockerhub_doc_config_update.fetch_official_manifest", return_value=""),
            redirect_stdout(output),
        ):
            generate_manifest(self.config, "manifest")
        return output.getvalue(), Path("manifest").read_text()

    def assert_readiness(self, summary, status, complete):
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in summary.splitlines() if line.startswith("|")
        ]
        self.assertIn(["25", "25.0.2_10", status, complete], rows)

    def test_complete_release_is_ready_and_summary_is_not_in_manifest(self):
        summary, manifest = self.generate()
        self.assert_readiness(summary, "READY", "4/4")
        self.assertIn("Ready for upstream publish: manifest", summary)
        self.assertNotIn("readiness", manifest)
        self.assertNotIn("Publication blockers:", summary)

    def test_pending_architecture_blocks_publish_without_removing_manifest_arch(self):
        self.write_dockerfile("jre", "ubuntu/noble", pending=("arm64",))
        summary, manifest = self.generate()
        self.assert_readiness(summary, "BLOCKED", "3/4")
        self.assertIn("pending binaries: arm64v8", summary)
        self.assertIn("JRE ubuntu/noble", summary)
        self.assertIn("NOT ready for upstream publish", summary)
        self.assertIn("Architectures: amd64, arm64v8", manifest)
        self.assertIn("Directory: 25/jre/ubuntu/noble", manifest)

    def test_missing_architecture_blocks_publish(self):
        self.write_dockerfile("jdk", "ubuntu/noble", arches=("amd64",))
        summary, _ = self.generate()
        self.assertIn("missing architectures: arm64v8", summary)
        self.assertIn("JDK ubuntu/noble", summary)
        self.assertIn("NOT ready for upstream publish", summary)

    def test_missing_jre_blocks_publish(self):
        Path("25/jre/ubuntu/noble/Dockerfile").unlink()
        summary, _ = self.generate()
        self.assertIn("missing Dockerfile", summary)
        self.assertIn("JRE ubuntu/noble", summary)
        self.assert_readiness(summary, "BLOCKED", "3/4")

    def test_missing_java_version_blocks_publish(self):
        Path("25/jre/ubuntu/noble/Dockerfile").write_text("FROM ubuntu:24.04\n")
        summary, _ = self.generate()
        self.assertIn("missing JAVA_VERSION", summary)
        self.assertIn("JRE ubuntu/noble", summary)

    def test_stale_jre_blocks_publish(self):
        self.write_dockerfile("jre", "ubuntu/noble", release="jdk-25.0.2+9")
        summary, _ = self.generate()
        self.assertIn("stale release jdk-25.0.2+9;", summary)
        self.assertIn("jdk-25.0.2+10", summary)
        self.assertIn("JRE ubuntu/noble", summary)
        self.assert_readiness(summary, "BLOCKED", "3/4")

    def test_stale_windows_release_blocks_publish(self):
        self.config["configurations"]["windows"] = [{
            "directory": "windows/windowsservercore-ltsc2022",
            "architectures": ["x64"],
        }]
        for package in ("jdk", "jre"):
            self.write_dockerfile(
                package, "windows/windowsservercore-ltsc2022",
                release="jdk-25+36", arches=(),
            )
        summary, _ = self.generate()
        self.assert_readiness(summary, "BLOCKED", "4/6")
        self.assertIn("stale release jdk-25+36;", summary)
        self.assertIn("jdk-25.0.2+10", summary)
        self.assertEqual(summary.count("stale release"), 1)
        self.assertIn("JDK+JRE windows/windowsservercore-ltsc2022", summary)

    def test_current_windows_release_is_ready(self):
        self.config["configurations"]["windows"] = [{
            "directory": "windows/windowsservercore-ltsc2022",
            "architectures": ["x64"],
        }]
        for package in ("jdk", "jre"):
            self.write_dockerfile(package, "windows/windowsservercore-ltsc2022", arches=())
        summary, manifest = self.generate()
        self.assert_readiness(summary, "READY", "6/6")
        self.assertIn("Architectures: windows-amd64", manifest)

    def test_global_and_local_architecture_overrides(self):
        self.config["architecture_overrides"] = [{"versions": ">=25", "exclude": ["aarch64"]}]
        self.config["configurations"]["linux"][0]["architecture_overrides"] = [
            {"versions": "==25", "include": ["s390x"]},
        ]
        summary, _ = self.generate()
        self.assertIn("missing architectures: s390x", summary)
        for package in ("jdk", "jre"):
            self.write_dockerfile(package, "ubuntu/noble", arches=("amd64", "s390x"))
            self.write_dockerfile(package, "alpine/3.24", arches=("amd64",))
        summary, _ = self.generate()
        self.assert_readiness(summary, "READY", "4/4")

    def test_deprecated_and_version_excluded_configs_are_not_blockers(self):
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        self.config["configurations"]["linux"].append({
            "directory": "ubuntu/jammy",
            "architectures": ["x64"],
            "versions": [21],
        })
        summary, _ = self.generate()
        self.assert_readiness(summary, "READY", "2/2")
        self.assertNotIn("missing Dockerfile", summary)

    def test_no_dockerfile_architectures_blocks_publish(self):
        self.write_dockerfile("jdk", "ubuntu/noble", arches=())
        summary, _ = self.generate()
        blocker_cells = [
            line.split("|")[2].strip()
            for line in summary.splitlines() if line.startswith("|")
        ]
        self.assertIn("no Dockerfile architectures", " ".join(blocker_cells))
        self.assertIn("NOT ready for upstream publish", summary)

    def test_no_configured_architectures_blocks_publish(self):
        self.config["configurations"]["linux"][0]["architectures"] = []
        summary, _ = self.generate()
        self.assertIn("no configured architectures", summary)
        self.assert_readiness(summary, "BLOCKED", "2/4")

    def test_identical_blockers_are_grouped_into_a_short_summary(self):
        for package in ("jdk", "jre"):
            for directory in ("ubuntu/noble", "alpine/3.24"):
                self.write_dockerfile(package, directory, pending=("arm64",))
        summary, _ = self.generate()
        self.assert_readiness(summary, "BLOCKED", "0/4")
        self.assertEqual(summary.count("pending binaries: arm64v8"), 1)
        self.assertIn("JDK+JRE alpine/3.24, ubuntu/noble", summary)
        table_lines = [line for line in summary.splitlines() if line.startswith(("|", "+"))]
        self.assertTrue(table_lines)
        self.assertLessEqual(max(map(len, table_lines)), 116)
        for table in summary.split("\n\n"):
            lines = [line for line in table.splitlines() if line.startswith(("|", "+"))]
            if lines:
                self.assertEqual(len({len(line) for line in lines}), 1)

    def test_long_blockers_wrap_without_losing_affected_images(self):
        directories = [
            "windows/windowsservercore-ltsc2022",
            "windows/nanoserver-ltsc2022",
            "windows/windowsservercore-ltsc2025",
            "windows/nanoserver-ltsc2025",
        ]
        self.config["configurations"]["windows"] = [
            {"directory": directory, "architectures": ["x64"]}
            for directory in directories
        ]
        for package in ("jdk", "jre"):
            for directory in directories:
                self.write_dockerfile(package, directory, release="jdk-25+36", arches=())
        summary, _ = self.generate()
        self.assert_readiness(summary, "BLOCKED", "4/12")
        table_lines = [line for line in summary.splitlines() if line.startswith(("|", "+"))]
        self.assertLessEqual(max(map(len, table_lines)), 116)
        for directory in directories:
            self.assertIn(directory, summary)
        self.assertIn("NOT ready for upstream publish", summary)


if __name__ == "__main__":
    unittest.main()
