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

import os

import requests
import yaml
from jinja2 import Environment, FileSystemLoader

# Setup the Jinja2 environment
env = Environment(loader=FileSystemLoader("docker_templates"))

headers = {
    "User-Agent": "Adoptium Dockerfile Updater",
}


def archHelper(arch, os_family):
    if arch == "aarch64":
        return "aarch64|arm64"
    elif arch == "ppc64le":
        return "ppc64el|powerpc:common64"
    elif arch == "s390x":
        return "s390x|s390:64-bit"
    elif arch == "arm":
        return "armhf|arm"
    elif arch == "x64":
        if os_family == "alpine-linux":
            return "amd64|x86_64"
        else:
            return "amd64|i386:x86-64"
    else:
        return arch


# Load the YAML configuration
with open("config/hotspot.yml", "r") as file:
    config = yaml.safe_load(file)

# Iterate through OS families and then configurations
for os_family, configurations in config["configurations"].items():
    for configuration in configurations:
        directory = configuration["directory"]
        architectures = configuration["architectures"]
        os_name = configuration["os"]
        base_image = configuration["image"]
        deprecated = configuration.get("deprecated", None)
        versions = configuration.get(
            "versions", config["supported_distributions"]["Versions"]
        )

        # Define the path for the template based on OS
        template_name = f"{os_name}.Dockerfile.j2"
        template = env.get_template(template_name)

        # Create output directories if they don't exist
        for version in versions:
            # if deprecated is set and version is greater than or equal to deprecated, skip
            if deprecated and version >= deprecated:
                continue
            print("Generating Dockerfiles for", base_image, "-", version)
            for image_type in ["jdk", "jre"]:
                output_directory = os.path.join(str(version), image_type, directory)
                os.makedirs(output_directory, exist_ok=True)

                # Fetch latest release for version from Adoptium API
                url = f"https://api.adoptium.net/v3/assets/feature_releases/{version}/ga?page=0&image_type={image_type}&page_size=1&vendor=eclipse"
                response = requests.get(url, headers=headers)
                response.raise_for_status()
                data = response.json()

                release = response.json()[0]

                # Extract the version number from the release name
                openjdk_version = release["release_name"]

                # Generate the data for each architecture
                arch_data = {}

                for binary in release["binaries"]:
                    if (
                        binary["architecture"] in architectures
                        and binary["os"] == os_family
                    ):
                        if os_family == "windows":
                            # Windows only has x64 binaries
                            copy_from = openjdk_version.replace(
                                "jdk", ""
                            )  # jdk8u292-b10 -> 8u292-b10
                            if version != 8:
                                copy_from = copy_from.replace("-", "").replace(
                                    "+", "_"
                                )  # 11.0.11+9 -> 11.0.11_9
                            copy_from = f"{copy_from}-{image_type}-windowsservercore-{base_image.split(':')[1]}"
                            arch_data = {
                                "download_url": binary["installer"]["link"],
                                "checksum": binary["installer"]["checksum"],
                                "copy_from": copy_from,
                            }
                        else:
                            arch_data[archHelper(binary["architecture"], os_family)] = {
                                "download_url": binary["package"]["link"],
                                "checksum": binary["package"]["checksum"],
                            }

                    else:
                        continue

                # If arch_data is empty, skip updating the dockerfile
                if arch_data.__len__() == 0:
                    continue

                # Sort arch_data by key
                arch_data = dict(sorted(arch_data.items()))

                # Generate Dockerfile for each architecture
                rendered_dockerfile = template.render(
                    base_image=base_image,
                    image_type=image_type,
                    java_version=openjdk_version,
                    version=version,
                    arch_data=arch_data,
                    os_family=os_family,
                    os=os_name,
                )

                print("Writing Dockerfile to", output_directory)
                # Save the rendered Dockerfile
                with open(
                    os.path.join(output_directory, "Dockerfile"), "w"
                ) as out_file:
                    out_file.write(rendered_dockerfile)

                # Copy entrypoint.sh to output directory
                entrypoint_path = os.path.join(
                    "docker_templates", "scripts", f"entrypoint.{os_name}.sh"
                )

                if os.path.exists(entrypoint_path):
                    os.system(
                        f"cp {entrypoint_path} {os.path.join(output_directory, 'entrypoint.sh')}"
                    )

print("Dockerfiles generated successfully!")
