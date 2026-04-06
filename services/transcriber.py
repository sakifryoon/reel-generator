import hashlib
import json
import os
import re
import tempfile

from google import genai
from google.genai import types

from .video_utils import extract_audio, split_audio, get_audio_duration


def _file_hash(filepath: str) -> str:
    """ファイルの先頭1MBとサイズからハッシュを生成（高速）"""
    h = hashlib.sha256()
    h.update(str(os.path.getsize(filepath)).encode())
    with open(filepath, "rb") as f:
        h.update(f.read(1024 * 1024))
    return h.hexdigest()[:16]


def _get_cache_path(video_path: str, cache_dir: str, prefix: str = "") -> str:
    fhash = _file_hash(video_path)
    filename = f"{prefix}{os.path.splitext(os.path.basename(video_path))[0]}_{fhash}.json"
    return os.path.join(cache_dir, filename)


def _dedup_segments(segments: list[dict]) -> list[dict]:
    """連続する同一テキストの繰り返しを除去"""
    if not segments:
        return segments
    deduped = [segments[0]]
    for seg in segments[1:]:
        if seg["text"] != deduped[-1]["text"]:
            deduped.append(seg)
    return deduped


def _call_gemini_transcribe(client: genai.Client, audio_path: str, offset: float = 0.0) -> list[dict]:
    """Gemini APIで音声を文字起こし（タイムスタンプ付き）"""
    audio_data = open(audio_path, "rb").read()
    duration = get_audio_duration(audio_path)

    prompt = f"""この音声ファイル（約{int(duration)}秒）を日本語で文字起こししてください。

以下のJSON形式で出力してください。他のテキストは一切出力しないでください。

```json
[
  {{"start": 0.0, "end": 5.2, "text": "発話内容"}},
  {{"start": 5.2, "end": 12.1, "text": "次の発話内容"}}
]
```

ルール：
- JSON配列のみを出力（```jsonで囲んでOK）
- startとendは秒数（小数点1桁）
- 1セグメントは1〜3文、5〜15秒程度
- 音声の最後まで漏れなく文字起こしすること
- 同じフレーズを繰り返し出力しないこと（ループ禁止）
- 音声の実際の長さは約{int(duration)}秒です。endの最大値がこれを大きく超えないようにしてください"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[
            types.Content(
                parts=[
                    types.Part.from_bytes(data=audio_data, mime_type="audio/mpeg"),
                    types.Part.from_text(text=prompt),
                ]
            )
        ],
        config=types.GenerateContentConfig(temperature=0.1),
    )

    text = response.text.strip()

    # JSONブロックを抽出
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        text = json_match.group(1)
    else:
        bracket_match = re.search(r'\[.*\]', text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(0)

    # JSONパース（複数の方法を試す）
    try:
        segments = json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r',\s*([}\]])', r'\1', text)
        cleaned = cleaned.replace('\n', ' ')
        try:
            segments = json.loads(cleaned)
        except json.JSONDecodeError:
            segments = []
            for m in re.finditer(
                r'\{[^{}]*"start"\s*:\s*([\d.]+)[^{}]*"end"\s*:\s*([\d.]+)[^{}]*"text"\s*:\s*"([^"]*)"[^{}]*\}',
                text
            ):
                segments.append({
                    "start": float(m.group(1)),
                    "end": float(m.group(2)),
                    "text": m.group(3)
                })
            if not segments:
                raise ValueError(f"Geminiの応答をパースできませんでした: {text[:500]}")

    # オフセット適用
    for seg in segments:
        seg["start"] = round(float(seg["start"]) + offset, 1)
        seg["end"] = round(float(seg["end"]) + offset, 1)
        seg["text"] = seg["text"].strip()

    # ループ除去
    segments = _dedup_segments(segments)

    return segments


def transcribe_video(
    video_path: str,
    cache_dir: str,
    api_key: str,
    prefix: str = "",
    progress_callback=None
) -> dict:
    """動画を文字起こし。キャッシュがあればそれを返す。
    Returns: {"segments": [...], "full_text": str, "duration": float}
    """
    os.makedirs(cache_dir, exist_ok=True)
    cache_path = _get_cache_path(video_path, cache_dir, prefix)

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)

    client = genai.Client(api_key=api_key)

    # 音声抽出
    if progress_callback:
        progress_callback("音声を抽出中...")
    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = os.path.join(tmpdir, "audio.mp3")
        extract_audio(video_path, audio_path)

        # 必要に応じて分割
        chunks = split_audio(audio_path, max_size_mb=19.0)

        all_segments = []
        for i, chunk in enumerate(chunks):
            if progress_callback:
                progress_callback(f"文字起こし中... ({i+1}/{len(chunks)})")

            segments = _call_gemini_transcribe(
                client, chunk["path"], offset=chunk["offset_seconds"]
            )
            all_segments.extend(segments)

    # 全体でも重複除去
    all_segments = _dedup_segments(all_segments)

    full_text = "".join(seg["text"] for seg in all_segments)
    duration = all_segments[-1]["end"] if all_segments else 0.0

    result = {
        "segments": all_segments,
        "full_text": full_text,
        "duration": duration
    }

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    return result
