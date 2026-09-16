"""Text -> clean domain fields (protocol #21 §5).

The extension sends original plain text captured from BOSS JSON; parsing of
salary / experience / degree into clean columns happens here, server-side.

Unparseable text yields ``None`` / ``"unknown"`` — never a guessed value.
"""

import re
from typing import Literal

SalaryUnit = Literal["month_K", "month_yuan", "day", "hour", "year", "unknown"]

_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-~～至]\s*(\d+(?:\.\d+)?)")
_SINGLE_RE = re.compile(r"(\d+(?:\.\d+)?)")


def parse_salary(text: str | None) -> tuple[float | None, float | None, SalaryUnit]:
    raw = re.sub(r"\s+", "", str(text or ""))
    if not raw or "面议" in raw:
        return None, None, "unknown"

    range_match = _RANGE_RE.search(raw)
    if range_match:
        low_s, high_s = range_match.group(1), range_match.group(2)
    else:
        single = _SINGLE_RE.search(raw)
        low_s = high_s = single.group(1) if single else None
    if low_s is None:
        return None, None, "unknown"

    low = float(low_s)
    high = float(high_s)

    if "K" in raw.upper():
        unit: SalaryUnit = "month_K"
    elif "天" in raw:
        unit = "day"
    elif "时" in raw:
        unit = "hour"
    elif "万" in raw:
        # BOSS bare "N-M万" denotes monthly salary; "万/年" is annual.
        low *= 10000
        high *= 10000
        unit = "year" if "年" in raw else "month_yuan"
    elif "年" in raw:
        unit = "year"
    elif "元" in raw:
        unit = "month_yuan"
    else:
        unit = "unknown"

    if high < low:
        high = low
    return low, high, unit


def parse_experience(text: str | None) -> tuple[int | None, int | None]:
    raw = str(text or "")
    if not raw:
        return None, None
    if "不限" in raw or "在校" in raw or "应届" in raw:
        return 0, 0
    if "以内" in raw or "以下" in raw:
        number = _SINGLE_RE.search(raw)
        return 0, int(number.group(1)) if number else 0
    if "以上" in raw:
        number = _SINGLE_RE.search(raw)
        return (int(number.group(1)), None) if number else (None, None)

    range_match = _RANGE_RE.search(raw)
    if range_match:
        return int(float(range_match.group(1))), int(float(range_match.group(2)))
    single = _SINGLE_RE.search(raw)
    if single and "年" in raw:
        years = int(single.group(1))
        return years, years
    return None, None


_DEGREE_MAP = (
    ("博士", "doctor"),
    ("硕士", "master"),
    ("本科", "bachelor"),
    ("大专", "associate"),
    ("中专", "secondary"),
    ("高中", "secondary"),
)


_TRAILING_FAVORITE_RE = re.compile(r"(?:已?收藏)+$")


def clean_company_name(text: str | None) -> str | None:
    """Company-page name nodes merge in the trailing 收藏/已收藏 button label.

    Only a trailing favorite marker is removed; a name merely containing
    收藏 mid-string (e.g. 某某收藏文化有限公司) is kept verbatim.
    """
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return None
    stripped = _TRAILING_FAVORITE_RE.sub("", raw).strip()
    return stripped or None


def parse_degree(text: str | None) -> str | None:
    raw = str(text or "")
    if not raw:
        return None
    if "不限" in raw:
        return "unrestricted"
    for needle, code in _DEGREE_MAP:
        if needle in raw:
            return code
    return None
