# NetBox source-test dependency locks

The Django compatibility matrix checks out immutable NetBox commits and then
installs the matching lock in this directory. Each `.in` file starts from the
`requirements.txt` in the commit named by its matrix row and applies the
minimum reviewed security overrides needed for that supported lane. The
row `.txt` file is a Python 3.12/Linux x86_64 resolution with artifact hashes.
Every row also resolves `netbox-proxbox-test-py312.in`, which mirrors the
plugin runtime and test metadata. The PDM row additionally resolves the pinned
companion metadata in `netbox-pdm-3408441672bf-py312.in` and uses its distinct
composed lock.

The workflow independently verifies the checked-out commit, release metadata,
upstream `requirements.txt` checksum, reviewed `.in` checksum, and generated
lock checksum before enforcing the lock with `--require-hashes` and an explicit
PyPI first-index policy. The workflow then installs the checksum-bound local
source trees with `--no-build-isolation --no-deps` and runs `uv pip check`.
Their build backends are included in the composed lock, so dependency resolution
therefore occurs only in the reviewed composed lock, while final package
metadata consistency is mandatory. This separation preserves source
provenance without keeping known-vulnerable versions in an installable
requirements manifest.

The NetBox 4.7 OpenBao assignment cell additionally resolves
`netbox-openbao-58677ef-py312.in`, checks out the exact netbox-openbao and
netbox-rpc commits named there, verifies both source identities and pyproject
digests, and installs them with `--no-deps`. Its distinct lock is
`v4.7.0-openbao-58677ef-py312-linux-x86_64.txt`.

The security-floor regression test currently enforces these minimum versions
in every affected matrix input and lock:

| Package | Minimum safe version |
| --- | --- |
| Django | `5.2.17` on NetBox 4.5; `6.0.8` on NetBox 4.6 |
| djangorestframework | `3.17.2` |
| mkdocs-material | `9.7.7` |
| Pillow | `12.3.0` |
| PyJWT | `2.13.0` |
| strawberry-graphql | `0.315.7` |
| tablib | `3.10.0` |

The PyJWT floor also requires a coherent authentication dependency chain in
the affected inputs: `social-auth-core==5.1.0`,
`social-auth-app-django==6.0.1`, and `requests==2.34.2` where required.
Regression tests require every direct `.in` declaration—not only the packages
with a published security floor—to exist in the adjacent lock and accept its
stable exact version. Direct URLs and environment markers are forbidden in
these fixed Python 3.12/Linux x86_64 inputs so every declaration is resolved
through the reviewed first-index policy and applies to the tested lane. Every
non-comment top-level install line in each generated `.txt` lock must be an
exact `name==version` index pin. Direct URLs, VCS or local-path installs, and
index or find-links directives are rejected so the generated lock cannot
silently bypass that provenance policy.

Refresh a lock when its NetBox source commit changes or a security floor is
raised. Start by copying the matching upstream `requirements.txt` into the
`.in` file, reapply every floor enforced by
`tests/test_dependency_security_floors.py`, then run the repository-pinned uv
version:

```shell
uv pip compile ci/netbox-requirements/<tag>-py312-linux-x86_64.in \
  ci/netbox-requirements/netbox-proxbox-test-py312.in \
  --generate-hashes \
  --python-version 3.12.13 \
  --python-platform x86_64-unknown-linux-gnu \
  --default-index https://pypi.org/simple \
  --index-strategy first-index \
  --output-file ci/netbox-requirements/<tag>-py312-linux-x86_64.txt
```

For the PDM row, add
`ci/netbox-requirements/netbox-pdm-3408441672bf-py312.in` and write the
distinct `v4.6.6-pdm-3408441672bf-py312-linux-x86_64.txt` output. Runtime,
test, and build-system requirements belong in the reviewed inputs. When project
or companion metadata changes, update its reviewed input and checksum before
regenerating; never let the editable install perform a second, unhashed
resolution.

Review the upstream-to-input overrides, the generated lock diff, and every
transitive change required to make the safe resolution coherent. Update the
input and lock checksums in `.github/workflows/django-tests.yml` and
`tests/test_version.py` together. The lock is CI evidence for the source
matrix, not a runtime dependency declaration for the published plugin package.
