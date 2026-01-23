"""Tests for the API compatibility coverage report generator.

This module provides comprehensive tests for:
- AggregateReport data aggregation and calculations
- BadgeGenerator SVG output and color mapping
- HTMLReportGenerator standalone HTML generation
- MarkdownReportGenerator documentation output
- ReportGenerator coordination and file output
- CLI interface functionality
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.compat.coverage_validator import (
    ActionCoverageReport,
    EntityCoverageReport,
    EntityPriority,
    MissingEntity,
)
from tests.compat.report_generator import (
    AggregateReport,
    BadgeColor,
    BadgeGenerator,
    FieldCoverageReport,
    HTMLReportGenerator,
    MarkdownReportGenerator,
    ReportGenerator,
    TrendData,
    generate_report,
    main,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_entity_report() -> EntityCoverageReport:
    """Create a sample entity coverage report."""
    return EntityCoverageReport(
        total_entities=100,
        implemented_entities=17,
        missing_entities=[
            MissingEntity(name="Relationship", priority=EntityPriority.CRITICAL),
            MissingEntity(name="Case", priority=EntityPriority.HIGH),
            MissingEntity(name="CustomField", priority=EntityPriority.MEDIUM),
        ],
        implemented_names={
            "Contact",
            "Individual",
            "Organization",
            "Household",
            "Activity",
            "Address",
            "Email",
            "Phone",
            "Contribution",
            "Event",
            "Group",
            "GroupContact",
            "Membership",
            "Note",
            "Participant",
            "Tag",
            "EntityTag",
        },
    )


@pytest.fixture
def sample_action_reports() -> dict[str, ActionCoverageReport]:
    """Create sample action coverage reports."""
    return {
        "Contact": ActionCoverageReport(
            entity_name="Contact",
            available_actions={"get", "create", "update", "delete", "save", "getFields"},
            implemented_actions={"get", "create", "update", "delete", "get_fields"},
        ),
        "Activity": ActionCoverageReport(
            entity_name="Activity",
            available_actions={"get", "create", "update", "delete", "save"},
            implemented_actions={"get", "create", "update", "delete"},
        ),
    }


@pytest.fixture
def sample_field_reports() -> dict[str, FieldCoverageReport]:
    """Create sample field coverage reports."""
    return {
        "Contact": FieldCoverageReport(
            entity_name="Contact",
            total_api_fields=45,
            implemented_fields=40,
            missing_fields=["custom_1", "custom_2", "image_URL", "legal_name", "sic_code"],
            extra_fields=[],
            type_mismatches=1,
        ),
        "Activity": FieldCoverageReport(
            entity_name="Activity",
            total_api_fields=25,
            implemented_fields=22,
            missing_fields=["weight", "is_current_revision", "original_id"],
            extra_fields=["computed_field"],
            type_mismatches=0,
        ),
    }


@pytest.fixture
def sample_aggregate_report(
    sample_entity_report: EntityCoverageReport,
    sample_action_reports: dict[str, ActionCoverageReport],
    sample_field_reports: dict[str, FieldCoverageReport],
) -> AggregateReport:
    """Create a complete sample aggregate report."""
    return AggregateReport(
        entity_report=sample_entity_report,
        action_reports=sample_action_reports,
        field_reports=sample_field_reports,
        civicrm_version="5.74",
        civi_py_version="0.1.0",
        trends=[
            TrendData(
                date="2024-01-01",
                entity_coverage=15.0,
                action_coverage=70.0,
                field_coverage=80.0,
                overall_score=50.0,
            ),
            TrendData(
                date="2024-01-15",
                entity_coverage=17.0,
                action_coverage=75.0,
                field_coverage=85.0,
                overall_score=55.0,
            ),
        ],
    )


@pytest.fixture
def temp_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    output_dir = tmp_path / "coverage_reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


# =============================================================================
# TrendData Tests
# =============================================================================


class TestTrendData:
    """Tests for TrendData class."""

    def test_to_dict(self) -> None:
        """Test conversion to dictionary."""
        trend = TrendData(
            date="2024-01-15",
            entity_coverage=85.5,
            action_coverage=90.25,
            field_coverage=88.0,
            overall_score=87.5,
        )

        result = trend.to_dict()

        assert result["date"] == "2024-01-15"
        assert result["entity_coverage"] == 85.5
        assert result["action_coverage"] == 90.25
        assert result["field_coverage"] == 88.0
        assert result["overall_score"] == 87.5

    def test_from_dict(self) -> None:
        """Test creation from dictionary."""
        data = {
            "date": "2024-01-15",
            "entity_coverage": 85.5,
            "action_coverage": 90.25,
            "field_coverage": 88.0,
            "overall_score": 87.5,
        }

        trend = TrendData.from_dict(data)

        assert trend.date == "2024-01-15"
        assert trend.entity_coverage == 85.5
        assert trend.action_coverage == 90.25
        assert trend.field_coverage == 88.0
        assert trend.overall_score == 87.5

    def test_roundtrip(self) -> None:
        """Test dict roundtrip preserves data."""
        original = TrendData(
            date="2024-06-15",
            entity_coverage=75.0,
            action_coverage=80.0,
            field_coverage=85.0,
            overall_score=79.0,
        )

        restored = TrendData.from_dict(original.to_dict())

        assert restored.date == original.date
        assert restored.entity_coverage == original.entity_coverage
        assert restored.overall_score == original.overall_score


# =============================================================================
# FieldCoverageReport Tests
# =============================================================================


class TestFieldCoverageReport:
    """Tests for FieldCoverageReport class."""

    def test_coverage_percentage(self) -> None:
        """Test field coverage percentage calculation."""
        report = FieldCoverageReport(
            entity_name="Contact",
            total_api_fields=100,
            implemented_fields=85,
        )

        assert report.coverage_percentage == 85.0

    def test_coverage_percentage_zero_total(self) -> None:
        """Test coverage with zero total fields."""
        report = FieldCoverageReport(
            entity_name="Empty",
            total_api_fields=0,
            implemented_fields=0,
        )

        assert report.coverage_percentage == 100.0

    def test_coverage_percentage_zero_implemented(self) -> None:
        """Test coverage with zero implemented fields."""
        report = FieldCoverageReport(
            entity_name="NotStarted",
            total_api_fields=50,
            implemented_fields=0,
        )

        assert report.coverage_percentage == 0.0

    def test_type_accuracy(self) -> None:
        """Test type accuracy calculation."""
        report = FieldCoverageReport(
            entity_name="Contact",
            total_api_fields=100,
            implemented_fields=50,
            type_mismatches=5,
        )

        assert report.type_accuracy == 90.0  # 45/50 = 90%

    def test_type_accuracy_no_mismatches(self) -> None:
        """Test type accuracy with no mismatches."""
        report = FieldCoverageReport(
            entity_name="Contact",
            total_api_fields=100,
            implemented_fields=50,
            type_mismatches=0,
        )

        assert report.type_accuracy == 100.0

    def test_type_accuracy_zero_implemented(self) -> None:
        """Test type accuracy with zero implemented fields."""
        report = FieldCoverageReport(
            entity_name="Empty",
            total_api_fields=100,
            implemented_fields=0,
            type_mismatches=0,
        )

        assert report.type_accuracy == 100.0

    def test_to_dict(self) -> None:
        """Test dictionary serialization."""
        report = FieldCoverageReport(
            entity_name="Contact",
            total_api_fields=50,
            implemented_fields=45,
            missing_fields=["field1", "field2"],
            extra_fields=["extra1"],
            type_mismatches=2,
        )

        result = report.to_dict()

        assert result["entity_name"] == "Contact"
        assert result["total_api_fields"] == 50
        assert result["implemented_fields"] == 45
        assert result["coverage_percentage"] == 90.0
        assert len(result["missing_fields"]) == 2
        assert len(result["extra_fields"]) == 1
        assert result["type_mismatches"] == 2


# =============================================================================
# AggregateReport Tests
# =============================================================================


class TestAggregateReport:
    """Tests for AggregateReport class."""

    def test_entity_coverage(self, sample_aggregate_report: AggregateReport) -> None:
        """Test entity coverage property."""
        # 17/100 = 17%
        assert sample_aggregate_report.entity_coverage == 17.0

    def test_action_coverage(self, sample_aggregate_report: AggregateReport) -> None:
        """Test action coverage averaging."""
        # Average of Contact and Activity coverage
        coverage = sample_aggregate_report.action_coverage
        assert 0 <= coverage <= 100

    def test_field_coverage(self, sample_aggregate_report: AggregateReport) -> None:
        """Test field coverage averaging."""
        coverage = sample_aggregate_report.field_coverage
        # Contact: 40/45 = 88.89%, Activity: 22/25 = 88%
        assert 85 <= coverage <= 95

    def test_type_accuracy(self, sample_aggregate_report: AggregateReport) -> None:
        """Test type accuracy averaging."""
        accuracy = sample_aggregate_report.type_accuracy
        # Contact: 39/40 = 97.5%, Activity: 22/22 = 100%
        assert accuracy >= 95

    def test_overall_score(self, sample_aggregate_report: AggregateReport) -> None:
        """Test weighted overall score calculation."""
        score = sample_aggregate_report.overall_score
        # Score is weighted combination
        assert 0 <= score <= 100

    def test_entities_implemented(self, sample_aggregate_report: AggregateReport) -> None:
        """Test entities implemented count."""
        assert sample_aggregate_report.entities_implemented == 17

    def test_entities_total(self, sample_aggregate_report: AggregateReport) -> None:
        """Test entities total count."""
        assert sample_aggregate_report.entities_total == 100

    def test_summary(self, sample_aggregate_report: AggregateReport) -> None:
        """Test summary dictionary generation."""
        summary = sample_aggregate_report.summary()

        assert "overall_score" in summary
        assert "entity_coverage" in summary
        assert "action_coverage" in summary
        assert "field_coverage" in summary
        assert "type_accuracy" in summary
        assert "entities_implemented" in summary
        assert "entities_total" in summary
        assert "generated_at" in summary
        assert "civicrm_version" in summary
        assert "civi_py_version" in summary

    def test_to_dict(self, sample_aggregate_report: AggregateReport) -> None:
        """Test full dictionary serialization."""
        result = sample_aggregate_report.to_dict()

        assert "summary" in result
        assert "entity_coverage" in result
        assert "action_coverage" in result
        assert "field_coverage" in result
        assert "trends" in result
        assert len(result["trends"]) == 2

    def test_to_trend_data(self, sample_aggregate_report: AggregateReport) -> None:
        """Test conversion to trend data point."""
        trend = sample_aggregate_report.to_trend_data()

        assert isinstance(trend, TrendData)
        assert trend.entity_coverage == sample_aggregate_report.entity_coverage
        assert trend.overall_score == sample_aggregate_report.overall_score

    def test_empty_report(self) -> None:
        """Test empty aggregate report defaults."""
        report = AggregateReport()

        assert report.entity_coverage == 0.0
        assert report.action_coverage == 0.0
        assert report.field_coverage == 0.0
        assert report.type_accuracy == 100.0
        assert report.overall_score >= 0


# =============================================================================
# BadgeColor Tests
# =============================================================================


class TestBadgeColor:
    """Tests for BadgeColor class."""

    @pytest.mark.parametrize(
        ("percentage", "expected_color"),
        [
            (100, BadgeColor.BRIGHTGREEN),
            (95, BadgeColor.BRIGHTGREEN),
            (90, BadgeColor.BRIGHTGREEN),
            (85, BadgeColor.GREEN),
            (80, BadgeColor.GREEN),
            (75, BadgeColor.YELLOWGREEN),
            (70, BadgeColor.YELLOWGREEN),
            (65, BadgeColor.YELLOW),
            (60, BadgeColor.YELLOW),
            (55, BadgeColor.ORANGE),
            (50, BadgeColor.ORANGE),
            (45, BadgeColor.RED),
            (0, BadgeColor.RED),
        ],
    )
    def test_from_percentage(self, percentage: float, expected_color: str) -> None:
        """Test color selection based on percentage."""
        assert BadgeColor.from_percentage(percentage) == expected_color


# =============================================================================
# BadgeGenerator Tests
# =============================================================================


class TestBadgeGenerator:
    """Tests for BadgeGenerator class."""

    def test_generate_basic_badge(self) -> None:
        """Test basic badge generation."""
        svg = BadgeGenerator.generate("test", "100%", BadgeColor.GREEN)

        assert isinstance(svg, str)
        assert "<svg" in svg
        assert "test" in svg
        assert "100%" in svg
        assert "</svg>" in svg

    def test_coverage_badge(self) -> None:
        """Test coverage-specific badge generation."""
        svg = BadgeGenerator.coverage_badge("entity", 85.5)

        assert "coverage-entity" in svg
        assert "86%" in svg  # Rounded

    def test_badge_color_mapping(self) -> None:
        """Test badge colors are correctly applied."""
        svg_high = BadgeGenerator.coverage_badge("test", 95)
        svg_low = BadgeGenerator.coverage_badge("test", 45)

        # High coverage should have green color
        assert "#4c1" in svg_high  # brightgreen
        # Low coverage should have red color
        assert "#e05d44" in svg_low  # red

    def test_generate_all(
        self,
        sample_aggregate_report: AggregateReport,
        temp_output_dir: Path,
    ) -> None:
        """Test generation of all badge types."""
        badges = BadgeGenerator.generate_all(sample_aggregate_report, temp_output_dir)

        assert "overall" in badges
        assert "entity" in badges
        assert "action" in badges
        assert "field" in badges
        assert "type-accuracy" in badges

        # Check files exist
        for path in badges.values():
            assert path.exists()
            content = path.read_text()
            assert "<svg" in content


# =============================================================================
# HTMLReportGenerator Tests
# =============================================================================


class TestHTMLReportGenerator:
    """Tests for HTMLReportGenerator class."""

    def test_generate_produces_valid_html(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML output is valid."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "<!DOCTYPE html>" in html
        assert "<html" in html
        assert "</html>" in html
        assert "<head>" in html
        assert "<body>" in html

    def test_html_contains_summary(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML contains summary information."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "Overall Compatibility Score" in html
        assert "Entity Coverage" in html
        assert "Action Coverage" in html
        assert "Field Coverage" in html
        assert "Type Accuracy" in html

    def test_html_contains_inline_css(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML has inline CSS (standalone)."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "<style>" in html
        assert ":root" in html
        assert "</style>" in html

    def test_html_contains_entity_section(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML contains entity coverage details."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "Entity Coverage" in html
        assert "Implemented Entities" in html
        assert "Contact" in html

    def test_html_contains_action_table(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML contains action coverage table."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "Action Coverage by Entity" in html
        assert "<table>" in html

    def test_html_contains_field_table(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML contains field coverage table."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "Field Coverage by Entity" in html

    def test_html_contains_trends(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML contains trend section."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        assert "Coverage Trends" in html
        assert "chart-container" in html

    def test_html_no_external_dependencies(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test HTML has no external CSS/JS dependencies (stylesheets/scripts)."""
        html = HTMLReportGenerator.generate(sample_aggregate_report)

        # Should not have external stylesheets (link rel=stylesheet)
        assert 'rel="stylesheet"' not in html
        # Should not have external script sources
        assert 'src="http' not in html
        assert 'src="https' not in html
        # Project link in footer is intentional, but no CDN resources
        assert "cdn." not in html.lower()
        assert "googleapis" not in html.lower()
        assert "unpkg" not in html.lower()


# =============================================================================
# MarkdownReportGenerator Tests
# =============================================================================


class TestMarkdownReportGenerator:
    """Tests for MarkdownReportGenerator class."""

    def test_generate_produces_valid_markdown(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown output is valid."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "# civi-py API Compatibility Report" in md
        assert "## Summary" in md
        assert "## Badges" in md

    def test_markdown_contains_summary_table(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown contains summary table."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "| Metric | Value |" in md
        assert "**Overall Score**" in md
        assert "**Entity Coverage**" in md

    def test_markdown_contains_badge_references(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown contains badge image references."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "![Overall Coverage]" in md
        assert "coverage-overall.svg" in md

    def test_markdown_contains_entity_section(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown contains entity coverage section."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "## Entity Coverage" in md
        assert "`Contact`" in md

    def test_markdown_contains_action_table(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown contains action coverage table."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "## Action Coverage" in md
        assert "| Entity | Available | Missing | Coverage |" in md

    def test_markdown_contains_field_table(
        self,
        sample_aggregate_report: AggregateReport,
    ) -> None:
        """Test Markdown contains field coverage table."""
        md = MarkdownReportGenerator.generate(sample_aggregate_report)

        assert "## Field Coverage" in md
        assert "| Entity | API Fields |" in md


# =============================================================================
# ReportGenerator Tests
# =============================================================================


class TestReportGenerator:
    """Tests for ReportGenerator class."""

    def test_init_default_output_dir(self) -> None:
        """Test default output directory."""
        generator = ReportGenerator()
        assert generator.output_dir == Path("coverage_reports")

    def test_init_custom_output_dir(self, temp_output_dir: Path) -> None:
        """Test custom output directory."""
        generator = ReportGenerator(output_dir=temp_output_dir)
        assert generator.output_dir == temp_output_dir

    def test_load_trends_no_file(self, temp_output_dir: Path) -> None:
        """Test loading trends when file doesn't exist."""
        generator = ReportGenerator(output_dir=temp_output_dir)
        trends = generator._load_trends()
        assert trends == []

    def test_save_and_load_trends(self, temp_output_dir: Path) -> None:
        """Test saving and loading trends."""
        generator = ReportGenerator(output_dir=temp_output_dir)

        trends = [
            TrendData("2024-01-01", 80.0, 85.0, 90.0, 82.0),
            TrendData("2024-01-15", 82.0, 87.0, 91.0, 84.0),
        ]

        generator._save_trends(trends)
        loaded = generator._load_trends()

        assert len(loaded) == 2
        assert loaded[0].date == "2024-01-01"
        assert loaded[1].overall_score == 84.0

    def test_save_all_formats(
        self,
        sample_aggregate_report: AggregateReport,
        temp_output_dir: Path,
    ) -> None:
        """Test saving all output formats."""
        generator = ReportGenerator(output_dir=temp_output_dir)
        paths = generator.save_all_formats(sample_aggregate_report)

        # Check all formats were created
        assert "json" in paths
        assert "html" in paths
        assert "markdown" in paths
        assert "endpoint" in paths

        # Check files exist and are valid
        assert paths["json"].exists()
        with paths["json"].open() as f:
            data = json.load(f)
            assert "summary" in data

        assert paths["html"].exists()
        html_content = paths["html"].read_text()
        assert "<!DOCTYPE html>" in html_content

        assert paths["markdown"].exists()
        md_content = paths["markdown"].read_text()
        assert "# civi-py" in md_content

    def test_generate_aggregate_report_offline(self, temp_output_dir: Path) -> None:
        """Test offline report generation."""
        generator = ReportGenerator(output_dir=temp_output_dir)

        with patch.object(generator, "generate_field_reports", return_value={}):
            report = generator.generate_aggregate_report_offline()

        assert isinstance(report, AggregateReport)
        assert report.entity_report is not None
        assert report.entities_implemented > 0

    @pytest.mark.asyncio
    async def test_generate_aggregate_report_with_client(
        self,
        temp_output_dir: Path,
    ) -> None:
        """Test online report generation with mocked client."""
        generator = ReportGenerator(output_dir=temp_output_dir)

        # Mock client and validators
        mock_client = MagicMock()

        with (
            patch(
                "tests.compat.report_generator.EntityCoverageValidator",
            ) as mock_entity_validator,
            patch(
                "tests.compat.report_generator.ActionCoverageValidator",
            ) as mock_action_validator,
            patch.object(generator, "generate_field_reports", return_value={}),
        ):
            # Setup mocks
            mock_entity_validator.return_value.generate_report = AsyncMock(
                return_value=EntityCoverageReport(
                    total_entities=100,
                    implemented_entities=17,
                    implemented_names={"Contact", "Activity"},
                ),
            )
            mock_action_validator.return_value.generate_all_reports = AsyncMock(
                return_value={},
            )

            report = await generator.generate_aggregate_report(mock_client)

        assert isinstance(report, AggregateReport)


# =============================================================================
# generate_report Function Tests
# =============================================================================


class TestGenerateReportFunction:
    """Tests for the generate_report convenience function."""

    def test_generate_report_offline(self, temp_output_dir: Path) -> None:
        """Test offline report generation."""
        with patch(
            "tests.compat.report_generator.ReportGenerator.generate_field_reports",
            return_value={},
        ):
            report = generate_report(output_dir=temp_output_dir, offline=True)

        assert isinstance(report, AggregateReport)

        # Check output files were created
        assert (temp_output_dir / "coverage_report.json").exists()
        assert (temp_output_dir / "coverage_report.html").exists()
        assert (temp_output_dir / "COVERAGE.md").exists()

    def test_generate_report_online_raises(self, temp_output_dir: Path) -> None:
        """Test online report raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            generate_report(output_dir=temp_output_dir, offline=False)


# =============================================================================
# CLI Tests
# =============================================================================


class TestCLI:
    """Tests for CLI interface."""

    def test_main_success(self, temp_output_dir: Path) -> None:
        """Test successful CLI execution."""
        with (
            patch(
                "sys.argv",
                ["report_generator", "-o", str(temp_output_dir)],
            ),
            patch(
                "tests.compat.report_generator.ReportGenerator.generate_field_reports",
                return_value={},
            ),
        ):
            exit_code = main()

        assert exit_code == 0

    def test_main_verbose_flag(self, temp_output_dir: Path, capsys: Any) -> None:
        """Test verbose flag enables detailed output."""
        with (
            patch(
                "sys.argv",
                ["report_generator", "-o", str(temp_output_dir), "-v"],
            ),
            patch(
                "tests.compat.report_generator.ReportGenerator.generate_field_reports",
                return_value={},
            ),
        ):
            exit_code = main()

        assert exit_code == 0

    def test_main_handles_exception(self, temp_output_dir: Path) -> None:
        """Test CLI handles exceptions gracefully."""
        with (
            patch(
                "sys.argv",
                ["report_generator", "-o", str(temp_output_dir)],
            ),
            patch(
                "tests.compat.report_generator.generate_report",
                side_effect=Exception("Test error"),
            ),
        ):
            exit_code = main()

        assert exit_code == 1


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    """Integration tests for full report generation workflow."""

    def test_full_offline_workflow(self, temp_output_dir: Path) -> None:
        """Test complete offline workflow."""
        generator = ReportGenerator(output_dir=temp_output_dir)

        with patch.object(generator, "generate_field_reports", return_value={}):
            report = generator.generate_aggregate_report_offline()
            paths = generator.save_all_formats(report)

        # Verify all outputs
        assert len(paths) >= 8  # json, html, md, endpoint + badges

        # Verify JSON is valid
        with paths["json"].open() as f:
            data = json.load(f)
            assert "summary" in data
            assert "entity_coverage" in data

        # Verify HTML is standalone
        html = paths["html"].read_text()
        assert "<!DOCTYPE html>" in html
        assert "<style>" in html

        # Verify badges directory
        badges_dir = temp_output_dir / "badges"
        assert badges_dir.exists()
        badge_files = list(badges_dir.glob("*.svg"))
        assert len(badge_files) >= 5

    def test_trend_accumulation(self, temp_output_dir: Path) -> None:
        """Test trends accumulate over multiple runs."""
        generator = ReportGenerator(output_dir=temp_output_dir)

        # Run multiple times
        for _ in range(3):
            with patch.object(generator, "generate_field_reports", return_value={}):
                report = generator.generate_aggregate_report_offline()

        # Verify trends accumulated
        trends = generator._load_trends()
        assert len(trends) == 3

    def test_badge_endpoint_format(
        self,
        sample_aggregate_report: AggregateReport,
        temp_output_dir: Path,
    ) -> None:
        """Test badge endpoint follows shields.io format."""
        generator = ReportGenerator(output_dir=temp_output_dir)
        paths = generator.save_all_formats(sample_aggregate_report)

        with paths["endpoint"].open() as f:
            endpoint = json.load(f)

        # Verify shields.io format
        assert endpoint["schemaVersion"] == 1
        assert "label" in endpoint
        assert "message" in endpoint
        assert "color" in endpoint
