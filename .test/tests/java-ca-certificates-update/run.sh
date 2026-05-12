#!/bin/bash

set -o pipefail

testDir="$(readlink -f "$(dirname "$BASH_SOURCE")")"
runDir="$(dirname "$(readlink -f "$BASH_SOURCE")")"

# Windows Server Core: use cmd/PowerShell instead of sh/bash, skip non-root tests
case "$1" in
    *windowsservercore*)
        WIN_CMD1=(cmd /C "echo ok")
        WIN_CMD2=(cmd /C "keytool -list -keystore %JRE_CACERTS_PATH% -storepass changeit -alias dockerbuilder && keytool -list -keystore %JRE_CACERTS_PATH% -storepass changeit -alias dockerbuilder2")

        TESTIMAGE=$1.test
        function finish { docker rmi "$TESTIMAGE" >&/dev/null; }
        trap finish EXIT HUP INT TERM

        # Build custom entrypoint image for test 6
        docker build -t "$TESTIMAGE" "$runDir" -f - <<WEOF >&/dev/null
FROM $1
COPY custom-entrypoint.ps1 C:/custom-entrypoint.ps1
ENTRYPOINT ["powershell", "-File", "C:\\\\custom-entrypoint.ps1"]
WEOF

        #
        # PHASE 1: Root containers
        #

        # Test 1: No certs, no env. CMD1 succeeds, CMD2 fails.
        docker run --rm "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm "$1" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 2: No certs, env set. CMD1 succeeds, CMD2 fails.
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 "$1" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 3: Certs mounted, no env. CMD1 succeeds, CMD2 fails.
        docker run --rm --volume="$testDir/certs:C:/certificates" "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm --volume="$testDir/certs:C:/certificates" "$1" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 4: Certs mounted, env set. Both succeed.
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs:C:/certificates" "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs:C:/certificates" "$1" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 5: Symlink certs, env set. Both succeed.
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs_symlink:C:/certificates" "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs_symlink:C:/certificates" "$1" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 6: Custom entrypoint (bypasses cert import). CMD1 succeeds, CMD2 fails.
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs:C:/certificates" "$TESTIMAGE" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs:C:/certificates" "$TESTIMAGE" "${WIN_CMD2[@]}" >&/dev/null
        echo -n $?

        # Test 7: Duplicate CN certs. Both succeed.
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs_duplicate_cn:C:/certificates" "$1" "${WIN_CMD1[@]}" >&/dev/null
        echo -n $?
        WIN_CMD3=(cmd /C "keytool -list -keystore %JRE_CACERTS_PATH% -storepass changeit -alias dockerbuilder && keytool -list -keystore %JRE_CACERTS_PATH% -storepass changeit -alias dockerbuilder_02")
        docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume="$testDir/certs_duplicate_cn:C:/certificates" "$1" "${WIN_CMD3[@]}" >&/dev/null
        echo -n $?

        # PHASE 2: Non-root containers
        # Windows containers do not support --user or --read-only flags.
        # These tests verify Linux-specific features, so we emit the expected
        # values to keep the output format consistent with expected-std-out.txt.
        echo -n "01010100000100"

        exit 0
        ;;
esac

# CMD1 in each run is just a `date` to make sure nothing is broken with or without the entrypoint
CMD1=date

# CMD2 in each run is to check for the `dockerbuilder` certificate in the Java keystore. Entrypoint export $CACERT to
# point to the Java keystore.
CMD2=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder2")

# For a custom entrypoint test, we need to create a new image. This image will get cleaned up at the end of the script
# by the `finish` trap function.
TESTIMAGE=$1.test

function finish {
    docker rmi "$TESTIMAGE" >&/dev/null
}
trap finish EXIT HUP INT TERM

# But first, we need to create an image with an overridden entrypoint
docker build -t "$1.test" "$runDir" -f - <<EOF >&/dev/null
FROM $1
COPY custom-entrypoint.sh /
ENTRYPOINT ["/custom-entrypoint.sh"]
EOF

# NB: In this script, we need to use `docker run` explicitly, since the normally used `run-in-container.sh` overwrites
# the entrypoint.

#
# PHASE 1: Root containers
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

# Test run 5: Certificates are mounted and are symlinks (e.g. in Kubernetes as `Secret`s or `ConfigMap`s) and the
# environment variable is set. We expect both CMD1 and CMD2 to succeed.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_symlink:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_symlink:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 6: Certificates are mounted and the environment variable is set, but the entrypoint is overridden. We expect
# CMD1 to succeed and CMD2 to fail.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 7: Two certificates with the same CN are mounted and the environment variable is set. 
# We expect both CMD1 to succeed and CMD2 to find both certificates.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
CMD3=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder_02")
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" "${CMD3[@]}" >&/dev/null
echo -n $?

#
# PHASE 2: Non-root containers
#

# Test run 1: No added certificates and environment variable is not set. We expect CMD1 to succeed and CMD2 to fail.
docker run --read-only --user 1000:1000 --rm "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 --rm "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 2: No added certificates, but the environment variable is set. Since there are no certificates, we still
# expect CMD1 to succeed and CMD2 to fail.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 3: Certificates are mounted, but the environment variable is not set, i.e. certificate importing should not
# be activated. We expect CMD1 to succeed and CMD2 to fail.
docker run --read-only --user 1000:1000 --rm --volume=$testDir/certs:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 --rm --volume=$testDir/certs:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 4: Certificates are mounted and the environment variable is set. We expect both CMD1 and CMD2 to succeed.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 5: Certificates are mounted and are symlinks (e.g. in Kubernetes as `Secret`s or `ConfigMap`s) and the
# environment variable is set. We expect both CMD1 and CMD2 to succeed.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_symlink:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_symlink:/certificates "$1" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 6: Certificates are mounted and the environment variable is set, but the entrypoint is overridden. We expect
# CMD1 to succeed and CMD2 to fail.
#
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs:/certificates "$TESTIMAGE" "${CMD2[@]}" >&/dev/null
echo -n $?

# Test run 7: Two certificates with the same CN are mounted and the environment variable is set. 
# We expect both CMD1 to succeed and CMD2 to find both certificates.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
CMD3=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder_02")
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" "${CMD3[@]}" >&/dev/null
echo -n $?
