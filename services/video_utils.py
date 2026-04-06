import subprocess
import os
import re
import math


def get_ffmpeg_path():
    """static_ffmpegからffmpegバイナリのパスを取得"""
    try:
        import static_ffmpeg
        static_ffmpeg.add_paths()
        import shutil
        path = shutil.which("ffmpeg")
        if path:
            return path
    except ImportError:
        pass
    return "ffmpeg"


def _get_duration_via_ffmpeg(file_path: str) -> float:
    """ffmpeg -i を使って長さ（秒）を取得（ffprobe不要）"""
    ffmpeg = get_ffmpeg_path()
    result = subprocess.run(
        [ffmpeg, "-i", file_path],
        capture_output=True, text=True
    )
    # ffmpegはstderrに情報を出力する
    output = result.stderr
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+)\.(\d+)", output)
    if match:
        h, m, s, cs = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
        return h * 3600 + m * 60 + s + cs / 100.0
    raise ValueError(f"Could not determine duration of {file_path}")


def get_video_duration(video_path: str) -> float:
    """動画の長さ（秒）を取得"""
    return _get_duration_via_ffmpeg(video_path)


def get_audio_duration(audio_path: str) -> float:
    """音声ファイルの長さ（秒）を取得"""
    return _get_duration_via_ffmpeg(audio_path)


def extract_audio(video_path: str, output_path: str) -> str:
    """動画から音声をMP3(64kbps)で抽出"""
    ffmpeg = get_ffmpeg_path()
    subprocess.run(
        [ffmpeg, "-i", video_path, "-vn", "-acodec", "libmp3lame",
         "-ab", "64k", "-ar", "16000", "-ac", "1", "-y", output_path],
        capture_output=True, check=True
    )
    return output_path


def split_audio(audio_path: str, max_size_mb: float = 24.0, chunk_minutes: int = 20) -> list[dict]:
    """音声ファイルが大きい場合、チャンクに分割。
    Returns: [{"path": str, "offset_seconds": float}, ...]
    """
    file_size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return [{"path": audio_path, "offset_seconds": 0.0}]

    ffmpeg = get_ffmpeg_path()
    duration = get_audio_duration(audio_path)
    chunk_seconds = chunk_minutes * 60
    num_chunks = math.ceil(duration / chunk_seconds)

    chunks = []
    base, ext = os.path.splitext(audio_path)
    for i in range(num_chunks):
        offset = i * chunk_seconds
        chunk_path = f"{base}_chunk{i}{ext}"
        subprocess.run(
            [ffmpeg, "-i", audio_path, "-ss", str(offset),
             "-t", str(chunk_seconds), "-acodec", "copy", "-y", chunk_path],
            capture_output=True, check=True
        )
        chunks.append({"path": chunk_path, "offset_seconds": offset})

    return chunks
