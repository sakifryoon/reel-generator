import os
import json

from google import genai
from google.genai import types


def _load_prompt(prompt_name: str) -> str:
    """prompts/ディレクトリからプロンプトテンプレートを読み込み"""
    prompt_dir = os.path.join(os.path.dirname(__file__), "..", "prompts")
    path = os.path.join(prompt_dir, prompt_name)
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _format_transcript(transcript: dict, label: str = "") -> str:
    """文字起こし結果を読みやすい形式に変換"""
    lines = []
    if label:
        lines.append(f"=== {label} ===")
    for seg in transcript["segments"]:
        m, s = divmod(int(seg["start"]), 60)
        h, m = divmod(m, 60)
        ts = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        lines.append(f"[{ts}] {seg['text']}")
    return "\n".join(lines)


def analyze_reference_reels(
    transcripts: list[dict],
    reel_names: list[str],
    api_key: str,
    save_path: str = None
) -> str:
    """参考リールを分析してリファレンスプロファイルを生成"""
    client = genai.Client(api_key=api_key)

    prompt_template = _load_prompt("analyze_reels.txt")

    reels_text = ""
    for i, (transcript, name) in enumerate(zip(transcripts, reel_names)):
        reels_text += _format_transcript(transcript, f"参考リール {i+1}: {name}")
        reels_text += f"\n（尺: {transcript['duration']:.1f}秒）\n\n"

    prompt = prompt_template.replace("{{REELS_TRANSCRIPTS}}", reels_text)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.3)
    )

    profile = response.text

    if save_path:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump({"profile": profile}, f, ensure_ascii=False, indent=2)

    return profile


def load_reference_profile(profile_path: str) -> str | None:
    """保存済みのリファレンスプロファイルを読み込み"""
    if os.path.exists(profile_path):
        with open(profile_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("profile")
    return None


def generate_proposals(
    reference_profile: str,
    longform_transcript: dict,
    api_key: str,
    num_proposals: int = 7,
    max_reel_seconds: int = 60
) -> str:
    """リファレンスプロファイル×長尺動画からリール企画を提案"""
    client = genai.Client(api_key=api_key)

    prompt_template = _load_prompt("generate_proposals.txt")

    longform_text = _format_transcript(longform_transcript, "長尺動画")
    longform_text += f"\n（総尺: {longform_transcript['duration']:.1f}秒）"

    prompt = (
        prompt_template
        .replace("{{REFERENCE_PROFILE}}", reference_profile)
        .replace("{{LONGFORM_TRANSCRIPT}}", longform_text)
        .replace("{{NUM_PROPOSALS}}", str(num_proposals))
        .replace("{{MAX_SECONDS}}", str(max_reel_seconds))
    )

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.7)
    )

    return response.text
