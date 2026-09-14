<div align="center">
  <img src="assets/logo.png" alt="deepseek-web-shim 标志" width="128" height="128">
  <h1>deepseek-web-shim</h1>
  <p>在 DeepSeek 网页版聊天前端的本地 OpenAI 兼容服务。<br>
  其工作量证明用 Python 重新实现，并与厂商自己的 wasm 模块逐字节校验。</p>
  <p>
    <a href="https://github.com/0xgetz/deepseek-web-shim/releases"><img src="https://img.shields.io/github/v/release/0xgetz/deepseek-web-shim?style=flat-square" alt="发布"></a>
    <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-3fb950?style=flat-square" alt="MIT 许可证"></a>
    <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.9%2B-blue?style=flat-square" alt="Python 3.9+"></a>
    <a href="tests"><img src="https://img.shields.io/badge/tests-74%20offline-2ea44f?style=flat-square" alt="54 个离线测试"></a>
  </p>
  <p>
    <a href="README.md">English</a> ·
    <a href="README.id.md">Bahasa Indonesia</a> ·
    <strong>简体中文</strong> ·
    <a href="README.ja.md">日本語</a> ·
    <a href="README.ko.md">한국어</a>
  </p>
</div>

---

## 这是什么

一个研究工具：用 Python 说与 `chat.deepseek.com` 相同的协议，并把它暴露为
OpenAI 兼容端点。

```bash
export DSW_API_KEY=local   # any value; it guards your own local port
curl http://127.0.0.1:8712/v1/chat/completions \
  -H "Authorization: Bearer local" \
  -H "Content-Type: application/json" \
  -d '{"model":"deepseek-web","messages":[{"role":"user","content":"你好"}]}'
```

即使你从不运行这个服务，也有两部分值得一读：

1. **工作量证明，且经过校验。** DeepSeek 的挑战不是前导零题，它的哈希也不是标准
   SHA3 或标准 Keccak。它是 Keccak-f[1600]、**23 轮**（跳过第 0 个轮常量）、
   rate 136、填充 `0x06`，而且挑战是 **原像目标**：服务端先选一个答案，对它求摘要，
   再要求你在难度上限内找出该原像。见 [`docs/protocol.md`](docs/protocol.md)。
2. **可测试的客户端。** Python 哈希逐字节复现 DeepSeek 自己 wasm 模块的输出，
   正因如此本项目无需分发他们的二进制即可运行。把这一点钉死的调研脚本，
   包括两个错误的假设，都在 [`research/`](research/README.md)。

## 安装

```bash
git clone https://github.com/0xgetz/deepseek-web-shim
cd deepseek-web-shim
uv venv && uv pip install -e ".[dev]"
```

## 抓取会话

本服务运行在**你自己的**会话之上。在浏览器打开 `chat.deepseek.com` 并登录，
然后在 DevTools 打开 Network，随便发一条消息，点开 `completion` 请求，
复制 `authorization` 头的值。

```bash
echo 'Bearer <把你的 token 粘贴到这里>' > /tmp/tok.txt
PYTHONPATH=src python -m deepseek_web_shim --session /tmp/tok.txt
# {"saved": "...", "token_len": ..., "cookies": 0, ...}
rm /tmp/tok.txt        # token 现在位于 ~/.deepseek-web-shim/session.json（权限 0600）
```

## 运行

```bash
PYTHONPATH=src DSW_API_KEY=local python -m deepseek_web_shim --serve
# GET  /healthz              -> {"ok":true,"pow_backend":"pure","authenticated":true}
# GET  /v1/models            -> deepseek-web, deepseek-web-reasoner, deepseek-web-search
# POST /v1/chat/completions  -> OpenAI 结构，stream=true|false
```

把任何 OpenAI 兼容客户端指向 `http://127.0.0.1:8712/v1` 即可。

| 模型名 | 映射到 |
| --- | --- |
| `deepseek-web` | 默认网页模型 |
| `deepseek-web-reasoner` | `thinking_enabled: true` |
| `deepseek-web-search` | `search_enabled: true` |

## 自己验证

```bash
PYTHONPATH=src python -m pytest tests/ -q          # 73 passed, 1 skipped, 0 failed
PYTHONPATH=src python -m deepseek_web_shim --selftest
# {"backend":"pure","planted":11,"pure_answer":11,"match":true}
```

测试套件完全离线：没有任何测试会访问网络。`test_pow.py` 把哈希钉在冻结的
已知答案向量上，`test_server.py` 则用注入的假上游驱动真实的 ASGI 应用。

若要把 Python 哈希与 DeepSeek 的 wasm 预言机对照，请自行获取该模块
（本项目**不**分发它）然后重跑：

```bash
python scripts/fetch_wasm.py                       # 记录它拿到的 sha256
python scripts/fetch_wasm.py --file ~/Downloads/sha3_wasm_bg.7b9ca65ddd.wasm   # 或者用你已经有的副本
PYTHONPATH=src DSW_WASM=wasm/sha3_wasm_bg.wasm python -m pytest tests/test_pow.py
```

## 快速与慢速 PoW

| 后端 | 速度 | 需要 |
| --- | --- | --- |
| `wasm` | 快 | DeepSeek 的 wasm 模块，由你自己获取（`DSW_WASM=`） |
| `pure` | 约每秒 1.9 千次哈希 | 什么都不需要，就是本仓库的代码 |

两者产生**完全相同的摘要**，所以选择只影响延迟。`--selftest` 会打印当前用的是哪个。

## 配置

全部通过环境变量，绝不提交。见 [`.env.example`](.env.example)。

| 变量 | 含义 |
| --- | --- |
| `DSW_API_KEY` | 客户端必须携带的密钥；必填，因为这个端口在你的会话前面 |
| `DSW_ALLOW_NO_AUTH` | 设为 `1` 时有意不带密钥运行，仅限回环地址 |
| `DSW_HOST` / `DSW_PORT` | 绑定地址，默认 `127.0.0.1:8712` |
| `DS_TOKEN` | DeepSeek bearer token，可替代 `--session` |
| `DSW_STATE_DIR` | 抓取到的会话存放位置 |
| `DSW_WASM` | 可选 wasm 模块的路径 |
| `DSW_POW_BACKEND` | 设为 `pure` 时即使模块存在也强制使用纯 Python 后端 |
| `DS_PROXY` | 出站走住宅代理，用于你的 IP 被拒时 |

## 使用前请读

这是研究工具，不是绕过访问的办法。它**不携带任何凭据**，从不创建账号，
也不破解验证码。它跑在你的会话上，所以你的账号限额与账号风险照旧适用。
对网页界面的自动化访问可能违反该服务的条款；这是你的判断，也是你的风险。
全文见 [`docs/intended-use.md`](docs/intended-use.md)。

它解析的是未公开协议，所以上游一变它就会坏。坏的时候它被设计成响亮失败，
返回有名字的 JSON 错误（`not_authenticated`、`upstream_error`），
而不是悄悄给出错误答案。静默的错误答案才值得报 bug。

如果你需要稳定的访问，请使用官方 API。官方 API 有文档、有支持，
并能去掉本页所有注意事项。

## 目录结构

```
src/deepseek_web_shim/   pow.py（已校验的哈希与搜索）、client.py（网页流程）、
                         server.py（OpenAI 服务）、config.py、__main__.py（命令行）
tests/                   54 个离线测试
research/                支撑结论的脚本，包含走过的弯路
docs/                    protocol.md、intended-use.md
scripts/fetch_wasm.py    可选的 wasm 获取脚本，会打印 sha256
```

## 许可证

MIT。见 [LICENSE](LICENSE)。
