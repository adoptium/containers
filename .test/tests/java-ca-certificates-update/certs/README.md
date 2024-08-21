These certificate/key pairs has been generated with

``` shell
$ openssl req -nodes -new -x509 -days 358000 -subj "/DC=Temurin/CN=DockerBuilder" -keyout certs/dockerbuilder.key -out certs/dockerbuilder.crt
$ openssl req -nodes -new -x509 -days 358000 -subj "/DC=Temurin/CN=DockerBuilder2" -keyout certs/dockerbuilder2.key -out certs/dockerbuilder2.crt
$ cat certs/dockerbuilder.crt certs/dockerbuilder2.crt > certs/multi-cert.crt
```

 and are only used for testing
