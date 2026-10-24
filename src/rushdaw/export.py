"""Convert a rendered WAV mixdown to other formats with ffmpeg."""
import os
import shutil
import struct
import subprocess
import tempfile
import threading
import time

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


class Cancelled(Exception):
    """The browser cancelled the export (progress dialog 'Cancel')."""


# ------------------------------------------------------------------ export jobs
# A browser export can pass ?job=<id>; while ffmpeg runs the dialog polls GET /api/jobs/<id> for the progress
# and DELETE /api/jobs/<id> cancels it (ffmpeg is killed). Jobs are tiny dicts kept in memory for a few minutes.
_JOBS = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL = 600  # seconds


def _clean_job_id(job_id):
    job_id = str(job_id or "")
    return job_id if job_id and len(job_id) <= 64 and all(c.isalnum() or c in "-_" for c in job_id) else None


def job_start(job_id):
    job_id = _clean_job_id(job_id)
    if not job_id:
        return None
    now = time.time()
    with _JOBS_LOCK:
        for k in [k for k, v in _JOBS.items() if now - v["t"] > _JOB_TTL]:
            _JOBS.pop(k, None)
        job = _JOBS.get(job_id)
        if job is None:  # a cancel may already have arrived (DELETE before the upload finished)
            job = _JOBS[job_id] = {"id": job_id, "stage": "queued", "progress": 0.0, "done": False, "error": None,
                                   "cancelled": False, "proc": None, "t": now}
        job["t"] = now
        return job


def job_get(job_id):
    job_id = _clean_job_id(job_id)
    with _JOBS_LOCK:
        job = _JOBS.get(job_id) if job_id else None
        if not job:
            return None
        return {k: job[k] for k in ("id", "stage", "progress", "done", "error", "cancelled")}


def job_cancel(job_id):
    """Cancel a running (or not yet started) export job. Returns True when the job is known / registered."""
    job_id = _clean_job_id(job_id)
    if not job_id:
        return False
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job is None:  # cancelled before the server saw the upload: remember it, the export refuses to start
            job = _JOBS[job_id] = {"id": job_id, "stage": "cancelled", "progress": 0.0, "done": True, "error": None,
                                   "cancelled": True, "proc": None, "t": time.time()}
        job["cancelled"] = True
        proc = job.get("proc")
    if proc is not None and proc.poll() is None:
        try:
            proc.kill()
        except OSError:
            pass
    return True


def job_set(job, **kw):
    if job is not None:
        with _JOBS_LOCK:
            job.update(kw)
            job["t"] = time.time()


def wav_duration(wav_bytes):
    """Duration in seconds of a PCM WAV (RIFF) file, or 0 when the header can't be read."""
    try:
        if wav_bytes[:4] != b"RIFF" or wav_bytes[8:12] != b"WAVE":
            return 0.0
        pos, byte_rate = 12, 0
        while pos + 8 <= len(wav_bytes):
            cid, size = wav_bytes[pos:pos + 4], struct.unpack("<I", wav_bytes[pos + 4:pos + 8])[0]
            if cid == b"fmt ":
                byte_rate = struct.unpack("<I", wav_bytes[pos + 16:pos + 20])[0]
            elif cid == b"data":
                return size / byte_rate if byte_rate else 0.0
            pos += 8 + size + (size & 1)
    except (struct.error, IndexError):
        pass
    return 0.0


def _run_ffmpeg(cmd, duration, job, timeout):
    """Run ffmpeg; with a job, report progress (``-progress pipe:1``: out_time_us vs the input duration) and let
    the job be cancelled. The extra ``-progress``/``-nostats`` flags only add status lines on stdout - the encoded
    output is identical to a plain run."""
    if job is None:
        proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return proc.returncode, proc.stderr
    full = cmd[:1] + ["-progress", "pipe:1", "-nostats"] + cmd[1:]
    with tempfile.TemporaryFile() as err:
        proc = subprocess.Popen(full, stdout=subprocess.PIPE, stderr=err)
        job_set(job, proc=proc, stage="convert", progress=0.0)
        if job.get("cancelled"):
            proc.kill()
        start = time.time()
        try:
            for raw in proc.stdout:
                line = raw.decode("ascii", "replace").strip()
                if line.startswith("out_time_us=") or line.startswith("out_time_ms="):  # both are microseconds
                    try:
                        us = int(line.split("=", 1)[1])
                    except ValueError:
                        continue
                    if duration > 0:
                        job_set(job, progress=max(0.0, min(0.999, us / 1e6 / duration)))
                elif line == "progress=end":
                    job_set(job, progress=1.0)
                if time.time() - start > timeout:
                    proc.kill()
                    break
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
            proc.stdout.close()
            job_set(job, proc=None)
        if job.get("cancelled"):
            raise Cancelled("export cancelled")
        err.seek(0)
        return proc.returncode, err.read()


def convert(wav_bytes, fmt, title="RushDAW", job=None):
    """Convert WAV bytes into ``fmt``. Returns (bytes, ext, mime). ``job`` (from :func:`job_start`) receives the
    ffmpeg progress and can cancel the conversion (raises :class:`Cancelled`)."""
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
        if job is not None and job.get("cancelled"):
            raise Cancelled("export cancelled")
        code, stderr = _run_ffmpeg(cmd, wav_duration(wav_bytes), job, 900)
        if code != 0 or not os.path.exists(dst):
            raise RuntimeError(stderr.decode("utf-8", "replace")[-800:] or "ffmpeg failed")
        with open(dst, "rb") as f:
            return f.read(), ext, mime


def noise_floor_db(ffmpeg, path):
    """Estimate the noise floor (dBFS) as the 10th-percentile RMS of 50 ms frames, clamped to afftdn's -80..-20 range."""
    import array
    import math
    proc = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-i", path, "-ac", "1", "-ar", "16000",
                           "-f", "s16le", "-"], capture_output=True, timeout=300)
    a = array.array("h")
    a.frombytes(proc.stdout[: len(proc.stdout) // 2 * 2])
    n = 800  # 50 ms at 16 kHz
    rms = sorted(math.sqrt(sum(x * x for x in a[i:i + n]) / n) / 32768 for i in range(0, len(a) - n + 1, n))
    rms = [r for r in rms if r > 1e-6]  # ignore digital silence
    if not rms:
        return -80.0
    return max(-80.0, min(-20.0, 20 * math.log10(rms[len(rms) // 10]) + 4))  # afftdn works best a few dB above the RMS


DENOISE_LEVELS = {"light": 6, "medium": 12, "strong": 24}


def denoise(wav_bytes, strength="medium", start=None, duration=None):
    """Reduce steady background noise (hiss, hum, room tone) with ffmpeg's FFT denoiser (afftdn) with the noise floor
    measured from the quietest 10% of the clip. start/duration (seconds) cut out just that part first (one region).
    Returns a new WAV (32-bit float, same rate/channels) - can be applied again for more reduction."""
    if wav_bytes[:4] != b"RIFF":
        raise ValueError("audio must be a WAV file")
    nr = DENOISE_LEVELS.get(str(strength).lower()) if not isinstance(strength, (int, float)) else float(strength)
    if nr is None:
        raise ValueError("strength must be light | medium | strong or a number of dB (1-40)")
    nr = max(1.0, min(40.0, float(nr)))
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise RuntimeError("ffmpeg not available; install imageio-ffmpeg or ffmpeg")
    with tempfile.TemporaryDirectory(prefix="rushdaw_dn_") as tmp:
        src, dst = os.path.join(tmp, "in.wav"), os.path.join(tmp, "out.wav")
        with open(src, "wb") as f:
            f.write(wav_bytes)
        if start is not None or duration is not None:  # only the region's part of the recording
            cut = os.path.join(tmp, "cut.wav")
            cc = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src, "-ss", f"{max(0.0, float(start or 0)):.6f}"]
            if duration is not None:
                cc += ["-t", f"{max(0.001, float(duration)):.6f}"]
            proc = subprocess.run(cc + ["-c:a", "pcm_f32le", cut], capture_output=True, timeout=600)
            if proc.returncode != 0:
                raise RuntimeError("cut failed: " + proc.stderr.decode("utf-8", "replace")[-400:])
            src = cut
        nf = noise_floor_db(ffmpeg, src)
        cmd = [ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", src,
               "-af", f"afftdn=nr={nr:g}:nf={nf:.1f}", "-c:a", "pcm_f32le", dst]
        proc = subprocess.run(cmd, capture_output=True, timeout=600)
        if proc.returncode != 0 or not os.path.exists(dst):
            raise RuntimeError("denoise failed: " + proc.stderr.decode("utf-8", "replace")[-400:])
        with open(dst, "rb") as f:
            return f.read()
