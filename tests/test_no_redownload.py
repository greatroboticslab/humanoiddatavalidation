"""Nothing is downloaded twice. Runs on temporary copies with downloading blocked (any attempt fails the test).
Needs one already-downloaded video. Run: venv\\Scripts\\python -m tests.test_no_redownload"""
import os, shutil, tempfile
from validator import config
from validator.sources import media


class NoDownload:
    def __init__(self, *a, **k):
        raise AssertionError("a download was attempted")


def main():
    vid = next((v for v in config.all_ids() if media.video_path(v)), None)
    if not vid:
        raise SystemExit("needs one downloaded video in work/videos")
    src = media.video_path(vid)
    tmp = tempfile.mkdtemp()
    real = (config.VIDEO_DIR, config.FRAME_DIR, config.AUDIO_DIR)
    config.VIDEO_DIR, config.FRAME_DIR, config.AUDIO_DIR = (os.path.join(tmp, d) for d in ("videos", "frames", "audio"))
    for d in (config.VIDEO_DIR, config.FRAME_DIR, config.AUDIO_DIR):
        os.makedirs(d)
    real_ydl, media.yt_dlp.YoutubeDL = media.yt_dlp.YoutubeDL, NoDownload
    failed = 0

    def check(name, fn):
        nonlocal failed
        try:
            ok = fn()
        except AssertionError as e:
            ok = False
            name += f" ({e})"
        failed += not ok
        print("OK  " if ok else "FAIL", name)

    try:
        shutil.copy(src, config.VIDEO_DIR)
        # yt-dlp leftovers next to it must never be taken for the video
        for junk in (f"{vid}.f397.mp4", f"{vid}.f251.webm", f"{vid}.mp4.part"):
            open(os.path.join(config.VIDEO_DIR, junk), "w").close()
        check("finished video found, leftovers ignored", lambda: os.path.basename(media.video_path(vid)) == os.path.basename(src))
        check("frames cut from the video on disk, no download", lambda: bool(media.extract(vid)["subtasks"]))
        check("second time: frames reused, no download", lambda: bool(media.extract(vid)))
        media.delete(vid, keep_frames=True)  # the dashboard's "Delete local video"
        check("after 'Delete local video': no video file left", lambda: media.video_path(vid) is None)
        check("after 'Delete local video': kept frames reused, no download", lambda: bool(media.extract(vid)))
    finally:
        media.yt_dlp.YoutubeDL = real_ydl
        config.VIDEO_DIR, config.FRAME_DIR, config.AUDIO_DIR = real
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n(tested with {vid}, on temporary copies)")
    print("all passed" if not failed else f"{failed} FAILED")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
