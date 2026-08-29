# NetBox source-test dependency locks

The Django compatibility matrix checks out immutable NetBox commits and then
installs the matching lock in this directory. Each `.in` file is the exact
`requirements.txt` from the commit named by its matrix row; the adjacent
`.txt` file is a Python 3.12/Linux x86_64 resolution with artifact hashes.
The workflow verifies the checked-out commit, release metadata, and upstream
requirements checksum before enforcing the lock with `--require-hashes` and an
explicit PyPI first-index policy.

Refresh a lock only when its NetBox source commit changes. With the matching
`.in` file copied from that commit, run the repository-pinned uv version:

```shell
uv pip compile ci/netbox-requirements/<tag>-py312-linux-x86_64.in \
  --generate-hashes \
  --python-version 3.12.13 \
  --python-platform x86_64-unknown-linux-gnu \
  --default-index https://pypi.org/simple \
  --index-strategy first-index \
  --output-file ci/netbox-requirements/<tag>-py312-linux-x86_64.txt
```

Review both the upstream input diff and the generated lock diff. The lock is
CI evidence for the source matrix, not a runtime dependency declaration for
the published plugin package.
