#!/bin/bash

set -o pipefail 

testDir="$(readlink -f "$(dirname "$BASH_SOURCE")")"
runDir="$(dirname "$(readlink -f "$BASH_SOURCE")")"

# Find Java major/minor/build/patch version
# 
# https://stackoverflow.com/a/74459237/6460
IFS='"' read -r _ java_version_string _ < <(docker run "$1" java -version 2>&1)
IFS='._' read -r \
    java_version_major \
    java_version_minor \
    java_version_build \
    java_version_patch \
    <<<"$java_version_string"

# CMD1 in each run is just a `date` to make sure nothing is broken with or without the entrypoint
CMD1=date

# CMD2 in each run is to check for the `dockerbuilder` certificate in the Java keystore
if [ "$java_version_major" -lt 11 ]; then
    # We are working with JDK/JRE 8
    #
    # `keytool` from JDK/JRE 8 does not have the `-cacerts` option and also does not have standardized location for the
    # `cacerts` file between the JDK and JRE, so we'd want to check both possible locations.
    CACERTS=/opt/java/openjdk/lib/security/cacerts
    CACERTS2=/opt/java/openjdk/jre/lib/security/cacerts

    CMD2=(sh -c "keytool -list -keystore $CACERTS -storepass changeit -alias dockerbuilder || keytool -list -keystore $CACERTS2 -storepass changeit -alias dockerbuilder")
else
    CMD2=(keytool -list -cacerts -storepass changeit -alias dockerbuilder)
fi

# 
# We need to use `docker run`, since `run-in-container.sh` overwrites the entrypoint
#

# Test run 1: No added certificates and environment variable is not set. We expect CMD1 to succeed and CMD2 to fail.
docker run --rm "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 2: No added certificates, but the environment variable is set. Since there are no certificates, we still
# expect CMD1 to succeed and CMD2 to fail.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 3: Certificates are mounted, but the environment variable is not set, i.e. certificate importing should not
# be activated. We expect CMD1 to succeed and CMD2 to fail.
docker run --rm --volume=$testDir/certs:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm --volume=$testDir/certs:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 4: Certificates are mounted and the environment variable is set. We expect both CMD1 and CMD2 to succeed.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

TESTIMAGE=$1.test

function finish {
    docker rmi "$TESTIMAGE" >&/dev/null
}
trap finish EXIT HUP INT TERM

# Test run 5: Certificates are mounted and the environment variable is set, but the entrypoint is overridden. We expect
# CMD1 to succeed and CMD2 to fail.
#
# But first, we need to create an image with an overridden entrypoint
docker build -t "$1.test" "$runDir" -f - <<EOF >&/dev/null 
FROM $1
COPY custom-entrypoint.sh /
ENTRYPOINT ["/custom-entrypoint.sh"]
EOF

docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" "${CMD2[@]}" >&/dev/null
echo -n $?
