"""Small ECharts helpers for server-rendered pages.

The app only plots posted actuals. This module never creates, fills or smooths a
data point; callers pass the exact series they already show in a table. Options
are JSON-safe dictionaries so no page builds JavaScript by string interpolation.
"""
from __future__ import annotations

import json
import re
from typing import Any

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")


def container(chart_id: str, height: int = 320) -> str:
    """Return the empty element ECharts mounts into."""
    if not _ID_RE.match(chart_id):
        raise ValueError(f"Invalid chart id: {chart_id!r}")
    height = max(180, min(int(height), 900))
    return f'<div id="{chart_id}" class="echart" style="height:{height}px"></div>'


def empty(message: str = "No posted actuals to chart for this period.") -> str:
    """A consistent empty state instead of drawing invented zero series."""
    return f'<div class="echart-empty">{_escape(message)}</div>'


def render(charts: list[dict[str, Any]], *, include_library: bool = True) -> str:
    """Return the ECharts library tag and one init script for a page.

    Each chart item is ``{"id": str, "option": dict}``. Callers put
    :func:`container` in the page body and call this at the end of the body.
    """
    valid: list[dict[str, Any]] = []
    for item in charts:
        chart_id = item.get("id")
        option = item.get("option")
        if not chart_id or not isinstance(option, dict):
            raise ValueError("A chart needs an id and an option dictionary")
        if not _ID_RE.match(chart_id):
            raise ValueError(f"Invalid chart id: {chart_id!r}")
        valid.append({"id": chart_id, "option": option})
    if not valid:
        return ""

    parts: list[str] = []
    if include_library:
        parts.append('<script src="/static/echarts.min.js"></script>')
    parts.append(
        "<script>\n"
        "(function () {\n"
        "  if (!window.echarts) return;\n"
        "  var root = getComputedStyle(document.documentElement);\n"
        "  function css(name, fallback) {\n"
        "    var value = root.getPropertyValue(name);\n"
        "    return (value && value.trim()) || fallback;\n"
        "  }\n"
        "  var palette = [\n"
        "    css('--chart-b', '#2563EB'), '#D97706', '#0F766E', '#7C3AED',\n"
        "    '#059669', '#B45309', '#64748B', '#DB2777', '#0891B2', '#65A30D'\n"
        "  ];\n"
        "  var muted = css('--muted', '#6C757D');\n"
        "  var line = css('--line', '#E6EDF7');\n"
        "  var ink = css('--ink', '#212529');\n"
        "  function inr(value) {\n"
        "    var n = Number(value);\n"
        "    if (!isFinite(n)) return String(value);\n"
        "    return '\\u20b9' + n.toLocaleString('en-IN', {\n"
        "      minimumFractionDigits: 2, maximumFractionDigits: 2\n"
        "    });\n"
        "  }\n"
        "  function compact(value) {\n"
        "    var n = Number(value);\n"
        "    if (!isFinite(n)) return String(value);\n"
        "    var sign = n < 0 ? '-' : '';\n"
        "    n = Math.abs(n);\n"
        "    if (n >= 10000000) return sign + (n / 10000000).toFixed(1) + ' Cr';\n"
        "    if (n >= 100000) return sign + (n / 100000).toFixed(1) + ' L';\n"
        "    if (n >= 1000) return sign + (n / 1000).toFixed(1) + 'k';\n"
        "    return sign + n.toFixed(0);\n"
        "  }\n"
        "  function styleAxis(axis) {\n"
        "    if (!axis) return;\n"
        "    var list = Array.isArray(axis) ? axis : [axis];\n"
        "    list.forEach(function (a) {\n"
        "      if (!a.axisLabel) a.axisLabel = {};\n"
        "      if (!a.axisLabel.color) a.axisLabel.color = muted;\n"
        "      if (a.type === 'value' && !a.axisLabel.formatter) {\n"
        "        a.axisLabel.formatter = compact;\n"
        "      }\n"
        "      if (a.type === 'value' && !a.splitLine) {\n"
        "        a.splitLine = { lineStyle: { color: line } };\n"
        "      }\n"
        "      if (!a.axisLine) a.axisLine = { lineStyle: { color: line } };\n"
        "    });\n"
        "  }\n"
        "  function applyDefaults(option) {\n"
        "    option.animationDuration = option.animationDuration || 400;\n"
        "    option.aria = option.aria || { enabled: true };\n"
        "    if (!option.color) option.color = palette;\n"
        "    if (option.tooltip) {\n"
        "      if (!option.tooltip.valueFormatter) option.tooltip.valueFormatter = inr;\n"
        "      if (option.tooltip.trigger === 'axis' && !option.tooltip.axisPointer) {\n"
        "        option.tooltip.axisPointer = { type: 'shadow' };\n"
        "      }\n"
        "    }\n"
        "    if (option.legend) {\n"
        "      var legends = Array.isArray(option.legend) ? option.legend : [option.legend];\n"
        "      legends.forEach(function (legend) {\n"
        "        if (!legend.textStyle) legend.textStyle = { color: muted };\n"
        "      });\n"
        "    }\n"
        "    styleAxis(option.xAxis);\n"
        "    styleAxis(option.yAxis);\n"
        "    if (!option.grid && option.xAxis && option.yAxis) {\n"
        "      option.grid = { left: 64, right: 24, top: 42, bottom: 34, containLabel: true };\n"
        "    } else if (option.grid && option.grid.containLabel === undefined) {\n"
        "      option.grid.containLabel = true;\n"
        "    }\n"
        "    var horizontal = !!(option.yAxis && option.yAxis.type === 'category');\n"
        "    if (option.series) {\n"
        "      option.series.forEach(function (series) {\n"
        "        if (series.type === 'pie') {\n"
        "          if (!series.label) series.label = {};\n"
        "          if (!series.label.formatter) series.label.formatter = '{b}  {d}%';\n"
        "          if (!series.label.color) series.label.color = ink;\n"
        "          if (!series.label.fontSize) series.label.fontSize = 11;\n"
        "          if (series.labelLine && series.labelLine.length === undefined) {\n"
        "            series.labelLine.length = 10;\n"
        "          }\n"
        "        }\n"
        "        if (series.type === 'bar' && !series.itemStyle) {\n"
        "          series.itemStyle = { borderRadius: horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0] };\n"
        "        }\n"
        "      });\n"
        "    }\n"
        "    return option;\n"
        "  }\n"
        f"  var charts = {_json(valid)};\n"
        "  charts.forEach(function (item) {\n"
        "    var el = document.getElementById(item.id);\n"
        "    if (!el) return;\n"
        "    var chart = echarts.init(el, null, { renderer: 'canvas' });\n"
        "    chart.setOption(applyDefaults(item.option));\n"
        "    window.addEventListener('resize', function () { chart.resize(); });\n"
        "  });\n"
        "})();\n"
        "</script>"
    )
    return "".join(parts)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
