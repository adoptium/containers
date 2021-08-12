#!/bin/bash
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
# 1. Run ./update_all.sh to update all the dockerfiles in the current repo.
# 2. Submit PR to push the newly generated dockerfiles to the current repo.
# 3. After above PR is merged, git pull the latest changes.
# 4. Run this command
#
set -o pipefail

# shellcheck source=common_functions.sh
source ./common_functions.sh

if [[ -z "$1" ]]; then
	official_docker_image_file="eclipse-temurin"
else
	official_docker_image_file="$1"
fi

oses="ubuntu centos windowsservercore-1809 windowsservercore-ltsc2016 nanoserver-1809"
# The image which is used by default when pulling shared tags on linux e.g 8-jdk
default_linux_image="focal"

# shellcheck disable=SC2034 # used externally
hotspot_latest_tags="latest"

git_repo="https://github.com/adoptium/containers/blob/master"

# Get the latest git commit of the current repo.
# This is assumed to have all the latest dockerfiles already.
gitcommit=$(git log | head -1 | awk '{ print $2 }')

print_official_text() {
	echo "$*" >> ${official_docker_image_file}
}

print_official_header() {
	print_official_text "# Eclipse Temurin OpenJDK images provided by the Eclipse Foundation."
	print_official_text
	print_official_text "Maintainers: George Adams <george.adams@microsoft.com> (@gdams)"
	print_official_text "GitRepo: https://github.com/adoptium/containers.git"
}

function generate_official_image_tags() {
	# Generate the tags
	full_version=$(grep "VERSION" "${file}" | awk '{ print $3 }')

	# Remove any `jdk` references in the version
	ojdk_version=$(echo "${full_version}" | sed 's/\(jdk-\)//;s/\(jdk\)//' | awk -F '_' '{ print $1 }')
	# Replace "+" with "_" in the version info as docker does not support "+"
	ojdk_version=${ojdk_version//+/_}
	
	case $os in
		"ubuntu") distro="focal" ;;
        "centos") distro="centos7" ;;
		"windows") distro=$(echo $dfdir | awk -F '/' '{ print $4 }' ) ;;
		*) distro=undefined;;
	esac

	# Official image build tags are as below
	# 8u212-jre-openj9_0.12.1
	# 8-jre-openj9
	# 8u212-jdk-hotspot
	full_ver_tag="${ojdk_version}-${pkg}"

	unset extra_shared_tags extra_ver_tags
	# Add the openj9 version
	if [ "${vm}" == "openj9" ]; then
		openj9_version=$(echo "${full_version}" | awk -F '_' '{ print $2 }')
		full_ver_tag="${full_ver_tag}-${openj9_version}-${distro}"
	else
		full_ver_tag="${full_ver_tag}-${distro}"
		# Commented out as this added the -hotspot tag which we don't need for temurin
		# extra_ver_tags=", ${ver}-${pkg}"
	fi
	ver_tag="${ver}-${pkg}-${distro}"
	all_tags="${full_ver_tag}, ${ver_tag}"
	# jdk builds also have additional tags
	if [ "${pkg}" == "jdk" ]; then
		jdk_tag="${ver}-${distro}"
		all_tags="${all_tags}, ${jdk_tag}"
		# jdk builds also have additional tags
		# Add the "latest", "hotspot" and "openj9" tags for the right version
		if [ "${ver}" == "${latest_version}" ]; then
			# Commented out as this added the -hotspot tag which we don't need for temurin
			# vm_tags_val="${vm}-${distro}"
			# shellcheck disable=SC2154
			if [ "${vm}" == "hotspot" ]; then
				extra_shared_tags=", latest"
				# Commented out as this added the -hotspot tag which we don't need for temurin
				# extra_ver_tags="${extra_ver_tags}, ${pkg}"
			fi
		fi
	fi
	
	unset windows_shared_tags
	shared_tags=$(echo ${all_tags} | sed "s/-$distro//g")
	if [ $os == "windows" ]; then
		windows_version=$(echo $distro | awk -F '-' '{ print $1 }' )
		windows_version_number=$(echo $distro | awk -F '-' '{ print $2 }' )
		windows_shared_tags=$(echo ${all_tags} | sed "s/$distro/$windows_version/g")
		case $distro in
			nanoserver*) 
				constraints="${distro}, windowsservercore-${windows_version_number}"
				all_shared_tags="${windows_shared_tags}"
				;;
			*) 
				constraints="${distro}"
				all_shared_tags="${windows_shared_tags}, ${shared_tags}${extra_ver_tags}${extra_shared_tags}"
				;;
		esac
	else
	all_shared_tags="${shared_tags}${extra_ver_tags}${extra_shared_tags}"
	fi
}

function generate_official_image_arches() {
	# Generate the supported arches for the above tags.
	# Official images supports amd64, arm64vX, s390x, ppc64le amd windows-amd64
	if [ $os == "windows" ]; then
		arches="windows-amd64"
	else
		# Remove ppc64el, x86_64, armv7l and aarch64
		# Retain ppc64le, amd64 and arm64
		# armhf is arm32v7 and arm64 is arm64v8 for docker builds
		# shellcheck disable=SC2046,SC2005,SC1003,SC2086,SC2063
		arches=$(echo $(grep ') \\' ${file} | sed 's/\(ppc64el\)//;s/\(x86_64\)//;s/\(armv7l\)//;s/\(armhf\)/arm32v7/;s/\(aarch64\)//;s/\(arm64\)/arm64v8/;' | grep -v "*" | sed 's/) \\//g; s/|//g' | sort) | sed 's/ /, /g')
	fi
}

function print_official_image_file() {
	# Print them all
	{
	  echo "Tags: ${all_tags}"
	  if [[ "${os}" == "windows" ]] || [[ "${distro}" == "${default_linux_image}" ]]; then
	  	echo "SharedTags: ${all_shared_tags}"
	  fi
	  echo "Architectures: ${arches}"
	  echo "GitCommit: ${gitcommit}"
	  echo "Directory: ${dfdir}"
	  echo "File: ${dfname}"
	  if [ $os == "windows" ]; then
		echo "Constraints: ${constraints}"
	  fi
	  echo ""
	} >> ${official_docker_image_file}
}

rm -f ${official_docker_image_file}
print_official_header

official_os_ignore_array=(alpine clefos debian debianslim leap tumbleweed ubi ubi-minimal)

# Generate config and doc info only for "supported" official builds.
function generate_official_image_info() {
	# If it is an unsupported OS from the array above, return.
	for arr_os in "${official_os_ignore_array[@]}"; 
	do
		if [ "${os}" == "${arr_os}" ]; then
			return;
		fi
	done
	if [ "${os}" == "windows" ]; then
		distro=$(echo $dfdir | awk -F '/' '{ print $4 }' )
		# 20h2 and 1909 is not supported upstream
		if [[ "${distro}" == "windowsservercore-20h2" ]] || [[ "${distro}" == "windowsservercore-1909" ]] || [[ "${distro}" == "windowsservercore-ltsc2019" ]] ; then
			return;
		fi
		if [[ "${distro}" == "nanoserver-20h2" ]] || [[ "${distro}" == "nanoserver-1909" ]]; then
			return;
		fi
	fi
	# We do not push our nightly and slim images either.
	if [ "${build}" == "nightly" ] || [ "${btype}" == "slim" ]; then
		return;
	fi

	generate_official_image_tags
	generate_official_image_arches
	print_official_image_file
}

# Iterate through all the VMs, for each supported version and packages to
# generate the config file for the official docker images.
# Official docker images = https://hub.docker.com/_/adoptopenjdk
for vm in ${all_jvms}
do
	# Official images support different versions
	official_supported_versions="8 11 16"
	for ver in ${official_supported_versions}
	do
		print_official_text
		print_official_text "#------------------------------v${ver} images---------------------------------"
		for pkg in ${all_packages}
		do
			for os in ${oses}
			do
				for file in $(find . -name "Dockerfile.*" | grep "/${ver}" | grep "${pkg}" | grep "${os}" | sort -n)
				do
					# file will look like ./12/jdk/debian/Dockerfile.openj9.nightly.slim
					# dockerfile name
					dfname=$(basename "${file}")
					# dockerfile dir
					dfdir=$(dirname $file | cut -c 3-)
					os=$(echo "${file}" | awk -F '/' '{ print $4 }')
					# build = release or nightly
					build=$(echo "${dfname}" | awk -F "." '{ print $3 }')
					# btype = full or slim
					btype=$(echo "${dfname}" | awk -F "." '{ print $4 }')
					generate_official_image_info
				done
			done
		done
	done
done
