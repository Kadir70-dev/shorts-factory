"""
YouTube uploader — one channel at a time, never the wrong one.

Safety rails, in the order they run:
  1. channel config + isolation checks (no shared credentials between channels)
  2. concept must be APPROVED and every source still license-verified
  3. duplicate protection: (channel, sha256 of the file) is UNIQUE in history
  4. quota: refuses when today's (Pacific) units + one upload exceed the budget
  5. channel lock: the OAuth token's own channel id must equal
     `youtube.expected_channel_id` before a single byte is sent
  6. privacy: `private` by default; `public`/scheduled needs `allow_public=True`
     AND channel `public_requires_approval` satisfied by the approved concept

Uploads are resumable (the session URI is stored so a crash resumes instead of
re-uploading) and retried with exponential backoff on 5xx / network errors.
google-api-python-client is imported lazily; dry runs work without it.
"""
from __future__ import annotations

import random
import time
from pathlib import Path

from . import channels, schedule
from .db import eligible_source_sql

SCOPES = ["https://www.googleapis.com/auth/youtube.upload",
          "https://www.googleapis.com/auth/youtube.readonly"]
RETRIABLE = {500, 502, 503, 504}


class UploadBlocked(RuntimeError):
    pass


def authorize(channel: str) -> Path:
    """Interactive one-off OAuth for ONE channel; token saved under its own dir.
    Pick the matching YouTube channel/brand account in the browser."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    cfg = channels.load(channel)
    flow = InstalledAppFlow.from_client_secrets_file(str(cfg["_client_secret"]), SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent")
    cfg["_token"].parent.mkdir(parents=True, exist_ok=True)
    cfg["_token"].write_text(creds.to_json())
    cfg["_token"].chmod(0o600)
    svc = _service(cfg)
    got = _whoami(svc)
    print(f"[auth] {channel}: token belongs to YouTube channel {got}")
    want = cfg["youtube"].get("expected_channel_id", "")
    if want and got != want:
        cfg["_token"].unlink()
        raise UploadBlocked(f"token is for {got}, config expects {want}; token deleted")
    return cfg["_token"]


def _service(cfg: dict):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    creds = Credentials.from_authorized_user_file(str(cfg["_token"]), SCOPES)
    if not creds.valid and creds.refresh_token:
        creds.refresh(Request())
        cfg["_token"].write_text(creds.to_json())
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def _whoami(svc) -> str:
    items = svc.channels().list(part="id", mine=True).execute().get("items", [])
    if len(items) != 1:
        raise UploadBlocked(f"token maps to {len(items)} channels; expected exactly 1")
    return items[0]["id"]


def preflight(con, channel: str, render: dict, concept: dict, *,
              privacy: str, allow_public: bool) -> dict:
    cfg = channels.load(channel)
    errs = channels.isolation_errors()
    if errs:
        raise UploadBlocked("channel isolation: " + "; ".join(errs))
    if concept["channel"] != channel:
        raise UploadBlocked(f"concept belongs to {concept['channel']}, not {channel}")
    if concept["status"] not in ("approved", "rendered") or not concept.get("approved_by"):
        raise UploadBlocked("concept not approved")
    where, args = eligible_source_sql()
    ids = sorted({r["source_id"] for r in concept["payload"]["ranks"]})
    ok = con.execute(f"SELECT COUNT(*) FROM sources s WHERE s.id IN "
                     f"({','.join('?' * len(ids))}) AND {where}", (*ids, *args)).fetchone()[0]
    if ok != len(ids):
        raise UploadBlocked("a source's license is no longer verified")
    if privacy not in ("private", "unlisted", "public"):
        raise UploadBlocked(f"bad privacy {privacy!r}")
    if privacy == "public" and not allow_public:
        raise UploadBlocked("public/scheduled publishing needs --allow-public")
    if privacy == "public" and cfg.get("public_requires_approval", True) \
            and not concept.get("approved_by"):
        raise UploadBlocked("public publishing requires a named approver")
    dup = con.execute("SELECT video_id, status FROM uploads WHERE channel=? AND render_sha=?",
                      (channel, render["sha256"])).fetchone()
    if dup and dup["status"] == "uploaded":
        raise UploadBlocked(f"already uploaded to {channel} as {dup['video_id']}")
    q = cfg.get("quota", {})
    used = con.execute("SELECT units FROM quota WHERE channel=? AND day=?",
                       (channel, schedule.quota_day())).fetchone()
    if (used[0] if used else 0) + q.get("upload_cost", 1600) > q.get("daily_units", 10000):
        raise UploadBlocked("daily API quota budget exhausted; retry after midnight PT")
    return cfg


def _body(meta: dict, privacy: str, publish_at: str | None) -> dict:
    status = {"privacyStatus": privacy, "selfDeclaredMadeForKids": meta["made_for_kids"],
              "containsSyntheticMedia": meta.get("contains_synthetic_media", False)}
    if publish_at:                      # scheduled: must be private until publishAt
        status.update(privacyStatus="private", publishAt=publish_at)
    return {"snippet": {"title": meta["title"], "description": meta["description"],
                        "tags": meta["tags"], "categoryId": meta["category_id"],
                        "defaultLanguage": meta["default_language"]},
            "status": status}


def upload(con, channel: str, render: dict, concept: dict, meta: dict, *,
           privacy: str = "private", schedule_slot: bool = False,
           allow_public: bool = False, dry_run: bool = False,
           max_retries: int = 6) -> dict:
    want_public = schedule_slot or privacy == "public"
    cfg = preflight(con, channel, render, concept,
                    privacy="public" if want_public else privacy, allow_public=allow_public)
    publish_at = None
    if schedule_slot:
        taken = {r[0] for r in con.execute(
            "SELECT publish_at FROM uploads WHERE channel=? AND publish_at != ''", (channel,))}
        publish_at = schedule.to_rfc3339(schedule.next_slots(cfg, taken)[0])
    body = _body(meta, privacy, publish_at)
    con.execute("""INSERT INTO uploads (channel, render_sha, concept_id, privacy, publish_at)
                   VALUES (?,?,?,?,?) ON CONFLICT(channel, render_sha) DO UPDATE SET
                   privacy=excluded.privacy, publish_at=excluded.publish_at""",
                (channel, render["sha256"], concept["id"], body["status"]["privacyStatus"],
                 publish_at or ""))
    con.commit()
    if dry_run:
        return {"dry_run": True, "channel": channel, "body": body,
                "blocking": channels.upload_readiness(cfg)}

    if cfg.get("uploads_enabled") is not True:
        raise UploadBlocked(f"uploads are disabled for {channel} (publishing config "
                            "`uploads_enabled: false`); only --dry-run is allowed")
    probs = channels.upload_readiness(cfg)
    if probs:
        raise UploadBlocked("; ".join(probs))
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload
    svc = _service(cfg)
    got = _whoami(svc)
    if got != cfg["youtube"]["expected_channel_id"]:
        raise UploadBlocked(f"token is for {got}, not {cfg['youtube']['expected_channel_id']}")

    media = MediaFileUpload(render["path"], mimetype="video/mp4", chunksize=8 << 20,
                            resumable=True)
    req = svc.videos().insert(part="snippet,status", body=body, media_body=media)
    row = con.execute("SELECT resume_uri FROM uploads WHERE channel=? AND render_sha=?",
                      (channel, render["sha256"])).fetchone()
    if row and row["resume_uri"]:
        req.resumable_uri = row["resume_uri"]            # resume an interrupted session
    con.execute("UPDATE uploads SET status='uploading' WHERE channel=? AND render_sha=?",
                (channel, render["sha256"]))
    response, attempt = None, 0
    while response is None:
        try:
            _, response = req.next_chunk()
            if req.resumable_uri:
                con.execute("UPDATE uploads SET resume_uri=? WHERE channel=? AND render_sha=?",
                            (req.resumable_uri, channel, render["sha256"]))
                con.commit()
        except (HttpError, OSError) as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            attempt += 1
            con.execute("UPDATE uploads SET attempts=attempts+1, error=? "
                        "WHERE channel=? AND render_sha=?", (str(e)[:500], channel, render["sha256"]))
            con.commit()
            if (status is not None and status not in RETRIABLE) or attempt > max_retries:
                con.execute("UPDATE uploads SET status='failed' WHERE channel=? AND render_sha=?",
                            (channel, render["sha256"]))
                raise
            time.sleep(min(64, 2 ** attempt) + random.random())
    con.execute("""INSERT INTO quota (channel, day, units) VALUES (?,?,?)
                   ON CONFLICT(channel, day) DO UPDATE SET units = units + excluded.units""",
                (channel, schedule.quota_day(), cfg.get("quota", {}).get("upload_cost", 1600)))
    con.execute("UPDATE uploads SET status='uploaded', video_id=?, resume_uri='', error='' "
                "WHERE channel=? AND render_sha=?", (response["id"], channel, render["sha256"]))
    return {"video_id": response["id"], "privacy": body["status"]["privacyStatus"],
            "publish_at": publish_at}
