#!/usr/bin/env bash

imageTests[openjdk]+='
	java-ca-certificates-update
'

globalExcludeTests+=(
	# nanoserver: PowerShell is not available for CA certificate handling
	[openjdk:nanoserver_java-ca-certificates-update]=1
)
