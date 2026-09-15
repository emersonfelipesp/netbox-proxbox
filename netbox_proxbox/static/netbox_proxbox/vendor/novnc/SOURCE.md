# noVNC vendoring record

This directory contains the minimal browser runtime from noVNC 1.7.0. The
upstream release tag is `v1.7.0` in `https://github.com/novnc/noVNC`. The exact
npm archive is:

```text
https://registry.npmjs.org/@novnc/novnc/-/novnc-1.7.0.tgz
```

The archive is pinned by this npm Subresource Integrity value from the published
`@novnc/novnc@1.7.0` package metadata:

```text
sha512-ucEJOx4T2avIRCleodk7YobZj5O2Ga2AeLfQ69A/yjG9HHba2+PDgwSkN3FttrmG+70ZGx21sElNFouK13RzyA==
```

Its equivalent hexadecimal SHA-512 digest is:

```text
b9c1093b1e13d9abc844295ea1d93b6286d98f93b619ad8078b7d0ebd03fca31bd1c76dadbe3c38304a437716db6b986fbbd191b1db5b0494d168b8ad77473c8
```

## Reconstruct the vendored runtime

Use a new temporary directory and verify the archive before copying anything:

```bash
vendor_scratch="$(mktemp -d)"
curl --fail --location --proto '=https' --tlsv1.2 \
  --output "${vendor_scratch}/novnc-1.7.0.tgz" \
  'https://registry.npmjs.org/@novnc/novnc/-/novnc-1.7.0.tgz'
sha512sum "${vendor_scratch}/novnc-1.7.0.tgz"
```

Compare the printed digest with the hexadecimal value above. After it matches,
extract the archive and copy these paths without rewriting their contents:

```bash
mkdir "${vendor_scratch}/archive"
tar --extract --gzip \
  --file "${vendor_scratch}/novnc-1.7.0.tgz" \
  --directory "${vendor_scratch}/archive"
cp -a "${vendor_scratch}/archive/package/core" ./core
cp -a "${vendor_scratch}/archive/package/LICENSE.txt" ./LICENSE.txt
mkdir -p ./vendor/pako/lib
cp -a "${vendor_scratch}/archive/package/vendor/pako/LICENSE" ./vendor/pako/LICENSE
cp -a "${vendor_scratch}/archive/package/vendor/pako/lib/utils" ./vendor/pako/lib/utils
cp -a "${vendor_scratch}/archive/package/vendor/pako/lib/zlib" ./vendor/pako/lib/zlib
```

The pako library is a transitive runtime requirement of `core/inflator.js` and
`core/deflator.js`. Its license is retained at `vendor/pako/LICENSE`. Package
README files, examples, application UI, tests, and development tools are not
part of the browser runtime copied here.

`RUNTIME_FILES.txt` is the package manifest for the copied runtime.
`tests/test_vm_console_frontend.py` pins that complete inventory, its aggregate
SHA-256 digest, and every runtime file's presence in the Git index. Both package
CI workflows run `scripts/verify_vm_console_artifacts.py` immediately after the
build; the verifier opens the wheel and sdist and requires the complete runtime
plus this provenance record and its manifest in both artifacts.
