import os
import tempfile
import streamlit as st
from dotenv import load_dotenv

from services.transcriber import transcribe_video
from services.analyzer import (
    analyze_reference_reels,
    load_reference_profile,
    generate_proposals,
)

# 設定
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, "data")
TRANSCRIPT_DIR = os.path.join(DATA_DIR, "transcripts")
PROFILE_PATH = os.path.join(TRANSCRIPT_DIR, "reference_profile.json")

load_dotenv(os.path.join(APP_DIR, ".env"))

st.set_page_config(page_title="リール企画ジェネレーター", page_icon="🎬", layout="wide")
st.title("リール企画ジェネレーター")

# APIキー設定
with st.sidebar:
    st.header("API設定")
    google_key = st.text_input(
        "Google AI APIキー",
        value=os.getenv("GOOGLE_API_KEY", ""),
        type="password",
        help="Gemini（文字起こし・分析・提案）に使用"
    )

    if not google_key:
        st.warning("Google AI APIキーを入力してください")

# タブ
tab1, tab2, tab3 = st.tabs(["📱 参考リール", "🎥 長尺動画", "💡 企画生成"])

# ===== タブ1: 参考リール =====
with tab1:
    st.header("参考リールの登録・分析")
    st.write("バズっているリール動画を5本程度アップロードして、構成パターンを学習させます。")

    uploaded_reels = st.file_uploader(
        "リール動画をアップロード（MP4）",
        type=["mp4", "mov", "m4v"],
        accept_multiple_files=True,
        key="reels"
    )

    # 既存プロファイルの表示
    existing_profile = load_reference_profile(PROFILE_PATH)
    if existing_profile:
        with st.expander("現在のリファレンスプロファイル（保存済み）", expanded=False):
            st.markdown(existing_profile)

    if uploaded_reels and st.button("参考リールを分析する", type="primary", key="analyze_btn"):
        if not google_key:
            st.error("Google AI APIキーを設定してください")
        else:
            transcripts = []
            reel_names = []
            progress = st.progress(0, text="準備中...")

            for i, reel_file in enumerate(uploaded_reels):
                progress.progress(
                    (i) / len(uploaded_reels),
                    text=f"リール {i+1}/{len(uploaded_reels)} を文字起こし中..."
                )
                # 一時ファイルに保存
                with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                    tmp.write(reel_file.read())
                    tmp_path = tmp.name

                try:
                    transcript = transcribe_video(
                        tmp_path, TRANSCRIPT_DIR, google_key, prefix="ref_"
                    )
                    transcripts.append(transcript)
                    reel_names.append(reel_file.name)
                finally:
                    os.unlink(tmp_path)

            progress.progress(0.9, text="パターンを分析中...")

            profile = analyze_reference_reels(
                transcripts, reel_names, google_key, save_path=PROFILE_PATH
            )

            progress.progress(1.0, text="完了!")
            st.success(f"{len(uploaded_reels)}本のリールを分析しました！")
            st.markdown("### 分析結果")
            st.markdown(profile)

# ===== タブ2: 長尺動画 =====
with tab2:
    st.header("長尺動画のアップロード")
    st.write("リールの素材となる長尺動画（セミナー、対談など）をアップロードします。")

    uploaded_long = st.file_uploader(
        "長尺動画をアップロード（MP4）",
        type=["mp4", "mov", "m4v"],
        accept_multiple_files=False,
        key="longform"
    )

    if uploaded_long and st.button("文字起こしを開始", type="primary", key="transcribe_btn"):
        if not google_key:
            st.error("Google AI APIキーを設定してください")
        else:
            status = st.empty()
            progress = st.progress(0, text="準備中...")

            with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
                tmp.write(uploaded_long.read())
                tmp_path = tmp.name

            try:
                def update_progress(msg):
                    status.text(msg)

                transcript = transcribe_video(
                    tmp_path, TRANSCRIPT_DIR, google_key,
                    prefix="long_", progress_callback=update_progress
                )
            finally:
                os.unlink(tmp_path)

            progress.progress(1.0, text="完了!")
            st.session_state["longform_transcript"] = transcript
            st.session_state["longform_name"] = uploaded_long.name

            duration_min = transcript["duration"] / 60
            st.success(f"文字起こし完了！（{duration_min:.1f}分）")

            with st.expander("文字起こし結果を確認", expanded=False):
                for seg in transcript["segments"]:
                    m, s = divmod(int(seg["start"]), 60)
                    st.text(f"[{m:02d}:{s:02d}] {seg['text']}")

    # 保存済みの文字起こしがある場合
    if "longform_transcript" in st.session_state:
        st.info(f"読み込み済み: {st.session_state.get('longform_name', '長尺動画')}")

# ===== タブ3: 企画生成 =====
with tab3:
    st.header("リール企画を生成")

    profile = load_reference_profile(PROFILE_PATH)
    has_longform = "longform_transcript" in st.session_state

    if not profile:
        st.warning("先に「参考リール」タブで参考リールを分析してください。")
    if not has_longform:
        st.warning("先に「長尺動画」タブで長尺動画をアップロードしてください。")

    if profile and has_longform:
        col1, col2 = st.columns(2)
        with col1:
            num_proposals = st.slider("企画数", min_value=3, max_value=10, value=7)
        with col2:
            max_seconds = st.selectbox("最大リール尺", [30, 60, 90], index=1)

        if st.button("企画を生成する", type="primary", key="generate_btn"):
            if not google_key:
                st.error("Google AI APIキーを設定してください")
            else:
                with st.spinner("AIがリール企画を考えています..."):
                    proposals = generate_proposals(
                        reference_profile=profile,
                        longform_transcript=st.session_state["longform_transcript"],
                        api_key=google_key,
                        num_proposals=num_proposals,
                        max_reel_seconds=max_seconds,
                    )

                st.session_state["proposals"] = proposals
                st.markdown("### 提案されたリール企画")
                st.markdown(proposals)

                st.download_button(
                    label="企画をダウンロード（.md）",
                    data=proposals,
                    file_name="reel_proposals.md",
                    mime="text/markdown"
                )

        # 前回の結果がある場合
        if "proposals" in st.session_state and not st.session_state.get("_just_generated"):
            st.markdown("### 前回の企画結果")
            st.markdown(st.session_state["proposals"])
            st.download_button(
                label="企画をダウンロード（.md）",
                data=st.session_state["proposals"],
                file_name="reel_proposals.md",
                mime="text/markdown",
                key="download_prev"
            )
