#!/usr/bin/env python3
"""Import the upstream opencode dev tree via jsDelivr and verify every blob."""

import base64
import concurrent.futures
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
import urllib.request

ROOT = os.path.abspath(os.path.dirname(__file__))
TREE_JSON = "/tmp/opencode-tree.json"
OWNER = "anomalyco"
REPO = "opencode"
BRANCH = "dev"
PROXY = "http://127.0.0.1:7897"
UA = {"User-Agent": "jkinco-upstream-import/0.1"}


def proxy_opener():
    handler = urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    return urllib.request.build_opener(handler)


def jsdelivr_fetch(path, timeout=90):
    url = "https://cdn.jsdelivr.net/gh/%s/%s@%s/%s" % (
        OWNER, REPO, BRANCH, urllib.parse.quote(path))
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def raw_fetch(path, timeout=180):
    url = "https://raw.githubusercontent.com/%s/%s/%s/%s" % (
        OWNER, REPO, BRANCH, path)
    req = urllib.request.Request(url, headers=UA)
    with proxy_opener().open(req, timeout=timeout) as resp:
        return resp.read()


def api_blob_fetch(sha, timeout=120):
    url = "https://api.github.com/repos/%s/%s/git/blobs/%s" % (OWNER, REPO, sha)
    req = urllib.request.Request(url, headers=UA)
    with proxy_opener().open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    raise RuntimeError("unexpected blob response for %s" % sha)


def api_contents_fetch(path, timeout=180):
    url = "https://api.github.com/repos/%s/%s/contents/%s?ref=%s" % (
        OWNER, REPO, urllib.parse.quote(path, safe="/"), BRANCH)
    req = urllib.request.Request(url, headers=UA)
    with proxy_opener().open(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode())
    if data.get("encoding") == "base64":
        return base64.b64decode(data["content"])
    raise RuntimeError("unexpected contents response for %s" % path)


def blob_sha(data):
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def download_file(entry):
    path = entry["path"]
    dest = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last_err = None
    for attempt in range(4):
        try:
            data = jsdelivr_fetch(path)
            if blob_sha(data) != entry["sha"]:
                raise RuntimeError("hash mismatch (jsdelivr stale?)")
            write_mode(dest, data, entry["mode"])
            return path, "ok"
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(1.5 * (attempt + 1) + random.random())
    # Fallback 1: raw.githubusercontent via proxy
    for attempt in range(2):
        try:
            data = raw_fetch(path)
            if blob_sha(data) == entry["sha"]:
                write_mode(dest, data, entry["mode"])
                return path, "ok-raw"
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(2)
    # Fallback 2: API contents (files <= 1MB are served; larger will fail)
    try:
        data = api_contents_fetch(path)
        if blob_sha(data) == entry["sha"]:
            write_mode(dest, data, entry["mode"])
            return path, "ok-api"
    except Exception as exc:  # noqa: BLE001
        last_err = exc
    return path, "FAILED: %s" % last_err


def write_mode(dest, data, mode):
    with open(dest, "wb") as fh:
        fh.write(data)
    if mode == "100755":
        os.chmod(dest, 0o755)


def download_symlink(entry):
    path = entry["path"]
    dest = os.path.join(ROOT, path)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    last_err = None
    for attempt in range(4):
        try:
            target = api_blob_fetch(entry["sha"]).decode()
            if os.path.islink(dest) or os.path.exists(dest):
                os.remove(dest)
            os.symlink(target, dest)
            return path, "ok"
        except Exception as exc:  # noqa: BLE001
            last_err = exc
            time.sleep(2 * (attempt + 1))
    return path, "FAILED: %s" % last_err


def main():
    tree = json.load(open(TREE_JSON))
    blobs = [t for t in tree["tree"] if t["type"] == "blob"]
    regular = [t for t in blobs if t["mode"] != "120000"]
    links = [t for t in blobs if t["mode"] == "120000"]
    print("regular=%d symlinks=%d" % (len(regular), len(links)), flush=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(download_file, t): t["path"] for t in regular}
        done = 0
        for fut in concurrent.futures.as_completed(futures):
            path, status = fut.result()
            done += 1
            results.append((path, status))
            if done % 250 == 0:
                print("progress %d/%d" % (done, len(regular)), flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(download_symlink, t): t["path"] for t in links}
        for fut in concurrent.futures.as_completed(futures):
            results.append(fut.result())
    failed = [r for r in results if not r[1].startswith("ok")]
    with open(os.path.join(ROOT, ".import-logs", "import-results.json"), "w") as fh:
        json.dump(results, fh, indent=2)
    with open(os.path.join(ROOT, ".import-logs", "import-failures.txt"), "w") as fh:
        for path, status in failed:
            fh.write("%s\t%s\n" % (path, status))
    print("total=%d failed=%d" % (len(results), len(failed)), flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
