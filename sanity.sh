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

# Check for empty Shasum
if [[ $(grep -R ESUM=\'\' . | wc -l | awk '{print $1}') != 0 ]]; then
    echo "detected empty ESUM"
    exit 1
fi

# Check for empty Binary URL
if [[ $(grep -R BINARY_URL=\'\' . | wc -l | awk '{print $1}') != 0 ]]; then
    echo "detected empty Binary URL"
    exit 1
fi

# Check for empty Shasum Windows
if [[ $(grep -R "Hash -ne '\'" . | wc -l | awk '{print $1}') != 0 ]]; then
    echo "detected empty ESUM"
    exit 1
fi

# Check for empty Binary URL Windows
if [[ $(grep -R 'Downloading \.\.\.' . | wc -l | awk '{print $1}') != 0 ]]; then
    echo "detected empty Binary URL"
    exit 1
fi