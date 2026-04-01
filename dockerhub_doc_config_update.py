#!/usr/bin/env python3
#
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
# 1. Run generate_dockerfiles.py to update all the dockerfiles in the current repo.
# 2. Submit PR to push the newly generated dockerfiles to the current repo.
# 3. After above PR is merged, git pull the latest changes.
# 4. Run this command

import os
import re
import subprocess
import sys
import urllib.request

import yaml

from adoptium_api import get_latest_lts, get_supported_versions

OFFICIAL_MANIFEST_URL = (
    "https://raw.githubusercontent.com/docker-library/official-images/"
    "master/library/eclipse-temurin"
)


def load_config():
    with open("config/temurin.yml", "r") as f:
        return yaml.safe_load(f)


def get_git_commit():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def fetch_official_manifest():
    """Fetch the current official manifest for diff comparison."""
    try:
        req = urllib.request.Request(OFFICIAL_MANIFEST_URL)
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8")
    except Exception:
        return ""


def get_java_version(dockerfile_path):
    """Extract JAVA_VERSION from a Dockerfile."""
    with open(dockerfile_path, "r") as f:
        for line in f:
            if "JAVA_VERSION=" in line:
                return line.split("=")[1].strip()
    return None


def format_ojdk_version(full_version):
    """Convert JAVA_VERSION to Docker tag-compatible version string.

    Examples:
        jdk8u482-b08 -> 8u482-b08
        jdk-25.0.1+9 -> 25.0.1_9
    """
    version = re.sub(r"^jdk-?", "", full_version)
    version = version.replace("+", "_")
    return version


def get_distro_name(os_family, directory):
    """Derive the distro tag name from the config directory."""
    name = directory.split("/")[-1]
    if os_family == "alpine-linux":
        return f"alpine-{name}"
    return name


# Map Dockerfile arch names to Docker Hub official image architecture names
DOCKERFILE_ARCH_MAP = {
    "amd64": "amd64",
    "x86_64": "amd64",
    "arm64": "arm64v8",
    "aarch64": "arm64v8",
    "armhf": "arm32v7",
    "ppc64el": "ppc64le",
    "ppc64le": "ppc64le",
    "s390x": "s390x",
    "riscv64": "riscv64",
}


def get_dockerfile_arches(dockerfile_path):
    """Parse architectures from the case statement in a Dockerfile."""
    arches = []
    with open(dockerfile_path, "r") as f:
        for line in f:
            match = re.match(r'\s+(\w+)\)\s*\\?\s*$', line)
            if match:
                arch = match.group(1)
                if arch in DOCKERFILE_ARCH_MAP:
                    arches.append(DOCKERFILE_ARCH_MAP[arch])
    return sorted(set(arches))


def find_manifest_block(official_manifest, tags_str):
    """Find the manifest block matching the given tags in the official manifest."""
    if not official_manifest:
        return None
    for block in official_manifest.split("\n\n"):
        if tags_str in block:
            return block
    return None


def get_block_gitcommit(block):
    """Extract GitCommit from a manifest block."""
    if not block:
        return None
    for line in block.split("\n"):
        if line.startswith("GitCommit:"):
            return line.split(":")[1].strip()
    return None


def has_changed(gitcommit, official_gitcommit, dfdir):
    """Check if Dockerfile or entrypoint.sh changed between two git commits."""
    if not official_gitcommit:
        return True
    try:
        result = subprocess.run(
            [
                "git", "diff",
                f"{gitcommit}:{dfdir}/Dockerfile",
                f"{official_gitcommit}:{dfdir}/Dockerfile",
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return True
        diff_lines = len(result.stdout.splitlines())

        entrypoint = os.path.join(dfdir, "entrypoint.sh")
        if os.path.exists(entrypoint):
            result = subprocess.run(
                [
                    "git", "diff",
                    f"{gitcommit}:{dfdir}/entrypoint.sh",
                    f"{official_gitcommit}:{dfdir}/entrypoint.sh",
                ],
                capture_output=True, text=True,
            )
            if result.returncode != 0:
                return True
            diff_lines += len(result.stdout.splitlines())

        return diff_lines > 0
    except Exception:
        return True


def generate_manifest(config, output_file):
    gitcommit = get_git_commit()
    official_manifest = fetch_official_manifest()

    versions = get_supported_versions()
    latest_version = get_latest_lts()
    # Default images are the first entry in each OS family
    default_linux_image = get_distro_name("linux", config["configurations"]["linux"][0]["directory"])
    default_alpine_image = get_distro_name("alpine-linux", config["configurations"]["alpine-linux"][0]["directory"])

    lines = []

    # Header
    lines.append("# Eclipse Temurin OpenJDK images provided by the Eclipse Foundation.")
    lines.append("")
    lines.append("Maintainers: George Adams <george.adams@microsoft.com> (@gdams),")
    lines.append("             Stewart Addison <sxa@redhat.com> (@sxa)")
    lines.append("GitRepo: https://github.com/adoptium/containers.git")
    lines.append("GitFetch: refs/heads/main")
    lines.append("Builder: buildkit")

    # OS family iteration order matches the original script
    os_family_order = ["alpine-linux", "linux", "windows"]

    for ver in versions:
        lines.append("")
        lines.append(
            f"#------------------------------v{ver} images---------------------------------"
        )

        for pkg in ["jdk", "jre"]:
            for os_family in os_family_order:
                if os_family not in config["configurations"]:
                    continue

                for cfg in config["configurations"][os_family]:
                    directory = cfg["directory"]
                    architectures = cfg["architectures"]
                    deprecated = cfg.get("deprecated", None)
                    cfg_versions = cfg.get("versions", versions)

                    if ver not in cfg_versions:
                        continue
                    if deprecated and ver >= deprecated:
                        continue

                    dfdir = os.path.join(str(ver), pkg, directory)
                    dockerfile = os.path.join(dfdir, "Dockerfile")

                    if not os.path.exists(dockerfile):
                        continue

                    full_version = get_java_version(dockerfile)
                    if not full_version:
                        continue

                    ojdk_version = format_ojdk_version(full_version)
                    distro = get_distro_name(os_family, directory)
                    is_windows = os_family == "windows"

                    # Build tags
                    full_ver_tag = f"{ojdk_version}-{pkg}-{distro}"
                    ver_tag = f"{ver}-{pkg}-{distro}"
                    all_tags = f"{full_ver_tag}, {ver_tag}"

                    extra_shared_tags = ""
                    if pkg == "jdk":
                        jdk_tag = f"{ver}-{distro}"
                        all_tags = f"{all_tags}, {jdk_tag}"
                        if ver == latest_version and os_family != "alpine-linux":
                            extra_shared_tags = ", latest"

                    # Shared tags = tags without distro suffix
                    shared_tags = all_tags.replace(f"-{distro}", "")

                    if is_windows:
                        parts = distro.split("-", 1)
                        windows_version = parts[0]
                        windows_version_number = parts[1] if len(parts) > 1 else ""
                        windows_shared_tags = all_tags.replace(distro, windows_version)

                        if distro.startswith("nanoserver"):
                            constraints = (
                                f"{distro}, windowsservercore-{windows_version_number}"
                            )
                            all_shared_tags = windows_shared_tags
                        else:
                            constraints = distro
                            all_shared_tags = (
                                f"{windows_shared_tags}, "
                                f"{shared_tags}{extra_shared_tags}"
                            )
                    else:
                        all_shared_tags = f"{shared_tags}{extra_shared_tags}"

                    # Compare with official manifest (before appending alpine aliases)
                    manifest_block = find_manifest_block(official_manifest, all_tags)
                    official_gitcommit = get_block_gitcommit(manifest_block)

                    if official_gitcommit and not has_changed(
                        gitcommit, official_gitcommit, dfdir
                    ):
                        commit = official_gitcommit
                    else:
                        commit = gitcommit

                    # Append alpine alias tags for the default alpine image
                    if distro == default_alpine_image:
                        alpine_aliases = (
                            all_shared_tags.replace(", ", "-alpine, ") + "-alpine"
                        )
                        all_tags = f"{all_tags}, {alpine_aliases}"

                    # Write entry
                    lines.append(f"Tags: {all_tags}")
                    if is_windows or distro == default_linux_image:
                        lines.append(f"SharedTags: {all_shared_tags}")
                    if is_windows:
                        lines.append("Architectures: windows-amd64")
                    else:
                        arches = ", ".join(get_dockerfile_arches(dockerfile))
                        lines.append(f"Architectures: {arches}")
                    lines.append(f"GitCommit: {commit}")
                    lines.append(f"Directory: {dfdir}")
                    if is_windows:
                        lines.append("Builder: classic")
                        lines.append(f"Constraints: {constraints}")
                    lines.append("")

    with open(output_file, "w") as f:
        # Remove trailing empty lines before writing
        while lines and lines[-1] == "":
            lines.pop()
        f.write("\n".join(lines))
        f.write("\n")


def main():
    output_file = sys.argv[1] if len(sys.argv) > 1 else "eclipse-temurin"
    config = load_config()
    generate_manifest(config, output_file)


if __name__ == "__main__":
    main()
