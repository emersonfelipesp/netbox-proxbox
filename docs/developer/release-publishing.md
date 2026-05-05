# Release Publishing

This page documents the staged package-release workflow for `netbox-proxbox` and
its companion `proxbox-api` backend. The workflow deliberately separates package
index validation from final publication so failed published artifacts are never
reused.

## Release State Machine

```mermaid
flowchart TD
    Start([Choose target release\nX.Y.Z])
    Bump[Bump package version\npyproject.toml + netbox_proxbox/__init__.py + uv.lock]
    TagTest[Create tag vX.Y.Z\nor vX.Y.Z.postN]
    TestCI[CI builds dist\nvalidates tag/version/lockfile]
    TestUpload[Upload to TestPyPI\nwithout --skip-existing]
    TestValidate[Install netbox-proxbox from TestPyPI\nrun package checks]
    TestE2E[E2E Docker\nnetbox-proxbox from TestPyPI\nproxbox-api from TestPyPI]
    TestFailed{Any TestPyPI\nvalidation failed?}
    RCBump[Bump to next vX.Y.Z.postN\nfor code or packaging fixes]
    RCTag[Create PyPI candidate tag\nvX.Y.ZrcN]
    RCValidate[Run PyPI candidate checks\nlocal package + E2E against PyPI proxbox-api]
    RCUpload[Upload vX.Y.ZrcN to PyPI]
    RCInstall[Install rcN from PyPI\nrun post-upload checks]
    RCFailed{RC failed?}
    NextRC[Bump to vX.Y.ZrcN+1]
    FinalTag[Create or dispatch final tag\nvX.Y.Z]
    FinalUpload[Upload vX.Y.Z to PyPI]
    FinalValidate[Install final from PyPI\nrun post-upload E2E]
    FinalFailed{Post-release fix needed?}
    Post[Bump to vX.Y.Z.postN\nrepeat TestPyPI then PyPI]
    Done([Release is green])

    Start --> Bump --> TagTest --> TestCI --> TestUpload --> TestValidate --> TestE2E --> TestFailed
    TestFailed -- yes --> RCBump --> TagTest
    TestFailed -- no --> RCTag --> RCValidate --> RCUpload --> RCInstall --> RCFailed
    RCFailed -- yes --> NextRC --> RCTag
    RCFailed -- no --> FinalTag --> FinalUpload --> FinalValidate --> FinalFailed
    FinalFailed -- yes --> Post --> TagTest
    FinalFailed -- no --> Done
```

## Cross-Package E2E Contract

The plugin does not import `proxbox-api` as a Python dependency. It consumes the
backend as a runtime HTTP service, so release coupling is validated in Docker
E2E rather than package metadata.

```mermaid
sequenceDiagram
    participant Tag as Release Tag
    participant WF as netbox-proxbox publish workflow
    participant TP as TestPyPI
    participant PY as PyPI
    participant E2E as e2e-docker.yml
    participant NB as NetBox container
    participant API as proxbox-api container

    Tag->>WF: vX.Y.Z or vX.Y.Z.postN
    WF->>TP: Upload netbox-proxbox package
    WF->>E2E: install_source=testpypi, dependency_mode=testpypi-package
    E2E->>NB: pip install netbox-proxbox==X.Y.Z from TestPyPI
    E2E->>API: pip install proxbox-api==configured version from TestPyPI
    E2E-->>WF: Full stack sync checks pass

    Tag->>WF: vX.Y.ZrcN or publish_target=pypi
    WF->>PY: Upload netbox-proxbox package
    WF->>E2E: install_source=pypi, dependency_mode=pypi-package
    E2E->>NB: pip install netbox-proxbox==X.Y.ZrcN or X.Y.Z from PyPI
    E2E->>API: pip install proxbox-api==configured version from PyPI
    E2E-->>WF: Post-publish checks pass
```

## Workflow Rules

- `pyproject.toml`, `netbox_proxbox/__init__.py`, `uv.lock`, and the Git tag
  must all describe the same version.
- Normal and `.postN` tag pushes publish to TestPyPI.
- `rcN` tag pushes, GitHub releases, or manual dispatch with
  `publish_target=pypi` publish to PyPI.
- Package uploads intentionally omit `twine --skip-existing`; a consumed version
  must move forward to the next `.postN` or `rcN`.
- `proxbox_api_version` can be supplied manually. If omitted, the workflow reads
  repository variables in this order:
  `PROXBOX_API_TESTPYPI_VERSION` / `PROXBOX_API_PYPI_VERSION`,
  `PROXBOX_API_RELEASE_VERSION`, then the checked-in default.

## Operator Checklist

1. Publish and validate `proxbox-api` on TestPyPI first.
2. Publish and validate `netbox-proxbox` on TestPyPI using that TestPyPI
   `proxbox-api` version.
3. Promote `proxbox-api` through PyPI release candidates and final PyPI release.
4. Promote `netbox-proxbox` through PyPI release candidates and final PyPI
   release using the matching PyPI `proxbox-api` version.
5. If any published validation fails, bump to the next `.postN` or `rcN`; never
   retry the same artifact version.
