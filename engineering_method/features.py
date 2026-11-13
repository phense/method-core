"""Readable capability inventory separate from canonical backlog execution state."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
from pathlib import Path
import re

from .models import Feature, utc_timestamp


SCHEMA_VERSION = 1
MARKER_PATTERN = re.compile(r"^\s*<!-- engineering-method:feature (?P<payload>\{.*\}) -->\s*$")
VISIBLE_FEATURE_PATTERN = re.compile(r"^## `(?P<id>F-[0-9]+)` (?P<name>.+)$")
PRE_RELEASE_STATEMENT = (
    "Peter's Engineering Method is currently pre-release. No plugin capability has been implemented "
    "or released yet."
)
ALLOWED_MARKER_FIELDS = frozenset(
    {
        "schema_version",
        "id",
        "name",
        "summary",
        "status",
        "related_backlog_ids",
        "updated_at",
        "rationale",
    }
)
BACKLOG_ONLY_FIELDS = frozenset(
    {"priority", "depends_on", "implementation_status", "blocker", "blocker_state"}
)


@dataclass(frozen=True)
class FeatureDocument:
    """The historical inventory of user-visible or architectural capabilities."""

    features: tuple[Feature, ...]
    removal_rationales: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.features, tuple):
            raise ValueError("features must be a tuple")
        identifiers = [entry.id for entry in self.features]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate feature ID")
        if not isinstance(self.removal_rationales, tuple):
            raise ValueError("removal rationales must be a tuple")
        rationale_ids: set[str] = set()
        feature_by_id = {entry.id: entry for entry in self.features}
        for entry in self.removal_rationales:
            if (
                not isinstance(entry, tuple)
                or len(entry) != 2
                or not isinstance(entry[0], str)
                or not isinstance(entry[1], str)
                or not entry[1].strip()
                or "\n" in entry[1]
                or "\r" in entry[1]
            ):
                raise ValueError("each removal rationale must contain an ID and non-empty text")
            if entry[0] in rationale_ids or entry[0] not in feature_by_id:
                raise ValueError("removal rationale must identify one feature exactly once")
            if feature_by_id[entry[0]].status != "removed":
                raise ValueError("only removed features may have a removal rationale")
            rationale_ids.add(entry[0])
        removed_ids = {entry.id for entry in self.features if entry.status == "removed"}
        if removed_ids != rationale_ids:
            raise ValueError("every removed feature requires exactly one removal rationale")


def _feature_sort_key(entry: Feature) -> tuple[int, str]:
    return int(entry.id.removeprefix("F-")), entry.id


def _rationale_by_id(document: FeatureDocument) -> dict[str, str]:
    return dict(document.removal_rationales)


def _marker_payload(entry: Feature, rationale: str | None) -> str:
    payload: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "id": entry.id,
        "name": entry.name,
        "summary": entry.summary,
        "status": entry.status,
        "related_backlog_ids": list(entry.related_backlog_ids),
        "updated_at": entry.updated_at,
    }
    if rationale is not None:
        payload["rationale"] = rationale
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def render_features(document: FeatureDocument) -> str:
    """Render the feature inventory without exposing it as a second task tracker."""
    if not document.features:
        return (
            "# Features\n\n"
            f"{PRE_RELEASE_STATEMENT}\n\n"
            "This file records working, user-visible or architectural capabilities after they exist. "
            "Planned work belongs only in `BACKLOG.md`.\n"
        )
    lines = [
        "# Features",
        "",
        "This inventory records implemented, changed, and historically removed capabilities. "
        "Planned work belongs only in `BACKLOG.md`.",
    ]
    rationales = _rationale_by_id(document)
    for entry in sorted(document.features, key=_feature_sort_key):
        lines.extend(
            [
                "",
                f"<!-- engineering-method:feature {_marker_payload(entry, rationales.get(entry.id))} -->",
                f"## `{entry.id}` {entry.name}",
                "",
                f"- Status: {entry.status}",
                f"- Summary: {entry.summary}",
            ]
        )
        if entry.related_backlog_ids:
            references = ", ".join(f"`{identifier}`" for identifier in entry.related_backlog_ids)
            lines.append(f"- Related backlog: {references}")
        if entry.id in rationales:
            lines.append(f"- Removal rationale: {rationales[entry.id]}")
    return "\n".join(lines).rstrip() + "\n"


def _parse_marker(payload: object, visible: re.Match[str]) -> tuple[Feature, str | None]:
    if not isinstance(payload, dict) or payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("feature marker must use schema_version 1")
    fields = frozenset(payload)
    if fields & BACKLOG_ONLY_FIELDS or not fields <= ALLOWED_MARKER_FIELDS:
        raise ValueError("feature marker contains backlog-only or unknown fields")
    required = {
        "id",
        "name",
        "summary",
        "status",
        "related_backlog_ids",
        "updated_at",
    }
    if not required <= fields or not isinstance(payload["related_backlog_ids"], list):
        raise ValueError("feature marker is incomplete")
    try:
        entry = Feature(
            id=payload["id"],
            name=payload["name"],
            summary=payload["summary"],
            status=payload["status"],
            related_backlog_ids=tuple(payload["related_backlog_ids"]),
            updated_at=payload["updated_at"],
        )
    except (TypeError, ValueError) as error:
        raise ValueError("feature marker contains invalid feature data") from error
    if visible.group("id") != entry.id or visible.group("name") != entry.name:
        raise ValueError("feature marker and visible heading disagree")
    rationale = payload.get("rationale")
    if rationale is not None and (not isinstance(rationale, str) or not rationale.strip()):
        raise ValueError("feature removal rationale must be non-empty text")
    if rationale is not None and entry.status != "removed":
        raise ValueError("only removed features may have a rationale")
    return entry, rationale


def load_features(path: Path) -> FeatureDocument:
    """Load the validated marker-backed inventory or the initial pre-release document."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"cannot read features inventory: {path}") from error
    features: list[Feature] = []
    rationales: list[tuple[str, str]] = []
    marker_indices = {index for index, line in enumerate(lines) if MARKER_PATTERN.fullmatch(line)}
    visible_indices = {
        index for index, line in enumerate(lines) if VISIBLE_FEATURE_PATTERN.fullmatch(line)
    }
    for index in visible_indices:
        if index == 0 or index - 1 not in marker_indices:
            raise ValueError("visible feature has no immediately preceding marker")
    for index, line in enumerate(lines):
        marker = MARKER_PATTERN.fullmatch(line)
        if marker is None:
            continue
        if index + 1 >= len(lines):
            raise ValueError("feature marker must precede a visible heading")
        visible = VISIBLE_FEATURE_PATTERN.fullmatch(lines[index + 1])
        if visible is None:
            raise ValueError("feature marker must immediately precede a visible heading")
        try:
            payload = json.loads(marker.group("payload"))
        except json.JSONDecodeError as error:
            raise ValueError("feature marker contains invalid JSON") from error
        entry, rationale = _parse_marker(payload, visible)
        expected_lines = [
            "",
            f"- Status: {entry.status}",
            f"- Summary: {entry.summary}",
        ]
        if entry.related_backlog_ids:
            expected_lines.append(
                "- Related backlog: "
                + ", ".join(f"`{identifier}`" for identifier in entry.related_backlog_ids)
            )
        if rationale is not None:
            expected_lines.append(f"- Removal rationale: {rationale}")
        actual_lines = lines[index + 2 : index + 2 + len(expected_lines)]
        if actual_lines != expected_lines:
            raise ValueError("feature marker and visible fields disagree")
        following = index + 2 + len(expected_lines)
        if following < len(lines) and any(
            lines[following].startswith(prefix)
            for prefix in (
                "- Status:",
                "- Summary:",
                "- Related backlog:",
                "- Removal rationale:",
            )
        ):
            raise ValueError("feature marker and visible fields disagree")
        features.append(entry)
        if rationale is not None:
            rationales.append((entry.id, rationale))
    if not features and PRE_RELEASE_STATEMENT not in "\n".join(lines):
        raise ValueError("feature inventory has no validated capabilities or pre-release statement")
    return FeatureDocument(features=tuple(features), removal_rationales=tuple(rationales))


def upsert_feature(document: FeatureDocument, feature: Feature) -> FeatureDocument:
    """Add or update one capability without discarding its historical backlog links."""
    existing = {entry.id: entry for entry in document.features}
    prior = existing.get(feature.id)
    if prior is not None:
        related = tuple(dict.fromkeys(prior.related_backlog_ids + feature.related_backlog_ids))
        feature = replace(feature, related_backlog_ids=related)
    existing[feature.id] = feature
    rationales = _rationale_by_id(document)
    if feature.status != "removed":
        rationales.pop(feature.id, None)
    return FeatureDocument(
        features=tuple(sorted(existing.values(), key=_feature_sort_key)),
        removal_rationales=tuple(sorted(rationales.items())),
    )


def remove_feature(
    document: FeatureDocument,
    feature_id: str,
    *,
    rationale: str,
    updated_at: str | None = None,
) -> FeatureDocument:
    """Record a removed capability while preserving its stable identity and task links."""
    if (
        not isinstance(rationale, str)
        or not rationale.strip()
        or "\n" in rationale
        or "\r" in rationale
    ):
        raise ValueError("feature removal rationale must be non-empty")
    features = {entry.id: entry for entry in document.features}
    if feature_id not in features:
        raise ValueError(f"feature does not exist: {feature_id}")
    features[feature_id] = replace(
        features[feature_id], status="removed", updated_at=updated_at or utc_timestamp()
    )
    rationales = _rationale_by_id(document)
    rationales[feature_id] = rationale
    return FeatureDocument(
        features=tuple(sorted(features.values(), key=_feature_sort_key)),
        removal_rationales=tuple(sorted(rationales.items())),
    )
