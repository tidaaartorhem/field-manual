#!/usr/bin/env python3
"""Fetch the newsletter subscriber list from Firestore.

Used by the scheduled email job: ``.venv/bin/python -m services.subscribers``
prints one ``name <email>`` per line (emails only with ``--emails``).

Auth: reuses the firebase CLI's stored OAuth tokens
(~/.config/configstore/firebase-tools.json), refreshing the access token
when expired. Tokens are never printed or logged.
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROJECT = "portfolio-3da31"
COLLECTION = "subscribers"

FIREBASE_CLIENT_ID = "32555940559.apps.googleusercontent.com"
FIREBASE_CLIENT_SECRET = "ZmBozySss5kCrKC9tr1iR0FViQ"
CONFIGSTORE = Path.home() / ".config" / "configstore" / "firebase-tools.json"


def _load_tokens():
    try:
        return json.loads(CONFIGSTORE.read_text())["tokens"]
    except (OSError, KeyError, ValueError) as exc:
        raise RuntimeError(f"cannot read firebase CLI tokens: {exc}")


def access_token():
    """Valid OAuth access token for Google APIs. Never logs the value."""
    toks = _load_tokens()
    if toks.get("access_token") and time.time() < toks.get("expires_at", 0) / 1000 - 60:
        return toks["access_token"]
    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": toks["refresh_token"],
        "client_id": FIREBASE_CLIENT_ID,
        "client_secret": FIREBASE_CLIENT_SECRET,
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    try:
        resp = json.load(urllib.request.urlopen(req, timeout=30))
    except Exception as exc:
        raise RuntimeError(f"token refresh failed: {type(exc).__name__}")
    return resp["access_token"]


def _doc_to_subscriber(doc):
    fields = doc.get("fields", {})
    def s(key):
        return (fields.get(key, {}).get("stringValue") or "").strip()
    return {"name": s("name"), "email": s("email")}


def list_subscribers(project=PROJECT):
    """Return [{name, email}] for every document in the subscribers collection."""
    token = access_token()
    url = (f"https://firestore.googleapis.com/v1/projects/{project}"
           f"/databases/(default)/documents/{COLLECTION}?pageSize=1000")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        payload = json.load(urllib.request.urlopen(req, timeout=30))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return []  # collection doesn't exist yet
        raise RuntimeError(f"firestore list failed: HTTP {exc.code}")
    subs = []
    for doc in payload.get("documents", []):
        sub = _doc_to_subscriber(doc)
        if sub["email"] and "@" in sub["email"]:
            subs.append(sub)
    return subs


def main(argv=None):
    emails_only = "--emails" in (argv or [])
    try:
        subs = list_subscribers()
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for sub in subs:
        print(sub["email"] if emails_only else f"{sub['name']} <{sub['email']}>")
    print(f"# {len(subs)} subscriber(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
