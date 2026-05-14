"""
Scorer 测试 — RED Phase
测试3维评分引擎: 互联网热度 / 角度独特度 / 预测传播热度
每个维度需附带证据，综合评分公式: total = hot*0.3 + unique*0.4 + spread*0.3
"""
import pytest
from src.scorer import (
    Scorer,
    score_hot,
    score_unique,
    score_spread,
    compute_total,
    generate_evidence_hot,
    generate_evidence_unique,
    generate_evidence_spread,
    SCORE_DIMENSIONS,
    WEIGHTS,
)


class TestScoreDimensions:
    def test_three_dimensions_defined(self):
        assert len(SCORE_DIMENSIONS) == 3
        assert "互联网热度" in SCORE_DIMENSIONS
        assert "角度独特度" in SCORE_DIMENSIONS
        assert "预测传播热度" in SCORE_DIMENSIONS

    def test_weights_sum_to_one(self):
        total = sum(WEIGHTS.values())
        assert abs(total - 1.0) < 0.01
        assert WEIGHTS["互联网热度"] == 0.30
        assert WEIGHTS["角度独特度"] == 0.40
        assert WEIGHTS["预测传播热度"] == 0.30


class TestHotScore:
    def test_score_hot_with_rich_data(self):
        external = {
            "wechat_count": 128,
            "web_count": 2400,
            "newsnow_mentions": 15,
            "hot_level": "hot",
        }
        result = score_hot(external)

        assert 7.0 <= result["value"] <= 10.0
        assert len(result["evidence"]) > 0

    def test_score_hot_with_cold_data(self):
        external = {
            "wechat_count": 2,
            "web_count": 50,
            "newsnow_mentions": 0,
            "hot_level": "cold",
        }
        result = score_hot(external)

        assert 0.0 <= result["value"] <= 4.0
        assert len(result["evidence"]) > 0

    def test_score_hot_with_no_data(self):
        result = score_hot(None)
        assert result["value"] == 0.0


class TestUniqueScore:
    def test_score_unique_with_low_competition(self):
        external = {"wechat_matches": 2, "wechat_articles": 128}
        forum = [{"novelty": 9}, {"novelty": 8}, {"novelty": 8}]
        graph = {"gaps_count": 5}

        result = score_unique(external, forum, graph)

        assert 7.0 <= result["value"] <= 10.0
        assert len(result["evidence"]) > 0
        assert any(c in result["evidence"] for c in ["98%", "8.3", "5个"])

    def test_score_unique_with_high_competition(self):
        external = {"wechat_matches": 80, "wechat_articles": 100}
        forum = [{"novelty": 3}, {"novelty": 2}]
        graph = {"gaps_count": 0}

        result = score_unique(external, forum, graph)

        assert result["value"] <= 4.0

    def test_score_unique_no_data(self):
        result = score_unique(None, None, None)
        assert result["value"] == 0.0


class TestSpreadScore:
    def test_score_spread_with_high_conflict(self):
        mirofish = {"conflict_intensity": 8.5}
        forum = [{"controversy": True}, {"controversy": True}]
        sentiments = {"争议": 10, "猎奇": 8, "共情": 5}

        result = score_spread(mirofish, forum, sentiments)

        assert 7.0 <= result["value"] <= 10.0

    def test_score_spread_with_low_conflict(self):
        mirofish = {"conflict_intensity": 1.0}
        forum = [{"controversy": False}]
        sentiments = {"争议": 1, "猎奇": 1, "共情": 1}

        result = score_spread(mirofish, forum, sentiments)

        assert result["value"] <= 4.0

    def test_score_spread_no_data(self):
        result = score_spread(None, None, None)
        assert result["value"] == 0.0


class TestEvidenceGeneration:
    def test_hot_evidence_includes_numbers(self):
        evidence = generate_evidence_hot(wechat_count=128, web_count=2400, newsnow_mentions=15, hot_level="hot")
        assert "128" in evidence or "hot" in evidence.lower()

    def test_unique_evidence_includes_gaps(self):
        evidence = generate_evidence_unique(wechat_matches=2, wechat_articles=128, avg_novelty=8.5, gaps=5)
        assert "2" in evidence or "5" in evidence or "128" in evidence

    def test_spread_evidence_includes_controversy(self):
        evidence = generate_evidence_spread(conflict=8.5, controversy_count=12, sentiment_summary="猎奇+争议")
        assert len(evidence) > 0


class TestComputeTotal:
    def test_weighted_average(self):
        hot = {"value": 7.0, "evidence": ""}
        unique = {"value": 8.0, "evidence": ""}
        spread = {"value": 6.0, "evidence": ""}

        result = compute_total(hot, unique, spread)

        expected = 7.0 * 0.3 + 8.0 * 0.4 + 6.0 * 0.3
        assert abs(result["total_score"] - expected) < 0.01

    def test_returns_all_three_dimensions(self):
        result = compute_total(
            {"value": 7, "evidence": "e1"},
            {"value": 8, "evidence": "e2"},
            {"value": 6, "evidence": "e3"},
        )
        assert result["hot_score"]["value"] == 7
        assert result["unique_score"]["value"] == 8
        assert result["spread_score"]["value"] == 6
        assert "total_score" in result


class TestScorerIntegration:
    def test_score_aggregates_all_dims(self):
        scorer = Scorer()

        analysis_data = {
            "external": {
                "wechat_count": 128,
                "web_count": 2400,
                "newsnow_mentions": 15,
                "hot_level": "hot",
                "wechat_matches": 5,
                "wechat_articles": 128,
            },
            "forum": [
                {"novelty": 9, "controversy": True},
                {"novelty": 8, "controversy": True},
                {"novelty": 6, "controversy": False},
            ],
            "mirofish": {"conflict_intensity": 7.2},
            "graph": {"gaps_count": 4},
            "sentiments": {"争议": 10, "猎奇": 8, "共情": 5},
        }

        result = scorer.score(analysis_data)

        assert "hot_score" in result
        assert "unique_score" in result
        assert "spread_score" in result
        assert "total_score" in result
        assert 0.0 <= result["total_score"] <= 10.0
        assert len(result["hot_score"]["evidence"]) > 0
        assert len(result["unique_score"]["evidence"]) > 0
        assert len(result["spread_score"]["evidence"]) > 0

    def test_score_with_minimal_data(self):
        scorer = Scorer()
        result = scorer.score({})

        assert result["total_score"] == 0.0
        assert result["hot_score"]["value"] == 0.0
        assert result["unique_score"]["value"] == 0.0
        assert result["spread_score"]["value"] == 0.0

    def test_score_for_sub_series(self):
        scorer = Scorer()

        sub_analysis = {
            "external": {
                "wechat_count": 35,
                "web_count": 500,
                "hot_level": "warm",
                "wechat_matches": 3,
                "wechat_articles": 35,
            },
            "forum": [
                {"novelty": 7, "controversy": True},
            ],
            "mirofish": {"conflict_intensity": 4.0},
            "graph": {"gaps_count": 1},
            "sentiments": {"争议": 3, "猎奇": 2, "共情": 4},
        }

        result = scorer.score(analysis_data=sub_analysis)

        assert result["total_score"] > 0.0
        assert isinstance(result["hot_score"]["value"], (int, float))
        assert isinstance(result["unique_score"]["value"], (int, float))
        assert isinstance(result["spread_score"]["value"], (int, float))

    def test_boundary_scores_in_range(self):
        scorer = Scorer()

        max_data = {
            "external": {
                "wechat_count": 10000, "web_count": 100000,
                "newsnow_mentions": 500, "hot_level": "hot",
                "wechat_matches": 0, "wechat_articles": 1,
            },
            "forum": [
                {"novelty": 10, "controversy": True},
                {"novelty": 10, "controversy": True},
            ],
            "mirofish": {"conflict_intensity": 10.0},
            "graph": {"gaps_count": 100},
            "sentiments": {"争议": 100, "猎奇": 100, "共情": 100},
        }

        result = scorer.score(max_data)

        assert 0.0 <= result["total_score"] <= 10.0
        assert 0.0 <= result["hot_score"]["value"] <= 10.0
        assert 0.0 <= result["unique_score"]["value"] <= 10.0
        assert 0.0 <= result["spread_score"]["value"] <= 10.0

    def test_format_score_table(self):
        scorer = Scorer()
        result = scorer.score({
            "external": {"wechat_count": 128, "web_count": 2400, "hot_level": "hot", "wechat_matches": 5, "wechat_articles": 128},
            "forum": [{"novelty": 9, "controversy": True}],
            "mirofish": {"conflict_intensity": 7.2},
            "graph": {"gaps_count": 4},
            "sentiments": {"争议": 10, "猎奇": 8, "共情": 5},
        })

        table = scorer.format_score_table(result)

        assert "互联网热度" in table
        assert "角度独特度" in table
        assert "预测传播热度" in table
        assert "综合评分" in table or "total" in table.lower()
