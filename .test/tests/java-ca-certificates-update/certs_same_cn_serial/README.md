These certificates reproduce the scenario where multiple CA certificates share **both the same CN and the
same serial number**. Neither the CN nor the CN+serial combination can disambiguate them, so the import
script appends the SHA-256 fingerprint to the alias (`<CN>_<fingerprint>`). They have been generated with

``` shell
$ openssl req -nodes -new -x509 -days 3650 -set_serial 4096 -subj "/DC=Temurin/CN=IdenticalCA" -keyout /dev/null -out certs_same_cn_serial/cert1.crt
$ openssl req -nodes -new -x509 -days 3650 -set_serial 4096 -subj "/DC=Temurin/CN=IdenticalCA" -keyout /dev/null -out certs_same_cn_serial/cert2.crt
$ openssl req -nodes -new -x509 -days 3650 -set_serial 4096 -subj "/DC=Temurin/CN=IdenticalCA" -keyout /dev/null -out certs_same_cn_serial/cert3.crt
```

Each command uses a fresh keypair, so the three certificates have identical subject and serial but distinct
fingerprints. The private keys are discarded (`-keyout /dev/null`); only the certificates are needed for
testing. The fingerprint based aliases asserted by `CMD5` in `run.sh` are derived from these exact files, so
regenerating the certificates requires updating those alias values.
