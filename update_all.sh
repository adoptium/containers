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
set -o pipefail

# shellcheck source=common_functions.sh
source ./common_functions.sh

for ver in ${supported_versions}
do
	# Remove any temporary files
	rm -f hotspot_*_latest.sh

	echo "==============================================================================="
	echo "                                                                               "
	echo "                      Writing Dockerfiles for Version ${ver}                   "
	echo "                                                                               "
	echo "==============================================================================="
	# Generate the Dockerfiles for the unofficial images.
	./update_multiarch.sh "${ver}"

	# Now generate the Dockerfiles for the official images.
	./update_multiarch.sh "${ver}"

	# Restore the original files.
	git checkout config/hotspot.config
done
