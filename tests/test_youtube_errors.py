"""YouTube requests. A private/removed video is a finding (saved as UNAVAILABLE); a bot check, rate limit or network
error is temporary (raised, nothing saved). A download right after the info request reuses it instead of asking
YouTube again. No network: YouTube's answers are simulated.
Run: venv\\Scripts\\python -m tests.test_youtube_errors"""
import os
from validator import config
from validator.sources import media, youtube

CASES = [  # (YouTube's message, should it be saved as UNAVAILABLE?)
    ("ERROR: [youtube] x: Video unavailable. This video is private", True),
    ("ERROR: [youtube] x: Private video. Sign in if you've been granted access to this video", True),
    ("ERROR: [youtube] x: This video has been removed by the uploader", True),
    ("ERROR: [youtube] x: Video unavailable. This video is no longer available because the YouTube account "
     "associated with this video has been terminated.", True),
    ("ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies", False),
    ("\x1b[0;31mERROR:\x1b[0m [youtube] x: Sign in to confirm you’re not a bot.", False),
    ("ERROR: [youtube] x: Sign in to confirm your age. This video may be inappropriate for some users.", False),
    ("ERROR: [youtube] x: Video unavailable. This content isn't available, try again later.", False),
    ("ERROR: [youtube] x: Unable to download API page: HTTP Error 429: Too Many Requests", False),
    ("ERROR: [youtube] x: Unable to download webpage: <urlopen error [Errno 11001] getaddrinfo failed>", False),
]


class _FakeYDL:
    """Stands in for YouTube's info request: fails with a message, or answers and counts the requests."""
    def __init__(self, msg=None):
        self.msg, self.calls = msg, 0

    def extract_info(self, url, download=False):
        self.calls += 1
        if self.msg:
            raise Exception(self.msg)
        return {"id": url.rsplit("=", 1)[1], "title": "t", "duration": 60}


class _FakeDownloader:
    """Stands in for yt-dlp's downloader: writes the video file, or fails with a message."""
    got, fail = [], None

    def __init__(self, opts):
        self.opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def process_ie_result(self, info, download=True):
        if _FakeDownloader.fail:
            raise Exception(_FakeDownloader.fail)
        _FakeDownloader.got.append(info)
        open(os.path.join(config.VIDEO_DIR, info["id"] + ".mp4"), "wb").close()


def main():
    failed, vid = 0, "__test_youtube_errors__"
    path = os.path.join(config.YOUTUBE_INFO_DIR, vid + ".json")
    real, youtube._GAP = youtube._ydl, 0
    try:
        for msg, gone in CASES:
            youtube._ydl, youtube._pause["until"] = _FakeYDL(msg), 0
            try:
                saved = "error" in youtube.get_meta(vid, refresh=True)
            except youtube.YouTubeBlocked:
                saved = False
            ok = saved == gone and os.path.exists(path) == gone
            failed += not ok
            print("OK  " if ok else "FAIL", "unavailable" if gone else "temporary  ", msg[17:85])
            if os.path.exists(path):
                os.remove(path)

        # after a refusal YouTube is left alone for a while: no request is sent, and the job is told when to retry
        youtube._pause.update(until=0, strikes=0)
        fake = youtube._ydl = _FakeYDL("ERROR: [youtube] x: Sign in to confirm you’re not a bot.")
        for _ in range(2):
            try:
                youtube.fetch_info(vid)
            except youtube.YouTubeBlocked as e:
                retry_at = e.retry_at
        ok = fake.calls == 1 and retry_at and 14 * 60 < retry_at - __import__("time").time() <= 15 * 60
        failed += not ok
        print("OK  " if ok else "FAIL", "after a refusal: paused 15 min, nothing sent meanwhile, the job is told when to retry")
        youtube._pause["until"] = 0
        try:
            youtube.fetch_info(vid)
        except youtube.YouTubeBlocked as e:
            ok = 29 * 60 < e.retry_at - __import__("time").time() <= 30 * 60
        failed += not ok
        print("OK  " if ok else "FAIL", "refused again: the next pause is longer (30 min)")
        youtube._pause.update(until=0, strikes=0)

        # downloads: reuse the info request; a bot check becomes the short message
        fake, real_ydl_class = _FakeYDL(), media.yt_dlp.YoutubeDL
        youtube._ydl, media.yt_dlp.YoutubeDL = fake, _FakeDownloader
        try:
            youtube.get_meta(vid, refresh=True)
            media.download(vid)
            ok = fake.calls == 1 and len(_FakeDownloader.got) == 1 and _FakeDownloader.got[0]["id"] == vid
            failed += not ok
            print("OK  " if ok else "FAIL", "download right after the info request asks YouTube once, not twice")
            os.remove(media.video_path(vid))
            media.download(vid)
            ok = fake.calls == 2
            failed += not ok
            print("OK  " if ok else "FAIL", "download without a recent info request asks YouTube itself")
            os.remove(media.video_path(vid))
            _FakeDownloader.fail = "ERROR: [youtube] x: Sign in to confirm you’re not a bot. Use --cookies"
            try:
                media.download(vid)
                ok = False
            except youtube.YouTubeBlocked as e:
                ok = str(e).startswith(youtube.BLOCKED_HINT) and e.retry_at
            failed += not ok
            print("OK  " if ok else "FAIL", "a bot check during a download gives the short message")
        finally:
            media.yt_dlp.YoutubeDL, _FakeDownloader.fail = real_ydl_class, None
            for p in (path, media.video_path(vid)):
                if p and os.path.exists(p):
                    os.remove(p)
    finally:
        youtube._ydl = real
        youtube._pause.update(until=0, strikes=0)
    print("\nall passed" if not failed else f"\n{failed} FAILED")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
