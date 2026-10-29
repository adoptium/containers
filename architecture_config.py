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

import operator
import re

VERSION_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}

VERSION_CONDITION_RE = re.compile(r"^(==|!=|>=|<=|>|<)(\d+)$")


def resolve_architectures(default_architectures, overrides, version):
    """Resolve effective architectures for a given version by applying overrides.

    All matching overrides are applied in order. Each override has a 'versions'
    string (e.g. '==8', '<=11', '>17') and either:
      - 'exclude': list of architectures to remove
      - 'include': list of architectures to add
      - 'architectures': full replacement list (overrides default entirely)
    """
    if not overrides:
        return default_architectures

    result = list(default_architectures)
    for override in overrides:
        condition = override["versions"].strip()
        match = VERSION_CONDITION_RE.match(condition)
        if not match:
            raise ValueError(f"Invalid version condition: '{condition}'")
        op_str, target = match.groups()
        if VERSION_OPERATORS[op_str](version, int(target)):
            if "architectures" in override:
                result = list(override["architectures"])
            if "exclude" in override:
                result = [a for a in result if a not in override["exclude"]]
            if "include" in override:
                result = result + [a for a in override["include"] if a not in result]

    return result
