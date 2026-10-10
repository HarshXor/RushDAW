"""Convert a rendered WAV mixdown to other formats with ffmpeg."""
import os
import shutil
import subprocess
import tempfile

# format -> (extension, mime, ffmpeg output args)
FORMATS = {
    "wav": ("wav", "audio/wav", None),
    "mp3": ("mp3", "audio/mpeg", ["-codec:a", "libmp3lame", "-b:a", "320k"]),
    "ogg": ("ogg", "audio/ogg", ["-codec:a", "libvorbis", "-q:a", "6"]),
    "flac": ("flac", "audio/flac", ["-codec:a", "flac"]),
    "m4a": ("m4a", "audio/mp4", ["-codec:a", "aac", "-b:a", "256k"]),
    "aac": ("aac", "audio/aac", ["-codec:a", "aac", "-b:a", "256k"]),
    "opus": ("opus", "audio/ogg", ["-codec:a", "libopus", "-b:a", "192k"]),
    "mp4": ("mp4", "video/mp4", "VIDEO"),
}


def find_ffmpeg():
    """Return path to an ffmpeg binary (system one first, then imageio-ffmpeg)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def available_formats():
    if find_ffmpeg():
        return list(FORMATS)
    return ["wav"]


def convert(wav_bytes, fmt, title="RushDAW"):
    """Convert WAV bytes into ``fmt``. Returns (bytes, ext, mime)."""
    fmt = fmt.lower()
    if fmt not in FORMATS:
        raise ValueError(f"unsupported format: {fmt}")
    ext, mime, args = FORMATS[fmt]
    if args is None:
        return wav_bytes, ext, mime
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not available; install imageio-ffmpeg or ffmpeg")
    safe_title = "".join(c for c in title if c.isalnum() or c in " -_.")[:80] or "RushDAW"
    with tempfile.TemporaryDirectory(prefix="rushdaw_") as tmp:
        src = os.path.join(tmp, "in.wav")
        dst = os.path.join(tmp, "out." + ext)
        with open(src, "wb") as f:
            f.write(wav_bytes)
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src]
        if args == "VIDEO":
            # music video: animated waveform on dark background
            cmd += [
                "-filter_complex",
                "[0:a]showwaves=s=1280x720:mode=cline:rate=30:colors=0x00e5ff|0xffffff,format=yuv420p[v]",
                "-map", "[v]", "-map", "0:a",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
                "-c:a", "aac", "-b:a", "256k", "-shortest", "-movflags", "+faststart",
            ]
        else:
            cmd += args
        cmd += ["-metadata", f"title={safe_title}", "-metadata", "encoder=RushDAW", dst]
        proc = subprocess.run(cmd, capture_output=True, timeout=900)
        if proc.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError(proc.stderr.decode("utf-8", "replace")[-800:] or "ffmpeg failed")
        with open(dst, "rb") as f:
            return f.read(), ext, mime
