"""YouTube text evidence: page metadata (always) and the spoken transcript (when YouTube allows). Cached in work/."""
import json, os, re, threading, time
import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi
from .. import config

URL = "https://www.youtube.com/watch?v="


def ydl_options(**extra):
    """yt-dlp options for every YouTube request: quiet, and signed in when .env sets YT_COOKIES or
    YT_COOKIES_FROM_BROWSER (YouTube asks signed-out computers that make many requests to prove they are not a bot)."""
    # pacing, as yt-dlp recommends for many videos: a pause between its own requests to YouTube (pages, player),
    # and 5-10 s before each download
    o = {"quiet": True, "no_warnings": True, "noprogress": True,
         "sleep_interval_requests": 1, "sleep_interval": 5, "max_sleep_interval": 10}
    if config.COOKIES:
        o["cookiefile"] = config.COOKIES
    if config.COOKIES_FROM_BROWSER:
        browser, _, profile = config.COOKIES_FROM_BROWSER.partition(":")
        o["cookiesfrombrowser"] = (browser.strip().lower(), profile.strip() or None, None, None)
    o.update(extra)
    return o


_ydl = yt_dlp.YoutubeDL(ydl_options(skip_download=True))
_api = YouTubeTranscriptApi()
_KEYS = ("title", "channel", "duration", "description", "categories", "tags", "chapters", "view_count", "upload_date")
# One YouTube request at a time, spaced out: parallel requests got this IP blocked once already.
_net = threading.Lock()
_GAP = 1.5


def _load(p):
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _save(p, obj):
    with open(p, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def cached_meta(vid):
    """Metadata from the cache only (no network); None if never fetched."""
    return _load(os.path.join(config.YOUTUBE_INFO_DIR, vid + ".json"))


# YouTube's answers that mean the video itself is gone or private: a finding (UNAVAILABLE), saved.
_GONE = ("video unavailable", "private video", "has been removed", "no longer available", "account associated",
         "is not available", "does not exist")
# Answers that only mean YouTube is not serving this computer right now (bot check, age check, rate limit).
_BLOCKED = ("not a bot", "sign in to confirm", "try again later", "429", "too many requests")
BLOCKED_HINT = "YouTube is blocking requests from this computer for now (it asks to confirm you're not a bot)."
# After YouTube refuses, send it nothing for a while (more requests only make the block last longer):
# 15 minutes, then 30, then 60 if it keeps refusing. Queued videos wait and retry by themselves.
_COOL_DOWN = (15 * 60, 30 * 60, 60 * 60)
_pause = {"until": 0.0, "strikes": 0}
_pause_lock = threading.Lock()


class YouTubeBlocked(RuntimeError):
    """YouTube did not answer (bot check, rate limit, network). Temporary: nothing is saved, and retry_at says when
    the job queue should try this video again."""
    def __init__(self, msg, retry_at=None):
        super().__init__(msg)
        self.retry_at = retry_at


def _waiting():
    until = time.strftime("%H:%M", time.localtime(_pause["until"]))
    return YouTubeBlocked(f"{BLOCKED_HINT} Waiting until {until} before asking again. Signing in to YouTube avoids "
                          "this: set YT_COOKIES_FROM_BROWSER or YT_COOKIES in .env.", retry_at=_pause["until"])


def _refused():
    """YouTube just refused: start the next, longer pause (unless one is already running)."""
    with _pause_lock:
        now = time.time()
        if now >= _pause["until"]:
            _pause["until"] = now + _COOL_DOWN[min(_pause["strikes"], len(_COOL_DOWN) - 1)]
            _pause["strikes"] += 1
    return _waiting()


class YouTubeGone(RuntimeError):
    """The video is private, removed or deleted."""


def _reason(e):
    """YouTube's error message, and whether it means 'gone', 'blocked' or something else (network...)."""
    msg = re.sub(r"\x1b\[[0-9;]*m", "", str(e)).split("\n")[0].replace("ERROR: ", "")[:300]  # no terminal colors
    low = msg.lower()
    return msg, "blocked" if any(k in low for k in _BLOCKED) else "gone" if any(k in low for k in _GONE) else "other"


def raise_if_blocked(e):
    """For errors from other YouTube requests (downloads): a bot check becomes a short YouTubeBlocked."""
    if _reason(e)[1] == "blocked":
        raise _refused() from e


# The full answer of the last few info requests, so the download right after reuses it instead of asking again:
# two requests for the same video seconds apart are what YouTube's bot check reacts to.
_fresh, _FRESH_MAX, _FRESH_AGE = {}, 4, 1800


def fetch_info(vid):
    """One YouTube info request (one at a time across all jobs, spaced out). The full yt-dlp info, formats included.
    While YouTube is refusing (see _COOL_DOWN) nothing is sent."""
    if time.time() < _pause["until"]:
        raise _waiting()
    try:
        with _net:
            time.sleep(_GAP)
            info = _ydl.extract_info(URL + vid, download=False)
    except Exception as e:
        msg, kind = _reason(e)
        if kind == "blocked":
            raise _refused() from e
        if kind == "gone":
            raise YouTubeGone(msg) from e
        raise YouTubeBlocked("YouTube did not answer: " + msg, retry_at=time.time() + 120) from e
    _pause["strikes"] = 0  # YouTube answers again: the next refusal starts with the short pause
    _fresh[vid] = (time.time(), info)
    while len(_fresh) > _FRESH_MAX:
        _fresh.pop(next(iter(_fresh)))
    return info


def take_fresh_info(vid):
    """The info from a request for this video in the last 30 minutes (used once), or None."""
    t, info = _fresh.pop(vid, (0, None))
    return info if info and time.time() - t < _FRESH_AGE else None


def get_meta(vid, refresh=False):
    p = os.path.join(config.YOUTUBE_INFO_DIR, vid + ".json")
    cached = _load(p)
    if cached is not None and not refresh and "error" not in cached:
        return cached
    try:
        info = fetch_info(vid)
        m = {k: info.get(k) for k in _KEYS}
        m["description"] = (m["description"] or "")[:1500]
        m["tags"] = (m["tags"] or [])[:15]
    except YouTubeGone as e:
        m = {"error": str(e)}  # private, removed or deleted: a finding, not a crash
    _save(p, m)
    return m


def get_transcript(vid, fetch=True):
    """List of [start, dur, text] or None. IP blocks are not cached so they can be retried.
    With fetch=False only the cache is consulted."""
    p = os.path.join(config.CAPTIONS_DIR, vid + ".json")
    cached = _load(p)
    if cached and cached.get("segs"):
        return cached["segs"]
    if not fetch or (cached and cached.get("error") in ("TranscriptsDisabled", "NoTranscriptFound")):
        return None
    try:
        with _net:
            time.sleep(_GAP)
            segs = [[round(s.start, 1), round(s.duration, 1), s.text]
                    for s in _api.fetch(vid, languages=["en", "en-US", "en-GB"])]
        _save(p, {"segs": segs})
        return segs
    except Exception as e:
        name = type(e).__name__
        if name not in ("IpBlocked", "RequestBlocked"):
            _save(p, {"error": name})
        return None


def said(segs, a, b):
    """Transcript text spoken between a and b seconds."""
    return " ".join(s[2].replace("\n", " ") for s in segs if s[0] + s[1] > a and s[0] < b)
