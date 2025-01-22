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

import argparse
import os
import subprocess
import requests
import yaml
import re
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Generate the official manifest for Eclipse Temurin images"
)

parser.add_argument(
    "--output",
    "-o",
    default="eclipse-temurin",
    help="Output file for the official manifest",
)

args = parser.parse_args()

# Load the YAML configuration
with open("config/temurin.yml", "r") as file:
    config = yaml.safe_load(file)


# Configuration settings
metadata = config["metadata"]
latest_version = metadata["latest_version"]
image_types = metadata["image_types"]
default_linux_image = metadata["default_linux_image"]
default_alpine_image = metadata["default_alpine_image"]
supported_versions = config["supported_distributions"]["Versions"]


# Fetch the latest manifest
def fetch_latest_manifest():
    """Fetch the latest manifest from the official-images repository."""
    url = "https://raw.githubusercontent.com/docker-library/official-images/master/library/eclipse-temurin"
    response = requests.get(url)
    response.raise_for_status()
    with open("official-eclipse-temurin", "w") as f:
        f.write(response.text)


# Get the latest git commit
def get_git_commit():
    """Get the latest git commit."""
    return (
        subprocess.check_output(["git", "log", "-1", "--pretty=format:%H"])
        .decode()
        .strip()
    )


# Parse Dockerfile to extract relevant information
def parse_dockerfile(dockerfile_path, osname):
    """Parse the Dockerfile to extract the Java version and supported architectures."""
    java_version = ""
    architectures = []

    with open(os.path.join(dockerfile_path, "Dockerfile"), "r") as dockerfile:
        lines = dockerfile.readlines()

        # Extract JAVA_VERSION
        for line in lines:
            if "ENV JAVA_VERSION=" in line:
                java_version = re.search(r"JAVA_VERSION=([\w\+\.\-]+)", line).group(1)
                break

        if osname == "windows":
            return java_version, ["windows-amd64"]

        # Extract architectures from the `case` statement
        inside_case_statement = False
        for line in lines:
            if line.strip().startswith('case "${ARCH}" in'):
                inside_case_statement = True
                continue
            if inside_case_statement:
                match = re.match(r"\s*(\w+)\)", line)
                if match:
                    arch = match.group(1)
                    match arch:
                        case "x86_64":
                            arch = "amd64"
                        case "armhf":
                            arch = "arm32v7"
                        case "arm64" | "aarch64":
                            arch = "arm64v8"
                        case "ppc64el":
                            arch = "ppc64le"
                    architectures.append(arch)
                elif line.strip() == ";;":
                    continue
                elif line.strip() == "*)":
                    break  # End of case statement

                # sort the architectures alphabetically
                architectures.sort()

    return java_version, architectures


def generate_tags(java_version, version, pkg, distro):
    """Generate tags for the given Java version, package, and distro."""
    base_tags = []
    base_tags.append(f"{java_version}-{pkg}-{distro}")
    base_tags.append(f"{version}-{pkg}-{distro}")
    if pkg == "jdk":
        base_tags.append(f"{version}-{distro}")
    if distro == default_alpine_image:
        base_tags.append(f"{java_version}-{pkg}-alpine")
        base_tags.append(f"{version}-{pkg}-alpine")
        if pkg == "jdk":
            base_tags.append(f"{version}-alpine")
    return base_tags


def generate_shared_tags(java_version, version, pkg, distro, os):
    """Generate shared tags for the given Java version, package, and distro."""
    shared_tags = []
    if os == "windows":
        if distro.startswith("nanoserver"):
            shared_tags.append(f"{java_version}-{pkg}-nanoserver")
            shared_tags.append(f"{version}-{pkg}-nanoserver")
            if pkg == "jdk":
                shared_tags.append(f"{version}-nanoserver")
        else:
            shared_tags.append(f"{java_version}-{pkg}-windowsservercore")
            shared_tags.append(f"{version}-{pkg}-windowsservercore")
            if pkg == "jdk":
                shared_tags.append(f"{version}-windowsservercore")

    if (
        os == "windows" and distro.startswith("windowsservercore")
    ) or distro == default_linux_image:
        shared_tags.append(f"{java_version}-{pkg}")
        shared_tags.append(f"{version}-{pkg}")
        if pkg == "jdk":
            shared_tags.append(f"{version}")
            if version == latest_version:
                shared_tags.append("latest")
    return shared_tags


# Generate the official header
def print_official_header(file):
    file.write("# Eclipse Temurin OpenJDK images provided by the Eclipse Foundation.\n")
    file.write("\n")
    file.write("Maintainers: George Adams <george.adams@microsoft.com> (@gdams),\n")
    file.write("             Stewart Addison <sxa@redhat.com> (@sxa)\n")
    file.write("GitRepo: https://github.com/adoptium/containers.git\n")
    file.write("GitFetch: refs/heads/main\n")
    file.write("Builder: buildkit\n")


# Generate tags, architectures, and print to file
def generate_official_image_info(file, ver, pkg, os, dfdir):
    # Extract distro name from path
    distro = dfdir.split("/")[3]
    if os == "alpine-linux":
        distro = "alpine-" + distro

    # Parse Dockerfile to get JAVA_VERSION and architectures
    java_version, arches = parse_dockerfile(dfdir, os)

    # Generate tags and other metadata
    full_version = java_version.replace("+", "_").replace("jdk-", "").replace("jdk", "")
    tags = generate_tags(full_version, ver, pkg, distro)
    shared_tags = generate_shared_tags(full_version, ver, pkg, distro, os)
    commit = get_git_commit()

    # Fetch the latest manifest block
    official_manifest = Path("official-eclipse-temurin").read_text()
    official_gitcommit = ""
    if any(tag in official_manifest for tag in tags):
        official_gitcommit = official_manifest.split("GitCommit: ")[1].split()[0]
        if (
            subprocess.call(
                [
                    "git",
                    "diff",
                    "--quiet",
                    f"{commit}:{dfdir}/Dockerfile",
                    f"{official_gitcommit}:{dfdir}/Dockerfile",
                ]
            )
            == 0
        ):
            diff = (
                subprocess.check_output(
                    [
                        "git",
                        "diff",
                        f"{commit}:{dfdir}/Dockerfile",
                        f"{official_gitcommit}:{dfdir}/Dockerfile",
                    ]
                )
                .decode()
                .strip()
            )
            diff_count = len(diff.splitlines())
            # check for diff in the entrypoint.sh file
            if Path(f"{dfdir}/entrypoint.sh").exists():
                # check if the entrypoint.sh file is different from the official one
                if (
                    subprocess.check_output(
                        [
                            "git",
                            "diff",
                            f"{commit}:{dfdir}/entrypoint.sh",
                            f"{official_gitcommit}:{dfdir}/entrypoint.sh",
                        ]
                    )
                    .decode()
                    .strip()
                    != ""
                ):
                    diff = (
                        subprocess.check_output(
                            [
                                "git",
                                "diff",
                                f"{commit}:{dfdir}/entrypoint.sh",
                                f"{official_gitcommit}:{dfdir}/entrypoint.sh",
                            ]
                        )
                        .decode()
                        .strip()
                    )
                    diff_count += len(diff.splitlines())
        else:
            # Forcefully sets a diff if the file doesn't exist
            diff_count = 1
    else:
        # Forcefully sets a diff if a new dockerfile has been added
        diff_count = 1

    commit = official_gitcommit if diff_count == 0 else get_git_commit()

    # Write to the output file
    file.write(f"Tags: {', '.join(tags)}\n")
    if len(shared_tags) > 0:
        file.write(f"SharedTags: {', '.join(shared_tags)}\n")
    file.write(f"Architectures: {', '.join(arches)}\n")
    file.write(f"GitCommit: {commit}\n")
    file.write(f"Directory: {dfdir}\n")
    if os == "windows":
        file.write("Builder: classic\n")
        constraint = distro
        if "nanoserver" in distro:
            # trim version from distro name
            version = distro.replace("nanoserver", "")
            constraint = f"{constraint}, windowsservercore{version}"
        file.write(f"Constraints: {constraint}\n")
    file.write("\n")


# Main execution logic
def main():
    fetch_latest_manifest()

    with open(args.output, "w") as file:
        print_official_header(file)

        for ver in supported_versions:
            file.write(
                f"\n#------------------------------v{ver} images---------------------------------\n"
            )
            for pkg in image_types:
                for os_family, configurations in config["configurations"].items():
                    for configuration in configurations:
                        directory = configuration["directory"]
                        os_name = configuration["os"]
                        for dockerfile in Path(".").rglob(
                            f"{ver}/{pkg}/{directory}/Dockerfile"
                        ):
                            dfdir = str(dockerfile.parent)
                            generate_official_image_info(
                                file, ver, pkg, os_family, dfdir
                            )


if __name__ == "__main__":
    main()
