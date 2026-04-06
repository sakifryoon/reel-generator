# リール企画ジェネレーター

参考リールの構成パターンを学習し、長尺動画から新しいリール企画をAIが提案するツール。

## セットアップ

```bash
# 1. 仮想環境を有効化
source ../.venv-pdf311/bin/activate

# 2. パッケージインストール
pip install -r requirements.txt

# 3. APIキーを設定
cp .env.example .env
# .envを編集してAPIキーを入力
```

## APIキーの取得

- **OpenAI**: https://platform.openai.com → API Keys → Create new key
- **Google AI Studio**: https://aistudio.google.com → Get API Key

## 起動

```bash
cd app
streamlit run app.py
```

ブラウザで http://localhost:8501 が開きます。

## 使い方

1. **参考リール**タブ: バズっているリール動画を5本程度アップ → 「分析する」
2. **長尺動画**タブ: 素材となる長尺動画をアップ → 「文字起こし開始」
3. **企画生成**タブ: 「企画を生成する」→ リール企画が提案される

## コスト目安

- 参考リール5本の分析: 約3円（初回のみ）
- 長尺動画60分の文字起こし: 約55円
- 企画生成: 約2円
- **1回あたり合計: 約60円**
