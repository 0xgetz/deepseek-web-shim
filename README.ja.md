<div align="center">
  <img src="assets/logo.png" alt="deepseek-web-shim のロゴ" width="128" height="128">
  <h1>deepseek-web-shim</h1>
  <p>DeepSeek の Web チャットの手前に置く、OpenAI 互換のローカルサーバ。<br>
  プルーフ・オブ・ワークを Python で再実装し、ベンダー自身の wasm モジュールと 1 バイト単位で照合しています。</p>
  <p>
    <a href="https://github.com/0xgetz/deepseek-web-shim/releases"><img src="https://img.shields.io/github/v/release/0xgetz/deepseek-web-shim?style=flat-square" alt="リリース"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3fb950?style=flat-square" alt="MIT ライセンス"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+"></a>
    <a href="tests"><img src="https://img.shields.io/badge/tests-54%20offline-2ea44f?style=flat-square" alt="54 件のオフラインテスト"></a>
  </p>
  <p>
    <a href="README.md">English</a> ·
    <a href="README.id.md">Bahasa Indonesia</a> ·
    <a href="README.zh-CN.md">简体中文</a> ·
    <strong>日本語</strong> ·
    <a href="README.ko.md">한국어</a>
  </p>
</div>

---

## これは何か

`chat.deepseek.com` と同じプロトコルを Python から話し、それを OpenAI 互換の
エンドポイントとして公開する研究用ツールです。

```bash
export DSW_API_KEY=local   # any value; it guards your own local port
curl http://127.0.0.1:8712/v1/chat/completions \
  -H "Authorization: Bearer local" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-web","messages":[{"role":"user","content":"こんにちは"}]}'
```

サーバを一度も動かさないとしても、読む価値のある部分が二つあります。

1. **プルーフ・オブ・ワークの検証済みな中身。** DeepSeek のチャレンジは先頭ゼロを
   探すパズルではなく、ハッシュも標準の SHA3 でも標準の Keccak でもありません。
   Keccak-f[1600] の**23 ラウンド**版（ラウンド定数の 0 番目をスキップ）、rate 136、
   パディング `0x06` で、チャレンジは**原像ターゲット**です。サーバが先に答えを選び、
   そのダイジェストを公開し、難易度の上限内で原像を見つけるよう求めます。
   詳細は [`docs/protocol.md`](docs/protocol.md)。
2. **テスト可能なクライアント。** Python のハッシュは DeepSeek 自身の wasm モジュールの
   出力を 1 バイト単位で再現します。だからこそ、彼らのバイナリを同梱せずにこのシムは
   動きます。ここへ至る調査スクリプトは、二つの誤った仮説も含めて
   [`research/`](research/README.md) にあります。

## インストール

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
```

## セッションを取得する

このシムは**あなた自身の**セッションの上で動きます。ブラウザで
`chat.deepseek.com` を開いてログインし、DevTools の Network を開いて何かメッセージを
送信し、`completion` リクエストをクリックして `authorization` ヘッダの値をコピーします。

```bash
echo 'Bearer <ここに token を貼り付け>' > /tmp/tok.txt
PYTHONPATH=src python -m deepseek_web_shim --session /tmp/tok.txt
# {"saved": "...", "token_len": ..., "cookies": 0, ...}
rm /tmp/tok.txt        # token は ~/.deepseek-web-shim/session.json に移動（モード 0600）
```

## 実行

```bash
PYTHONPATH=src DSW_API_KEY=local python -m deepseek_web_shim --serve
# GET  /healthz              -> {"ok":true,"pow_backend":"pure","authenticated":true}
# GET  /v1/models            -> deepseek-web, deepseek-web-reasoner, deepseek-web-search
# POST /v1/chat/completions  -> OpenAI スキーマ、stream=true|false
```

OpenAI 互換のクライアントを `http://127.0.0.1:8712/v1` に向けてください。

| モデル名 | マッピング先 |
| --- | --- |
| `deepseek-web` | 既定の Web モデル |
| `deepseek-web-reasoner` | `thinking_enabled: true` |
| `deepseek-web-search` | `search_enabled: true` |

## 自分で検証する

```bash
PYTHONPATH=src python -m pytest tests/ -q          # 54 passed, 1 skipped, 0 failed
PYTHONPATH=src python -m deepseek_web_shim --selftest
# {"backend":"pure","planted":11,"pure_answer":11,"match":true}
```

スイートは完全にオフラインで、ネットワークに触れるテストは一つもありません。
`test_pow.py` はハッシュを凍結した既知解ベクタに固定し、`test_server.py` は
注入した偽の上流に対して本物の ASGI アプリを動かします。

Python のハッシュを DeepSeek の wasm オラクルと突き合わせるには、そのモジュールを
自分で取得して（ここでは**再配布していません**）再実行します。

```bash
python scripts/fetch_wasm.py                       # 取得した sha256 を記録します
python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm   # すでに手元にあるコピーでも可
PYTHONPATH=src DSW_WASM=wasm/sha3_wasm_bg.wasm python -m pytest tests/test_pow.py
```

## 高速な PoW と低速な PoW

| バックエンド | 速度 | 必要なもの |
| --- | --- | --- |
| `wasm` | 高速 | DeepSeek の wasm モジュールを自分で取得（`DSW_WASM=`） |
| `pure` | 毎秒およそ 1.9 千ハッシュ | 何も不要、このリポジトリのコードそのもの |

どちらも**同一のダイジェスト**を生むので、違いは遅延だけです。`--selftest` が
どちらが有効かを表示します。

## 設定

すべて環境変数経由で、コミットはしません。[`.env.example`](.env.example) を参照。

| 変数 | 意味 |
| --- | --- |
| `DSW_API_KEY` | クライアントが提示すべきキー。必須です。このポートはあなたのセッションの前段だからです |
| `DSW_ALLOW_NO_AUTH` | `1` にすると意図的に鍵なしで動かします（ループバック限定） |
| `DSW_HOST` / `DSW_PORT` | バインド先、既定は `127.0.0.1:8712` |
| `DS_TOKEN` | DeepSeek の bearer token、`--session` の代替 |
| `DSW_STATE_DIR` | 取得したセッションの保存先 |
| `DSW_WASM` | 任意の wasm モジュールへのパス |
| `DSW_POW_BACKEND` | `pure` にするとモジュールがあっても純 Python バックエンドを強制します |
| `DS_PROXY` | 送信側を住宅プロキシ経由にする（IP が拒否される場合） |

## 使う前に読んでください

これは研究用ツールであり、アクセスの抜け道ではありません。**資格情報は一切同梱せず**、
アカウント作成も CAPTCHA の突破も行いません。あなたのセッションで動くので、
あなたのアカウントの上限と、あなたのアカウントのリスクがそのまま適用されます。
Web インターフェースへの自動アクセスは、そのサービスの規約に違反する可能性があります。
それはあなたの判断であり、あなたのリスクです。全文は
[`docs/intended-use.md`](docs/intended-use.md)。

未公開のプロトコルを解析しているので、上流が変われば壊れます。壊れるときは、
黙って誤った答えを返すのではなく、名前の付いた JSON エラー
（`not_authenticated`、`upstream_error`）で大きく失敗するよう設計しています。
静かな誤答こそが報告すべきバグです。

安定したアクセスが必要なら公式 API を使ってください。公式 API は文書化され、
サポートされ、このページの注意事項をすべて取り除けます。

## 構成

```
src/deepseek_web_shim/   pow.py（検証済みのハッシュと探索）、client.py（Web フロー）、
                         server.py（OpenAI シム）、config.py、__main__.py（CLI）
tests/                   54 件のオフラインテスト
research/                結論を支えるスクリプト群、回り道も含めて
docs/                    protocol.md、intended-use.md
scripts/fetch_wasm.py    任意の wasm 取得スクリプト、sha256 を表示します
```

## ライセンス

MIT。[LICENSE](LICENSE) を参照。
