from __future__ import annotations

import hashlib
import html
import ipaddress
import re
import socket
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from xml.etree import ElementTree as ET

import httpx
from sqlalchemy.orm import Session

from app.models import IdeaQueueItem, IdeaQueueStatus
from app.schemas.news import (
    NewsCandidate,
    NewsDiscoveryRequest,
    NewsDiscoveryResponse,
    NewsPromotionRequest,
    NewsSourceFailure,
    NewsSourceInput,
)
from app.services.pipeline_service import build_idea_input_config, get_default_account


TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "mc_cid",
    "mc_eid",
    "ref",
    "ref_src",
}
ACTION_TERMS = {
    "acquires",
    "announces",
    "approves",
    "bans",
    "breaks",
    "cuts",
    "falls",
    "launches",
    "raises",
    "releases",
    "reveals",
    "surges",
    "wins",
}
MAX_FEED_BYTES = 2_000_000
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 8.0


class NewsSourceFetchError(RuntimeError):
    """Raised when a configured news source cannot be fetched safely."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return " ".join(html.unescape(without_tags).split())


def _child_text(element: ET.Element, names: set[str]) -> str:
    for child in list(element):
        if _local_name(child.tag) in names:
            text = "".join(child.itertext())
            cleaned = _clean_text(text)
            if cleaned:
                return cleaned
    return ""


def _entry_link(element: ET.Element, feed_url: str) -> str:
    for child in list(element):
        if _local_name(child.tag) != "link":
            continue
        href = (child.attrib.get("href") or "").strip()
        rel = (child.attrib.get("rel") or "alternate").lower()
        if href and rel in {"alternate", ""}:
            return _canonicalize_url(urljoin(feed_url, href))
        text = _clean_text("".join(child.itertext()))
        if text:
            return _canonicalize_url(urljoin(feed_url, text))
    return ""


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    cleaned = value.strip()
    try:
        parsed = parsedate_to_datetime(cleaned)
    except (TypeError, ValueError, OverflowError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _canonicalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return ""
    filtered_query = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=True):
        lowered = key.lower()
        if lowered.startswith("utm_") or lowered in TRACKING_QUERY_KEYS:
            continue
        filtered_query.append((key, value))
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return urlunsplit(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            urlencode(filtered_query, doseq=True),
            "",
        )
    )


def _normalized_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def _candidate_id(url: str, title: str) -> str:
    identity = url or _normalized_title(title)
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def parse_feed_xml(content: bytes | str, source: NewsSourceInput) -> list[dict]:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise NewsSourceFetchError(f"Invalid RSS/Atom XML: {exc}") from exc

    entry_nodes = [
        element
        for element in root.iter()
        if _local_name(element.tag) in {"item", "entry"}
    ]
    entries: list[dict] = []
    for node in entry_nodes:
        title = _child_text(node, {"title"})
        link = _entry_link(node, source.feed_url)
        if not title or not link:
            continue
        summary = _child_text(node, {"description", "summary", "content", "encoded"})
        published_raw = _child_text(node, {"pubdate", "published", "updated", "date"})
        entries.append(
            {
                "title": title,
                "url": link,
                "source_name": source.name,
                "source_quality": source.source_quality,
                "published_at": _parse_datetime(published_raw),
                "summary": summary,
            }
        )
    return entries


def _assert_public_host(url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").rstrip(".").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise NewsSourceFetchError("Feed URL must be an absolute http(s) URL.")
    if host == "localhost" or host.endswith(".localhost") or host.endswith(".local"):
        raise NewsSourceFetchError("Local/private feed hosts are not allowed.")

    addresses: set[str] = set()
    try:
        addresses.add(str(ipaddress.ip_address(host)))
    except ValueError:
        try:
            infos = socket.getaddrinfo(
                host,
                parsed.port or (443 if parsed.scheme == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        except socket.gaierror as exc:
            raise NewsSourceFetchError(f"Could not resolve feed host: {host}") from exc
        for info in infos:
            addresses.add(info[4][0])

    if not addresses:
        raise NewsSourceFetchError("Feed host did not resolve to an address.")
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address)
        except ValueError as exc:
            raise NewsSourceFetchError("Feed host resolved to an invalid address.") from exc
        if not ip.is_global:
            raise NewsSourceFetchError("Local/private feed addresses are not allowed.")


def fetch_news_source(source: NewsSourceInput) -> list[dict]:
    current_url = source.feed_url
    headers = {
        "User-Agent": "StoryEngineNews/1.0 (+RSS discovery)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.5",
    }
    with httpx.Client(
        timeout=httpx.Timeout(FETCH_TIMEOUT_SECONDS),
        follow_redirects=False,
        headers=headers,
    ) as client:
        for redirect_count in range(MAX_REDIRECTS + 1):
            _assert_public_host(current_url)
            try:
                response = client.get(current_url)
            except httpx.HTTPError as exc:
                raise NewsSourceFetchError(f"Feed request failed: {exc}") from exc

            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise NewsSourceFetchError("Feed redirect did not include a Location header.")
                if redirect_count >= MAX_REDIRECTS:
                    raise NewsSourceFetchError("Feed exceeded the redirect limit.")
                current_url = urljoin(current_url, location)
                continue

            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise NewsSourceFetchError(f"Feed returned HTTP {response.status_code}.") from exc

            content = response.content
            if len(content) > MAX_FEED_BYTES:
                raise NewsSourceFetchError("Feed is larger than the 2 MB safety limit.")
            return parse_feed_xml(
                content,
                NewsSourceInput(
                    name=source.name,
                    feed_url=current_url,
                    source_quality=source.source_quality,
                ),
            )

    raise NewsSourceFetchError("Feed could not be fetched.")


def _freshness_score(
    published_at: datetime | None,
    now: datetime,
    max_age_hours: int,
) -> float | None:
    if published_at is None:
        return 0.20
    age_hours = max(0.0, (now - published_at).total_seconds() / 3600.0)
    if age_hours > max_age_hours:
        return None
    return max(0.0, 1.0 - (age_hours / max_age_hours))


def _relevance_score(
    title: str,
    summary: str,
    keywords: list[str],
) -> tuple[float, list[str]]:
    title_lower = title.lower()
    summary_lower = summary.lower()
    title_hits = [keyword for keyword in keywords if keyword in title_lower]
    summary_hits = [keyword for keyword in keywords if keyword in summary_lower]
    matched = [
        keyword
        for keyword in keywords
        if keyword in title_hits or keyword in summary_hits
    ]
    weighted_hits = (2 * len(title_hits)) + len(summary_hits)
    score = min(1.0, weighted_hits / max(1, 3 * len(keywords)))
    return score, matched


def _instagram_potential_score(title: str, summary: str) -> float:
    words = title.lower().split()
    score = 0.35
    if 30 <= len(title) <= 110:
        score += 0.20
    if len(words) <= 14:
        score += 0.10
    if re.search(r"\d", title):
        score += 0.10
    if any(term in words for term in ACTION_TERMS):
        score += 0.15
    if summary:
        score += 0.10
    return min(1.0, score)


def _deduplicate_entries(entries: list[dict]) -> list[dict]:
    def preference(entry: dict) -> tuple[float, float, int]:
        published_at = entry.get("published_at")
        published_value = (
            published_at.timestamp()
            if isinstance(published_at, datetime)
            else 0.0
        )
        return (
            float(entry.get("source_quality") or 0.0),
            published_value,
            len(entry.get("summary") or ""),
        )

    ordered = sorted(entries, key=preference, reverse=True)
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    result: list[dict] = []
    for entry in ordered:
        canonical_url = _canonicalize_url(entry.get("url") or "")
        normalized_title = _normalized_title(entry.get("title") or "")
        if not canonical_url or not normalized_title:
            continue
        if canonical_url in seen_urls or normalized_title in seen_titles:
            continue
        entry = {**entry, "url": canonical_url}
        seen_urls.add(canonical_url)
        seen_titles.add(normalized_title)
        result.append(entry)
    return result


def rank_news_entries(
    entries: list[dict],
    payload: NewsDiscoveryRequest,
    *,
    now: datetime | None = None,
) -> tuple[list[NewsCandidate], int]:
    reference_time = now or datetime.now(UTC)
    if reference_time.tzinfo is None or reference_time.utcoffset() is None:
        reference_time = reference_time.replace(tzinfo=UTC)
    else:
        reference_time = reference_time.astimezone(UTC)

    deduplicated = _deduplicate_entries(entries)
    candidates: list[NewsCandidate] = []
    for entry in deduplicated:
        freshness = _freshness_score(
            entry.get("published_at"),
            reference_time,
            payload.max_age_hours,
        )
        if freshness is None:
            continue

        relevance, matched_keywords = _relevance_score(
            entry.get("title") or "",
            entry.get("summary") or "",
            payload.niche_keywords,
        )
        if relevance < payload.min_relevance_score:
            continue

        instagram_potential = _instagram_potential_score(
            entry.get("title") or "",
            entry.get("summary") or "",
        )
        source_quality = float(entry.get("source_quality") or 0.0)
        overall = (
            (0.35 * freshness)
            + (0.30 * relevance)
            + (0.20 * instagram_potential)
            + (0.15 * source_quality)
        )
        candidates.append(
            NewsCandidate(
                candidate_id=_candidate_id(entry["url"], entry["title"]),
                title=entry["title"],
                url=entry["url"],
                source_name=entry["source_name"],
                published_at=entry.get("published_at"),
                summary=entry.get("summary") or "",
                source_quality=round(source_quality, 3),
                matched_keywords=matched_keywords,
                freshness_score=round(freshness * 100, 1),
                relevance_score=round(relevance * 100, 1),
                instagram_potential_score=round(
                    instagram_potential * 100,
                    1,
                ),
                source_quality_score=round(source_quality * 100, 1),
                overall_score=round(overall * 100, 1),
            )
        )

    candidates.sort(
        key=lambda candidate: (
            candidate.overall_score,
            candidate.published_at.timestamp()
            if candidate.published_at
            else 0.0,
        ),
        reverse=True,
    )
    return candidates[: payload.limit], len(deduplicated)


def discover_news_candidates(
    payload: NewsDiscoveryRequest,
) -> NewsDiscoveryResponse:
    entries: list[dict] = []
    failures: list[NewsSourceFailure] = []
    fetched_sources = 0

    for source in payload.sources:
        try:
            source_entries = fetch_news_source(source)
        except NewsSourceFetchError as exc:
            failures.append(
                NewsSourceFailure(
                    source_name=source.name,
                    feed_url=source.feed_url,
                    error=str(exc)[:240],
                )
            )
            continue
        fetched_sources += 1
        entries.extend(source_entries)

    candidates, deduplicated_count = rank_news_entries(entries, payload)
    return NewsDiscoveryResponse(
        candidates=candidates,
        fetched_sources=fetched_sources,
        failed_sources=failures,
        raw_entries=len(entries),
        deduplicated_entries=deduplicated_count,
    )


def promote_news_candidate(
    db: Session,
    payload: NewsPromotionRequest,
) -> IdeaQueueItem:
    account = get_default_account(db)
    candidate = payload.candidate
    input_config = build_idea_input_config(
        account.account_config_json or {},
        {
            "content_type": "news_image",
            "target_platform": "instagram",
            "caption_tone": "concise factual news",
            "content_format": "news image",
            "style_preset": payload.style_preset,
        },
    )
    input_config["news_source"] = {
        "candidate_id": candidate.candidate_id,
        "source_name": candidate.source_name,
        "url": candidate.url,
        "published_at": (
            candidate.published_at.isoformat()
            if candidate.published_at
            else None
        ),
        "summary": candidate.summary,
    }
    input_config["news_ranking"] = {
        "overall_score": candidate.overall_score,
        "freshness_score": candidate.freshness_score,
        "relevance_score": candidate.relevance_score,
        "instagram_potential_score": (
            candidate.instagram_potential_score
        ),
        "source_quality_score": candidate.source_quality_score,
        "matched_keywords": candidate.matched_keywords,
    }

    item = IdeaQueueItem(
        account_id=account.id,
        topic=candidate.title,
        style_preset=input_config["style_preset"],
        input_config_json=input_config,
        target_platform="instagram",
        priority=payload.priority,
        status=IdeaQueueStatus.DRAFT,
        notes=(
            f"News source: {candidate.source_name}\n"
            f"{candidate.url}\n\n"
            f"{candidate.summary[:700]}"
        ),
        planned_date=None,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item
