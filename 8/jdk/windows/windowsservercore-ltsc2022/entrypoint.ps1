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
# PowerShell entrypoint for Eclipse Temurin Windows containers.
# Equivalent of entrypoint.sh for Linux — imports system and user-provided CA
# certificates into the JVM truststore when USE_SYSTEM_CA_CERTS is set.

$ErrorActionPreference = 'Stop'

# JDK truststore location
# JDK8 puts its JRE in a subdirectory
$JRE_CACERTS_PATH = "$env:JAVA_HOME\jre\lib\security\cacerts"

# Opt-in is only activated if the environment variable is set
if ($env:USE_SYSTEM_CA_CERTS) {

    $TEMP_DIR = $env:TEMP
    if (-not (Test-Path $TEMP_DIR)) {
        Write-Host "Using additional CA certificates requires a writable TEMP directory. Cannot create truststore."
        exit 1
    }

    # Figure out whether we can write to the JVM truststore. If we can, we'll add the certificates there. If not,
    # we'll use a temporary truststore.
    $cacertsReadOnly = (Get-Item $JRE_CACERTS_PATH).IsReadOnly
    if ($cacertsReadOnly) {
        $JRE_CACERTS_PATH_NEW = Join-Path $TEMP_DIR "cacerts-$(Get-Random)"
        Write-Host "Using a temporary truststore at $JRE_CACERTS_PATH_NEW"
        Copy-Item $JRE_CACERTS_PATH $JRE_CACERTS_PATH_NEW
        $JRE_CACERTS_PATH = $JRE_CACERTS_PATH_NEW
        # If we use a custom truststore, we need to make sure that the JVM uses it
        $env:JAVA_TOOL_OPTIONS = "$env:JAVA_TOOL_OPTIONS -Djavax.net.ssl.trustStore=$JRE_CACERTS_PATH -Djavax.net.ssl.trustStorePassword=changeit"
    }

    # Import certificates from the Windows certificate store (Cert:\LocalMachine\Root) into the JVM truststore.
    # This is the Windows equivalent of `trust extract` on Linux.
    $systemCerts = Get-ChildItem -Path Cert:\LocalMachine\Root
    foreach ($cert in $systemCerts) {
        $alias = $cert.Subject -replace '^CN=', '' -replace ',.*$', ''
        if (-not $alias) { $alias = $cert.Thumbprint }

        # Check if already present by thumbprint
        $existing = & keytool -list -keystore $JRE_CACERTS_PATH -storepass changeit -v 2>$null |
            Select-String -Pattern $cert.Thumbprint -Quiet
        if ($existing) { continue }

        # Export the certificate to a temp file and import it
        $certFile = Join-Path $TEMP_DIR "$($cert.Thumbprint).cer"
        try {
            [System.IO.File]::WriteAllBytes($certFile, $cert.Export([System.Security.Cryptography.X509Certificates.X509ContentType]::Cert))
            & keytool -import -noprompt -alias $alias -file $certFile -keystore $JRE_CACERTS_PATH -storepass changeit 2>$null | Out-Null
        } finally {
            Remove-Item -Path $certFile -Force -ErrorAction SilentlyContinue
        }
    }

    # Import additional certificates mounted at C:\certificates
    $certsDir = "C:\certificates"
    if (Test-Path $certsDir) {
        $certFiles = Get-ChildItem -Path $certsDir -Filter "*.crt" -ErrorAction SilentlyContinue
        foreach ($certFile in $certFiles) {
            # A .crt file may contain multiple PEM certificates — split them
            $content = Get-Content $certFile.FullName -Raw
            $pemBlocks = [regex]::Matches($content, '-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----')

            foreach ($pem in $pemBlocks) {
                $tmpCert = Join-Path $TEMP_DIR "cert-$(Get-Random).crt"
                try {
                    Set-Content -Path $tmpCert -Value $pem.Value -NoNewline

                    # Parse the certificate to get CN and Serial
                    $x509 = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($tmpCert)
                    $cn = ($x509.Subject -replace '^CN=', '' -replace ',.*$', '').Trim()
                    $serial = $x509.SerialNumber
                    $thumbprint = $x509.Thumbprint

                    # Check if already in the JVM truststore by thumbprint
                    $alreadyExists = & keytool -list -keystore $JRE_CACERTS_PATH -storepass changeit -v 2>$null |
                        Select-String -Pattern $thumbprint -Quiet
                    if ($alreadyExists) {
                        Write-Host "Certificate with CN=$cn is already in the JVM truststore, skipping"
                        continue
                    }

                    # Check if alias already exists, append serial if so
                    $alias = if ($cn) { $cn } else { "cert-$serial" }
                    $aliasExists = & keytool -list -keystore $JRE_CACERTS_PATH -storepass changeit -alias $alias 2>$null
                    if ($LASTEXITCODE -eq 0) {
                        $alias = "${cn}_${serial}"
                    }

                    Write-Host "Adding certificate with alias $alias to the JVM truststore"
                    & keytool -import -noprompt -alias $alias -file $tmpCert -keystore $JRE_CACERTS_PATH -storepass changeit 2>$null | Out-Null
                } finally {
                    Remove-Item -Path $tmpCert -Force -ErrorAction SilentlyContinue
                    if ($x509) { $x509.Dispose() }
                }
            }
        }
    }
}

# Expose the cacerts path for tools that need it
$env:JRE_CACERTS_PATH = $JRE_CACERTS_PATH

# Execute the original command
if ($args.Count -gt 0) {
    & $args[0] $args[1..($args.Count-1)]
} else {
    # Default: drop into PowerShell
    powershell
}