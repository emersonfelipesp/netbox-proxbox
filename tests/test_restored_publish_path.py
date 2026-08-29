"""Guards for the restored in-repository publish path.

The locked control plane is deferred until the isolated runner fleet exists, so
the properties these tests assert are the ones that actually hold for the
workflow that ships. They are deliberately about *reachability and destination*
— the two ways this workflow could silently do the wrong thing:

* pin a job to a runner label nobody advertises, which fails closed and looks
  like a hung release; and
* push a tag or publish a release to a repository that is not the single
  authorised destination.
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = REPO_ROOT / ".gitea/workflows/publish-gitea.yml"

# Labels advertised by runners that exist today. A job pinned outside this set
# cannot be scheduled, which is exactly the failure that blocked this release.
AVAILABLE_LABELS = {
    # Quality lane, 10.0.30.241
    "ubuntu-latest",
    "ci-untrusted-python312",
    # Deployment lane. "package-publish" is served by
    # ci-publish-nmulticloud-org-246 on 10.0.30.246; "mirror-host" and
    # "prod-deploy" are still on their legacy hosts pending that migration.
    "package-publish",
    "mirror-host",
    "prod-deploy",
}


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_every_job_targets_a_runner_label_that_exists() -> None:
    jobs = _workflow()["jobs"]
    assert jobs, "publish workflow defines no jobs"
    unschedulable = {
        name: spec.get("runs-on")
        for name, spec in jobs.items()
        if spec.get("runs-on") not in AVAILABLE_LABELS
    }
    assert not unschedulable, (
        f"jobs pinned to labels no runner advertises: {unschedulable}. "
        "Such a job queues forever instead of failing, and the tag is consumed "
        "for nothing."
    )


def test_workflow_publishes_to_the_gitea_package_registry() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "https://git.nmulti.cloud/api/packages/emersonfelipesp/pypi" in text
    assert "twine upload" in text


def test_release_tags_are_validated_before_anything_is_published() -> None:
    jobs = _workflow()["jobs"]
    assert "validate-version" in jobs
    # publish must depend on validation, not merely run after it by luck
    assert "validate-version" in jobs["publish-gitea"]["needs"]


def test_github_push_targets_only_the_authorised_destination() -> None:
    """The EdgeUno fork is read-only context and must never be a destination."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "github.com/emersonfelipesp/" in text
    assert "edgeuno" not in text.lower(), (
        "the publish workflow references EdgeUno; it is a read-only reference "
        "fork and is never a push, tag, release, or mirror destination"
    )


def test_github_release_is_created_only_for_non_rc_tags() -> None:
    """An rc must not produce a public GitHub Release.

    A GitHub Release fires the `release: published` event, which is the sole
    trigger for the public PyPI upload. Creating one for a release candidate
    would publish an rc to PyPI as though it were final.
    """
    steps = _workflow()["jobs"]["push-to-github"]["steps"]
    release_steps = [s for s in steps if "Release" in str(s.get("name", ""))]
    assert release_steps, "no GitHub Release step found"
    for step in release_steps:
        assert step.get("if") == "env.IS_RC == 'false'", (
            f"release step {step.get('name')!r} is not gated on a non-rc tag"
        )


def test_release_notes_file_is_preferred_over_generated_notes() -> None:
    """The curated notes are what describe features and fixes to users."""
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "docs/release-notes/version-${VERSION}.md" in text
    assert "--notes-file" in text
