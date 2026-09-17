# 每日气象电力规划论文摘要

GitHub Actions 每天 UTC 01:00（北京时间 09:00）从 OpenAlex 检索 10 本目标期刊的新论文，筛「气象/气候 × 电力规划」相关条目，把摘要译成中文，写成 Markdown。文件在 `papers/日期/中文题目.md`。

## 仓库 Secrets

在 GitHub → Settings → Secrets and variables → Actions 中添加：

| 名称 | 必填 | 说明 |
|------|------|------|
| `OPENAI_API_KEY` | 是 | OpenAI / DeepSeek 等兼容接口的密钥 |
| `OPENAI_BASE_URL` | 否 | 默认 `https://api.openai.com/v1`；DeepSeek 用 `https://api.deepseek.com/v1` |
| `OPENAI_MODEL` | 否 | 默认 `gpt-4o-mini`；DeepSeek 用 `deepseek-chat` |
| `OPENALEX_MAILTO` | 建议 | 你的邮箱，供 OpenAlex 礼貌池使用 |

没有翻译密钥时仍会落盘，中文摘要处会标注未翻译。

## 本地试跑

```bash
export OPENAI_API_KEY=...
python3 paper_digest.py
# 或指定日期窗口（UTC）
python3 paper_digest.py 2026-09-15 2026-09-17
```

手动触发：GitHub → Actions → Daily weather-power papers → Run workflow。
