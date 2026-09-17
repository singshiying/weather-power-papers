"""Fetch new journal papers, filter weather-power planning, write Chinese markdown."""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

ROOT = Path(__file__).resolve().parent
JOURNALS_PATH = ROOT / "config" / "journals.json"
SEEN_PATH = ROOT / "data" / "seen_dois.json"
PAPERS_DIR = ROOT / "papers"

OPENALEX = "https://api.openalex.org/works"

WEATHER_TERMS = [
    "weather",
    "climate",
    "meteorolog",
    "nwp",
    "numerical weather",
    "extreme weather",
    "typhoon",
    "hurricane",
    "storm",
    "irradiance",
    "wind speed",
    "reanalysis",
    "气象",
    "气候",
    "极端天气",
    "台风",
    "数值天气预报",
    "再分析",
]

POWER_PLANNING_TERMS = [
    "power system",
    "electricity",
    "generation expansion",
    "transmission expansion",
    "capacity expansion",
    "unit commitment",
    "grid planning",
    "power planning",
    "renewable",
    "photovoltaic",
    "wind power",
    "energy storage",
    "规划",
    "电力系统",
    "电源",
    "电网",
    "新能源",
    "风光",
    "储能",
    "输电",
]


def reconstruct_abstract(inverted: Optional[Dict[str, List[int]]]) -> str:
    if not inverted:
        return ""
    positions: List[tuple[int, str]] = []
    for word, idxs in inverted.items():
        for idx in idxs:
            positions.append((idx, word))
    positions.sort(key=lambda item: item[0])
    return " ".join(word for _, word in positions)


def markdown_filename(zh_title: str, max_len: int = 80) -> str:
    title = (zh_title or "").strip()
    if not title:
        return "untitled.md"
    cleaned = re.sub(r'[\\/:*?"<>|]', " ", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    if not cleaned:
        return "untitled.md"
    if len(cleaned) > max_len:
        cleaned = cleaned[:max_len].rstrip()
    return f"{cleaned}.md"


def _contains_any(text: str, terms: Iterable[str]) -> bool:
    lowered = text.lower()
    return any(term.lower() in lowered for term in terms)


def is_relevant(title: str, abstract: str) -> bool:
    blob = f"{title or ''}\n{abstract or ''}"
    return _contains_any(blob, WEATHER_TERMS) and _contains_any(blob, POWER_PLANNING_TERMS)


def render_markdown(
    *,
    zh_title: str,
    en_title: str,
    authors: str,
    journal: str,
    doi: str,
    date: str,
    zh_abstract: str,
    en_abstract: str,
) -> str:
    doi_url = doi if doi.startswith("http") else (f"https://doi.org/{doi}" if doi else "")
    return (
        f"# {zh_title}\n\n"
        f"- 原文题目：{en_title}\n"
        f"- 作者：{authors}\n"
        f"- 期刊：{journal}\n"
        f"- DOI：{doi_url or '无'}\n"
        f"- 发表/入库日期：{date}\n\n"
        f"## 中文摘要\n\n{zh_abstract or '（无摘要）'}\n\n"
        f"## Abstract\n\n{en_abstract or '(No abstract)'}\n"
    )


class SeenStore:
    def __init__(self, path: Path):
        self.path = path
        self._dois = set()
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            self._dois = set(payload.get("dois", []))

    def has(self, doi: str) -> bool:
        return bool(doi) and doi.lower() in self._dois

    def add(self, doi: str) -> None:
        if doi:
            self._dois.add(doi.lower())

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = sorted(self._dois)
        self.path.write_text(
            json.dumps({"dois": ordered}, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def load_journals(path: Path = JOURNALS_PATH) -> List[Dict[str, str]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _openalex_mailto() -> str:
    return os.environ.get("OPENALEX_MAILTO", "papers@example.com")


def _get_json(url: str, retries: int = 5) -> Dict[str, Any]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"weather-power-digest/1.0 (mailto:{_openalex_mailto()})",
            "Accept": "application/json",
        },
    )
    last_error: Optional[Exception] = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503, 504} and attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise RuntimeError(f"HTTP {exc.code} for {url}") from exc
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    raise RuntimeError(f"Failed to fetch {url}") from last_error


def fetch_journal_works(issn: str, since: str, until: str) -> List[Dict[str, Any]]:
    """Works created or published in [since, until], OpenAlex dates are YYYY-MM-DD."""
    results: List[Dict[str, Any]] = []
    cursor = "*"
    while cursor:
        params = {
            "filter": (
                f"primary_location.source.issn:{issn},"
                f"from_created_date:{since},"
                f"to_created_date:{until}"
            ),
            "per-page": "50",
            "cursor": cursor,
            "mailto": _openalex_mailto(),
            "select": (
                "id,doi,title,authorships,primary_location,publication_date,"
                "created_date,abstract_inverted_index"
            ),
        }
        url = f"{OPENALEX}?{urllib.parse.urlencode(params)}"
        payload = _get_json(url)
        results.extend(payload.get("results") or [])
        cursor = (payload.get("meta") or {}).get("next_cursor")
        time.sleep(0.1)
    return results


def work_authors(work: Dict[str, Any]) -> str:
    names = []
    for item in work.get("authorships") or []:
        author = item.get("author") or {}
        name = author.get("display_name")
        if name:
            names.append(name)
    return "; ".join(names) if names else "未知"


def work_journal(work: Dict[str, Any], fallback: str) -> str:
    source = ((work.get("primary_location") or {}).get("source") or {})
    return source.get("display_name") or fallback


def work_doi(work: Dict[str, Any]) -> str:
    doi = work.get("doi") or ""
    return doi.replace("https://doi.org/", "").strip()


def work_to_record(work: Dict[str, Any], journal_name: str) -> Dict[str, str]:
    return {
        "title": work.get("title") or "Untitled",
        "authors": work_authors(work),
        "journal": work_journal(work, journal_name),
        "doi": work_doi(work),
        "date": work.get("publication_date") or work.get("created_date") or "",
        "abstract": reconstruct_abstract(work.get("abstract_inverted_index")),
        "openalex_id": work.get("id") or "",
    }


def translate(text: str, target_instruction: str) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return ""
    if not (text or "").strip():
        return ""
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    body = json.dumps(
        {
            "model": model,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "你是电力与气象交叉领域的学术翻译。"
                        "只输出译文，不要解释，不要加引号。"
                    ),
                },
                {
                    "role": "user",
                    "content": f"{target_instruction}\n\n{text}",
                },
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"{base}/chat/completions",
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (payload["choices"][0]["message"]["content"] or "").strip()


def unique_output_path(directory: Path, filename: str) -> Path:
    candidate = directory / filename
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    for i in range(2, 50):
        alt = directory / f"{stem}-{i}.md"
        if not alt.exists():
            return alt
    return directory / f"{stem}-{int(time.time())}.md"


def default_window() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    since = today - timedelta(days=2)
    return since.isoformat(), today.isoformat()


def collect_new_papers(since: str, until: str, seen: SeenStore) -> List[Dict[str, str]]:
    collected: List[Dict[str, str]] = []
    for journal in load_journals():
        works = fetch_journal_works(journal["issn"], since, until)
        for work in works:
            record = work_to_record(work, journal["name"])
            key = record["doi"] or record["openalex_id"]
            if not key or seen.has(key):
                continue
            if not is_relevant(record["title"], record["abstract"]):
                continue
            collected.append(record)
        time.sleep(0.2)
    return collected


def write_paper_markdown(record: Dict[str, str], out_dir: Path) -> Path:
    zh_title = translate(record["title"], "把论文题目译成简洁的中文学术标题：")
    if not zh_title:
        zh_title = record["title"]
    zh_abstract = translate(record["abstract"], "把论文摘要译成中文，保留专业术语：")
    if not zh_abstract:
        zh_abstract = "（未配置 OPENAI_API_KEY，摘要未翻译）\n\n" + (record["abstract"] or "")
    text = render_markdown(
        zh_title=zh_title,
        en_title=record["title"],
        authors=record["authors"],
        journal=record["journal"],
        doi=record["doi"],
        date=record["date"],
        zh_abstract=zh_abstract,
        en_abstract=record["abstract"],
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    path = unique_output_path(out_dir, markdown_filename(zh_title))
    path.write_text(text, encoding="utf-8")
    return path


def run(since: Optional[str] = None, until: Optional[str] = None) -> int:
    if not since or not until:
        since, until = default_window()
    seen = SeenStore(SEEN_PATH)
    papers = collect_new_papers(since, until, seen)
    day_dir = PAPERS_DIR / date.today().isoformat()
    written = 0
    for record in papers:
        write_paper_markdown(record, day_dir)
        seen.add(record["doi"] or record["openalex_id"])
        written += 1
    seen.save()
    summary = PAPERS_DIR / date.today().isoformat() / "_本次检索.md"
    if papers:
        lines = [
            f"# {date.today().isoformat()} 气象电力规划新文",
            "",
            f"- 窗口：{since} ~ {until}（OpenAlex created_date）",
            f"- 命中：{written} 篇",
            "",
        ]
        for record in papers:
            lines.append(f"- {record['journal']}｜{record['title']}")
        summary.parent.mkdir(parents=True, exist_ok=True)
        summary.write_text("\n".join(lines) + "\n", encoding="utf-8")
    else:
        day_dir.mkdir(parents=True, exist_ok=True)
        summary.write_text(
            f"# {date.today().isoformat()} 气象电力规划新文\n\n"
            f"窗口 {since} ~ {until} 内，10 本目标期刊没有新的相关论文"
            f"（或摘要尚不可用）。\n",
            encoding="utf-8",
        )
    print(f"window={since}..{until} new={written}")
    return 0


def main(argv: List[str]) -> int:
    since = until = None
    if len(argv) >= 3:
        since, until = argv[1], argv[2]
    return run(since, until)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
