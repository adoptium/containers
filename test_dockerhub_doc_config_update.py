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
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.error import URLError

from adoptium_api import get_latest_lts, get_supported_versions
from dockerhub_doc_config_update import (
    find_manifest_block,
    fetch_official_manifest,
    fetch_open_publication_prs,
    create_publication_pr,
    format_ojdk_version,
    get_block_gitcommit,
    get_distro_name,
    get_dockerfile_arches,
    get_java_version,
    get_pending_arches,
    get_github_token,
    generate_manifest,
    java_version_key,
    main,
    merge_publication_manifest,
    github_pages,
    PublicationPlan,
    PublicationPR,
    prepare_publication_source,
    run_publication_command,
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
    def test_get_supported_versions_excludes_eol_26(self, _mock):
        with patch.dict(MOCK_API_RESPONSE, {"most_recent_feature_release": 27, "available_releases": [8, 11, 17, 21, 25, 26, 27]}):
            self.assertEqual(get_supported_versions(), [8, 11, 17, 21, 25, 27])

    @patch("adoptium_api.urllib.request.urlopen", side_effect=mock_urlopen)
    def test_get_supported_versions_multiple_non_lts(self, _mock):
        """Only the latest non-LTS release is supported alongside LTS releases."""
        with patch.dict(MOCK_API_RESPONSE, {"most_recent_feature_release": 28, "available_releases": [8, 11, 17, 21, 25, 26, 27, 28]}):
            versions = get_supported_versions()
            self.assertEqual(versions, [8, 11, 17, 21, 25, 28])

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

    def test_manifest_tag_and_java_version_compare_equal(self):
        self.assertEqual(java_version_key("25.0.2_10"), java_version_key("jdk-25.0.2+10"))
        self.assertEqual(java_version_key("8u502-b10"), java_version_key("jdk8u502-b10"))


class TestFetchOfficialManifest(unittest.TestCase):

    @patch("dockerhub_doc_config_update.urllib.request.urlopen", side_effect=URLError("unavailable"))
    def test_fetch_failure_is_reported_as_unavailable_not_an_empty_manifest(self, _urlopen):
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertIsNone(fetch_official_manifest())
        self.assertIn("cannot compare with the official manifest", output.getvalue())


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

    def generate(self, official_manifest="", versions=None, open_prs=(), dry_run=False):
        output = io.StringIO()
        stdout = io.StringIO()
        with (
            patch("dockerhub_doc_config_update.get_supported_versions", return_value=versions or [25]),
            patch("dockerhub_doc_config_update.get_latest_lts", return_value=25),
            patch("dockerhub_doc_config_update.get_git_commit", return_value="abc123"),
            patch("dockerhub_doc_config_update.fetch_official_manifest", return_value=official_manifest),
            patch("dockerhub_doc_config_update.fetch_open_publication_prs", return_value=open_prs),
            redirect_stderr(output),
            redirect_stdout(stdout),
        ):
            self.plan = generate_manifest(self.config, "manifest", dry_run=dry_run)
        self.assertEqual(stdout.getvalue(), "")
        return output.getvalue(), self.plan.manifest if dry_run else Path("manifest").read_text()

    def assert_readiness(self, summary, status, complete):
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in summary.splitlines() if line.startswith("|")
        ]
        self.assertIn(["25", "25.0.2_10", status, complete], [row[:4] for row in rows])

    def test_complete_release_is_ready_and_summary_is_not_in_manifest(self):
        summary, manifest = self.generate()
        self.assert_readiness(summary, "READY", "4/4")
        self.assertIn("Ready for upstream publish: Java 25.", summary)
        self.assertNotIn("readiness", manifest)
        self.assertNotIn("Publication blockers:", summary)
        self.assertIn("python3 dockerhub_doc_config_update.py --create-pr", summary)
        self.assertIn("python3 dockerhub_doc_config_update.py --dry-run", summary)
        self.assertEqual(self.plan.ready_releases, {25: "25.0.2_10"})

    def test_pending_architecture_blocks_publish_without_removing_manifest_arch(self):
        self.write_dockerfile("jre", "ubuntu/noble", pending=("arm64",))
        summary, manifest = self.generate()
        self.assert_readiness(summary, "BLOCKED", "3/4")
        self.assertIn("pending binaries: arm64v8", summary)
        self.assertIn("JRE ubuntu/noble", summary)
        self.assertIn("No updated Java versions are ready for upstream publish.", summary)
        self.assertIn("Architectures: amd64, arm64v8", manifest)
        self.assertIn("Directory: 25/jre/ubuntu/noble", manifest)

    def test_missing_architecture_blocks_publish(self):
        self.write_dockerfile("jdk", "ubuntu/noble", arches=("amd64",))
        summary, _ = self.generate()
        self.assertIn("missing architectures: arm64v8", summary)
        self.assertIn("JDK ubuntu/noble", summary)
        self.assertIn("No updated Java versions are ready for upstream publish.", summary)

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

    def test_removed_distro_still_upstream_is_reported_without_changing_readiness(self):
        _, upstream = self.generate()
        upstream += "\n" + "\n\n".join(
            f"Tags: 25.0.2_10-{package}-alpine-3.21\nDirectory: 25/{package}/alpine/3.21"
            for package in ("jdk", "jre")
        ) + "\n"
        summary, manifest = self.generate(official_manifest=upstream)
        self.assertIn("Deprecated or removed images still in the upstream official manifest:", summary)
        self.assertEqual(summary.count("JDK+JRE alpine/3.21"), 1)
        self.assert_readiness(summary, "UP TO DATE", "4/4")
        self.assertEqual(self.plan.ready_releases, {})
        self.assertNotIn("alpine/3.21", manifest)
        self.assertEqual(self.plan.cleanup_directories, {
            "25/jdk/alpine/3.21", "25/jre/alpine/3.21",
        })
        self.assertIn("Upstream cleanup ready: 2 retired image entries", summary)
        self.assertIn("--create-pr", summary)

    def test_deprecated_and_excluded_upstream_configs_are_reported(self):
        _, upstream = self.generate()
        for field, value in (("deprecated", 25), ("versions", [21])):
            with self.subTest(field=field):
                configuration = self.config["configurations"]["alpine-linux"][0]
                configuration[field] = value
                summary, _ = self.generate(official_manifest=upstream)
                self.assertIn("Deprecated or removed images still in the upstream official manifest:", summary)
                self.assertIn("JDK+JRE alpine/3.24", summary)
                self.assert_readiness(summary, "UP TO DATE", "2/2")
                del configuration[field]

    def test_distro_below_deprecation_threshold_is_not_reported(self):
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 26
        _, upstream = self.generate()
        summary, _ = self.generate(official_manifest=upstream)
        self.assertNotIn("Deprecated or removed images", summary)
        self.assert_readiness(summary, "UP TO DATE", "4/4")

    def test_missing_local_dockerfile_is_not_reported_as_deprecated_upstream(self):
        _, upstream = self.generate()
        Path("25/jre/ubuntu/noble/Dockerfile").unlink()
        summary, _ = self.generate(official_manifest=upstream)
        self.assertNotIn("Deprecated or removed images", summary)
        self.assertIn("missing Dockerfile", summary)
        self.assert_readiness(summary, "BLOCKED", "3/4")

    def test_retired_upstream_entries_are_reported_in_dry_runs(self):
        _, upstream = self.generate()
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        summary, _ = self.generate(official_manifest=upstream, dry_run=True)
        self.assertIn("Deprecated or removed images still in the upstream official manifest:", summary)
        self.assertIn("JDK+JRE alpine/3.24", summary)

    def test_unavailable_upstream_does_not_claim_retired_entries_exist(self):
        summary, _ = self.generate(official_manifest=None)
        self.assertNotIn("Deprecated or removed images", summary)
        self.assertIn("Upstream comparison unavailable", summary)

    def test_cleanup_can_be_planned_while_required_images_are_blocked(self):
        _, upstream = self.generate()
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        Path("25/jre/ubuntu/noble/Dockerfile").unlink()
        summary, _ = self.generate(official_manifest=upstream)
        self.assert_readiness(summary, "BLOCKED", "1/2")
        self.assertEqual(self.plan.ready_releases, {})
        self.assertEqual(self.plan.cleanup_directories, {
            "25/jdk/alpine/3.24", "25/jre/alpine/3.24",
        })

    def test_cleanup_already_in_open_pr_is_not_suggested_again(self):
        _, upstream = self.generate()
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        url = "https://github.com/docker-library/official-images/pull/456"
        summary, _ = self.generate(
            official_manifest=upstream,
            open_prs=[PublicationPR(url, set(), {
                "25/jdk/alpine/3.24", "25/jre/alpine/3.24",
            })],
        )
        self.assertEqual(self.plan.cleanup_directories, set())
        self.assertIn(f"Upstream cleanup PR open: {url}", summary)
        self.assertNotIn("Upstream cleanup ready:", summary)

    def test_partial_cleanup_pr_leaves_other_retired_entries_available(self):
        _, upstream = self.generate()
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        self.generate(
            official_manifest=upstream,
            open_prs=[PublicationPR("https://github.com/docker-library/official-images/pull/456",
                                    set(), {"25/jdk/alpine/3.24"})],
        )
        self.assertEqual(self.plan.cleanup_directories, {"25/jre/alpine/3.24"})

    def test_cleanup_requires_successful_pr_lookup_even_without_release_updates(self):
        _, upstream = self.generate()
        self.config["configurations"]["alpine-linux"][0]["deprecated"] = 25
        summary, _ = self.generate(official_manifest=upstream, open_prs=None)
        self.assertFalse(self.plan.open_prs_available)
        self.assertEqual(self.plan.cleanup_directories, set())
        self.assertIn("Upstream cleanup UNKNOWN", summary)
        self.assertNotIn("Upstream cleanup ready:", summary)

    def test_no_dockerfile_architectures_blocks_publish(self):
        self.write_dockerfile("jdk", "ubuntu/noble", arches=())
        summary, _ = self.generate()
        blocker_cells = [
            line.split("|")[2].strip()
            for line in summary.splitlines() if line.startswith("|")
        ]
        self.assertIn("no Dockerfile architectures", " ".join(blocker_cells))
        self.assertIn("No updated Java versions are ready for upstream publish.", summary)

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
        self.assertIn("No updated Java versions are ready for upstream publish.", summary)

    def test_same_release_upstream_is_up_to_date_even_with_different_git_commit(self):
        _, manifest = self.generate()
        upstream = manifest.replace("GitCommit: abc123", "GitCommit: already-published")
        summary, _ = self.generate(official_manifest=upstream)
        self.assert_readiness(summary, "UP TO DATE", "4/4")
        self.assertNotIn("Ready for upstream publish: Java 25.", summary)

    def test_new_release_relative_to_upstream_is_ready(self):
        _, manifest = self.generate()
        summary, _ = self.generate(official_manifest=manifest.replace("25.0.2_10", "25.0.1_8"))
        self.assert_readiness(summary, "READY", "4/4")

    def test_new_distro_is_an_update_even_when_release_matches(self):
        _, manifest = self.generate()
        upstream = "\n\n".join(
            block for block in manifest.split("\n\n") if "Directory: 25/jre/ubuntu/noble" not in block
        )
        summary, _ = self.generate(official_manifest=upstream)
        self.assert_readiness(summary, "READY", "4/4")

    def test_older_local_release_than_upstream_is_blocked(self):
        _, manifest = self.generate()
        summary, _ = self.generate(official_manifest=manifest.replace("25.0.2_10", "25.0.3_7"))
        self.assert_readiness(summary, "BLOCKED", "0/4")
        self.assertIn("older than upstream release 25.0.3_7", summary)

    def test_missing_upstream_comparison_does_not_claim_ready(self):
        summary, _ = self.generate(official_manifest=None)
        self.assert_readiness(summary, "UNKNOWN", "4/4")
        self.assertIn("Upstream comparison unavailable", summary)
        self.assertNotIn("Ready for upstream publish:", summary)

    def test_ready_release_can_publish_independently_of_blocked_and_unchanged_releases(self):
        import shutil
        shutil.copytree("25", "26")
        shutil.copytree("25", "27")
        for path in Path("26").rglob("Dockerfile"):
            path.write_text(path.read_text().replace("jdk-25.0.2+10", "jdk-26.0.2.1+1"))
        for path in Path("27").rglob("Dockerfile"):
            path.write_text(path.read_text().replace("jdk-25.0.2+10", "jdk-27.0.1+1"))
        Path("27/jre/ubuntu/noble/Dockerfile").unlink()
        _, upstream = self.generate(versions=[25, 26, 27])
        upstream = "\n\n".join(
            block.replace("25.0.2_10", "25.0.1_8")
            for block in upstream.split("\n\n")
            if "Directory: 27/" not in block
        )
        summary, _ = self.generate(official_manifest=upstream, versions=[25, 26, 27])
        rows = [
            [cell.strip() for cell in line.strip("|").split("|")]
            for line in summary.splitlines() if line.startswith("|")
        ]
        self.assertIn(["25", "25.0.2_10", "READY", "4/4"], [row[:4] for row in rows])
        self.assertIn(["26", "26.0.2.1_1", "UP TO DATE", "4/4"], [row[:4] for row in rows])
        self.assertIn(["27", "27.0.1_1", "BLOCKED", "3/4"], [row[:4] for row in rows])
        self.assertIn("Ready for upstream publish: Java 25.", summary)
        self.assertNotIn("Ready for upstream publish: Java 25, 26", summary)

    def test_exact_release_in_open_pr_is_not_suggested_again(self):
        _, manifest = self.generate()
        url = "https://github.com/docker-library/official-images/pull/123"
        summary, _ = self.generate(
            official_manifest=manifest.replace("25.0.2_10", "25.0.1_8"),
            open_prs=[PublicationPR(url, {"25.0.2_10"})],
        )
        self.assert_readiness(summary, "PR OPEN", "4/4")
        self.assertIn("#123", summary)
        self.assertIn(url, summary)
        self.assertNotIn("Ready for upstream publish: Java 25.", summary)
        self.assertIn("Publication already in progress: Java 25.", summary)
        self.assertNotIn("No updated Java versions are ready", summary)
        self.assertEqual(self.plan.ready_releases, {})
        self.assertNotIn("--create-pr", summary)

    def test_open_pr_for_different_patch_release_does_not_match(self):
        _, manifest = self.generate()
        summary, _ = self.generate(
            official_manifest=manifest.replace("25.0.2_10", "25.0.1_8"),
            open_prs=[PublicationPR("https://github.com/docker-library/official-images/pull/123", {"25.0.1_8"})],
        )
        self.assert_readiness(summary, "READY", "4/4")
        self.assertNotIn("#123", summary)

    def test_failed_pr_lookup_does_not_claim_no_pr_exists(self):
        _, manifest = self.generate()
        summary, _ = self.generate(
            official_manifest=manifest.replace("25.0.2_10", "25.0.1_8"), open_prs=None,
        )
        self.assert_readiness(summary, "UNKNOWN", "4/4")
        self.assertIn("Open upstream PRs could not be checked", summary)
        self.assertEqual(self.plan.ready_releases, {})

    def test_blocked_and_up_to_date_versions_are_not_offered_for_pr_creation(self):
        _, manifest = self.generate()
        self.generate(official_manifest=manifest)
        self.assertEqual(self.plan.ready_releases, {})
        self.write_dockerfile("jre", "ubuntu/noble", pending=("arm64",))
        self.generate(official_manifest=manifest.replace("25.0.2_10", "25.0.1_8"))
        self.assertEqual(self.plan.ready_releases, {})

    def test_unavailable_upstream_is_not_offered_for_pr_creation(self):
        self.generate(official_manifest=None)
        self.assertEqual(self.plan.ready_releases, {})

    def test_dry_run_does_not_overwrite_existing_manifest(self):
        Path("manifest").write_text("existing manifest")
        _, manifest = self.generate(dry_run=True)
        self.assertEqual(Path("manifest").read_text(), "existing manifest")
        self.assertIn("Directory: 25/jdk/", manifest)
        self.assertIn("Directory: 25/jre/", manifest)

    def test_dry_run_does_not_create_manifest_file(self):
        self.generate(dry_run=True)
        self.assertFalse(Path("manifest").exists())


class TestOpenPublicationPRs(unittest.TestCase):

    @patch("dockerhub_doc_config_update.github_pages")
    def test_cleanup_only_pr_matches_removed_directories_not_replaced_entries(self, pages):
        pages.side_effect = [
            [{"number": 456, "html_url": "https://github.com/docker-library/official-images/pull/456"}],
            [{
                "filename": "library/eclipse-temurin",
                "patch": (
                    "-Tags: 25.0.2_10-jdk-alpine-3.21\n"
                    "-Directory: 25/jdk/alpine/3.21\n"
                    "-Directory: 25/jre/alpine/3.21\n"
                    "-Directory: 25/jdk/ubuntu/noble\n"
                    "+Directory: 25/jdk/ubuntu/noble\n"
                ),
            }],
        ]
        prs = fetch_open_publication_prs()
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].releases, set())
        self.assertEqual(prs[0].removed_directories, {
            "25/jdk/alpine/3.21", "25/jre/alpine/3.21",
        })

    @patch.dict(os.environ, {}, clear=True)
    @patch("shutil.which", return_value="/usr/local/bin/gh")
    @patch("dockerhub_doc_config_update.subprocess.run")
    @patch("dockerhub_doc_config_update.urllib.request.urlopen")
    def test_logged_in_gh_authenticates_requests_without_token_environment(self, urlopen, run, _which):
        run.return_value = subprocess.CompletedProcess(
            ["gh", "auth", "token"], 0, stdout="test-gh-token\n", stderr="",
        )
        urlopen.return_value.__enter__.return_value.read.return_value = b"[]"
        self.assertEqual(list(github_pages("https://api.github.com/example")), [])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-gh-token")

    @patch("dockerhub_doc_config_update.github_pages")
    def test_match_added_tags_not_titles_removed_tags_or_context(self, pages):
        pages.side_effect = [
            [{"number": 123, "html_url": "https://github.com/docker-library/official-images/pull/123"}],
            [{
                "filename": "library/eclipse-temurin",
                "patch": (
                    " Tags: 17.0.21_9-jdk-noble\n"
                    "-Tags: 26.0.2.1_1-jdk-noble\n"
                    "+Tags: 25.0.5_8-jdk-noble, 25-jdk-noble\n"
                    "+Tags: 25.0.5_8-jre-noble, 25-jre-noble\n"
                ),
            }],
        ]
        prs = fetch_open_publication_prs()
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].releases, {"25.0.5_8"})

    @patch("dockerhub_doc_config_update.github_pages")
    def test_unrelated_file_does_not_match(self, pages):
        pages.side_effect = [
            [{"number": 123, "html_url": "https://github.com/docker-library/official-images/pull/123"}],
            [{"filename": "library/other", "patch": "+Tags: 25.0.5_8-jdk-noble"}],
        ]
        self.assertEqual(fetch_open_publication_prs(), [])

    @patch("dockerhub_doc_config_update.github_pages", side_effect=URLError("rate limited"))
    def test_lookup_failure_is_explicit(self, _pages):
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertIsNone(fetch_open_publication_prs())
        self.assertIn("cannot check open upstream publication PRs", output.getvalue())

    @patch("dockerhub_doc_config_update.github_pages")
    def test_omitted_manifest_diff_does_not_claim_no_matching_pr(self, pages):
        pages.side_effect = [
            [{"number": 123, "html_url": "https://github.com/docker-library/official-images/pull/123"}],
            [{"filename": "library/eclipse-temurin"}],
        ]
        output = io.StringIO()
        with redirect_stderr(output):
            self.assertIsNone(fetch_open_publication_prs())
        self.assertIn("omitted the manifest diff", output.getvalue())

    @patch("dockerhub_doc_config_update.get_github_token", return_value="test-api-token")
    @patch("dockerhub_doc_config_update.urllib.request.urlopen")
    def test_github_results_are_paginated(self, urlopen, _token):
        responses = []
        for data in [[{"number": n} for n in range(100)], [{"number": 100}]]:
            response = MagicMock()
            response.__enter__.return_value.read.return_value = json.dumps(data).encode("utf-8")
            responses.append(response)
        urlopen.side_effect = responses
        self.assertEqual(len(list(github_pages("https://api.github.com/example"))), 101)
        self.assertIn("page=2", urlopen.call_args.args[0].full_url)

    @patch("dockerhub_doc_config_update.get_github_token", return_value="test-api-token")
    @patch("dockerhub_doc_config_update.urllib.request.urlopen")
    def test_incomplete_search_results_cannot_claim_no_matching_pr(self, urlopen, _token):
        urlopen.return_value.__enter__.return_value.read.return_value = json.dumps({
            "incomplete_results": True, "items": [],
        }).encode("utf-8")
        with self.assertRaisesRegex(ValueError, "incomplete PR search"):
            list(github_pages("https://api.github.com/search/issues?q=example", "items"))


class TestGithubAuthentication(unittest.TestCase):
    @patch("dockerhub_doc_config_update.subprocess.run")
    @patch.dict(os.environ, {"GH_TOKEN": "explicit-gh-token", "GITHUB_TOKEN": "other-token"}, clear=True)
    def test_explicit_gh_token_takes_precedence_over_cli_and_github_token(self, run):
        self.assertEqual(get_github_token(), "explicit-gh-token")
        run.assert_not_called()

    @patch("dockerhub_doc_config_update.subprocess.run")
    @patch.dict(os.environ, {"GITHUB_TOKEN": "explicit-github-token"}, clear=True)
    def test_github_token_is_used_without_calling_cli(self, run):
        self.assertEqual(get_github_token(), "explicit-github-token")
        run.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("dockerhub_doc_config_update.shutil.which", return_value=None)
    @patch("dockerhub_doc_config_update.subprocess.run")
    def test_cli_remains_optional_when_no_authentication_is_available(self, run, _which):
        self.assertIsNone(get_github_token())
        run.assert_not_called()

    @patch.dict(os.environ, {}, clear=True)
    @patch("dockerhub_doc_config_update.shutil.which", return_value="/usr/local/bin/gh")
    @patch("dockerhub_doc_config_update.subprocess.run")
    def test_failed_cli_authentication_is_explicit(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["gh"], 1, stdout="", stderr="not logged in")
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertIsNone(get_github_token())
        self.assertIn("API requests are unauthenticated", stderr.getvalue())
        self.assertIn("gh auth login", stderr.getvalue())

    @patch.dict(os.environ, {}, clear=True)
    @patch("dockerhub_doc_config_update.shutil.which", return_value="/usr/local/bin/gh")
    @patch("dockerhub_doc_config_update.subprocess.run")
    def test_cli_token_is_captured_without_printing_it(self, run, _which):
        run.return_value = subprocess.CompletedProcess(["gh"], 0, stdout="test-cli-token\n", stderr="")
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(get_github_token(), "test-cli-token")
        self.assertEqual(stdout.getvalue(), "")
        self.assertEqual(stderr.getvalue(), "")
        run.assert_called_once_with(
            ["gh", "auth", "token", "--hostname", "github.com"], capture_output=True, text=True,
        )


class TestPublicationManifest(unittest.TestCase):
    header = "# upstream header\n\nGitRepo: https://github.com/adoptium/containers.git\nGitFetch: refs/heads/main"

    @staticmethod
    def entry(version, package="jdk", release=None, distro="ubuntu/noble"):
        release = release or f"{version}.0.1_1"
        return (
            f"Tags: {release}-{package}-noble, {version}-{package}-noble\n"
            "Architectures: amd64, arm64v8\n"
            f"GitCommit: commit-{release}\n"
            f"Directory: {version}/{package}/{distro}"
        )

    def test_replaces_only_selected_versions_including_jre_and_new_distros(self):
        preserved_8 = "# Java 8\n\n" + self.entry(8)
        preserved_25 = "# Java 25\n\n" + self.entry(25) + "\n"
        upstream = "\n\n".join([
            self.header, preserved_8, "# Java 17",
            self.entry(17), self.entry(17, "jre"),
            self.entry(17, distro="alpine/3.21"), preserved_25,
        ])
        selected = [
            self.entry(17, release="17.0.21_9"),
            self.entry(17, "jre", "17.0.21_9"),
            self.entry(17, release="17.0.21_9", distro="alpine/3.24"),
        ]
        generated = "\n\n".join(["# different generated header", self.entry(25, release="25.0.5_8"), *selected])
        result = merge_publication_manifest(upstream, generated, [17])
        self.assertEqual(result, "\n\n".join([
            self.header, preserved_8, "# Java 17", *selected, preserved_25,
        ]))
        self.assertNotIn("alpine/3.21", result)
        self.assertNotIn("different generated header", result)
        self.assertNotIn("25.0.5_8", result)

    def test_new_java_version_can_be_added_without_changing_existing_entries(self):
        upstream = self.header + "\n\n" + self.entry(17) + "\n"
        generated = self.entry(25) + "\n\n" + self.entry(25, "jre") + "\n"
        result = merge_publication_manifest(upstream, generated, [25])
        self.assertTrue(result.startswith(upstream))
        self.assertIn("Directory: 25/jdk/", result)
        self.assertIn("Directory: 25/jre/", result)

    def test_multiple_selected_versions_are_replaced(self):
        upstream = "\n\n".join([self.header, self.entry(8), self.entry(17), self.entry(25)]) + "\n"
        generated = "\n\n".join([self.entry(17, release="17.0.21_9"), self.entry(25, release="25.0.5_8")])
        result = merge_publication_manifest(upstream, generated, [17, 25])
        self.assertIn(self.entry(8), result)
        self.assertIn("17.0.21_9", result)
        self.assertIn("25.0.5_8", result)
        self.assertNotIn("17.0.1_1", result)
        self.assertNotIn("25.0.1_1", result)

    def test_cleanup_only_removes_exact_entries_and_preserves_everything_else(self):
        retired = [self.entry(17, distro="alpine/3.21"), self.entry(25, "jre", distro="alpine/3.21")]
        preserved = "\n\n".join([self.header, self.entry(17), self.entry(25)]) + "\n"
        upstream = preserved.rstrip("\n") + "\n\n" + "\n\n".join(retired) + "\n"
        generated = self.entry(25, release="25.0.5_8")
        result = merge_publication_manifest(
            upstream, generated, [], {"17/jdk/alpine/3.21", "25/jre/alpine/3.21"},
        )
        self.assertEqual(result, preserved)
        self.assertNotIn("25.0.5_8", result)

    def test_ready_release_and_cleanup_of_unselected_version_can_share_a_pr(self):
        upstream = "\n\n".join([
            self.header, self.entry(17), self.entry(25),
            self.entry(25, distro="alpine/3.21"),
        ]) + "\n"
        generated = self.entry(17, release="17.0.21_9")
        result = merge_publication_manifest(upstream, generated, [17], {"25/jdk/alpine/3.21"})
        self.assertIn("17.0.21_9", result)
        self.assertIn(self.entry(25), result)
        self.assertNotIn("alpine/3.21", result)

    def test_cleanup_cannot_remove_a_generated_image(self):
        manifest = self.entry(25)
        with self.assertRaisesRegex(ValueError, "still have generated manifest entries"):
            merge_publication_manifest(manifest, manifest, [], {"25/jdk/ubuntu/noble"})

    def test_cleanup_target_must_exist_upstream(self):
        manifest = self.entry(25)
        with self.assertRaisesRegex(ValueError, "absent from upstream"):
            merge_publication_manifest(manifest, manifest, [], {"25/jdk/alpine/3.21"})

    def test_missing_generated_version_is_an_error(self):
        with self.assertRaisesRegex(ValueError, "no generated manifest entries"):
            merge_publication_manifest(self.entry(17), self.entry(25), [17])

    def test_shared_tag_conflict_does_not_modify_an_unselected_version(self):
        upstream = self.entry(17) + "\nSharedTags: latest\n\n" + self.entry(25)
        generated = self.entry(25, release="25.0.5_8") + "\nSharedTags: latest"
        with self.assertRaisesRegex(ValueError, "preserved upstream tags: latest"):
            merge_publication_manifest(upstream, generated, [25])


class TestPublicationSource(unittest.TestCase):
    def setUp(self):
        temporary = self.enterContext(tempfile.TemporaryDirectory())
        original = os.getcwd()
        os.chdir(temporary)
        self.addCleanup(os.chdir, original)
        self.paths = ["config/temurin.yml"]
        for package in ("jdk", "jre"):
            self.paths.extend([
                f"17/{package}/ubuntu/noble/Dockerfile",
                f"17/{package}/ubuntu/noble/entrypoint.sh",
            ])
        self.tree = []
        for name in self.paths:
            path = Path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = (name + "\n").encode()
            path.write_bytes(data)
            blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
            self.tree.append({"type": "blob", "path": name, "sha": blob})
        self.plan = PublicationPlan("upstream", "\n\n".join([
            TestPublicationManifest.entry(17),
            TestPublicationManifest.entry(17, "jre"),
            TestPublicationManifest.entry(25),
        ]), {17: "17.0.21_9"})
        self.requests = self.enterContext(patch(
            "dockerhub_doc_config_update.github_request",
            side_effect=[{"sha": "published-main"}, {"truncated": False, "tree": self.tree}],
        ))

    def test_tooling_branch_and_dirty_documentation_can_publish_merged_sources(self):
        Path("README.md").write_text("uncommitted documentation")
        Path("dockerhub_doc_config_update.py").write_text("uncommitted tooling")
        commit, manifest = prepare_publication_source(self.plan)
        self.assertEqual(commit, "published-main")
        selected = manifest.split("\n\n")[:2]
        self.assertTrue(all("GitCommit: published-main" in block for block in selected))
        self.assertIn(TestPublicationManifest.entry(25), manifest)
        self.assertNotIn("published-main", self.plan.manifest)

    def test_cleanup_only_requires_merged_config_but_not_unselected_images(self):
        self.plan.ready_releases = {}
        self.plan.cleanup_directories = {"25/jdk/alpine/3.21"}
        Path("17/jdk/ubuntu/noble/Dockerfile").write_text("unmerged image change")
        commit, manifest = prepare_publication_source(self.plan)
        self.assertEqual(commit, "published-main")
        self.assertEqual(manifest, self.plan.manifest)

    def test_cleanup_only_still_rejects_unmerged_configuration(self):
        self.plan.ready_releases = {}
        self.plan.cleanup_directories = {"25/jdk/alpine/3.21"}
        Path("config/temurin.yml").write_text("unmerged config change")
        with self.assertRaisesRegex(ValueError, "differs from published upstream main"):
            prepare_publication_source(self.plan)

    def test_dirty_or_unmerged_images_and_configuration_are_rejected(self):
        for name in self.paths:
            with self.subTest(path=name):
                self.requests.side_effect = [{"sha": "published-main"}, {"tree": self.tree}]
                original = Path(name).read_bytes()
                Path(name).write_text("unmerged source changes")
                with self.assertRaisesRegex(ValueError, "differs from published upstream main"):
                    prepare_publication_source(self.plan)
                Path(name).write_bytes(original)

    def test_deleted_published_entrypoint_is_rejected(self):
        Path("17/jre/ubuntu/noble/entrypoint.sh").unlink()
        with self.assertRaisesRegex(ValueError, "missing or not merged upstream"):
            prepare_publication_source(self.plan)

    def test_new_unpublished_image_cannot_be_published(self):
        self.tree[:] = [entry for entry in self.tree if entry["path"] != "17/jdk/ubuntu/noble/Dockerfile"]
        with self.assertRaisesRegex(ValueError, "missing or not merged upstream"):
            prepare_publication_source(self.plan)

    def test_local_unpublished_entrypoint_cannot_be_added(self):
        self.tree[:] = [entry for entry in self.tree if entry["path"] != "17/jre/ubuntu/noble/entrypoint.sh"]
        with self.assertRaisesRegex(ValueError, "missing or not merged upstream"):
            prepare_publication_source(self.plan)

    def test_truncated_upstream_tree_is_not_accepted(self):
        self.requests.side_effect = [{"sha": "published-main"}, {"truncated": True, "tree": self.tree}]
        with self.assertRaisesRegex(ValueError, "complete published containers source tree"):
            prepare_publication_source(self.plan)

    def test_missing_published_commit_is_an_explicit_error(self):
        self.requests.side_effect = [{}]
        with self.assertRaisesRegex(ValueError, "published containers main commit"):
            prepare_publication_source(self.plan)

    @patch("dockerhub_doc_config_update.run_publication_command", return_value="one-hash")
    def test_missing_source_hashes_are_not_accepted(self, _command):
        with self.assertRaisesRegex(ValueError, "hash for every publication source file"):
            prepare_publication_source(self.plan)


class TestCreatePublicationPR(unittest.TestCase):
    def setUp(self):
        self.upstream = "\n\n".join([
            TestPublicationManifest.header,
            TestPublicationManifest.entry(8),
            TestPublicationManifest.entry(17),
            TestPublicationManifest.entry(17, "jre"),
            TestPublicationManifest.entry(25),
        ]) + "\n"
        self.generated = "\n\n".join([
            TestPublicationManifest.entry(17, release="17.0.21_9"),
            TestPublicationManifest.entry(17, "jre", "17.0.21_9"),
            TestPublicationManifest.entry(25, release="25.0.5_8"),
        ]) + "\n"
        self.plan = PublicationPlan(self.upstream, self.generated, {17: "17.0.21_9"})
        self.url = "https://github.com/docker-library/official-images/pull/123"
        self.commands = []
        self.cloned_manifest = self.upstream
        self.push_error = None
        self.runner = self.enterContext(patch(
            "dockerhub_doc_config_update.run_publication_command", side_effect=self.command,
        ))
        self.prepare = self.enterContext(patch(
            "dockerhub_doc_config_update.prepare_publication_source",
            side_effect=lambda plan: ("published", plan.manifest),
        ))
        self.open_prs = self.enterContext(patch(
            "dockerhub_doc_config_update.fetch_open_publication_prs", return_value=[],
        ))

    def command(self, *args, cwd=None):
        self.commands.append((args, cwd))
        if args[:3] == ("gh", "api", "user"):
            return "publisher"
        if args[:3] == ("gh", "repo", "clone"):
            self.checkout = Path(args[4])
            path = self.checkout / "library" / "eclipse-temurin"
            path.parent.mkdir(parents=True)
            path.write_text(self.cloned_manifest)
        if args[:2] == ("git", "commit"):
            self.proposed = (cwd / "library" / "eclipse-temurin").read_text()
        if "push" in args and self.push_error:
            raise self.push_error
        if args[:3] == ("gh", "pr", "create"):
            return self.url
        return ""

    def test_creates_all_ready_releases_without_publishing_unready_versions(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertEqual(create_publication_pr(self.plan), self.url)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn(self.url, stderr.getvalue())
        self.assertIn("17.0.21_9", self.proposed)
        self.assertIn("Directory: 17/jre/", self.proposed)
        self.assertIn(TestPublicationManifest.entry(8), self.proposed)
        self.assertIn(TestPublicationManifest.entry(25), self.proposed)
        self.assertNotIn("25.0.5_8", self.proposed)
        self.assertFalse(self.checkout.exists())
        self.open_prs.assert_called_once()
        args, cwd = next(call for call in self.commands if call[0][:3] == ("gh", "pr", "create"))
        self.assertIn("publisher:eclipse-temurin-17.0.21_9", args)
        self.assertIn("master", args)
        self.assertEqual(cwd, self.checkout)
        commit_args, _ = next(call for call in self.commands if call[0][:2] == ("git", "commit"))
        self.assertIn("Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>", commit_args)
        self.assertTrue(all(cwd == self.checkout for args, cwd in self.commands if args[:2] == ("git", "checkout")))
        self.assertFalse(any(args[:3] == ("gh", "auth", "setup-git") for args, _ in self.commands))

    def test_all_ready_versions_are_automatically_included(self):
        self.plan.ready_releases[25] = "25.0.5_8"
        with redirect_stderr(io.StringIO()):
            create_publication_pr(self.plan)
        self.assertIn("17.0.21_9", self.proposed)
        self.assertIn("25.0.5_8", self.proposed)

    def add_cleanup(self):
        directory = "25/jdk/alpine/3.21"
        self.plan.cleanup_directories = {directory}
        self.upstream += "\n" + TestPublicationManifest.entry(25, distro="alpine/3.21") + "\n"
        self.plan.upstream_manifest = self.upstream
        self.cloned_manifest = self.upstream
        return directory

    def test_creates_cleanup_only_pr_without_ready_releases(self):
        directory = self.add_cleanup()
        self.plan.ready_releases = {}
        with redirect_stderr(io.StringIO()):
            self.assertEqual(create_publication_pr(self.plan), self.url)
        self.assertEqual(self.proposed, "\n\n".join([
            TestPublicationManifest.header, TestPublicationManifest.entry(8),
            TestPublicationManifest.entry(17), TestPublicationManifest.entry(17, "jre"),
            TestPublicationManifest.entry(25),
        ]) + "\n")
        args, _ = next(call for call in self.commands if call[0][:3] == ("gh", "pr", "create"))
        self.assertIn("eclipse-temurin: remove deprecated images", args)
        self.assertIn(directory, args[args.index("--body") + 1])
        self.assertTrue(args[args.index("--head") + 1].startswith("publisher:eclipse-temurin-cleanup-"))
        self.prepare.assert_called_once_with(self.plan)

    def test_release_updates_can_include_cleanup_for_other_versions(self):
        self.add_cleanup()
        with redirect_stderr(io.StringIO()):
            create_publication_pr(self.plan)
        self.assertIn("17.0.21_9", self.proposed)
        self.assertIn(TestPublicationManifest.entry(25), self.proposed)
        self.assertNotIn("alpine/3.21", self.proposed)
        args, _ = next(call for call in self.commands if call[0][:3] == ("gh", "pr", "create"))
        self.assertIn("remove deprecated images", args[args.index("--title") + 1])

    def test_cleanup_dry_run_shows_only_deletions_without_mutation(self):
        self.add_cleanup()
        self.plan.ready_releases = {}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            create_publication_pr(self.plan, dry_run=True)
        self.assertIn("eclipse-temurin: remove deprecated images", stderr.getvalue())
        self.assertIn("-Directory: 25/jdk/alpine/3.21", stderr.getvalue())
        additions = [
            line for line in stderr.getvalue().splitlines()
            if line.startswith("+") and not line.startswith("+++")
        ]
        self.assertEqual(additions, [])
        self.runner.assert_not_called()
        self.open_prs.assert_not_called()

    def test_cleanup_opened_after_planning_aborts_before_mutation(self):
        directory = self.add_cleanup()
        self.plan.ready_releases = {}
        self.open_prs.return_value = [PublicationPR(self.url, set(), {directory})]
        with self.assertRaisesRegex(ValueError, "Cleanup is already in an upstream PR"):
            create_publication_pr(self.plan)
        self.assert_no_github_mutation()

    def test_explicit_repository_fork_does_not_use_the_remote_flag(self):
        with redirect_stderr(io.StringIO()):
            create_publication_pr(self.plan)
        args, _ = next(call for call in self.commands if call[0][:3] == ("gh", "repo", "fork"))
        self.assertIn("docker-library/official-images", args)
        self.assertIn("--clone=false", args)
        self.assertFalse(any(arg.startswith("--remote") for arg in args))

    def test_publication_git_flow_pushes_only_ready_entries_to_an_isolated_fork(self):
        with tempfile.TemporaryDirectory() as temporary:
            upstream = Path(temporary) / "upstream"
            fork = Path(temporary) / "fork.git"
            run_publication_command("git", "init", "-b", "master", str(upstream))
            run_publication_command("git", "config", "user.name", "Test Publisher", cwd=upstream)
            run_publication_command("git", "config", "user.email", "publisher@example.com", cwd=upstream)
            run_publication_command("git", "config", "commit.gpgsign", "false", cwd=upstream)
            manifest_file = upstream / "library" / "eclipse-temurin"
            manifest_file.parent.mkdir()
            manifest_file.write_text(self.upstream)
            run_publication_command("git", "add", ".", cwd=upstream)
            run_publication_command("git", "commit", "-m", "Initial manifest", cwd=upstream)
            run_publication_command("git", "clone", "--bare", str(upstream), str(fork))

            def integration_command(*args, cwd=None):
                if args[:3] == ("gh", "repo", "clone"):
                    checkout = Path(args[4])
                    run_publication_command("git", "clone", str(upstream), str(checkout))
                    run_publication_command("git", "config", "user.name", "Test Publisher", cwd=checkout)
                    run_publication_command("git", "config", "user.email", "publisher@example.com", cwd=checkout)
                    run_publication_command("git", "config", "commit.gpgsign", "false", cwd=checkout)
                    return ""
                if args[:4] == ("git", "remote", "add", "publication"):
                    return run_publication_command(*args[:4], str(fork), cwd=cwd)
                if args[0] == "gh":
                    return self.command(*args, cwd=cwd)
                return run_publication_command(*args, cwd=cwd)

            self.runner.side_effect = integration_command
            with redirect_stderr(io.StringIO()):
                self.assertEqual(create_publication_pr(self.plan), self.url)
            refs = subprocess.run(
                ["git", f"--git-dir={fork}", "for-each-ref", "--format=%(refname)"],
                capture_output=True, text=True,
            )
            self.assertEqual(refs.returncode, 0, refs.stderr)
            self.assertIn("refs/heads/eclipse-temurin-17.0.21_9", refs.stdout, self.runner.call_args_list)
            pushed = run_publication_command(
                "git", f"--git-dir={fork}", "show", "eclipse-temurin-17.0.21_9:library/eclipse-temurin",
            )
            self.assertIn("17.0.21_9", pushed)
            self.assertIn("Directory: 17/jre/", pushed)
            self.assertIn(TestPublicationManifest.entry(8), pushed)
            self.assertIn(TestPublicationManifest.entry(25), pushed)
            self.assertNotIn("25.0.5_8", pushed)
            self.assertEqual(manifest_file.read_text(), self.upstream)

    def test_no_ready_versions_reports_no_op_without_publication_commands(self):
        self.plan.ready_releases = {}
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            self.assertIsNone(create_publication_pr(self.plan))
        self.assertIn("No unpublished READY versions", stderr.getvalue())
        self.runner.assert_not_called()

    def test_unknown_upstream_never_runs_publication_commands(self):
        self.plan.upstream_manifest = None
        with self.assertRaisesRegex(ValueError, "comparison unavailable"):
            create_publication_pr(self.plan)
        self.runner.assert_not_called()

    def test_failed_initial_pr_lookup_is_not_a_successful_no_op(self):
        self.plan.ready_releases = {}
        self.plan.open_prs_available = False
        with self.assertRaisesRegex(ValueError, "Open upstream PRs could not be checked"):
            create_publication_pr(self.plan)
        self.runner.assert_not_called()

    def test_dry_run_previews_diff_without_commands_or_files(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            self.assertIsNone(create_publication_pr(self.plan, dry_run=True))
        self.runner.assert_not_called()
        self.open_prs.assert_not_called()
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("Dry run: would open upstream PR", stderr.getvalue())
        self.assertIn("--- a/library/eclipse-temurin", stderr.getvalue())
        self.assertIn("+Tags: 17.0.21_9", stderr.getvalue())
        self.assertNotIn("+Tags: 25.0.5_8", stderr.getvalue())
        self.assertIn("no files, branches, forks, or PRs were changed", stderr.getvalue())

    def test_dirty_source_checkout_cannot_publish(self):
        self.prepare.side_effect = ValueError("Publication source differs from published upstream main: Dockerfile")
        with self.assertRaisesRegex(ValueError, "differs from published upstream main"):
            create_publication_pr(self.plan)
        self.runner.assert_not_called()

    def test_unmerged_source_configuration_cannot_publish(self):
        self.prepare.side_effect = ValueError("Publication source differs from published upstream main: config/temurin.yml")
        with self.assertRaisesRegex(ValueError, "differs from published upstream main"):
            create_publication_pr(self.plan)
        self.assertFalse(any(args[:3] == ("gh", "repo", "clone") for args, _ in self.commands))

    def test_dirty_tooling_changes_do_not_block_already_published_images(self):
        self.enterContext(patch("dockerhub_doc_config_update.get_git_commit", return_value="tooling-feature-commit"))
        with redirect_stderr(io.StringIO()):
            self.assertEqual(create_publication_pr(self.plan), self.url)

    def test_changed_upstream_aborts_before_any_github_mutation(self):
        self.cloned_manifest += "\n# another update"
        with self.assertRaisesRegex(ValueError, "upstream manifest changed"):
            create_publication_pr(self.plan)
        self.assert_no_github_mutation()
        self.assertFalse(self.checkout.exists())

    def test_pr_opened_after_readiness_check_is_not_duplicated(self):
        self.open_prs.return_value = [PublicationPR(self.url, {"17.0.21+9"})]
        with self.assertRaisesRegex(ValueError, "already in an upstream PR"):
            create_publication_pr(self.plan)
        self.assert_no_github_mutation()

    def test_failed_fresh_pr_lookup_aborts_without_mutation(self):
        self.open_prs.return_value = None
        with self.assertRaisesRegex(ValueError, "could not be checked"):
            create_publication_pr(self.plan)
        self.assert_no_github_mutation()

    def test_push_failure_never_attempts_to_open_pr(self):
        self.push_error = subprocess.CalledProcessError(1, ["git", "push"], stderr="push rejected")
        with self.assertRaises(subprocess.CalledProcessError):
            create_publication_pr(self.plan)
        self.assertFalse(any(args[:3] == ("gh", "pr", "create") for args, _ in self.commands))
        self.assertFalse(self.checkout.exists())

    def test_empty_pr_url_is_not_success(self):
        self.url = ""
        with self.assertRaisesRegex(ValueError, "did not return a publication PR URL"):
            create_publication_pr(self.plan)

    def assert_no_github_mutation(self):
        self.assertFalse(any(args[:3] in (("gh", "repo", "fork"), ("gh", "pr", "create")) for args, _ in self.commands))
        self.assertFalse(any("push" in args for args, _ in self.commands))

    @patch("dockerhub_doc_config_update.subprocess.run")
    def test_command_output_is_captured_and_failures_propagate(self, run):
        run.return_value.stdout = "result\n"
        self.assertEqual(run_publication_command("gh", "api", "user"), "result")
        run.assert_called_once_with(
            ("gh", "api", "user"), cwd=None, capture_output=True, text=True, check=True,
        )
        run.side_effect = subprocess.CalledProcessError(1, ["gh"], stderr="authentication required")
        with self.assertRaises(subprocess.CalledProcessError):
            run_publication_command("gh", "api", "user")


class TestManifestCLI(unittest.TestCase):

    def setUp(self):
        self.config = self.enterContext(patch("dockerhub_doc_config_update.load_config", return_value={}))
        self.enterContext(patch("dockerhub_doc_config_update.print_eol_warnings"))
        self.generate = self.enterContext(patch(
            "dockerhub_doc_config_update.generate_manifest",
            return_value=PublicationPlan("upstream", "generated", {17: "17.0.21_9"}),
        ))
        self.create = self.enterContext(patch("dockerhub_doc_config_update.create_publication_pr"))

    def test_default_run_does_not_create_a_pr(self):
        with patch.object(sys, "argv", ["script"]):
            main()
        self.generate.assert_called_once_with({}, "eclipse-temurin", dry_run=False)
        self.create.assert_not_called()

    def test_create_pr_needs_no_version_selection(self):
        with patch.object(sys, "argv", ["script", "manifest", "--create-pr"]):
            main()
        self.generate.assert_called_once_with({}, "manifest", dry_run=False)
        self.create.assert_called_once_with(self.generate.return_value, dry_run=False)

    def test_version_arguments_are_not_accepted_by_create_pr(self):
        with patch.object(sys, "argv", ["script", "--create-pr=17"]), redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 2)
        self.generate.assert_not_called()
        self.create.assert_not_called()

    def test_dry_run_is_a_standalone_preview_option(self):
        with patch.object(sys, "argv", ["script", "--dry-run"]):
            main()
        self.generate.assert_called_once_with({}, "eclipse-temurin", dry_run=True)
        self.create.assert_called_once_with(self.generate.return_value, dry_run=True)

    def test_dry_run_overrides_create_pr_mutations(self):
        with patch.object(sys, "argv", ["script", "--create-pr", "--dry-run"]):
            main()
        self.generate.assert_called_once_with({}, "eclipse-temurin", dry_run=True)
        self.create.assert_called_once_with(self.generate.return_value, dry_run=True)

    def test_publication_command_failure_has_nonzero_exit_and_details(self):
        self.create.side_effect = subprocess.CalledProcessError(1, ["gh"], stderr="authentication required")
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["script", "--create-pr"]), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn("authentication required", stderr.getvalue())

    def test_unavailable_pr_lookup_has_nonzero_exit_and_details(self):
        self.create.side_effect = ValueError("Open upstream PRs could not be checked")
        stderr = io.StringIO()
        with patch.object(sys, "argv", ["script", "--create-pr"]), redirect_stderr(stderr):
            with self.assertRaises(SystemExit) as error:
                main()
        self.assertEqual(error.exception.code, 1)
        self.assertIn("Open upstream PRs could not be checked", stderr.getvalue())

    def test_stdout_manifest_needs_only_yaml_and_report_goes_to_stderr(self):
        code = textwrap.dedent("""\
            import builtins
            import sys
            from unittest.mock import patch

            original_import = builtins.__import__

            def minimal_import(name, *args, **kwargs):
                if name.split(".")[0] in {"requests", "requests_cache", "jinja2", "generate_dockerfiles"}:
                    raise ModuleNotFoundError(f"{name} is not available in the matrix-generation job")
                return original_import(name, *args, **kwargs)

            with patch("builtins.__import__", side_effect=minimal_import):
                import dockerhub_doc_config_update as manifest
                with (
                    patch.object(manifest, "get_supported_versions", return_value=[25]),
                    patch.object(manifest, "get_latest_lts", return_value=25),
                    patch.object(manifest, "fetch_official_manifest", return_value=""),
                    patch.object(manifest, "print_eol_warnings"),
                    patch.object(sys, "argv", ["dockerhub_doc_config_update.py", "/dev/stdout"]),
                ):
                    manifest.main()
        """)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("# Eclipse Temurin OpenJDK images"))
        self.assertIn("Directory: 25/jdk/", result.stdout)
        self.assertIn("Directory: 25/jre/", result.stdout)
        self.assertNotIn("Upstream publish readiness", result.stdout)
        self.assertNotIn("|", result.stdout)
        self.assertIn("Upstream publish readiness", result.stderr)
        self.assertIn("| Java", result.stderr)


if __name__ == "__main__":
    unittest.main()
