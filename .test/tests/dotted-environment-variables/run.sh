#!/bin/bash

set -o pipefail 

CMD1=(env | grep variable.with.a.dot )

# Test run 1: Expect dotted environment variables to be set correctly
docker run --rm -e "variable.with.a.dot=value.foo" "$1" $CMD1
