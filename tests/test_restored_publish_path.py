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
PROMOTION_WORKFLOW = REPO_ROOT / ".gitea/workflows/promote-final-tag.yml"

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


def test_manual_release_tags_are_validated_before_anything_is_published() -> None:
    jobs = _workflow()["jobs"]
    assert "validate-version" in jobs
    triggers = _workflow().get("on", _workflow().get(True))
    assert set(triggers) == {"workflow_dispatch"}
    assert (
        "github.repository == 'emersonfelipesp/netbox-proxbox'"
        in jobs["validate-version"]["if"]
    )
    assert "github.ref == 'refs/heads/main'" in jobs["validate-version"]["if"]
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


def test_publish_workflow_reserves_only_rc_tags() -> None:
    """The package publisher must not make a final release public.

    A GitHub Release fires the `release: published` event, which is the sole
    trigger for the public PyPI upload. Creating one for a release candidate
    would publish an rc to PyPI as though it were final.
    """
    workflow = _workflow()
    publish = workflow["jobs"]["publish-gitea"]
    reserve = next(
        step
        for step in publish["steps"]
        if step.get("name") == "Reserve and verify RC promotion"
    )
    assert reserve["if"] == "env.IS_RC == 'true'"
    assert "git -C candidate push github" in reserve["run"]
    assert "push-to-github" not in workflow["jobs"]
    assert "gh release create" not in WORKFLOW.read_text(encoding="utf-8")


def test_final_tags_use_the_production_evidence_promotion_path() -> None:
    """Final tags remain private until the production evidence gate passes."""
    text = PROMOTION_WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/release_artifacts.py fetch-gitea" in text
    assert "scripts/release_artifacts.py fetch-attestation" in text
    assert "refs/remotes/gitea/release-main" in text
    assert "refs/remotes/gitea/release-develop" in text
    assert "https://github.com/emersonfelipesp/netbox-proxbox.git" in text
    assert text.index("fetch-attestation") < text.index("git push github")
    assert '"refs/tags/${TAG}"' in text
    assert '"refs/tags/${TAG}^{}"' in text
    assert 'test "$REMOTE_TAG_OBJECT" = "$LOCAL_TAG_OBJECT"' in text
    assert 'test "$REMOTE_SOURCE_SHA" = "$SOURCE_SHA"' in text
    assert "github.repository == 'emersonfelipesp/netbox-proxbox'" in text
    assert "ref: ${{ github.sha }}" in text
    assert 'test "$(git rev-parse HEAD^{commit})" = "${GITHUB_SHA}"' in text
    assert "gh release create" not in text
