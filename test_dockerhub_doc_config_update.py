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
from unittest.mock import patch, mock_open
from pathlib import Path
import dockerhub_doc_config_update


class TestManifestGeneration(unittest.TestCase):
    @patch("dockerhub_doc_config_update.requests.get")
    def test_fetch_latest_manifest(self, mock_get):
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "test manifest content"

        dockerhub_doc_config_update.fetch_latest_manifest()

        with open("official-eclipse-temurin", "r") as f:
            self.assertEqual(f.read(), "test manifest content")

    @patch("subprocess.check_output", return_value=b"mock-git-commit-hash")
    def test_get_git_commit(self, mock_subprocess):
        commit = dockerhub_doc_config_update.get_git_commit()
        self.assertEqual(commit, "mock-git-commit-hash")

    def test_parse_dockerfile(self):
        dockerfile_content = """\
        ENV JAVA_VERSION=jdk-11.0.16+8
        case "${ARCH}" in
            x86_64)
                echo "amd64 selected"
            ;;
            arm64)
                echo "arm64v8 selected"
            ;;
        esac
        """

        with patch("builtins.open", mock_open(read_data=dockerfile_content)):
            java_version, architectures = dockerhub_doc_config_update.parse_dockerfile(
                "path/to/Dockerfile", "linux"
            )
            self.assertEqual(java_version, "jdk-11.0.16+8")
            self.assertEqual(architectures, ["amd64", "arm64v8"])

    def test_generate_tags(self):
        tags = dockerhub_doc_config_update.generate_tags(
            "11.0.16_8", "11", "jdk", "alpine-3.21"
        )
        expected_tags = [
            "11.0.16_8-jdk-alpine-3.21",
            "11-jdk-alpine-3.21",
            "11-alpine-3.21",
            "11.0.16_8-jdk-alpine",
            "11-jdk-alpine",
            "11-alpine",
        ]
        self.assertEqual(tags, expected_tags)

    def test_generate_shared_tags(self):
        shared_tags = dockerhub_doc_config_update.generate_shared_tags(
            "11.0.16_8", "11", "jdk", "noble", "linux"
        )
        expected_shared_tags = ["11.0.16_8-jdk", "11-jdk", "11"]
        self.assertEqual(shared_tags, expected_shared_tags)


@patch("manifest_generator.get_git_commit", return_value="mock-git-commit-hash")
@patch("pathlib.Path.read_text", return_value="Tags: 11-jdk-alpine-3.21")
def test_generate_official_image_info(self, mock_read_text, mock_git_commit):
    # Mock an open file
    output_file = mock_open()
    with patch("builtins.open", output_file):
        with open("dummy_output", "w") as file:  # Simulate a file object
            dockerhub_doc_config_update.generate_official_image_info(
                file, "11", "jdk", "linux", "11/jdk/alpine/3.21"
            )

    # Extract the written data from the mock file handle
    handle = output_file()
    written_content = "".join(call[0][0] for call in handle.write.call_args_list)

    # Verify parts of the generated content
    self.assertIn(
        "Tags: 11.0.16_8-jdk-alpine-3.21, 11-jdk-alpine-3.21, 11-alpine-3.21",
        written_content,
    )
    self.assertIn("Architectures: amd64, arm64v8", written_content)
    self.assertIn("GitCommit: mock-git-commit-hash", written_content)
    self.assertIn("Directory: 11/jdk/alpine/3.21", written_content)


if __name__ == "__main__":
    unittest.main()
