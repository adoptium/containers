#!/usr/bin/env bash

# shellcheck disable=SC2154
imageTests[openjdk]+='
	java-ca-certificates-update
'

globalExcludeTests+=(
	# nanoserver/windowsservercore: updating local store with additional certificates is not implemented
	[openjdk:nanoserver_java-ca-certificates-update]=1
	[openjdk:windowsservercore_java-ca-certificates-update]=1
)
