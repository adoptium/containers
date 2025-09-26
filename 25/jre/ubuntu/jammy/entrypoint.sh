#!/usr/bin/env bash
# ------------------------------------------------------------------------------
#             NOTE: THIS FILE IS GENERATED VIA "generate_dockerfiles.py"
#
#                       PLEASE DO NOT EDIT IT DIRECTLY.
# ------------------------------------------------------------------------------
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
# This script defines `sh` as the interpreter, which is available in all POSIX environments. However, it might get
# started with `bash` as the shell to support dotted.environment.variable.names which are not supported by POSIX, but
# are supported by `sh` in some Linux flavours.

set -e

TMPDIR=${TMPDIR:-/tmp}

# JDK truststore location
JRE_CACERTS_PATH=$JAVA_HOME/lib/security/cacerts

# Opt-in is only activated if the environment variable is set
if [ -n "$USE_SYSTEM_CA_CERTS" ]; then

    if [ ! -w "$TMPDIR" ]; then
        echo "Using additional CA certificates requires write permissions to $TMPDIR. Cannot create truststore."
        exit 1
    fi

    # Figure out whether we can write to the JVM truststore. If we can, we'll add the certificates there. If not,
    # we'll use a temporary truststore.
    if [ ! -w "$JRE_CACERTS_PATH" ]; then
        # We cannot write to the JVM truststore, so we create a temporary one
        JRE_CACERTS_PATH_NEW=$(mktemp)
        echo "Using a temporary truststore at $JRE_CACERTS_PATH_NEW"
        cp "$JRE_CACERTS_PATH" "$JRE_CACERTS_PATH_NEW"
        JRE_CACERTS_PATH=$JRE_CACERTS_PATH_NEW
        # If we use a custom truststore, we need to make sure that the JVM uses it
        export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS} -Djavax.net.ssl.trustStore=${JRE_CACERTS_PATH} -Djavax.net.ssl.trustStorePassword=changeit"
    fi

    tmp_store=$(mktemp)

    # Copy full system CA store to a temporary location
    trust extract --overwrite --format=java-cacerts --filter=ca-anchors --purpose=server-auth "$tmp_store" > /dev/null

    # Add the system CA certificates to the JVM truststore.
    keytool -importkeystore -destkeystore "$JRE_CACERTS_PATH" -srckeystore "$tmp_store" -srcstorepass changeit -deststorepass changeit -noprompt > /dev/null

    # Clean up the temporary truststore
    rm -f "$tmp_store"

    # Import the additional certificate into JVM truststore
    for i in /certificates/*crt; do
        if [ ! -f "$i" ]; then
            continue
        fi
        tmp_dir=$(mktemp -d)
        BASENAME=$(basename "$i" .crt)

        # We might have multiple certificates in the file. Split this file into single files. The reason is that
        # `keytool` does not accept multi-certificate files
        csplit -s -z -b %02d.crt -f "$tmp_dir/$BASENAME-" "$i" '/-----BEGIN CERTIFICATE-----/' '{*}'

        for crt in "$tmp_dir/$BASENAME"-*; do
            # Extract the Common Name (CN) and Serial Number from the certificate
            CN=$(openssl x509 -in "$crt" -noout -subject -nameopt -space_eq | sed -n 's/^.*CN=\([^,]*\).*$/\1/p')
            SERIAL=$(openssl x509 -in "$crt" -noout -serial | sed -n 's/^serial=\(.*\)$/\1/p')
            
            # Check if an alias with the CN already exists in the keystore
            ALIAS=$CN
            if keytool -list -keystore "$JRE_CACERTS_PATH" -storepass changeit -alias "$ALIAS" >/dev/null 2>&1; then
                # If the CN already exists, append the serial number to the alias
                ALIAS="${CN}_${SERIAL}"
            fi

            echo "Adding certificate with alias $ALIAS to the JVM truststore"

            # Add the certificate to the JVM truststore
            keytool -import -noprompt -alias "$ALIAS" -file "$crt" -keystore "$JRE_CACERTS_PATH" -storepass changeit >/dev/null
        done
    done

    # Add additional certificates to the system CA store. This requires write permissions to several system
    # locations, which is not possible in a container with read-only filesystem and/or non-root container.
    if [ "$(id -u)" -eq 0 ]; then

        # Copy certificates from /certificates to the system truststore, but only if the directory exists and is not empty.
        # The reason why this is not part of the opt-in is because it leaves open the option to mount certificates at the
        # system location, for whatever reason.
        if [ -d /certificates ] && [ "$(ls -A /certificates 2>/dev/null)" ]; then
            cp -La /certificates/* /usr/local/share/ca-certificates/
        fi
        update-ca-certificates
    else
        # If we are not root, we cannot update the system truststore. That's bad news for tools like `curl` and `wget`,
        # but since the JVM is the primary focus here, we can live with that.
        true
    fi
fi

# Let's provide a variable with the correct path for tools that want or need to use it
export JRE_CACERTS_PATH

exec "$@"
