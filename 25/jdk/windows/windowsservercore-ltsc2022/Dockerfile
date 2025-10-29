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

FROM mcr.microsoft.com/windows/servercore:ltsc2022

# $ProgressPreference: https://github.com/PowerShell/PowerShell/issues/2138#issuecomment-251261324
SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop'; $ProgressPreference = 'SilentlyContinue';"]

ENV JAVA_VERSION=jdk-25.0.1+8

RUN Write-Host ('Downloading https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.1%2B8/OpenJDK25U-jdk_x64_windows_hotspot_25.0.1_8.msi ...'); \
    curl.exe -LfsSo openjdk.msi https://github.com/adoptium/temurin25-binaries/releases/download/jdk-25.0.1%2B8/OpenJDK25U-jdk_x64_windows_hotspot_25.0.1_8.msi ; \
    Write-Host ('Verifying sha256 (c49e19ba5b47bf119402b1e0a0a71ce5b19ddd9e4ac3e038ea99fe648bd0b3f9) ...'); \
    if ((Get-FileHash openjdk.msi -Algorithm sha256).Hash -ne 'c49e19ba5b47bf119402b1e0a0a71ce5b19ddd9e4ac3e038ea99fe648bd0b3f9') { \
        Write-Host 'FAILED!'; \
        exit 1; \
    }; \
    \
    New-Item -ItemType Directory -Path C:\temp | Out-Null; \
    \
    Write-Host 'Installing using MSI ...'; \
    $proc = Start-Process -FilePath "msiexec.exe" -ArgumentList '/i', 'openjdk.msi', '/L*V', 'C:\temp\OpenJDK.log', \
    '/quiet', 'ADDLOCAL=FeatureEnvironment,FeatureJarFileRunWith,FeatureJavaHome', 'INSTALLDIR=C:\openjdk-25' -Wait -Passthru; \
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
