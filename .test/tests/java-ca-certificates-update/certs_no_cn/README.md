These certificates reproduce the scenario where multiple CA certificates have **no CN** and share a
non-unique serial number (`00`). The alias cannot be derived from CN+serial, so the import script falls
back to a SHA-256 fingerprint based alias (`adoptium_<fingerprint>`). They have been generated with

``` shell
$ openssl req -nodes -new -x509 -days 3650 -set_serial 0 -subj "/C=US/O=Acme No CN Authority/OU=Acme No CN Authority Root CA" -keyout /dev/null -out certs_no_cn/ca_a.crt
$ openssl req -nodes -new -x509 -days 3650 -set_serial 0 -subj "/C=US/O=Globex No CN Authority/OU=Globex No CN Authority Root CA" -keyout /dev/null -out certs_no_cn/ca_b.crt
$ openssl req -nodes -new -x509 -days 3650 -set_serial 0 -subj "/C=US/O=Initech No CN Authority/OU=Initech No CN Authority Root CA" -keyout /dev/null -out certs_no_cn/ca_c.crt
```

The private keys are discarded (`-keyout /dev/null`); only the certificates are needed for testing.
The fingerprint based aliases asserted by `CMD4` in `run.sh` are derived from these exact files, so
regenerating the certificates requires updating those alias values.
