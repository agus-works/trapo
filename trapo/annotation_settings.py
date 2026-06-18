from __future__ import annotations

from trapo.db import DuckConnection, table_exists
from trapo.server.models import AnnotationStyle, AnnotationStyleSetting


DEFAULT_REGION_KINDS = (
    "text",
    "title",
    "table",
    "table_cell",
    "formula",
    "image",
    "chart",
    "code",
    "list",
    "header",
    "footer",
    "footnote",
    "page_number",
    "other",
)

HEX_COLOR_LENGTH = 7

ENGINE_COLORS = {
    "docling": "#d55344",
    "docling_normalized": "#f07d5f",
    "mineru": "#36cfd1",
    "mineru_normalized": "#43b39f",
    "lmstudio": "#c490ff",
    "lmstudio_strict": "#8f86ff",
    "lmstudio_recall": "#e08bd6",
    "fusion": "#f1c232",
}

KIND_COLORS = {
    "text": "#d55344",
    "title": "#b85bd4",
    "table": "#35a36b",
    "table_cell": "#60b878",
    "formula": "#d09a23",
    "image": "#5f8df7",
    "chart": "#4fa9c6",
    "code": "#8f86ff",
    "list": "#d37b2d",
    "header": "#9aa4b2",
    "footer": "#9aa4b2",
    "footnote": "#b68b62",
    "page_number": "#9aa4b2",
    "other": "#d55344",
}


def default_annotation_settings() -> list[AnnotationStyleSetting]:
    settings: list[AnnotationStyleSetting] = []
    for engine, engine_color in ENGINE_COLORS.items():
        for region_kind in DEFAULT_REGION_KINDS:
            color = engine_color if region_kind == "other" else KIND_COLORS[region_kind]
            settings.append(
                AnnotationStyleSetting(
                    annotation_engine=engine,
                    region_kind=region_kind,
                    style=AnnotationStyle(
                        stroke_color=color,
                        fill_color=color,
                        stroke_opacity=0.82,
                        fill_opacity=0.14,
                        stroke_width=2.0,
                    ),
                )
            )
    return settings


def read_annotation_settings(
    connection: DuckConnection,
) -> list[AnnotationStyleSetting]:
    settings_by_key = {
        _setting_key(setting): setting for setting in default_annotation_settings()
    }
    if not table_exists(connection, "annotation_style_settings"):
        return list(settings_by_key.values())

    rows = connection.execute(
        """
        SELECT
            annotation_engine, region_kind, label, stroke_color, fill_color,
            stroke_opacity, fill_opacity, stroke_width
        FROM annotation_style_settings
        ORDER BY annotation_engine, region_kind, label
        """
    ).fetchall()
    for row in rows:
        setting = AnnotationStyleSetting(
            annotation_engine=str(row[0]),
            region_kind=str(row[1]),
            label=str(row[2] or ""),
            style=AnnotationStyle(
                stroke_color=str(row[3]),
                fill_color=str(row[4]),
                stroke_opacity=float(row[5]),
                fill_opacity=float(row[6]),
                stroke_width=float(row[7]),
            ),
        )
        settings_by_key[_setting_key(setting)] = setting
    return list(settings_by_key.values())


def upsert_annotation_settings(
    connection: DuckConnection,
    settings: list[AnnotationStyleSetting],
) -> int:
    if not table_exists(connection, "annotation_style_settings"):
        return 0
    updated = 0
    for setting in settings:
        style = normalized_style(setting.style)
        connection.execute(
            """
            INSERT INTO annotation_style_settings (
                annotation_engine, region_kind, label, stroke_color, fill_color,
                stroke_opacity, fill_opacity, stroke_width
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (annotation_engine, region_kind, label) DO UPDATE SET
                stroke_color = excluded.stroke_color,
                fill_color = excluded.fill_color,
                stroke_opacity = excluded.stroke_opacity,
                fill_opacity = excluded.fill_opacity,
                stroke_width = excluded.stroke_width,
                updated_at = now()
            """,
            [
                setting.annotation_engine.strip().lower(),
                setting.region_kind.strip().lower() or "other",
                setting.label.strip(),
                style.stroke_color,
                style.fill_color,
                style.stroke_opacity,
                style.fill_opacity,
                style.stroke_width,
            ],
        )
        updated += 1
    return updated


def annotation_style_lookup(
    connection: DuckConnection,
) -> dict[tuple[str, str, str], AnnotationStyle]:
    return {
        _setting_key(setting): setting.style
        for setting in read_annotation_settings(connection)
    }


def resolve_annotation_style(
    styles: dict[tuple[str, str, str], AnnotationStyle],
    *,
    annotation_engine: str,
    region_kind: str,
    label: str | None,
) -> AnnotationStyle:
    engine = annotation_engine.strip().lower() or "docling"
    kind = region_kind.strip().lower() or "other"
    label_value = (label or "").strip()
    fallback_color = ENGINE_COLORS.get(engine, "#9aa4b2")
    return (
        styles.get((engine, kind, label_value))
        or styles.get((engine, kind, ""))
        or styles.get((engine, "other", ""))
        or AnnotationStyle(
            stroke_color=fallback_color,
            fill_color=fallback_color,
            stroke_opacity=0.82,
            fill_opacity=0.14,
            stroke_width=2.0,
        )
    )


def normalized_style(style: AnnotationStyle) -> AnnotationStyle:
    return AnnotationStyle(
        stroke_color=_hex_color(style.stroke_color, "#d55344"),
        fill_color=_hex_color(style.fill_color, "#d55344"),
        stroke_opacity=_clamp(style.stroke_opacity, 0.0, 1.0),
        fill_opacity=_clamp(style.fill_opacity, 0.0, 1.0),
        stroke_width=_clamp(style.stroke_width, 1.0, 8.0),
    )


def _setting_key(setting: AnnotationStyleSetting) -> tuple[str, str, str]:
    return (
        setting.annotation_engine.strip().lower(),
        setting.region_kind.strip().lower() or "other",
        setting.label.strip(),
    )


def _hex_color(value: str, fallback: str) -> str:
    normalized = value.strip()
    if len(normalized) == HEX_COLOR_LENGTH and normalized.startswith("#"):
        digits = normalized[1:]
        if all(char in "0123456789abcdefABCDEF" for char in digits):
            return normalized.lower()
    return fallback


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, float(value)))
