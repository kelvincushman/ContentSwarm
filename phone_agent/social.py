"""Account-scoped context and durable draft scheduling. No model or device calls."""

import json
import math
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def text(data, key, limit=8000):
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{key} must contain 1–{limit} characters")
    return value.strip()


def next_time(spec, after):
    """Return the next occurrence strictly after an epoch; skip missed occurrences.

    Calendar times use local wall time. Missing DST times are skipped and folds
    run once at the earlier instant. Monthly dates absent in a month are skipped.
    """
    kind = spec.get("kind")
    if kind == "once":
        value = datetime.fromisoformat(text(spec, "at", 80))
        if value.tzinfo is None:
            raise ValueError("One-off time must include a UTC offset")
        return value.timestamp() if value.timestamp() > after else None
    if kind == "interval":
        minutes = spec.get("minutes")
        if type(minutes) is not int or not 1 <= minutes <= 525600:
            raise ValueError("Interval must be 1–525600 minutes")
        anchor = spec.get("anchor")
        if not isinstance(anchor, (float, int)) or isinstance(anchor, bool) or not math.isfinite(anchor):
            raise ValueError("Interval requires a finite anchor timestamp")
        return anchor + max(0, math.floor((after - anchor) / (minutes * 60)) + 1) * minutes * 60
    if kind not in ("daily", "weekly", "monthly"):
        raise ValueError("Schedule kind must be once, interval, daily, weekly or monthly")
    try:
        zone = ZoneInfo(text(spec, "timezone", 100))
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise ValueError("Unknown timezone") from exc
    clock = text(spec, "time", 5)
    try:
        hour, minute = map(int, clock.split(":"))
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise ValueError()
    except ValueError as exc:
        raise ValueError("Use HH:MM for calendar time") from exc
    weekday, day = spec.get("weekday"), spec.get("day")
    if kind == "weekly" and (type(weekday) is not int or not 0 <= weekday <= 6):
        raise ValueError("weekday is 0 (Monday) through 6 (Sunday)")
    if kind == "monthly" and (type(day) is not int or not 1 <= day <= 31):
        raise ValueError("day must be 1–31")
    start = datetime.fromtimestamp(after, zone).date()
    for offset in range(370):
        date = start + timedelta(days=offset)
        if kind == "weekly" and date.weekday() != weekday:
            continue
        if kind == "monthly" and date.day != day:
            continue
        local = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone)
        stamp = local.timestamp()
        if datetime.fromtimestamp(stamp, zone).replace(tzinfo=None) != local.replace(tzinfo=None):
            continue
        if stamp > after:
            return stamp
    raise ValueError("No occurrence within a year")


class SocialStore:
    def __init__(self, filename):
        self.filename = str(filename)
        Path(filename).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            for table in ("accounts", "schedules", "jobs", "memories"):
                db.execute(f"CREATE TABLE IF NOT EXISTS {table} (id TEXT PRIMARY KEY, body TEXT NOT NULL)")
        Path(filename).chmod(0o600)

    def connect(self):
        return sqlite3.connect(self.filename, timeout=10)

    def list(self, table, db=None):
        if table not in ("accounts", "schedules", "jobs", "memories"):
            raise ValueError("Unknown collection")
        if db is None:
            with self.connect() as conn:
                return self.list(table, conn)
        return [json.loads(row[0]) for row in db.execute(f"SELECT body FROM {table} ORDER BY rowid DESC")]

    def get(self, table, item_id, db=None):
        for item in self.list(table, db):
            if item["id"] == item_id:
                return item
        raise LookupError(f"{table} item not found")

    @staticmethod
    def save(db, table, item):
        db.execute(f"INSERT OR REPLACE INTO {table} VALUES (?, ?)", (item["id"], json.dumps(item)))
        return item

    def account(self, data):
        item = {key: text(data, key) for key in ("name", "platform", "handle", "soul")}
        if item["platform"] not in ("x", "linkedin", "facebook"):
            raise ValueError("Unsupported platform")
        phones = data.get("phones", [])
        if not isinstance(phones, list) or len(phones) > 20 or any(not isinstance(p, str) or not p or len(p) > 200 for p in phones):
            raise ValueError("phones must be a list of up to 20 device names")
        item["phones"] = list(dict.fromkeys(phones))
        indicator = data.get("delivery_indicator")
        if indicator:
            if not isinstance(indicator, dict):
                raise ValueError("delivery_indicator must contain id and text")
            resource = text(indicator, "id", 300)
            if ":id/" not in resource:
                raise ValueError("Use the full resource id of the composer's account indicator")
            item["delivery_indicator"] = dict(id=resource, text=text(indicator, "text", 300))
            if indicator.get("posted_id"):
                posted = text(indicator, "posted_id", 300)
                if ":id/" not in posted or posted == resource:
                    raise ValueError("Use a separate full resource id for published post content")
                item["delivery_indicator"]["posted_id"] = posted
            if indicator.get("compose_id"):
                entry = text(indicator, "compose_id", 300)
                if ":id/" not in entry or entry == resource:
                    raise ValueError("Use the full resource id of the separate composer-entry button")
                item["delivery_indicator"]["compose_id"] = entry
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            old = self.get("accounts", data["id"], db) if data.get("id") else None
            if old and "delivery_indicator" not in data and old.get("delivery_indicator"):
                item["delivery_indicator"] = old["delivery_indicator"]
            if old and data.get("revision") != old["revision"]:
                raise ValueError("Account changed; refresh first")
            # Keep identity stable so existing approvals never change account meaning.
            if old and any(old[k] != item[k] for k in ("platform", "handle")):
                raise ValueError("Create a separate profile to change platform or handle")
            if not old and any(a["platform"] == item["platform"] and a["handle"].casefold() == item["handle"].casefold() for a in self.list("accounts", db)):
                raise ValueError("That account already has a profile")
            item.update(id=old["id"] if old else uuid.uuid4().hex, revision=old["revision"] + 1 if old else 1)
            return self.save(db, "accounts", item)

    def remember(self, account_id, data, trusted=False):
        self.get("accounts", account_id)
        item = {key: text(data, key) for key in ("text", "source")}
        item.update(id=uuid.uuid4().hex, account_id=account_id, trusted=trusted,
                    thread=str(data.get("thread", ""))[:500], at=time.time())
        with self.connect() as db:
            return self.save(db, "memories", item)

    def context(self, account_id, query="", thread=""):
        account = self.get("accounts", account_id)
        words = str(query).casefold().split()[:20]
        memories = [m for m in self.list("memories") if m["account_id"] == account_id]
        memories.sort(key=lambda m: (bool(thread and m["thread"] == thread), sum(w in m["text"].casefold() for w in words), m["at"]), reverse=True)
        selected, remaining = [], 16000
        for m in memories[:30]:
            if len(m["text"]) > remaining:
                continue
            selected.append(m)
            remaining -= len(m["text"])
        return dict(account=account, memories=selected, truncated=len(selected) < len(memories))

    def schedule(self, data, now=None):
        now = time.time() if now is None else now
        account_id = text(data, "account_id", 64)
        prompt = text(data, "prompt")
        spec = data.get("spec")
        if not isinstance(spec, dict):
            raise ValueError("spec must be an object")
        spec = dict(spec)
        if spec.get("kind") == "interval":
            spec.setdefault("anchor", now + spec.get("minutes", 0) * 60 if type(spec.get("minutes")) is int else now)
        due = next_time(spec, now)
        if due is None:
            raise ValueError("Choose a future date")
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self.get("accounts", account_id, db)
            old = self.get("schedules", data["id"], db) if data.get("id") else None
            if old and data.get("revision") != old["revision"]:
                raise ValueError("Schedule changed; refresh first")
            item = dict(id=old["id"] if old else uuid.uuid4().hex, revision=old["revision"] + 1 if old else 1,
                        account_id=account_id, prompt=prompt, spec=spec, next_at=due, enabled=True)
            # Editing cancels only work which has not started.
            if old:
                for job in self.list("jobs", db):
                    if job.get("schedule_id") == old["id"] and job["status"] == "queued":
                        job["status"] = "cancelled"
                        self.save(db, "jobs", job)
            return self.save(db, "schedules", item)

    def pause(self, item_id, revision):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self.get("schedules", item_id, db)
            if revision != item["revision"]:
                raise ValueError("Schedule changed; refresh first")
            item.update(enabled=False, revision=revision + 1)
            for job in self.list("jobs", db):
                if job.get("schedule_id") == item_id and job["status"] == "queued":
                    job["status"] = "cancelled"
                    self.save(db, "jobs", job)
            return self.save(db, "schedules", item)

    def enqueue(self, account_id, prompt):
        with self.connect() as db:
            self.get("accounts", account_id, db)
            return self._job(db, account_id, text({"prompt": prompt}, "prompt"))

    def _job(self, db, account_id, prompt, schedule_id=None):
        return self.save(db, "jobs", dict(id=uuid.uuid4().hex, account_id=account_id, prompt=prompt,
                         schedule_id=schedule_id, status="queued", at=time.time()))

    def tick(self, now=None):
        now = time.time() if now is None else now
        created = []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item in self.list("schedules", db):
                if not item["enabled"] or item["next_at"] > now:
                    continue
                # Coalesce backlog: never generate a burst after suspend or an outage.
                busy = any(j.get("schedule_id") == item["id"] and j["status"] in ("queued", "running") for j in self.list("jobs", db))
                if not busy:
                    created.append(self._job(db, item["account_id"], item["prompt"], item["id"]))
                item["next_at"] = next_time(item["spec"], now)
                item["enabled"] = item["next_at"] is not None
                self.save(db, "schedules", item)
        return created

    def claim(self):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for item in reversed(self.list("jobs", db)):
                if item["status"] == "queued":
                    item.update(status="running", started_at=time.time())
                    return self.save(db, "jobs", item)
        return None

    def finish(self, item_id, result=None, error=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            item = self.get("jobs", item_id, db)
            if item["status"] != "running":
                raise ValueError("Job is not running")
            item.update(status="failed" if error else "drafted", result=result, error=error, finished_at=time.time())
            return self.save(db, "jobs", item)
