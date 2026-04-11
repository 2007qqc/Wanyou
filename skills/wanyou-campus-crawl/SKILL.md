---
name: wanyou-campus-crawl
description: Collect Wanyou raw Markdown from individual campus sources, including WeChat, public sites, and login-only sites. Use when Codex needs to test one crawler module, generate a source-specific Markdown preview, or debug crawl failures before LLM synthesis and richtext export.
---

# Wanyou Campus Crawl

## Purpose

Use this skill to run one or more crawler modules independently and produce module-level raw/final Markdown plus optional HTML.

Supported modules:

- `wechat`: 公众号信息
- `lib`: 图书馆信息
- `hall`: 新清华学堂
- `physics`: 物理系学术报告
- `info`: 教务通知，requires unified login
- `myhome`: 家园网信息，requires unified login
- `public`: `lib hall physics wechat`
- `login`: `info myhome`
- `all`: all modules

## Commands

Run only WeChat and generate its Wanyou Markdown/HTML:

```powershell
python scripts/run_wanyou_module.py wechat
```


Generate Markdown and richtext HTML explicitly:

```powershell
python scripts/run_wanyou_module.py wechat --with-richtext
```

Run WeChat Markdown only, without richtext HTML:

```powershell
python scripts/run_wanyou_module.py wechat --md-only
```

Run each public module separately:

```powershell
python scripts/run_wanyou_module.py lib
python scripts/run_wanyou_module.py hall
python scripts/run_wanyou_module.py physics
python scripts/run_wanyou_module.py wechat
```

Run login-only sources with shared Tsinghua authentication:

```powershell
python scripts/run_wanyou_module.py info
python scripts/run_wanyou_module.py myhome
python scripts/run_wanyou_module.py login
```

Run all public sources:

```powershell
python scripts/run_wanyou_module.py public
```

Run all modules:

```powershell
python scripts/run_wanyou_module.py all
```

Equivalent skill wrapper:

```powershell
python skills/wanyou-campus-crawl/scripts/run_wanyou_campus_crawl.py wechat
python skills/wanyou-campus-crawl/scripts/run_wanyou_campus_crawl.py public --md-only
```

## Debug Rules

- If WeChat reports `invalid session` or `ret=200003`, refresh `WECHAT_PUBLIC_API_KEY` or the upstream session/key.
- Use `--md-only` when only Markdown is needed. Use `--raw-only --md-only` when checking crawler output before LLM synthesis.
- Use `login` when testing `info` and `myhome` together, because they share one unified-auth browser session.
- Inspect `output/module_<modules>_<timestamp>/debug/` for login and selector snapshots.
