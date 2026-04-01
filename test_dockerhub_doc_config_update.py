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
import os
import tempfile
import textwrap
import unittest
from unittest.mock import patch

from adoptium_api import get_latest_lts, get_supported_versions
from dockerhub_doc_config_update import (
    find_manifest_block,
    format_ojdk_version,
    get_block_gitcommit,
    get_distro_name,
    get_dockerfile_arches,
    get_java_version,
    generate_manifest,
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


if __name__ == "__main__":
    unittest.main()
