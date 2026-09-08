import pytest
from phone_agent.review_queue import ReviewQueue


@pytest.fixture
def queue(tmp_path):
    return ReviewQueue(tmp_path / "reviews.db")


def draft():
    return dict(platform="x", account="@test", phone="primary", source_url="https://x.com/test/status/1",
                author="Reader", original="Does it run locally?", reply="The phone controls run locally.", humanizer_version="3.0.0")


def test_revision_binds_approval_and_claim_is_single_use(queue):
    item = queue.create(draft())
    edited = queue.update(item["id"], "edit", dict(revision=1, reply="Yes, the controls run locally."))
    with pytest.raises(ValueError):
        queue.update(item["id"], "approve", dict(revision=1))
    approved = queue.update(item["id"], "approve", dict(revision=edited["revision"]))
    claim = queue.update(item["id"], "claim", dict(revision=approved["revision"]))
    with pytest.raises(ValueError):
        queue.update(item["id"], "claim", dict(revision=claim["revision"]))
    with pytest.raises(ValueError):
        queue.update(item["id"], "complete", dict(revision=claim["revision"]))
    done = queue.update(item["id"], "complete", dict(revision=claim["revision"], evidence="Visible reply at https://x.com/test/status/2"))
    assert done["status"] == "verified"
    assert ReviewQueue(queue.filename).list()[0] == done


def test_rejection_cannot_be_claimed_and_uncertain_cannot_retry(queue):
    item=queue.create(draft())
    item=queue.update(item["id"],"reject",dict(revision=1))
    with pytest.raises(ValueError): queue.update(item["id"],"claim",dict(revision=item["revision"]))
    item=queue.update(item["id"],"approve",dict(revision=item["revision"]))
    item=queue.update(item["id"],"claim",dict(revision=item["revision"]))
    item=queue.update(item["id"],"uncertain",dict(revision=item["revision"],evidence="Connection lost after tap"))
    with pytest.raises(ValueError): queue.update(item["id"],"claim",dict(revision=item["revision"]))


def test_requires_humanizer_provenance_and_platform_link(queue):
    data=draft();data.pop("humanizer_version")
    with pytest.raises(ValueError):queue.create(data)
    data=draft();data["source_url"]="javascript:alert(1)"
    with pytest.raises(ValueError):queue.create(data)
