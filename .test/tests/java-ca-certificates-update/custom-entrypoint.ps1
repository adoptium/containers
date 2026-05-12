# Custom entrypoint that does NOT import certificates.
# Used to test that overriding the entrypoint skips CA cert injection.
if ($args.Count -gt 0) {
    & $args[0] $args[1..($args.Count-1)]
    exit $LASTEXITCODE
}
