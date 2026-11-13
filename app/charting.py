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


def render(charts: list[dict[str, Any]], *, include_library: bool = True,
           lang: str = "en", maps: list[dict[str, str]] | None = None) -> str:
    """Return the ECharts library tag and one init script for a page.

    Each chart item is ``{"id": str, "option": dict}`` and may add
    ``"format": "money" | "percent"``. Callers put :func:`container` in the
    page body and call this at the end of the body.

    ``maps`` is an optional list of ``{"name": str, "url": str}`` GeoJSON
    sources. When supplied, the script loads and registers them before it
    initialises chart instances, so a map series can use the registered name.
    """
    valid: list[dict[str, Any]] = []
    for item in charts:
        chart_id = item.get("id")
        option = item.get("option")
        if not chart_id or not isinstance(option, dict):
            raise ValueError("A chart needs an id and an option dictionary")
        if not _ID_RE.match(chart_id):
            raise ValueError(f"Invalid chart id: {chart_id!r}")
        value_format = item.get("format", "money")
        if value_format not in ("money", "percent", "number"):
            raise ValueError(f"Invalid chart format: {value_format!r}")
        valid.append({"id": chart_id, "option": option, "format": value_format})
    if not valid:
        return ""

    map_defs = []
    for item in maps or []:
        name = item.get("name")
        url = item.get("url")
        if name and url:
            map_defs.append({"name": str(name), "url": str(url)})

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
        "  var hindi = " + ("true" if lang == "hi" else "false") + ";\n"
        "  function devanagari(text) {\n"
        "    if (!hindi) return String(text);\n"
        "    return String(text).replace(/[0-9]/g, function (digit) {\n"
        "      return '०१२३४५६७८९'.charAt(Number(digit));\n"
        "    });\n"
        "  }\n"
        "  function inr(value) {\n"
        "    var n = Number(value);\n"
        "    if (!isFinite(n)) return String(value);\n"
        "    return devanagari('\\u20b9' + n.toLocaleString('en-IN', {\n"
        "      minimumFractionDigits: 2, maximumFractionDigits: 2\n"
        "    }));\n"
        "  }\n"
        "  function percent(value) {\n"
        "    var n = Number(value);\n"
        "    if (!isFinite(n)) return String(value);\n"
        "    return devanagari(n.toFixed(1)) + '%';\n"
        "  }\n"
        "  function compact(value) {\n"
        "    var n = Number(value);\n"
        "    if (!isFinite(n)) return String(value);\n"
        "    var sign = n < 0 ? '-' : '';\n"
        "    n = Math.abs(n);\n"
        "    if (n >= 10000000) return devanagari(sign + (n / 10000000).toFixed(1) + ' Cr');\n"
        "    if (n >= 100000) return devanagari(sign + (n / 100000).toFixed(1) + ' L');\n"
        "    if (n >= 1000) return devanagari(sign + (n / 1000).toFixed(1) + 'k');\n"
        "    return devanagari(sign + n.toFixed(0));\n"
        "  }\n"
        "  function styleAxis(axis, fmt, percentAxis) {\n"
        "    if (!axis) return;\n"
        "    var list = Array.isArray(axis) ? axis : [axis];\n"
        "    list.forEach(function (a) {\n"
        "      if (!a.axisLabel) a.axisLabel = {};\n"
        "      if (!a.axisLabel.color) a.axisLabel.color = muted;\n"
        "      if (a.type === 'value' && !a.axisLabel.formatter) {\n"
        "        a.axisLabel.formatter = percentAxis ? percent : compact;\n"
        "      }\n"
        "      if (a.type === 'value' && !a.splitLine) {\n"
        "        a.splitLine = { lineStyle: { color: line } };\n"
        "      }\n"
        "      if (!a.axisLine) a.axisLine = { lineStyle: { color: line } };\n"
        "    });\n"
        "  }\n"
        "  function applyDefaults(option, valueFormat) {\n"
        "    option.animationDuration = option.animationDuration || 400;\n"
        "    option.aria = option.aria || { enabled: true };\n"
        "    if (!option.color) option.color = palette;\n"
        "    var fmt = valueFormat === 'percent' ? percent : inr;\n"
        "    if (option.tooltip) {\n"
        "      if (!option.tooltip.valueFormatter) option.tooltip.valueFormatter = fmt;\n"
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
        "    styleAxis(option.xAxis, fmt, valueFormat === 'percent');\n"
        "    styleAxis(option.yAxis, fmt, valueFormat === 'percent');\n"
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
        "  function initCharts() {\n"
        f"    var charts = {_json(valid)};\n"
        "    charts.forEach(function (item) {\n"
        "      var el = document.getElementById(item.id);\n"
        "      if (!el) return;\n"
        "      try {\n"
        "        var chart = echarts.init(el, null, { renderer: 'canvas' });\n"
        "        chart.setOption(applyDefaults(item.option, item.format));\n"
        "        window.addEventListener('resize', function () { chart.resize(); });\n"
        "      } catch (error) {\n"
        "        el.innerHTML = '<div class=\"echart-empty\">Chart could not be drawn from the available actuals.</div>';\n"
        "      }\n"
        "    });\n"
        "  }\n"
        f"  var maps = {_json(map_defs)};\n"
        "  if (maps.length) {\n"
        "    Promise.all(maps.map(function (item) {\n"
        "      return fetch(item.url).then(function (response) {\n"
        "        if (!response.ok) throw new Error('map load failed');\n"
        "        return response.json();\n"
        "      }).then(function (geo) {\n"
        "        echarts.registerMap(item.name, geo);\n"
        "      });\n"
        "    })).then(initCharts).catch(function () { initCharts(); });\n"
        "  } else {\n"
        "    initCharts();\n"
        "  }\n"
        "})();\n"
        "</script>"
    )
    return "".join(parts)


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _escape(value: str) -> str:
    return (value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
