"""Cleaning unit tests — protocol #21 §5 (server-side text -> clean fields)."""

import pytest

from services.api.app.cleaning import (
    clean_company_name,
    parse_degree,
    parse_experience,
    parse_salary,
)


class TestParseSalary:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("15-25K·14薪", (15.0, 25.0, "month_K")),
            ("15-25K", (15.0, 25.0, "month_K")),
            ("8-13K·13薪", (8.0, 13.0, "month_K")),
            ("200-300元/天", (200.0, 300.0, "day")),
            ("50-80元/时", (50.0, 80.0, "hour")),
            ("15-25万/年", (150000.0, 250000.0, "year")),
            ("1-2万", (10000.0, 20000.0, "month_yuan")),
            ("300-500元/月", (300.0, 500.0, "month_yuan")),
            ("15-20K", (15.0, 20.0, "month_K")),
        ],
    )
    def test_known_formats(self, text, expected):
        assert parse_salary(text) == expected

    @pytest.mark.parametrize("text", ["面议", "薪资面议", "", None])
    def test_negotiable_or_empty(self, text):
        assert parse_salary(text) == (None, None, "unknown")

    def test_single_value_range_collapses(self):
        low, high, unit = parse_salary("20K")
        assert low == high == 20.0
        assert unit == "month_K"


class TestParseExperience:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("1-3年", (1, 3)),
            ("3-5年", (3, 5)),
            ("经验不限", (0, 0)),
            ("学历不限", (0, 0)),
            ("在校/应届生", (0, 0)),
            ("应届生", (0, 0)),
            ("5年以上", (5, None)),
            ("3年以内", (0, 3)),
            ("经验不限", (0, 0)),
        ],
    )
    def test_known_formats(self, text, expected):
        assert parse_experience(text) == expected

    @pytest.mark.parametrize("text", ["", None, "无结构文本"])
    def test_unparseable(self, text):
        assert parse_experience(text) == (None, None)


class TestParseDegree:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("本科", "bachelor"),
            ("大专", "associate"),
            ("硕士", "master"),
            ("博士", "doctor"),
            ("高中", "secondary"),
            ("学历不限", "unrestricted"),
            ("本科及以上", "bachelor"),
        ],
    )
    def test_known(self, text, expected):
        assert parse_degree(text) == expected

    @pytest.mark.parametrize("text", ["", None, "神秘学历"])
    def test_unparseable(self, text):
        assert parse_degree(text) is None


class TestCleanCompanyName:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("杭州天星橙人工智能收藏", "杭州天星橙人工智能"),
            ("魔筷科技 已收藏", "魔筷科技"),
            ("  同花顺收藏", "同花顺"),
        ],
    )
    def test_strips_trailing_favorite(self, text, expected):
        assert clean_company_name(text) == expected

    @pytest.mark.parametrize("text", ["某某收藏文化有限公司", "正常公司名"])
    def test_keeps_names_with_midstring_keyword(self, text):
        assert clean_company_name(text) == text

    @pytest.mark.parametrize("text", ["", None, "收藏", "  已收藏 "])
    def test_blank_after_strip_is_none(self, text):
        assert clean_company_name(text) is None
