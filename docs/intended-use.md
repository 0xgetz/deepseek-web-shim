# Intended use, and what this project refuses to do

Read this before running the shim. It is short, and it is the part of the
project that matters most.

## What this is

A research tool. It exists to document, in reproducible code, two things about
a web chat client: how its proof-of-work challenge is constructed and solved,
and how its session and streaming flow is shaped. The value is the
documentation and the testable implementation, both verified against the
vendor's own wasm module.

It is also useful as a local lab artifact: you can point any OpenAI-compatible
tool at it and watch exactly which requests go out, which is a real reason to
have it in a research environment.

## What it is not

- Not a way to obtain free or anonymous access to anything. It carries no
  credentials and it never will. You supply your own session token, so every
  request is billed to, rate limited by, and attributed to your own account.
- Not a bypass. The proof of work is not defeated here; it is solved, exactly
  as a browser solves it. The CAPTCHA on signup and login is untouched, and
  no code here attempts it.
- Not a vulnerability report. Reimplementing a client-side proof of work is what
  the scheme is for. A CAPTCHA that blocks automated signup is a control
  working correctly. Neither of those is a bug, and this project does not
  present them as one.

## Things contributions may never add

1. Bundled or harvested credentials, cookies, or session tokens.
2. Account creation, CAPTCHA solving, or any anti-bot bypass helper.
3. Wrappers that present the result as an anonymous or "unlimited" API while
   quietly spending somebody else's session.

## Your responsibilities

- **Terms of service.** Automated access to a web interface may violate the
  terms that govern that service. That is your call to make and your risk to
  carry, not something this repository can grant you.
- **Account risk.** Enforcement is aimed at accounts, and an automated client is
  trivially distinguishable from a person by pattern and volume. Use a session
  you can afford to lose.
- **Your token is a credential.** The captured session is written to
  `~/.deepseek-web-shim/session.json` with mode `0600`. Do not commit it, do
  not paste it into issues, and delete it when you are done.
- **Fragility.** This parses an undocumented protocol. It will break when
  upstream changes, and when it does it should fail with a clear error rather
  than silently returning wrong output. If you find a case where it does the
  latter, that is a bug worth reporting.
- **Legality where you are.** Anti-circumvention and computer misuse rules vary
  by jurisdiction. Understand yours before running this.

## If you want stable access

Use the official API. It is documented, it is stable, it does not require
reverse engineering, and it removes every caveat above. This project is for
studying the web flow, not for depending on it.
