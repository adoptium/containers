#!/usr/bin/env bash
# Sheband needs to be `bash`, see https://github.com/adoptium/containers/issues/415 for details

set -e

# Opt-in is only activated if the environment variable is set
if [ -n "$USE_SYSTEM_CA_CERTS" ]; then

    # Copy certificates from /certificates to the system truststore, but only if the directory exists and is not empty.
    # The reason why this is not part of the opt-in is because it leaves open the option to mount certificates at the
    # system location, for whatever reason.
    if [ -d /certificates ] && [ "$(ls -A /certificates)" ]; then
        cp -a /certificates/* /usr/local/share/ca-certificates/
    fi

    CACERT=$JAVA_HOME/lib/security/cacerts

    # JDK8 puts its JRE in a subdirectory
    if [ -f "$JAVA_HOME/jre/lib/security/cacerts" ]; then
        CACERT=$JAVA_HOME/jre/lib/security/cacerts
    fi

    # OpenJDK images used to create a hook for `update-ca-certificates`. Since we are using an entrypoint anyway, we
    # might as well just generate the truststore and skip the hooks.
    update-ca-certificates

    trust extract --overwrite --format=java-cacerts --filter=ca-anchors --purpose=server-auth "$CACERT"
fi

exec "$@"
