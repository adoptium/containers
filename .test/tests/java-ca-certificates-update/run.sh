#!/bin/bash

set -o pipefail

testDir="$(readlink -f "$(dirname "$BASH_SOURCE")")"
runDir="$(dirname "$(readlink -f "$BASH_SOURCE")")"

# CMD1 in each run is just a `date` to make sure nothing is broken with or without the entrypoint
CMD1=date

# CMD2 in each run is to check for the `dockerbuilder` certificate in the Java keystore. Entrypoint exports $JRE_CACERTS_PATH to
# point to the Java keystore.
CMD2=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder2 && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder3")

# CMD3 is looking for certificates with same CN, script appends the SHA-256 fingerprint to avoid alias conflict.
# certs_duplicate_cn/cert1.crt will be imported first with alias dockerbuilder
# certs_duplicate_cn/cert2.crt will be imported later with alias dockerbuilder_<fingerprint of cert2>
ALIAS_DUP_CN="dockerbuilder_127f5ee7608fc59ee4c9ae4ae59f7a1fff101eb33ac9509a64907067ad9ba6f5"
CMD3=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias dockerbuilder && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_DUP_CN")

# CMD4 covers certificates that have no CN and share a non-unique serial number (00). These cannot be
# disambiguated by CN+serial, so the script derives a unique alias from the SHA-256 fingerprint:
# adoptium_<fingerprint>. Both certs in certs_no_cn must import under their distinct fingerprint aliases.
ALIAS_NO_CN_A="adoptium_27b513b1e7f0f61a23c2b4e3135bf606b7b81339a126bfebd86a306e69406eef"
ALIAS_NO_CN_B="adoptium_f4a91cab0ad6e7fe0c41d4827b44a89b21234425b0f973d9cbb63bfa09688b92"
ALIAS_NO_CN_C="adoptium_3418bd65082762a1a37ab63b19dbe5b17db17472900eaa192a72499cadfd845e"
CMD4=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_NO_CN_A && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_NO_CN_B && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_NO_CN_C")

# CMD5 covers certificates that share BOTH the same CN (IdenticalCA) and the same serial number. Neither CN
# nor CN+serial can disambiguate them, so the script appends the SHA-256 fingerprint. The first cert imports
# as the bare CN, the others as CN_<fingerprint>. All three certs in certs_same_cn_serial must be present.
ALIAS_SAME_A="IdenticalCA"
ALIAS_SAME_B="IdenticalCA_528d3da80a18ace9cd569595363d592d7a13b67f582149434c88a6c77e43c457"
ALIAS_SAME_C="IdenticalCA_01d2a1ff022af410deb620d298f11b3eae13e114519d84ca46513fa5a1837f0d"
CMD5=(sh -c "keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_SAME_A && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_SAME_B && keytool -list -keystore \"\$JRE_CACERTS_PATH\" -storepass changeit -alias $ALIAS_SAME_C")

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
# We expect both CMD1 to succeed and CMD3 to find both certificates.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" "${CMD3[@]}" >&/dev/null
echo -n $?

# Test run 8: Two certificates with no CN and the same serial number (00) are mounted and the environment
# variable is set. We expect CMD1 to succeed and CMD4 to find both fingerprint-based aliases.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_no_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_no_cn:/certificates "$1" "${CMD4[@]}" >&/dev/null
echo -n $?

# Test run 9: Three certificates with identical CN and identical serial number are mounted and the
# environment variable is set. We expect CMD1 to succeed and CMD5 to find all three fingerprint-based aliases.
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_same_cn_serial:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_same_cn_serial:/certificates "$1" "${CMD5[@]}" >&/dev/null
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
# We expect both CMD1 to succeed and CMD3 to find both certificates.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_duplicate_cn:/certificates "$1" "${CMD3[@]}" >&/dev/null
echo -n $?

# Test run 8: Two certificates with no CN and the same serial number (00) are mounted and the environment
# variable is set. We expect CMD1 to succeed and CMD4 to find both fingerprint-based aliases.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_no_cn:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_no_cn:/certificates "$1" "${CMD4[@]}" >&/dev/null
echo -n $?

# Test run 9: Three certificates with identical CN and identical serial number are mounted and the
# environment variable is set. We expect CMD1 to succeed and CMD5 to find all three fingerprint-based aliases.
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_same_cn_serial:/certificates "$1" $CMD1 >&/dev/null
echo -n $?
docker run --read-only --user 1000:1000 -v /tmp --rm -e USE_SYSTEM_CA_CERTS=1 --volume=$testDir/certs_same_cn_serial:/certificates "$1" "${CMD5[@]}" >&/dev/null
echo -n $?
