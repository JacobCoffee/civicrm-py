"""API compatibility coverage report generator for civi-py.

This module aggregates data from EntityCoverageValidator, ActionCoverageValidator,
and SchemaValidator to generate comprehensive coverage reports in multiple formats:

- JSON: Machine-readable format for CI/CD integration
- HTML: Standalone HTML report with inline CSS
- Markdown: Documentation-friendly format
- SVG Badge: Shields.io-compatible coverage badges

Usage:
    # As a module:
    python -m tests.compat.report_generator

    # Programmatically:
    >>> from tests.compat.report_generator import ReportGenerator
    >>> generator = ReportGenerator()
    >>> report = generator.generate_aggregate_report()
    >>> generator.save_all_formats(report, "coverage_reports/")

Features:
    - Aggregates entity, action, and field coverage metrics
    - Generates trend tracking data for historical comparison
    - Creates shields.io-compatible SVG badges
    - Produces standalone HTML with inline CSS
    - Provides JSON endpoint data for dynamic badges
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from civi_py.core.client import CiviClient

from tests.compat.coverage_validator import (
    ActionCoverageReport,
    ActionCoverageValidator,
    EntityCoverageReport,
    EntityCoverageValidator,
    EntityPriority,
)
from tests.compat.schema_validator import (
    SchemaCache,
    SchemaValidator,
    ValidationReport,
    ValidationResult,
)

__all__ = [
    "AggregateReport",
    "BadgeColor",
    "BadgeGenerator",
    "FieldCoverageReport",
    "HTMLReportGenerator",
    "MarkdownReportGenerator",
    "ReportGenerator",
    "TrendData",
    "generate_report",
]

logger = logging.getLogger(__name__)


class BadgeColor:
    """Badge color constants for shields.io compatibility."""

    BRIGHTGREEN = "brightgreen"
    GREEN = "green"
    YELLOWGREEN = "yellowgreen"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"

    @classmethod
    def from_percentage(cls, percentage: float) -> str:
        """Get badge color based on coverage percentage.

        Args:
            percentage: Coverage percentage (0-100).

        Returns:
            Color string for badge.
        """
        if percentage >= 90:
            return cls.BRIGHTGREEN
        if percentage >= 80:
            return cls.GREEN
        if percentage >= 70:
            return cls.YELLOWGREEN
        if percentage >= 60:
            return cls.YELLOW
        if percentage >= 50:
            return cls.ORANGE
        return cls.RED


@dataclass
class FieldCoverageReport:
    """Coverage report for entity field implementations.

    Attributes:
        entity_name: Name of the entity.
        total_api_fields: Number of fields in API schema.
        implemented_fields: Number of fields in our model.
        missing_fields: List of missing field names.
        extra_fields: List of extra fields in model but not API.
        type_mismatches: Number of type mismatch errors.
        validation_result: Full validation result if available.
    """

    entity_name: str
    total_api_fields: int = 0
    implemented_fields: int = 0
    missing_fields: list[str] = field(default_factory=list)
    extra_fields: list[str] = field(default_factory=list)
    type_mismatches: int = 0
    validation_result: ValidationResult | None = None

    @property
    def coverage_percentage(self) -> float:
        """Calculate field coverage percentage."""
        if self.total_api_fields == 0:
            return 100.0 if self.implemented_fields == 0 else 0.0
        return (self.implemented_fields / self.total_api_fields) * 100

    @property
    def type_accuracy(self) -> float:
        """Calculate type accuracy percentage."""
        if self.implemented_fields == 0:
            return 100.0
        correct = self.implemented_fields - self.type_mismatches
        return (correct / self.implemented_fields) * 100

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "entity_name": self.entity_name,
            "total_api_fields": self.total_api_fields,
            "implemented_fields": self.implemented_fields,
            "coverage_percentage": round(self.coverage_percentage, 2),
            "type_accuracy": round(self.type_accuracy, 2),
            "missing_fields": self.missing_fields,
            "extra_fields": self.extra_fields,
            "type_mismatches": self.type_mismatches,
        }


@dataclass
class TrendData:
    """Historical trend data for coverage tracking.

    Attributes:
        date: Date of the measurement.
        entity_coverage: Entity coverage percentage.
        action_coverage: Action coverage percentage.
        field_coverage: Average field coverage percentage.
        overall_score: Combined compatibility score.
    """

    date: str
    entity_coverage: float
    action_coverage: float
    field_coverage: float
    overall_score: float

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "date": self.date,
            "entity_coverage": round(self.entity_coverage, 2),
            "action_coverage": round(self.action_coverage, 2),
            "field_coverage": round(self.field_coverage, 2),
            "overall_score": round(self.overall_score, 2),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TrendData:
        """Create from dictionary."""
        return cls(
            date=data["date"],
            entity_coverage=data["entity_coverage"],
            action_coverage=data["action_coverage"],
            field_coverage=data["field_coverage"],
            overall_score=data["overall_score"],
        )


@dataclass
class AggregateReport:
    """Aggregated coverage report combining all validators.

    Attributes:
        entity_report: Entity coverage report.
        action_reports: Per-entity action coverage reports.
        field_reports: Per-entity field coverage reports.
        validation_report: Schema validation report.
        generated_at: Report generation timestamp.
        civicrm_version: Target CiviCRM version.
        civi_py_version: civi-py library version.
        trends: Historical trend data.
    """

    entity_report: EntityCoverageReport | None = None
    action_reports: dict[str, ActionCoverageReport] = field(default_factory=dict)
    field_reports: dict[str, FieldCoverageReport] = field(default_factory=dict)
    validation_report: ValidationReport | None = None
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    civicrm_version: str = "unknown"
    civi_py_version: str = "unknown"
    trends: list[TrendData] = field(default_factory=list)

    @property
    def entity_coverage(self) -> float:
        """Entity coverage percentage."""
        if self.entity_report is None:
            return 0.0
        return self.entity_report.coverage_percentage

    @property
    def action_coverage(self) -> float:
        """Average action coverage across entities."""
        if not self.action_reports:
            return 0.0
        total = sum(r.coverage_percentage for r in self.action_reports.values())
        return total / len(self.action_reports)

    @property
    def field_coverage(self) -> float:
        """Average field coverage across entities."""
        if not self.field_reports:
            return 0.0
        total = sum(r.coverage_percentage for r in self.field_reports.values())
        return total / len(self.field_reports)

    @property
    def type_accuracy(self) -> float:
        """Average type accuracy across entities."""
        if not self.field_reports:
            return 100.0
        total = sum(r.type_accuracy for r in self.field_reports.values())
        return total / len(self.field_reports)

    @property
    def overall_score(self) -> float:
        """Combined compatibility score (0-100).

        Weights:
            - Entity coverage: 30%
            - Action coverage: 30%
            - Field coverage: 25%
            - Type accuracy: 15%
        """
        return (
            self.entity_coverage * 0.30
            + self.action_coverage * 0.30
            + self.field_coverage * 0.25
            + self.type_accuracy * 0.15
        )

    @property
    def entities_implemented(self) -> int:
        """Number of implemented entities."""
        if self.entity_report is None:
            return 0
        return self.entity_report.implemented_entities

    @property
    def entities_total(self) -> int:
        """Total number of API entities."""
        if self.entity_report is None:
            return 0
        return self.entity_report.total_entities

    def summary(self) -> dict[str, Any]:
        """Get summary statistics."""
        return {
            "overall_score": round(self.overall_score, 2),
            "entity_coverage": round(self.entity_coverage, 2),
            "action_coverage": round(self.action_coverage, 2),
            "field_coverage": round(self.field_coverage, 2),
            "type_accuracy": round(self.type_accuracy, 2),
            "entities_implemented": self.entities_implemented,
            "entities_total": self.entities_total,
            "generated_at": self.generated_at.isoformat(),
            "civicrm_version": self.civicrm_version,
            "civi_py_version": self.civi_py_version,
        }

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "summary": self.summary(),
            "entity_coverage": self.entity_report.to_dict() if self.entity_report else None,
            "action_coverage": {name: report.to_dict() for name, report in self.action_reports.items()},
            "field_coverage": {name: report.to_dict() for name, report in self.field_reports.items()},
            "schema_validation": (self.validation_report.to_dict() if self.validation_report else None),
            "trends": [t.to_dict() for t in self.trends],
        }

    def to_trend_data(self) -> TrendData:
        """Convert current report to trend data point."""
        return TrendData(
            date=self.generated_at.strftime("%Y-%m-%d"),
            entity_coverage=self.entity_coverage,
            action_coverage=self.action_coverage,
            field_coverage=self.field_coverage,
            overall_score=self.overall_score,
        )


class BadgeGenerator:
    """Generates SVG badges for coverage metrics."""

    # SVG template for shields.io-style badge
    SVG_TEMPLATE: ClassVar[
        str
    ] = """<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{width}" height="20" role="img" aria-label="{label}: {value}">
  <title>{label}: {value}</title>
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r">
    <rect width="{width}" height="20" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#555"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" text-rendering="geometricPrecision" font-size="110">
    <text aria-hidden="true" x="{label_x}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{label_text_width}">{label}</text>
    <text x="{label_x}" y="140" transform="scale(.1)" fill="#fff" textLength="{label_text_width}">{label}</text>
    <text aria-hidden="true" x="{value_x}" y="150" fill="#010101" fill-opacity=".3" transform="scale(.1)" textLength="{value_text_width}">{value}</text>
    <text x="{value_x}" y="140" transform="scale(.1)" fill="#fff" textLength="{value_text_width}">{value}</text>
  </g>
</svg>"""

    @classmethod
    def generate(
        cls,
        label: str,
        value: str,
        color: str = BadgeColor.GREEN,
    ) -> str:
        """Generate an SVG badge.

        Args:
            label: Badge label text.
            value: Badge value text.
            color: Badge color (hex or named color).

        Returns:
            SVG string for the badge.
        """
        # Calculate widths (approximate character width of 7px)
        label_width = len(label) * 7 + 10
        value_width = len(value) * 7 + 10
        width = label_width + value_width

        # Calculate text positions
        label_x = (label_width / 2) * 10
        value_x = (label_width + value_width / 2) * 10
        label_text_width = (len(label) * 7) * 10
        value_text_width = (len(value) * 7) * 10

        # Map named colors to hex
        color_map = {
            BadgeColor.BRIGHTGREEN: "#4c1",
            BadgeColor.GREEN: "#97ca00",
            BadgeColor.YELLOWGREEN: "#a4a61d",
            BadgeColor.YELLOW: "#dfb317",
            BadgeColor.ORANGE: "#fe7d37",
            BadgeColor.RED: "#e05d44",
        }
        hex_color = color_map.get(color, color)

        return cls.SVG_TEMPLATE.format(
            width=width,
            label=label,
            value=value,
            color=hex_color,
            label_width=label_width,
            value_width=value_width,
            label_x=label_x,
            value_x=value_x,
            label_text_width=label_text_width,
            value_text_width=value_text_width,
        )

    @classmethod
    def coverage_badge(
        cls,
        coverage_type: str,
        percentage: float,
    ) -> str:
        """Generate a coverage badge.

        Args:
            coverage_type: Type of coverage (entity, action, field, overall).
            percentage: Coverage percentage.

        Returns:
            SVG string for the coverage badge.
        """
        label = f"coverage-{coverage_type}"
        value = f"{percentage:.0f}%"
        color = BadgeColor.from_percentage(percentage)
        return cls.generate(label, value, color)

    @classmethod
    def generate_all(cls, report: AggregateReport, output_dir: Path) -> dict[str, Path]:
        """Generate all coverage badges.

        Args:
            report: Aggregate coverage report.
            output_dir: Directory to save badges.

        Returns:
            Dict mapping badge names to file paths.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        badges: dict[str, Path] = {}

        # Generate individual badges
        badge_configs = [
            ("overall", report.overall_score),
            ("entity", report.entity_coverage),
            ("action", report.action_coverage),
            ("field", report.field_coverage),
            ("type-accuracy", report.type_accuracy),
        ]

        for name, percentage in badge_configs:
            svg = cls.coverage_badge(name, percentage)
            path = output_dir / f"coverage-{name}.svg"
            path.write_text(svg)
            badges[name] = path
            logger.info("Generated badge: %s (%.1f%%)", name, percentage)

        return badges


class HTMLReportGenerator:
    """Generates standalone HTML reports with inline CSS."""

    # Inline CSS styles for the report
    CSS_STYLES: ClassVar[str] = """
    :root {
      --bg-primary: #ffffff;
      --bg-secondary: #f8f9fa;
      --bg-tertiary: #e9ecef;
      --text-primary: #212529;
      --text-secondary: #6c757d;
      --border-color: #dee2e6;
      --success: #198754;
      --success-bg: #d1e7dd;
      --warning: #ffc107;
      --warning-bg: #fff3cd;
      --danger: #dc3545;
      --danger-bg: #f8d7da;
      --info: #0dcaf0;
      --info-bg: #cff4fc;
      --accent: #0d6efd;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
      line-height: 1.6;
      color: var(--text-primary);
      background: var(--bg-secondary);
      padding: 2rem;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    header {
      background: var(--bg-primary);
      border-radius: 8px;
      padding: 2rem;
      margin-bottom: 2rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    h1 { color: var(--accent); font-size: 2rem; margin-bottom: 0.5rem; }
    .subtitle { color: var(--text-secondary); font-size: 1rem; }
    .meta { margin-top: 1rem; font-size: 0.875rem; color: var(--text-secondary); }
    .meta span { margin-right: 1.5rem; }
    .score-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 1rem;
      margin-bottom: 2rem;
    }
    .score-card {
      background: var(--bg-primary);
      border-radius: 8px;
      padding: 1.5rem;
      text-align: center;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    .score-card.main { grid-column: span 2; }
    .score-value {
      font-size: 2.5rem;
      font-weight: 700;
      margin-bottom: 0.25rem;
    }
    .score-label { color: var(--text-secondary); font-size: 0.875rem; }
    .progress-bar {
      height: 8px;
      background: var(--bg-tertiary);
      border-radius: 4px;
      margin-top: 0.75rem;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      border-radius: 4px;
      transition: width 0.3s ease;
    }
    .progress-fill.success { background: var(--success); }
    .progress-fill.warning { background: var(--warning); }
    .progress-fill.danger { background: var(--danger); }
    section {
      background: var(--bg-primary);
      border-radius: 8px;
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      box-shadow: 0 1px 3px rgba(0,0,0,0.1);
    }
    h2 { font-size: 1.25rem; margin-bottom: 1rem; color: var(--text-primary); }
    h3 { font-size: 1rem; margin: 1rem 0 0.5rem; color: var(--text-secondary); }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.875rem;
    }
    th, td {
      padding: 0.75rem;
      text-align: left;
      border-bottom: 1px solid var(--border-color);
    }
    th { background: var(--bg-secondary); font-weight: 600; }
    tr:hover { background: var(--bg-secondary); }
    .badge {
      display: inline-block;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 600;
    }
    .badge.success { background: var(--success-bg); color: var(--success); }
    .badge.warning { background: var(--warning-bg); color: #856404; }
    .badge.danger { background: var(--danger-bg); color: var(--danger); }
    .badge.info { background: var(--info-bg); color: #055160; }
    .entity-list {
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-top: 0.5rem;
    }
    .entity-tag {
      background: var(--bg-tertiary);
      padding: 0.25rem 0.75rem;
      border-radius: 4px;
      font-size: 0.875rem;
    }
    .entity-tag.implemented { background: var(--success-bg); color: var(--success); }
    .entity-tag.missing { background: var(--warning-bg); color: #856404; }
    .collapsible { cursor: pointer; }
    .collapsible:after { content: ' [+]'; font-size: 0.75rem; }
    .collapsible.open:after { content: ' [-]'; }
    .content { display: none; margin-top: 1rem; }
    .content.show { display: block; }
    .chart-container {
      height: 200px;
      display: flex;
      align-items: flex-end;
      gap: 4px;
      padding: 1rem 0;
    }
    .chart-bar {
      flex: 1;
      min-width: 30px;
      background: var(--accent);
      border-radius: 4px 4px 0 0;
      position: relative;
    }
    .chart-bar:hover { opacity: 0.8; }
    .chart-bar .tooltip {
      position: absolute;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%);
      background: var(--text-primary);
      color: white;
      padding: 0.25rem 0.5rem;
      border-radius: 4px;
      font-size: 0.75rem;
      white-space: nowrap;
      opacity: 0;
      transition: opacity 0.2s;
    }
    .chart-bar:hover .tooltip { opacity: 1; }
    footer {
      text-align: center;
      color: var(--text-secondary);
      font-size: 0.875rem;
      margin-top: 2rem;
    }
    footer a { color: var(--accent); text-decoration: none; }
    """

    @classmethod
    def generate(cls, report: AggregateReport) -> str:
        """Generate HTML report.

        Args:
            report: Aggregate coverage report.

        Returns:
            Complete HTML document string.
        """
        summary = report.summary()

        # Build entity coverage section
        entity_section = cls._build_entity_section(report)

        # Build action coverage section
        action_section = cls._build_action_section(report)

        # Build field coverage section
        field_section = cls._build_field_section(report)

        # Build trends section
        trends_section = cls._build_trends_section(report)

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>civi-py API Compatibility Report</title>
    <style>{cls.CSS_STYLES}</style>
</head>
<body>
    <div class="container">
        <header>
            <h1>civi-py API Compatibility Report</h1>
            <p class="subtitle">Coverage analysis for CiviCRM API v4 compatibility</p>
            <div class="meta">
                <span>Generated: {summary["generated_at"]}</span>
                <span>CiviCRM: {summary["civicrm_version"]}</span>
                <span>civi-py: {summary["civi_py_version"]}</span>
            </div>
        </header>

        <div class="score-grid">
            <div class="score-card main">
                <div class="score-value" style="color: {cls._get_color(summary["overall_score"])}">{summary["overall_score"]:.1f}%</div>
                <div class="score-label">Overall Compatibility Score</div>
                <div class="progress-bar">
                    <div class="progress-fill {cls._get_class(summary["overall_score"])}" style="width: {summary["overall_score"]}%"></div>
                </div>
            </div>
            <div class="score-card">
                <div class="score-value" style="color: {cls._get_color(summary["entity_coverage"])}">{summary["entity_coverage"]:.1f}%</div>
                <div class="score-label">Entity Coverage ({summary["entities_implemented"]}/{summary["entities_total"]})</div>
                <div class="progress-bar">
                    <div class="progress-fill {cls._get_class(summary["entity_coverage"])}" style="width: {summary["entity_coverage"]}%"></div>
                </div>
            </div>
            <div class="score-card">
                <div class="score-value" style="color: {cls._get_color(summary["action_coverage"])}">{summary["action_coverage"]:.1f}%</div>
                <div class="score-label">Action Coverage</div>
                <div class="progress-bar">
                    <div class="progress-fill {cls._get_class(summary["action_coverage"])}" style="width: {summary["action_coverage"]}%"></div>
                </div>
            </div>
            <div class="score-card">
                <div class="score-value" style="color: {cls._get_color(summary["field_coverage"])}">{summary["field_coverage"]:.1f}%</div>
                <div class="score-label">Field Coverage</div>
                <div class="progress-bar">
                    <div class="progress-fill {cls._get_class(summary["field_coverage"])}" style="width: {summary["field_coverage"]}%"></div>
                </div>
            </div>
            <div class="score-card">
                <div class="score-value" style="color: {cls._get_color(summary["type_accuracy"])}">{summary["type_accuracy"]:.1f}%</div>
                <div class="score-label">Type Accuracy</div>
                <div class="progress-bar">
                    <div class="progress-fill {cls._get_class(summary["type_accuracy"])}" style="width: {summary["type_accuracy"]}%"></div>
                </div>
            </div>
        </div>

        {entity_section}
        {action_section}
        {field_section}
        {trends_section}

        <footer>
            <p>Generated by <a href="https://github.com/JacobCoffee/civi-py">civi-py</a> | API Compatibility Testing Module</p>
        </footer>
    </div>

    <script>
        document.querySelectorAll('.collapsible').forEach(el => {{
            el.addEventListener('click', function() {{
                this.classList.toggle('open');
                const content = this.nextElementSibling;
                content.classList.toggle('show');
            }});
        }});
    </script>
</body>
</html>"""

    @classmethod
    def _get_color(cls, percentage: float) -> str:
        """Get CSS color for percentage."""
        if percentage >= 80:
            return "var(--success)"
        if percentage >= 60:
            return "#856404"  # Warning yellow text
        return "var(--danger)"

    @classmethod
    def _get_class(cls, percentage: float) -> str:
        """Get CSS class for percentage."""
        if percentage >= 80:
            return "success"
        if percentage >= 60:
            return "warning"
        return "danger"

    @classmethod
    def _build_entity_section(cls, report: AggregateReport) -> str:
        """Build entity coverage HTML section."""
        if report.entity_report is None:
            return ""

        entity_report = report.entity_report
        implemented = sorted(entity_report.implemented_names)
        missing_by_priority = entity_report.missing_by_priority()

        implemented_tags = "".join(f'<span class="entity-tag implemented">{name}</span>' for name in implemented)

        missing_sections = ""
        for priority in EntityPriority:
            entities = missing_by_priority.get(priority, [])
            if entities:
                tags = "".join(
                    f'<span class="entity-tag missing">{e.name}</span>' for e in sorted(entities, key=lambda x: x.name)
                )
                missing_sections += f"""
                <h3>{priority.name} Priority ({len(entities)})</h3>
                <div class="entity-list">{tags}</div>
                """

        return f"""
        <section>
            <h2>Entity Coverage</h2>
            <h3 class="collapsible">Implemented Entities ({len(implemented)})</h3>
            <div class="content">
                <div class="entity-list">{implemented_tags}</div>
            </div>
            <h3 class="collapsible">Missing Entities ({entity_report.missing_count})</h3>
            <div class="content">
                {missing_sections}
            </div>
        </section>
        """

    @classmethod
    def _build_action_section(cls, report: AggregateReport) -> str:
        """Build action coverage HTML section."""
        if not report.action_reports:
            return ""

        rows = ""
        for name, action_report in sorted(report.action_reports.items()):
            pct = action_report.coverage_percentage
            badge_class = cls._get_class(pct)
            available = len(action_report.available_actions)
            implemented = len(action_report.implemented_actions)
            missing_count = len(action_report.missing_actions)

            rows += f"""
            <tr>
                <td>{name}</td>
                <td>{available}</td>
                <td>{implemented}</td>
                <td>{missing_count}</td>
                <td><span class="badge {badge_class}">{pct:.1f}%</span></td>
            </tr>
            """

        return f"""
        <section>
            <h2>Action Coverage by Entity</h2>
            <table>
                <thead>
                    <tr>
                        <th>Entity</th>
                        <th>Available Actions</th>
                        <th>Implemented</th>
                        <th>Missing</th>
                        <th>Coverage</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </section>
        """

    @classmethod
    def _build_field_section(cls, report: AggregateReport) -> str:
        """Build field coverage HTML section."""
        if not report.field_reports:
            return ""

        rows = ""
        for name, field_report in sorted(report.field_reports.items()):
            cov_pct = field_report.coverage_percentage
            acc_pct = field_report.type_accuracy
            cov_class = cls._get_class(cov_pct)
            acc_class = cls._get_class(acc_pct)

            rows += f"""
            <tr>
                <td>{name}</td>
                <td>{field_report.total_api_fields}</td>
                <td>{field_report.implemented_fields}</td>
                <td>{len(field_report.missing_fields)}</td>
                <td>{field_report.type_mismatches}</td>
                <td><span class="badge {cov_class}">{cov_pct:.1f}%</span></td>
                <td><span class="badge {acc_class}">{acc_pct:.1f}%</span></td>
            </tr>
            """

        return f"""
        <section>
            <h2>Field Coverage by Entity</h2>
            <table>
                <thead>
                    <tr>
                        <th>Entity</th>
                        <th>API Fields</th>
                        <th>Implemented</th>
                        <th>Missing</th>
                        <th>Type Errors</th>
                        <th>Coverage</th>
                        <th>Accuracy</th>
                    </tr>
                </thead>
                <tbody>
                    {rows}
                </tbody>
            </table>
        </section>
        """

    @classmethod
    def _build_trends_section(cls, report: AggregateReport) -> str:
        """Build trends HTML section."""
        if not report.trends:
            return ""

        # Build chart bars
        max_score = 100
        bars = ""
        for trend in report.trends[-10:]:  # Last 10 data points
            height = (trend.overall_score / max_score) * 100
            bars += f"""
            <div class="chart-bar" style="height: {height}%">
                <span class="tooltip">{trend.date}: {trend.overall_score:.1f}%</span>
            </div>
            """

        return f"""
        <section>
            <h2>Coverage Trends</h2>
            <div class="chart-container">
                {bars}
            </div>
        </section>
        """


class MarkdownReportGenerator:
    """Generates Markdown reports for documentation."""

    @classmethod
    def generate(cls, report: AggregateReport) -> str:
        """Generate Markdown report.

        Args:
            report: Aggregate coverage report.

        Returns:
            Markdown document string.
        """
        summary = report.summary()

        # Build entity section
        entity_section = cls._build_entity_section(report)

        # Build action section
        action_section = cls._build_action_section(report)

        # Build field section
        field_section = cls._build_field_section(report)

        return f"""# civi-py API Compatibility Report

Generated: {summary["generated_at"]}
CiviCRM Version: {summary["civicrm_version"]}
civi-py Version: {summary["civi_py_version"]}

## Summary

| Metric | Value |
|--------|-------|
| **Overall Score** | {summary["overall_score"]:.1f}% |
| **Entity Coverage** | {summary["entity_coverage"]:.1f}% ({summary["entities_implemented"]}/{summary["entities_total"]}) |
| **Action Coverage** | {summary["action_coverage"]:.1f}% |
| **Field Coverage** | {summary["field_coverage"]:.1f}% |
| **Type Accuracy** | {summary["type_accuracy"]:.1f}% |

## Badges

![Overall Coverage](./badges/coverage-overall.svg)
![Entity Coverage](./badges/coverage-entity.svg)
![Action Coverage](./badges/coverage-action.svg)
![Field Coverage](./badges/coverage-field.svg)

{entity_section}

{action_section}

{field_section}

---
*Generated by [civi-py](https://github.com/JacobCoffee/civi-py) API Compatibility Testing Module*
"""

    @classmethod
    def _build_entity_section(cls, report: AggregateReport) -> str:
        """Build entity coverage Markdown section."""
        if report.entity_report is None:
            return ""

        entity_report = report.entity_report
        implemented = sorted(entity_report.implemented_names)
        missing_by_priority = entity_report.missing_by_priority()

        implemented_list = ", ".join(f"`{name}`" for name in implemented)

        missing_sections = ""
        for priority in EntityPriority:
            entities = missing_by_priority.get(priority, [])
            if entities:
                names = ", ".join(f"`{e.name}`" for e in sorted(entities, key=lambda x: x.name))
                missing_sections += f"\n### {priority.name} Priority ({len(entities)})\n\n{names}\n"

        return f"""## Entity Coverage

### Implemented Entities ({len(implemented)})

{implemented_list}

### Missing Entities ({entity_report.missing_count})
{missing_sections}
"""

    @classmethod
    def _build_action_section(cls, report: AggregateReport) -> str:
        """Build action coverage Markdown section."""
        if not report.action_reports:
            return ""

        rows = []
        for name, action_report in sorted(report.action_reports.items()):
            pct = action_report.coverage_percentage
            available = len(action_report.available_actions)
            missing_count = len(action_report.missing_actions)
            rows.append(f"| {name} | {available} | {missing_count} | {pct:.1f}% |")

        table = "\n".join(rows)

        return f"""## Action Coverage

| Entity | Available | Missing | Coverage |
|--------|-----------|---------|----------|
{table}
"""

    @classmethod
    def _build_field_section(cls, report: AggregateReport) -> str:
        """Build field coverage Markdown section."""
        if not report.field_reports:
            return ""

        rows = []
        for name, field_report in sorted(report.field_reports.items()):
            cov_pct = field_report.coverage_percentage
            acc_pct = field_report.type_accuracy
            rows.append(
                f"| {name} | {field_report.total_api_fields} | "
                f"{field_report.implemented_fields} | {field_report.type_mismatches} | "
                f"{cov_pct:.1f}% | {acc_pct:.1f}% |",
            )

        table = "\n".join(rows)

        return f"""## Field Coverage

| Entity | API Fields | Implemented | Type Errors | Coverage | Accuracy |
|--------|------------|-------------|-------------|----------|----------|
{table}
"""


class ReportGenerator:
    """Main report generator coordinating all validators and output formats."""

    def __init__(
        self,
        output_dir: str | Path | None = None,
        schema_cache: SchemaCache | None = None,
    ) -> None:
        """Initialize report generator.

        Args:
            output_dir: Directory for output files. Defaults to ./coverage_reports.
            schema_cache: Schema cache instance for field validation.
        """
        self.output_dir = Path(output_dir) if output_dir else Path("coverage_reports")
        self.schema_cache = schema_cache or SchemaCache()
        self._trends_file = self.output_dir / "trends.json"

    def _load_trends(self) -> list[TrendData]:
        """Load historical trend data."""
        if not self._trends_file.exists():
            return []

        try:
            with self._trends_file.open() as f:
                data = json.load(f)
                return [TrendData.from_dict(item) for item in data]
        except (json.JSONDecodeError, OSError, KeyError) as e:
            logger.warning("Failed to load trends: %s", e)
            return []

    def _save_trends(self, trends: list[TrendData]) -> None:
        """Save trend data."""
        self._trends_file.parent.mkdir(parents=True, exist_ok=True)
        with self._trends_file.open("w") as f:
            json.dump([t.to_dict() for t in trends], f, indent=2)

    def generate_field_reports(
        self,
        entities: dict[str, type],
    ) -> dict[str, FieldCoverageReport]:
        """Generate field coverage reports for entities.

        Args:
            entities: Dict mapping entity names to classes.

        Returns:
            Dict mapping entity names to field reports.
        """
        validator = SchemaValidator(cache=self.schema_cache, ignore_extra_api_fields=False)
        validation_report = validator.validate_all_entities(entities)

        field_reports: dict[str, FieldCoverageReport] = {}

        for result in validation_report.results:
            # Count missing fields from warnings/info
            missing_fields = [
                m.field_name
                for m in result.all_mismatches
                if "not defined in model" in m.message or "not in API" in m.message
            ]
            extra_fields = [
                m.field_name for m in result.all_mismatches if "exists in model but not in API" in m.message
            ]

            field_reports[result.entity_name] = FieldCoverageReport(
                entity_name=result.entity_name,
                total_api_fields=result.api_field_count,
                implemented_fields=result.model_field_count,
                missing_fields=missing_fields,
                extra_fields=extra_fields,
                type_mismatches=result.error_count,
                validation_result=result,
            )

        return field_reports

    def generate_aggregate_report_offline(
        self,
        entities: dict[str, type] | None = None,
    ) -> AggregateReport:
        """Generate aggregate report using cached data (no API calls).

        Args:
            entities: Dict of entity classes. If None, uses default entities.

        Returns:
            AggregateReport with available data.
        """
        from civi_py.entities import (
            Activity,
            Address,
            Contact,
            Contribution,
            Email,
            EntityTag,
            Event,
            Group,
            GroupContact,
            Household,
            Individual,
            Membership,
            Note,
            Organization,
            Participant,
            Phone,
            Tag,
        )

        if entities is None:
            entities = {
                "Contact": Contact,
                "Individual": Individual,
                "Organization": Organization,
                "Household": Household,
                "Activity": Activity,
                "Address": Address,
                "Contribution": Contribution,
                "Email": Email,
                "Event": Event,
                "Group": Group,
                "GroupContact": GroupContact,
                "Membership": Membership,
                "Note": Note,
                "Participant": Participant,
                "Phone": Phone,
                "Tag": Tag,
                "EntityTag": EntityTag,
            }

        # Generate field reports from cached schemas
        field_reports = self.generate_field_reports(entities)

        # Create mock entity report based on our known implementations
        entity_report = EntityCoverageReport(
            total_entities=len(entities) + 50,  # Approximate total
            implemented_entities=len(entities),
            missing_entities=[],
            implemented_names=set(entities.keys()),
        )

        # Load trends
        trends = self._load_trends()

        # Get version info
        try:
            from importlib.metadata import version as get_version

            civi_py_version = get_version("civi-py")
        except Exception:
            civi_py_version = "unknown"

        report = AggregateReport(
            entity_report=entity_report,
            action_reports={},
            field_reports=field_reports,
            civicrm_version="cached",
            civi_py_version=civi_py_version,
            trends=trends,
        )

        # Add current data point to trends
        current_trend = report.to_trend_data()
        trends.append(current_trend)
        self._save_trends(trends[-30:])  # Keep last 30 data points

        return report

    async def generate_aggregate_report(
        self,
        client: CiviClient,
        entities: dict[str, type] | None = None,
    ) -> AggregateReport:
        """Generate comprehensive aggregate report.

        Args:
            client: Active CiviClient for API calls.
            entities: Dict of entity classes. If None, uses default entities.

        Returns:
            AggregateReport with all coverage data.
        """
        from civi_py.entities import (
            Activity,
            Address,
            Contact,
            Contribution,
            Email,
            EntityTag,
            Event,
            Group,
            GroupContact,
            Household,
            Individual,
            Membership,
            Note,
            Organization,
            Participant,
            Phone,
            Tag,
        )

        if entities is None:
            entities = {
                "Contact": Contact,
                "Individual": Individual,
                "Organization": Organization,
                "Household": Household,
                "Activity": Activity,
                "Address": Address,
                "Contribution": Contribution,
                "Email": Email,
                "Event": Event,
                "Group": Group,
                "GroupContact": GroupContact,
                "Membership": Membership,
                "Note": Note,
                "Participant": Participant,
                "Phone": Phone,
                "Tag": Tag,
                "EntityTag": EntityTag,
            }

        # Generate entity coverage report
        entity_validator = EntityCoverageValidator(client)
        entity_report = await entity_validator.generate_report()

        # Generate action coverage reports
        action_validator = ActionCoverageValidator(client)
        action_reports = await action_validator.generate_all_reports(list(entities.keys()))

        # Generate field reports
        field_reports = self.generate_field_reports(entities)

        # Load trends
        trends = self._load_trends()

        # Get version info
        try:
            from importlib.metadata import version as get_version

            civi_py_version = get_version("civi-py")
        except Exception:
            civi_py_version = "unknown"

        report = AggregateReport(
            entity_report=entity_report,
            action_reports=action_reports,
            field_reports=field_reports,
            civicrm_version="5.x",  # Would come from API
            civi_py_version=civi_py_version,
            trends=trends,
        )

        # Add current data point to trends
        current_trend = report.to_trend_data()
        trends.append(current_trend)
        self._save_trends(trends[-30:])  # Keep last 30 data points

        return report

    def save_all_formats(self, report: AggregateReport) -> dict[str, Path]:
        """Save report in all formats.

        Args:
            report: Aggregate report to save.

        Returns:
            Dict mapping format names to file paths.
        """
        self.output_dir.mkdir(parents=True, exist_ok=True)
        paths: dict[str, Path] = {}

        # JSON
        json_path = self.output_dir / "coverage_report.json"
        with json_path.open("w") as f:
            json.dump(report.to_dict(), f, indent=2, default=str)
        paths["json"] = json_path
        logger.info("Saved JSON report: %s", json_path)

        # HTML
        html_path = self.output_dir / "coverage_report.html"
        html_content = HTMLReportGenerator.generate(report)
        html_path.write_text(html_content)
        paths["html"] = html_path
        logger.info("Saved HTML report: %s", html_path)

        # Markdown
        md_path = self.output_dir / "COVERAGE.md"
        md_content = MarkdownReportGenerator.generate(report)
        md_path.write_text(md_content)
        paths["markdown"] = md_path
        logger.info("Saved Markdown report: %s", md_path)

        # Badges
        badges_dir = self.output_dir / "badges"
        badge_paths = BadgeGenerator.generate_all(report, badges_dir)
        paths.update({f"badge_{k}": v for k, v in badge_paths.items()})

        # JSON endpoint for dynamic badges
        endpoint_path = self.output_dir / "badge_endpoint.json"
        endpoint_data = {
            "schemaVersion": 1,
            "label": "API coverage",
            "message": f"{report.overall_score:.0f}%",
            "color": BadgeColor.from_percentage(report.overall_score),
            "namedLogo": "python",
        }
        with endpoint_path.open("w") as f:
            json.dump(endpoint_data, f, indent=2)
        paths["endpoint"] = endpoint_path
        logger.info("Saved badge endpoint: %s", endpoint_path)

        return paths


def generate_report(
    output_dir: str | Path = "coverage_reports",
    offline: bool = True,
) -> AggregateReport:
    """Generate coverage report (convenience function).

    Args:
        output_dir: Directory for output files.
        offline: If True, use cached data only (no API calls).

    Returns:
        AggregateReport with coverage data.
    """
    generator = ReportGenerator(output_dir=output_dir)

    if offline:
        report = generator.generate_aggregate_report_offline()
    else:
        raise NotImplementedError("Online report generation requires async context")

    generator.save_all_formats(report)
    return report


def main() -> int:
    """CLI entry point for report generator.

    Returns:
        Exit code (0 for success).
    """
    parser = argparse.ArgumentParser(
        description="Generate civi-py API compatibility coverage reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Generate offline report (uses cached schemas)
    python -m tests.compat.report_generator

    # Specify output directory
    python -m tests.compat.report_generator -o ./docs/coverage

    # Verbose output
    python -m tests.compat.report_generator -v

Output Formats:
    - coverage_report.json    JSON data for CI/CD integration
    - coverage_report.html    Standalone HTML report
    - COVERAGE.md             Markdown for documentation
    - badges/*.svg            SVG badges for README
    - badge_endpoint.json     shields.io JSON endpoint
        """,
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default="coverage_reports",
        help="Output directory for reports (default: coverage_reports)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["all", "json", "html", "markdown", "badges"],
        default="all",
        help="Output format (default: all)",
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    try:
        logger.info("Generating coverage report...")
        report = generate_report(output_dir=args.output, offline=True)

        # Print summary
        summary = report.summary()
        print("\n" + "=" * 60)
        print("civi-py API Compatibility Report")
        print("=" * 60)
        print(f"Overall Score:    {summary['overall_score']:.1f}%")
        print(f"Entity Coverage:  {summary['entity_coverage']:.1f}%")
        print(f"Action Coverage:  {summary['action_coverage']:.1f}%")
        print(f"Field Coverage:   {summary['field_coverage']:.1f}%")
        print(f"Type Accuracy:    {summary['type_accuracy']:.1f}%")
        print("=" * 60)
        print(f"\nReports saved to: {args.output}/")

        return 0

    except Exception:
        logger.exception("Failed to generate report")
        return 1


if __name__ == "__main__":
    sys.exit(main())
