# Preserve source bytes in release archives

The source hashes in the experiment's provenance are byte-sensitive. When archiving a Git subtree, the parent repository's `.gitattributes` is outside that tree. On Windows, `core.autocrlf` can then turn LF into CRLF inside the archive even though the checked-out experiment has LF.

From the repository root, create the bundle with conversion disabled for that command. Replace the version and commit with the intended release:

```sh
git -c core.autocrlf=false archive --format=zip --prefix=wallet-policy-kit-v0.1.1/ -o wallet-policy-kit-v0.1.1.zip HEAD:bitcoin-research/experiments/prepared-checkout
```

Before uploading, compare **every extracted file** with its `git show COMMIT:bitcoin-research/experiments/prepared-checkout/PATH` bytes. A passing test suite alone does not verify provenance. Then run the quickstart from a fresh extraction and record the ZIP's SHA-256 in `SHA256SUMS.txt`.

After uploading, download the public ZIP without authentication, check its checksum and file bytes again, and run the quickstart. Publish corrections under a new version and describe what changed; retain old releases as dated history rather than silently replacing their assets.
