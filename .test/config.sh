#!/usr/bin/env bash

imageTests[openjdk]+='
	java-ca-certificates-update
'

globalExcludeTests+=(
	# nanoservcer/windowsservercore: updating local store with additional certificates is not implemented
	[openjdk:nanoserver_java-ca-certificates-update]=1
	[openjdk:windowsservercore_java-ca-certificates-update]=1
)
