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

FROM mcr.microsoft.com/windows/servercore:1809

# $ProgressPreference: https://github.com/PowerShell/PowerShell/issues/2138#issuecomment-251261324
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]

ENV JAVA_VERSION=jdk-17.0.13+11

RUN Write-Host ('Downloading https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_windows_hotspot_17.0.13_11.msi ...'); \
    curl.exe -LfsSo openjdk.msi https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.13%2B11/OpenJDK17U-jdk_x64_windows_hotspot_17.0.13_11.msi ; \
    Write-Host ('Verifying sha256 (09c8cd1d57681030acfd41105eaf5da2a9721f442cfc9655a3a9a7f382268d94) ...'); \
    if ((Get-FileHash openjdk.msi -Algorithm sha256).Hash -ne '09c8cd1d57681030acfd41105eaf5da2a9721f442cfc9655a3a9a7f382268d94') { \
        Write-Host 'FAILED!'; \
        exit 1; \
    }; \
    \
    New-Item -ItemType Directory -Path C:\temp | Out-Null; \
    \
    Write-Host 'Installing using MSI ...'; \
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList '/i', 'openjdk.msi', '/L*V', 'C:\temp\OpenJDK.log', \
    '/quiet', 'ADDLOCAL=FeatureEnvironment,FeatureJarFileRunWith,FeatureJavaHome', 'INSTALLDIR=C:\openjdk-17' -Wait -Passthru; \
    $proc.WaitForExit() ; \
    if ($proc.ExitCode -ne 0) { \
        Write-Host 'FAILED installing MSI!' ; \
        exit 1; \
    }; \
    \
    Remove-Item -Path C:\temp -Recurse | Out-Null; \
    Write-Host 'Removing openjdk.msi ...'; \
    Remove-Item openjdk.msi -Force

RUN Write-Host 'Verifying install ...'; \
    Write-Host 'javac --version'; javac --version; \
    Write-Host 'java --version'; java --version; \
    \
    Write-Host 'Complete.'

CMD ["jshell"]
