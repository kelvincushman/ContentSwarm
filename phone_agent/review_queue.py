"""Durable review handoff. Approval records intent; a worker must verify delivery."""

import json
import sqlite3
import time
import uuid
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
            return [json.loads(row[0]) for row in db.execute("SELECT body FROM reviews ORDER BY rowid DESC")]

    def create(self, data):
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
        item.update(id=uuid.uuid4().hex, revision=1, status="pending", created_at=time.time(), history=[])
        with self.connect() as db:
            db.execute("INSERT INTO reviews VALUES (?, ?)", (item["id"], json.dumps(item)))
        return item

    def update(self, item_id, action, data):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM reviews WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise LookupError("review not found")
            item = json.loads(row[0])
            if type(data.get("revision")) is not int or data["revision"] != item["revision"]:
                raise ValueError("Review changed; refresh before acting")
            before = item["status"]
            if action in ("approve", "reject", "edit"):
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
                else:
                    item["status"] = "approved" if action == "approve" else "rejected"
            elif action == "claim":
                if before != "approved":
                    raise ValueError("Only an approved reply can be claimed once")
                item["status"] = "executing"
            elif action in ("complete", "uncertain"):
                if before != "executing":
                    raise ValueError("Only an executing reply can be completed")
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
        return item
