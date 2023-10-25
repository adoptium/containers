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

FROM mcr.microsoft.com/windows/nanoserver:ltsc2022

SHELL ["cmd", "/s", "/c"]

ENV JAVA_VERSION jdk-11.0.21+9

ENV JAVA_HOME C:\\openjdk-11
# "ERROR: Access to the registry path is denied."
USER ContainerAdministrator
RUN echo Updating PATH: %JAVA_HOME%\bin;%PATH% \
    && setx /M PATH %JAVA_HOME%\bin;%PATH% \
    && echo Complete.
USER ContainerUser

COPY --from=eclipse-temurin:11.0.21_9-jre-windowsservercore-ltsc2022 $JAVA_HOME $JAVA_HOME

RUN echo Verifying install ... \
    && echo java --version && java --version \
    && echo Complete.
