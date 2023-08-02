#!/usr/bin/env bash

set -e

# Opt-in is only activated if the environment variable is set
if [ -n "$USE_SYSTEM_CA_CERTS" ]; then

    # Copy certificates from /certificates to the system truststore, but only if the directory exists and is not empty.
    # The reason why this is not part of the opt-in is because it leaves open the option to mount certificates at the
    # system location, for whatever reason.
    if [ -d /certificates ] && [ "$(ls -A /certificates)" ]; then
        cp -a /certificates/* /usr/share/pki/ca-trust-source/anchors/
    fi

    CACERT=$JAVA_HOME/lib/security/cacerts

    # JDK8 puts its JRE in a subdirectory
    if [ -f "$JAVA_HOME/jre/lib/security/cacerts" ]; then
        CACERT=$JAVA_HOME/jre/lib/security/cacerts
    fi

    # RHEL-based images already include a routine to update a java truststore from the system CA bundle within
    # `update-ca-trust`. All we need to do is to link the system CA bundle to the java truststore.
    update-ca-trust

    ln -sf /etc/pki/ca-trust/extracted/java/cacerts "$CACERT"
fi

exec "$@"
