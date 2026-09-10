"""Durable review handoff. Approval records intent; a worker must verify delivery."""

import json
import sqlite3
import time
import uuid
import secrets
import hashlib
import hmac
from pathlib import Path


class ReviewQueue:
    def __init__(self, filename):
        self.filename = str(filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS reviews (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        Path(filename).chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.filename, timeout=10)

    def list(self):
        with self.connect() as db:
            return [self.public(json.loads(row[0])) for row in db.execute("SELECT body FROM reviews ORDER BY rowid DESC")]

    @staticmethod
    def public(item):
        return {k: v for k, v in item.items() if k != "lease_hash"}

    def check_lease(self, review_id, token):
        with self.connect() as db:
            row = db.execute("SELECT body FROM reviews WHERE id=?", (review_id,)).fetchone()
        item = json.loads(row[0]) if row else {}
        if item.get("status") != "executing" or not hmac.compare_digest(item.get("lease_hash", "!"), hashlib.sha256(str(token or "").encode()).hexdigest()):
            raise RuntimeError("Invalid delivery lease")

    def authorize_phone(self, phone, review_id=None, token=None):
        items = self.list()
        if review_id:
            self.check_lease(review_id, token)
            assigned = next((item for item in items if item["id"] == review_id), None)
            if not assigned or assigned["phone"] != phone or assigned["status"] != "executing":
                raise RuntimeError("Delivery session cannot control this phone")
        for item in items:
            if item["phone"] == phone and item["status"] == "executing" and item["id"] != review_id:
                raise RuntimeError("Phone is busy with an approved delivery; inspect its result before other work")

    def create(self, data):
        data = dict(data)
        kind = data.get("kind", "reply")
        if kind not in ("reply", "post"):
            raise ValueError("kind must be reply or post")
        if kind == "post":
            data.setdefault("author", "New post")
            data.setdefault("original", "Original post for owner review")
        required = ("platform", "account", "phone", "source_url", "author", "original", "reply", "humanizer_version")
        for key in required:
            if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > 8000:
                raise ValueError(f"{key} must be non-empty text up to 8000 characters")
        if data["platform"] not in ("x", "linkedin", "facebook"):
            raise ValueError("platform must be x, linkedin, or facebook")
        from urllib.parse import urlparse
        hosts = {"x": {"x.com", "www.x.com", "twitter.com"}, "linkedin": {"linkedin.com", "www.linkedin.com"}, "facebook": {"facebook.com", "www.facebook.com", "m.facebook.com"}}
        url = urlparse(data["source_url"])
        if url.scheme != "https" or url.hostname not in hosts[data["platform"]] or url.username:
            raise ValueError("source_url must be an HTTPS link on the selected platform")
        item = {key: data[key] for key in required}
        item["kind"] = kind
        if data.get("account_id"):
            item["account_id"] = data["account_id"]
        item.update(id=uuid.uuid4().hex, revision=1, status="pending", created_at=time.time(), history=[])
        with self.connect() as db:
            db.execute("INSERT INTO reviews VALUES (?, ?)", (item["id"], json.dumps(item)))
        return item

    def update(self, item_id, action, data):
        lease_token = None
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM reviews WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise LookupError("review not found")
            item = json.loads(row[0])
            if type(data.get("revision")) is not int or data["revision"] != item["revision"]:
                raise ValueError("Review changed; refresh before acting")
            before = item["status"]
            if action == "schedule":
                from datetime import datetime
                if before not in ("pending", "rejected", "approved"):
                    raise ValueError("Only an unstarted draft can be scheduled")
                try:
                    when = datetime.fromisoformat(data.get("at", ""))
                    if when.tzinfo is None or when.timestamp() <= time.time():
                        raise ValueError()
                except (ValueError, TypeError) as exc:
                    raise ValueError("Choose a future time including its UTC offset") from exc
                item["publish_at"] = when.timestamp()
            elif action == "cancel":
                if before not in ("pending", "rejected", "approved"):
                    raise ValueError("Cannot cancel delivery after it has started")
                item["status"] = "cancelled"
            elif action in ("approve", "reject", "edit"):
                if action == "edit" and before == "approved":
                    before = "pending"
                if before not in ("pending", "rejected"):
                    raise ValueError("Only pending or rejected drafts can be reviewed")
                if action == "edit":
                    reply = data.get("reply")
                    if not isinstance(reply, str) or not reply.strip() or len(reply) > 8000:
                        raise ValueError("reply must be non-empty text up to 8000 characters")
                    item["history"].append({"reply": item["reply"], "at": time.time()})
                    item["reply"] = reply
                    item["edited_by_user"] = True
                    item["status"] = "pending"
                    item.pop("publish_at", None)
                else:
                    item["status"] = "approved" if action == "approve" else "rejected"
            elif action == "claim":
                if before != "approved":
                    raise ValueError("Only an approved reply can be claimed once")
                if item.get("publish_at", 0) > time.time():
                    raise ValueError("Scheduled publish time has not arrived")
                for record in db.execute("SELECT body FROM reviews"):
                    other = json.loads(record[0])
                    if other["phone"] == item["phone"] and other["status"] == "executing":
                        raise ValueError("Phone is busy with another delivery")
                item["status"] = "executing"
                lease_token = secrets.token_urlsafe(32)
                item["lease_hash"] = hashlib.sha256(lease_token.encode()).hexdigest()
            elif action in ("complete", "uncertain", "recover"):
                if before != "executing":
                    raise ValueError("Only an executing reply can be completed")
                if action != "recover" and not hmac.compare_digest(item.get("lease_hash", "!"), hashlib.sha256(str(data.get("lease_token", "")).encode()).hexdigest()):
                    raise ValueError("Invalid delivery lease")
                evidence = data.get("evidence")
                if not isinstance(evidence, str) or not evidence.strip() or len(evidence) > 8000:
                    raise ValueError("Verification evidence is required")
                item["evidence"] = evidence
                item["status"] = "verified" if action == "complete" else "uncertain"
            else:
                raise ValueError("Unknown review action")
            item["revision"] += 1
            item["updated_at"] = time.time()
            db.execute("UPDATE reviews SET body=? WHERE id=?", (json.dumps(item), item_id))
        result = self.public(item)
        if lease_token:
            result["lease_token"] = lease_token
        return result
