<div align="center">
  <img src="assets/logo.png" alt="deepseek-web-shim 로고" width="128" height="128">
  <h1>deepseek-web-shim</h1>
  <p>DeepSeek 웹 채팅 앞단에 두는 OpenAI 호환 로컬 서버.<br>
  작업 증명은 Python으로 다시 구현했고, 벤더 자체의 wasm 모듈과 바이트 단위로 검증했습니다.</p>
  <p>
    <a href="https://github.com/0xgetz/deepseek-web-shim/releases"><img src="https://img.shields.io/github/v/release/0xgetz/deepseek-web-shim?style=flat-square" alt="릴리스"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3fb950?style=flat-square" alt="MIT 라이선스"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+"></a>
    <a href="tests"><img src="https://img.shields.io/badge/tests-74%20offline-2ea44f?style=flat-square" alt="오프라인 테스트 54개"></a>
  </p>
  <p>
    <a href="README.md">English</a> ·
    <a href="README.id.md">Bahasa Indonesia</a> ·
    <a href="README.zh-CN.md">简体中文</a> ·
    <a href="README.ja.md">日本語</a> ·
    <strong>한국어</strong>
  </p>
</div>

---

## 이것은 무엇인가

`chat.deepseek.com`이 쓰는 것과 같은 프로토콜을 Python에서 말하고, 그것을
OpenAI 호환 엔드포인트로 노출하는 연구 도구입니다.

```bash
export DSW_API_KEY=local   # any value; it guards your own local port
curl http://127.0.0.1:8712/v1/chat/completions \
  -H "Authorization: Bearer local" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-web","messages":[{"role":"user","content":"안녕하세요"}]}'
```

서버를 한 번도 실행하지 않더라도 읽을 가치가 있는 두 부분이 있습니다.

1. **작업 증명, 검증 완료.** DeepSeek의 챌린지는 앞자리 0을 찾는 퍼즐이 아니고,
   그 해시도 표준 SHA3나 표준 Keccak이 아닙니다. Keccak-f[1600]의 **23 라운드**
   버전(라운드 상수 0번을 건너뜀), rate 136, 패딩 `0x06`이며, 챌린지는 **원상
   목표**입니다. 서버가 먼저 답을 고르고 그 다이제스트를 공개한 뒤, 난이도 상한
   안에서 원상을 찾으라고 요구합니다. 자세한 내용은
   [`docs/protocol.md`](docs/protocol.md).
2. **테스트 가능한 클라이언트.** Python 해시는 DeepSeek 자체 wasm 모듈의 출력을
   바이트 단위로 재현합니다. 그래서 이 심은 그들의 바이너리를 함께 배포하지 않고도
   동작합니다. 여기까지 밝혀낸 조사 스크립트는 두 개의 잘못된 가설까지 포함해
   [`research/`](research/README.md)에 있습니다.

## 설치

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
```

## 세션 캡처하기

이 심은 **당신 자신의** 세션 위에서 동작합니다. 브라우저에서
`chat.deepseek.com`을 열어 로그인한 뒤, DevTools의 Network를 열고 아무 메시지나
보낸 다음 `completion` 요청을 클릭해 `authorization` 헤더 값을 복사하세요.

```bash
echo 'Bearer <여기에 토큰을 붙여넣기>' > /tmp/tok.txt
PYTHONPATH=src python -m deepseek_web_shim --session /tmp/tok.txt
# {"saved": "...", "token_len": ..., "cookies": 0, ...}
rm /tmp/tok.txt        # 토큰은 이제 ~/.deepseek-web-shim/session.json (모드 0600)
```

## 실행

```bash
PYTHONPATH=src DSW_API_KEY=local python -m deepseek_web_shim --serve
# GET  /healthz              -> {"ok":true,"pow_backend":"pure","authenticated":true}
# GET  /v1/models            -> deepseek-web, deepseek-web-reasoner, deepseek-web-search
# POST /v1/chat/completions  -> OpenAI 스키마, stream=true|false
```

OpenAI 호환 클라이언트를 `http://127.0.0.1:8712/v1`로 향하게 하세요.

| 모델 이름 | 매핑 대상 |
| --- | --- |
| `deepseek-web` | 기본 웹 모델 |
| `deepseek-web-reasoner` | `thinking_enabled: true` |
| `deepseek-web-search` | `search_enabled: true` |

## 직접 검증하기

```bash
PYTHONPATH=src python -m pytest tests/ -q          # 73 passed, 1 skipped, 0 failed
PYTHONPATH=src python -m deepseek_web_shim --selftest
# {"backend":"pure","planted":11,"pure_answer":11,"match":true}
```

스위트는 완전히 오프라인이며, 네트워크에 닿는 테스트는 하나도 없습니다.
`test_pow.py`는 해시를 고정된 기지답 벡터에 못 박고, `test_server.py`는 주입한
가짜 업스트림에 대해 실제 ASGI 앱을 구동합니다.

Python 해시를 DeepSeek의 wasm 오라클과 대조하려면 그 모듈을 직접 받아서
(여기서는 **재배포하지 않습니다**) 다시 실행하세요.

```bash
python scripts/fetch_wasm.py                       # 받은 sha256을 기록합니다
python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm   # 이미 가진 사본을 써도 됩니다
PYTHONPATH=src DSW_WASM=wasm/sha3_wasm_bg.wasm python -m pytest tests/test_pow.py
```

## 빠른 PoW와 느린 PoW

| 백엔드 | 속도 | 필요한 것 |
| --- | --- | --- |
| `wasm` | 빠름 | DeepSeek의 wasm 모듈, 직접 받아야 함 (`DSW_WASM=`) |
| `pure` | 초당 약 1.9천 해시 | 없음, 이 저장소의 코드 자체 |

둘 다 **동일한 다이제스트**를 만들므로 차이는 지연뿐입니다. `--selftest`가 어느
쪽이 활성인지 출력합니다.

## 설정

모두 환경 변수로만 하며, 커밋하지 않습니다. [`.env.example`](.env.example) 참고.

| 변수 | 의미 |
| --- | --- |
| `DSW_API_KEY` | 클라이언트가 제시해야 하는 키. 필수입니다. 이 포트가 당신 세션 앞단이기 때문입니다 |
| `DSW_ALLOW_NO_AUTH` | `1`로 설정하면 의도적으로 키 없이 실행합니다 (루프백 전용) |
| `DSW_HOST` / `DSW_PORT` | 바인드 주소, 기본 `127.0.0.1:8712` |
| `DS_TOKEN` | DeepSeek bearer 토큰, `--session`의 대안 |
| `DSW_STATE_DIR` | 캡처한 세션을 저장하는 위치 |
| `DSW_WASM` | 선택적 wasm 모듈 경로 |
| `DSW_POW_BACKEND` | `pure`로 설정하면 모듈이 있어도 순수 Python 백엔드를 강제합니다 |
| `DS_PROXY` | IP가 거부될 때 송신 구간에 쓸 주거용 프록시 |

## 사용하기 전에 읽어 주세요

이것은 연구 도구이며 접근 우회 수단이 아닙니다. **자격 증명을 일절 포함하지 않고**,
계정을 만들지 않으며, CAPTCHA를 풀지 않습니다. 당신의 세션에서 동작하므로
당신 계정의 한도와 당신 계정의 위험이 그대로 적용됩니다. 웹 인터페이스에 대한
자동 접근은 해당 서비스의 약관을 위반할 수 있습니다. 그것은 당신의 판단이고
당신의 위험입니다. 전문은 [`docs/intended-use.md`](docs/intended-use.md).

공개되지 않은 프로토콜을 파싱하므로 업스트림이 바뀌면 깨집니다. 깨질 때는 조용히
틀린 답을 돌려주는 대신, 이름이 붙은 JSON 오류(`not_authenticated`,
`upstream_error`)로 크게 실패하도록 설계했습니다. 조용한 오답이야말로 보고할
가치가 있는 버그입니다.

안정적인 접근이 필요하면 공식 API를 쓰세요. 공식 API는 문서화되어 있고 지원되며,
이 페이지의 모든 주의 사항을 없애 줍니다.

## 구조

```
src/deepseek_web_shim/   pow.py (검증된 해시와 탐색), client.py (웹 흐름),
                         server.py (OpenAI 심), config.py, __main__.py (CLI)
tests/                   오프라인 테스트 54개
research/                결론을 뒷받침하는 스크립트, 헛다리도 포함
docs/                    protocol.md, intended-use.md
scripts/fetch_wasm.py    선택적 wasm 가져오기 스크립트, sha256을 출력합니다
```

## 라이선스

MIT. [LICENSE](LICENSE) 참고.
