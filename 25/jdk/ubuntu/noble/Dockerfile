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

FROM ubuntu:24.04

ENV JAVA_HOME=/opt/java/openjdk
ENV PATH=$JAVA_HOME/bin:$PATH

# Default to UTF-8 file.encoding
ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'

RUN set -eux; \
    apt-get update; \
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        # java.lang.UnsatisfiedLinkError: libfontmanager.so: libfreetype.so.6: cannot open shared object file: No such file or directory
        # java.lang.NoClassDefFoundError: Could not initialize class sun.awt.X11FontManager
        # https://github.com/docker-library/openjdk/pull/235#issuecomment-424466077
        fontconfig \
        # utilities for keeping Ubuntu and OpenJDK CA certificates in sync
        # https://github.com/adoptium/containers/issues/293
        ca-certificates p11-kit \
        # jlink --strip-debug on 13+ needs objcopy: https://github.com/docker-library/openjdk/issues/351
        # Error: java.io.IOException: Cannot run program "objcopy": error=2, No such file or directory
        binutils \
        tzdata \
        # locales ensures proper character encoding and locale-specific behaviors using en_US.UTF-8
        locales \
    ; \
    echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen; \
    locale-gen en_US.UTF-8; \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_VERSION=jdk-25.0.5+8

RUN set -eux; \
    ARCH="$(dpkg --print-architecture)"; \
    case "${ARCH}" in \
       amd64) \
         ESUM='68982529869257d0ee6b824ec5aa270ff8b118bb438670da0b97ebdab178d7fb'; \
         BINARY_URL='https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_x64_linux_hotspot_25.0.5_8.tar.gz'; \
         ;; \
       arm64) \
         ESUM='bb5b2ded252f21c6090cf780b0a408ad0d83bbb557e702955643557f13231880'; \
         BINARY_URL='https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_aarch64_linux_hotspot_25.0.5_8.tar.gz'; \
         ;; \
       ppc64el) \
         ESUM='47825886fd72e86c94e6fd1687a13bebb4ae729e24d2788be0d294589bf07297'; \
         BINARY_URL='https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_ppc64le_linux_hotspot_25.0.5_8.tar.gz'; \
         ;; \
       riscv64) \
         ESUM='21d9ee84f64d845e7de888f86cc2abe3256c75853a0d5abe7fd42d6526374e90'; \
         BINARY_URL='https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_riscv64_linux_hotspot_25.0.5_8.tar.gz'; \
         ;; \
       s390x) \
         ESUM='dfed6b7b428852ab1a3b9eb7734264f4d4cc163686e4136f93b9942f3d8f44cd'; \
         BINARY_URL='https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.5%2B8/OpenJDK25U-jdk_s390x_linux_hotspot_25.0.5_8.tar.gz'; \
         ;; \
       *) \
         echo "Unsupported arch: ${ARCH}"; \
         exit 1; \
         ;; \
    esac; \
    savedAptMark="$(apt-mark showmanual)"; \
    apt-get update; \
    apt-get install -y --no-install-recommends wget gnupg; \
    wget --progress=dot:giga -O /tmp/openjdk.tar.gz ${BINARY_URL}; \
    wget --progress=dot:giga -O /tmp/openjdk.tar.gz.sig ${BINARY_URL}.sig; \
    export GNUPGHOME="$(mktemp -d)"; \
    # gpg: key 843C48A565F8F04B: "Adoptium GPG Key (DEB/RPM Signing Key) <temurin-dev@eclipse.org>" imported
    gpg --batch --keyserver keyserver.ubuntu.com --recv-keys 3B04D753C9050D9A5D343F39843C48A565F8F04B; \
    gpg --batch --verify /tmp/openjdk.tar.gz.sig /tmp/openjdk.tar.gz; \
    rm -rf "${GNUPGHOME}" /tmp/openjdk.tar.gz.sig; \
    echo "${ESUM} */tmp/openjdk.tar.gz" | sha256sum -c -; \
    mkdir -p "$JAVA_HOME"; \
    tar --extract \
        --file /tmp/openjdk.tar.gz \
        --directory "$JAVA_HOME" \
        --strip-components 1 \
        --no-same-owner \
    ; \
    rm -f /tmp/openjdk.tar.gz ${JAVA_HOME}/lib/src.zip; \
    apt-mark auto '.*' > /dev/null; \
    apt-mark manual $savedAptMark > /dev/null; \
    apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false; \
    rm -rf /var/lib/apt/lists/*; \
    # https://github.com/docker-library/openjdk/issues/331#issuecomment-498834472
    find "$JAVA_HOME/lib" -name '*.so' -exec dirname '{}' ';' | sort -u > /etc/ld.so.conf.d/docker-openjdk.conf; \
    ldconfig; \
    # https://github.com/docker-library/openjdk/issues/212#issuecomment-420979840
    # https://openjdk.java.net/jeps/341
    java -Xshare:dump;

RUN set -eux; \
    echo "Verifying install ..."; \
    fileEncoding="$(echo 'System.out.println(System.getProperty("file.encoding"))' | jshell -s -)"; [ "$fileEncoding" = 'UTF-8' ]; rm -rf ~/.java; \
    echo "javac --version"; javac --version; \
    echo "java --version"; java --version; \
    echo "Complete."
COPY --chmod=755 entrypoint.sh /__cacert_entrypoint.sh
ENTRYPOINT ["/__cacert_entrypoint.sh"]

CMD ["jshell"]
