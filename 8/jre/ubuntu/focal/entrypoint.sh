#!/usr/bin/env sh
# Converted to POSIX shell to avoid the need for bash in the image

set -e

# JDK truststore location
CACERT=$JAVA_HOME/lib/security/cacerts

# JDK8 puts its JRE in a subdirectory
if [ -f "$JAVA_HOME/jre/lib/security/cacerts" ]; then
    CACERT=$JAVA_HOME/jre/lib/security/cacerts
fi

# Opt-in is only activated if the environment variable is set
if [ -n "$USE_SYSTEM_CA_CERTS" ]; then

    if [ ! -w /tmp ]; then
        echo "Using additional CA certificates requires write permissions to /tmp. Cannot create truststore."
        exit 1
    fi

    # Figure out whether we can write to the JVM truststore. If we can, we'll add the certificates there. If not,
    # we'll use a temporary truststore.
    if [ ! -w "$CACERT" ]; then
        # We cannot write to the JVM truststore, so we create a temporary one
        CACERT_NEW=$(mktemp)
        echo "Using a temporary truststore at $CACERT_NEW"
        cp $CACERT $CACERT_NEW
        CACERT=$CACERT_NEW
        # If we use a custom truststore, we need to make sure that the JVM uses it
        export JAVA_TOOL_OPTIONS="${JAVA_TOOL_OPTIONS} -Djavax.net.ssl.trustStore=${CACERT} -Djavax.net.ssl.trustStorePassword=changeit"
    fi

    tmp_store=$(mktemp)

    # Copy full system CA store to a temporary location
    trust extract --overwrite --format=java-cacerts --filter=ca-anchors --purpose=server-auth "$tmp_store"

    # Add the system CA certificates to the JVM truststore.
    keytool -importkeystore -destkeystore "$CACERT" -srckeystore "$tmp_store" -srcstorepass changeit -deststorepass changeit -noprompt # >/dev/null

    # Import the additional certificate into JVM truststore
    for i in /certificates/*crt; do
        if [ ! -f "$i" ]; then
            continue
        fi
        keytool -import -noprompt -alias "$(basename "$i" .crt)" -file "$i" -keystore "$CACERT" -storepass changeit # >/dev/null
    done

    # Add additional certificates to the system CA store. This requires write permissions to several system
    # locations, which is not possible in a container with read-only filesystem and/or non-root container.
    if [ "$(id -u)" -eq 0 ]; then

        # Copy certificates from /certificates to the system truststore, but only if the directory exists and is not empty.
        # The reason why this is not part of the opt-in is because it leaves open the option to mount certificates at the
        # system location, for whatever reason.
        if [ -d /certificates ] && [ "$(ls -A /certificates 2>/dev/null)" ]; then

            # UBI
            if [ -d /usr/share/pki/ca-trust-source/anchors/ ]; then
                cp -La /certificates/* /usr/share/pki/ca-trust-source/anchors/
            fi

            # Ubuntu/Alpine
            if [ -d /usr/local/share/ca-certificates/ ]; then
                cp -La /certificates/* /usr/local/share/ca-certificates/
            fi
        fi

        # UBI
        if which update-ca-trust >/dev/null; then
            update-ca-trust
        fi

        # Ubuntu/Alpine
        if which update-ca-certificates >/dev/null; then
            update-ca-certificates
        fi
    else
        # If we are not root, we cannot update the system truststore. That's bad news for tools like `curl` and `wget`,
        # but since the JVM is the primary focus here, we can live with that.
        true
    fi
fi

# Let's provide a variable with the correct path for tools that want or need to use it
export CACERT

exec "$@"
