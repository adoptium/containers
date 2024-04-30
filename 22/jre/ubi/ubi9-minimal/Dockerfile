# ------------------------------------------------------------------------------
#               NOTE: THIS DOCKERFILE IS GENERATED VIA "generate_dockerfiles.py"
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

FROM redhat/ubi9-minimal

ENV JAVA_HOME /opt/java/openjdk
ENV PATH $JAVA_HOME/bin:$PATH

# Default to UTF-8 file.encoding
ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'

RUN set -eux; \
    microdnf install -y \
        gzip \
        tar \
        # Required for objdump and also jlink
        binutils \
        tzdata \
        wget \
        # utilities for keeping UBI and OpenJDK CA certificates in sync
        # https://github.com/adoptium/containers/issues/293
        ca-certificates \
        # java.lang.UnsatisfiedLinkError: libfontmanager.so: libfreetype.so.6: cannot open shared object file: No such file or directory
        # java.lang.NoClassDefFoundError: Could not initialize class sun.awt.X11FontManager
        # https://github.com/docker-library/openjdk/pull/235#issuecomment-424466077
        fontconfig \
        glibc-langpack-en \
    ; \
    microdnf clean all

ENV JAVA_VERSION jdk-22.0.1+8

RUN set -eux; \
    ARCH="$(objdump="$(command -v objdump)" && objdump --file-headers "$objdump" | awk -F '[:,]+[[:space:]]+' '$1 == "architecture" { print $2 }')"; \
    case "${ARCH}" in \
       aarch64|arm64) \
         ESUM='8e5996a2bbae2da9797cff5a62cb2080965e08fd66de24673b29a8e481ec769e'; \
         BINARY_URL='https://github.com/adoptium/temurin22-binaries/releases/download/jdk-22.0.1%2B8/OpenJDK22U-jre_aarch64_linux_hotspot_22.0.1_8.tar.gz'; \
         ;; \
       amd64|i386:x86-64) \
         ESUM='154dbc7975cf765c59bdaa1e693d6c8b009635c9a182d6d6d9f0cfbec5317b4c'; \
         BINARY_URL='https://github.com/adoptium/temurin22-binaries/releases/download/jdk-22.0.1%2B8/OpenJDK22U-jre_x64_linux_hotspot_22.0.1_8.tar.gz'; \
         ;; \
       ppc64el|powerpc:common64) \
         ESUM='7df4a10fab324181a6c9e8b1e2a45042b8d30490f0fdb937a536f6cd17c907ef'; \
         BINARY_URL='https://github.com/adoptium/temurin22-binaries/releases/download/jdk-22.0.1%2B8/OpenJDK22U-jre_ppc64le_linux_hotspot_22.0.1_8.tar.gz'; \
         ;; \
       s390x|s390:64-bit) \
         ESUM="86dd7d37d5bb6091f3e6e2da4049ffaa0c5c2576cfcb45659606c4aab83b5824"; \
         BINARY_URL='https://github.com/adoptium/temurin22-binaries/releases/download/jdk-22.0.1.1%2B1/OpenJDK22U-jre_s390x_linux_hotspot_22.0.1.1_1.tar.gz'; \
         ;; \
       *) \
         echo "Unsupported arch: ${ARCH}"; \
         exit 1; \
         ;; \
    esac; \
    wget --progress=dot:giga -O /tmp/openjdk.tar.gz ${BINARY_URL}; \
    echo "${ESUM} */tmp/openjdk.tar.gz" | sha256sum -c -; \
    mkdir -p "$JAVA_HOME"; \
    tar --extract \
        --file /tmp/openjdk.tar.gz \
        --directory "$JAVA_HOME" \
        --strip-components 1 \
        --no-same-owner \
    ; \
    rm -f /tmp/openjdk.tar.gz ${JAVA_HOME}/lib/src.zip;

RUN set -eux; \
    echo "Verifying install ..."; \
    echo "java --version"; java --version; \
    echo "Complete."
COPY entrypoint.sh /__cacert_entrypoint.sh
ENTRYPOINT ["/__cacert_entrypoint.sh"]
