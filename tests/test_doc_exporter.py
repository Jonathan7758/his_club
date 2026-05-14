"""
DocExporter 测试 — RED Phase
测试: MD系列设计文档生成，汇总主主题/评分/子系列/子评分
"""
import pytest
from datetime import datetime
from src.doc_exporter import DocExporter, format_md_header, format_scores_section, format_sub_series_table


class TestFormatHelpers:
    def test_format_md_header(self):
        result = format_md_header("安史之乱", "2026-05-09", 7.83)

        assert "# 微信公众号系列设计文档" in result
        assert "安史之乱" in result
        assert "2026-05-09" in result
        assert "7.83" in result

    def test_format_scores_section(self):
        scores = {
            "hot_score": {"value": 7.2, "evidence": "微信128篇"},
            "unique_score": {"value": 8.5, "evidence": "竞品覆盖98%"},
            "spread_score": {"value": 7.8, "evidence": "冲突度7.2"},
            "total_score": 7.83,
        }
        result = format_scores_section(scores)

        assert "## 多维度评分" in result
        assert "7.2" in result
        assert "8.5" in result
        assert "7.8" in result
        assert "7.83" in result

    def test_format_sub_series_table(self):
        sub_series = [
            {
                "dimension": "政治制度",
                "name": "权力的代价",
                "viewpoint": "节度使制度是根本原因",
                "outline": ["府兵到募兵", "三权合一"],
                "quotes": ["忠诚成了奢侈品"],
                "scores": {
                    "hot_score": {"value": 6.5},
                    "unique_score": {"value": 9.0},
                    "spread_score": {"value": 7.5},
                    "total_score": 7.8,
                }
            }
        ]

        result = format_sub_series_table(sub_series)

        assert "权力的代价" in result
        assert "节度使制度是根本原因" in result
        assert "府兵到募兵" in result


class TestDocExporter:
    def test_export_returns_markdown(self):
        exporter = DocExporter()

        session_data = {
            "main_topic": "安史之乱的多维度分析",
            "content": "原始分析内容...",
            "key_points": ["政治制度崩溃", "经济失衡", "军事布局漏洞"],
            "scores": {
                "hot_score": {"value": 7.2, "evidence": "搜狗微信128篇 | 网页2400条"},
                "unique_score": {"value": 8.5, "evidence": "竞品覆盖98%未重叠 | 平均新颖度8.3/10"},
                "spread_score": {"value": 7.8, "evidence": "博弈冲突度7.2 | 争议论点12个"},
                "total_score": 7.83,
            },
            "sub_series": [
                {
                    "dimension": "政治制度",
                    "name": "权力的代价",
                    "viewpoint": "节度使制度是安史之乱的根本制度性原因",
                    "outline": ["府兵制到募兵制", "节度使三权合一", "中央与地方权力博弈", "制度设计的代价"],
                    "quotes": ["当一个将军同时掌握军饷和任命权，忠诚就成了奢侈品。", "权力失衡的代价由整个帝国承担。"],
                },
                {
                    "dimension": "经济财政",
                    "name": "一场叛乱的经济账",
                    "viewpoint": "安史之乱暴露了唐朝财政体系的深层危机",
                    "outline": ["租庸调到两税法", "军费黑洞", "商业和税收的博弈"],
                    "quotes": ["战争是最昂贵的消费。", "当税收系统失灵，帝国就开始失血。"],
                },
            ],
            "sub_scores": [
                {
                    "sub_index": 0,
                    "hot_score": 6.5, "unique_score": 9.0,
                    "spread_score": 7.5, "total_score": 7.8,
                }
            ],
        }

        md = exporter.export(session_data)

        assert isinstance(md, str)
        assert len(md) > 0
        assert "# 微信公众号系列设计文档" in md
        assert "安史之乱的多维度分析" in md
        assert "权力的代价" in md
        assert "7.83" in md

    def test_export_attaches_sub_scores_to_series(self):
        exporter = DocExporter()

        session_data = {
            "main_topic": "测试主题",
            "content": "内容",
            "key_points": ["点1"],
            "scores": {
                "hot_score": {"value": 7.0, "evidence": ""},
                "unique_score": {"value": 7.0, "evidence": ""},
                "spread_score": {"value": 7.0, "evidence": ""},
                "total_score": 7.0,
            },
            "sub_series": [
                {"dimension": "政治制度", "name": "子1", "viewpoint": "v", "outline": ["a"], "quotes": ["q"]},
            ],
            "sub_scores": [
                {"sub_index": 0, "hot_score": 6.5, "unique_score": 9.0, "spread_score": 7.5, "total_score": 7.8},
            ],
        }

        md = exporter.export(session_data)

        assert "6.5" in md
        assert "7.8" in md

    def test_export_without_sub_scores_still_works(self):
        exporter = DocExporter()

        session_data = {
            "main_topic": "测试主题",
            "content": "内容",
            "key_points": ["点1"],
            "scores": {
                "hot_score": {"value": 7.0, "evidence": ""},
                "unique_score": {"value": 7.0, "evidence": ""},
                "spread_score": {"value": 7.0, "evidence": ""},
                "total_score": 7.0,
            },
            "sub_series": [
                {"dimension": "政治制度", "name": "子1", "viewpoint": "v", "outline": ["a"], "quotes": ["q"]},
            ],
        }

        md = exporter.export(session_data)

        assert "# 微信公众号系列设计文档" in md
        assert "子1" in md

    def test_export_minimal_data(self):
        exporter = DocExporter()

        md = exporter.export({})

        assert isinstance(md, str)
        assert len(md) > 0

    def test_file_name_generation(self):
        exporter = DocExporter()
        today = datetime.now().strftime("%Y%m%d")

        name = exporter.generate_filename("安史之乱")
        assert "安史之乱" in name
        assert today in name
        assert name.endswith(".md")
