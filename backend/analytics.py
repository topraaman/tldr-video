"""Video analytics computed from public yt-dlp metadata.

Only public data is available here (views, likes, comments, subscribers, tags,
description...). Impressions, CTR and watch time require YouTube Studio access
for the channel owner, so "reach" is estimated from the public numbers.
"""
import re
from collections import Counter
from datetime import datetime, timezone

_STOPWORDS = set("""
a an the and or but if of to in on at by for with from as is are was were be been
being it its this that these those i you he she we they me my your our their his her
them us do does did not no yes so than then too very can will just about into over
out up down more most some any all how what when where who why which video videos
new get got make like one two also only here there have has had what's it's don't
youtube subscribe channel watch http https www com
""".split())

# Rough public benchmarks for YouTube engagement (percent of views)
LIKE_RATE_TYPICAL = (2.0, 5.0)
COMMENT_RATE_TYPICAL = (0.05, 0.5)
ENGAGEMENT_TYPICAL = (2.0, 6.0)


def _pct(part, whole):
    if not part or not whole:
        return None
    return round(part / whole * 100, 3)


def _words(text: str) -> list:
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'+#-]{2,}", (text or "").lower())
            if w not in _STOPWORDS and not w.isdigit()]


def _rate_status(value, typical):
    """Classify a rate against a (low, high) typical band."""
    if value is None:
        return "unknown"
    low, high = typical
    if value >= high:
        return "good"
    if value >= low:
        return "ok"
    return "low"


def _seo_checks(info: dict, keywords: list) -> list:
    title = info.get("title") or ""
    description = info.get("description") or ""
    tags = info.get("tags") or []
    hashtags = re.findall(r"#\w+", description)
    has_chapters = bool(info.get("chapters")) or bool(
        re.search(r"(^|\n)\s*\(?\d{1,2}:\d{2}", description))
    has_captions = bool(info.get("subtitles"))
    has_auto_captions = bool(info.get("automatic_captions"))
    max_thumb_width = max((t.get("width") or 0 for t in info.get("thumbnails") or []), default=0)
    top_keyword = keywords[0]["word"] if keywords else None

    def check(key, label, passed, weight, detail, tip):
        return {"key": key, "label": label, "passed": bool(passed), "weight": weight,
                "detail": detail, "tip": "" if passed else tip}

    title_len = len(title)
    desc_len = len(description)
    return [
        check("title_length", "Title length", 30 <= title_len <= 70, 15,
              f"{title_len} characters",
              "Aim for 30-70 characters so the full title shows in search results."),
        check("keyword_in_title", "Main keyword in title",
              top_keyword and top_keyword in title.lower(), 15,
              f"Top keyword: \"{top_keyword}\"" if top_keyword else "No keywords found",
              "Put your main keyword near the start of the title."),
        check("description_length", "Description length", desc_len >= 250, 15,
              f"{desc_len} characters",
              "Write at least 250 characters; the first 2 lines matter most."),
        check("keyword_in_description", "Main keyword in description opening",
              top_keyword and top_keyword in description[:200].lower(), 10,
              "Checked first 200 characters",
              "Mention the main keyword in the first sentence of the description."),
        check("tags", "Tags", 5 <= len(tags) <= 30, 10, f"{len(tags)} tags",
              "Add 5-15 relevant tags, including common misspellings and variations."),
        check("hashtags", "Hashtags", 1 <= len(hashtags) <= 5, 5, f"{len(hashtags)} hashtags",
              "Add 1-3 hashtags to the description; they appear above the title."),
        check("chapters", "Chapters / timestamps", has_chapters, 10,
              "Found" if has_chapters else "None",
              "Add timestamps (0:00 Intro ...) to get chapters and key moments in Google."),
        check("captions", "Captions", has_captions or has_auto_captions, 10,
              "Manual" if has_captions else ("Auto-generated only" if has_auto_captions else "None"),
              "Upload captions; they are indexed for search and improve accessibility."),
        check("hd_thumbnail", "HD custom thumbnail", max_thumb_width >= 1280, 10,
              f"Max width {max_thumb_width}px" if max_thumb_width else "Unknown",
              "Use a 1280x720 thumbnail (try the Thumbnail Studio tab)."),
    ]


def build_analytics(info: dict, now: datetime = None) -> dict:
    """Turn a yt-dlp info dict into metrics, reach estimates and an SEO report."""
    now = now or datetime.now(timezone.utc)

    views = info.get("view_count")
    likes = info.get("like_count")
    comments = info.get("comment_count")
    subscribers = info.get("channel_follower_count")

    upload_date = info.get("upload_date")  # YYYYMMDD
    published = None
    days_live = None
    if upload_date:
        try:
            published = datetime.strptime(upload_date, "%Y%m%d").replace(tzinfo=timezone.utc)
            days_live = max((now - published).days, 1)
        except ValueError:
            pass

    like_rate = _pct(likes, views)
    comment_rate = _pct(comments, views)
    engagement = _pct((likes or 0) + (comments or 0), views) if (likes or comments) else None
    views_per_day = round(views / days_live) if views and days_live else None
    reach_ratio = round(views / subscribers, 2) if views and subscribers else None

    if reach_ratio is None:
        reach_tier = "Unknown"
    elif reach_ratio >= 3:
        reach_tier = "Viral - reached far beyond subscribers"
    elif reach_ratio >= 1:
        reach_tier = "Broad - reached beyond the subscriber base"
    elif reach_ratio >= 0.1:
        reach_tier = "Core - mostly reached existing audience"
    else:
        reach_tier = "Limited - reached a small share of subscribers"

    # Keywords: tags count triple, title double, description once
    counter = Counter()
    for tag in info.get("tags") or []:
        for w in _words(tag):
            counter[w] += 3
    for w in _words(info.get("title")):
        counter[w] += 2
    for w in _words(info.get("description")):
        counter[w] += 1
    keywords = [{"word": w, "score": s} for w, s in counter.most_common(12)]

    checks = _seo_checks(info, keywords)
    total_weight = sum(c["weight"] for c in checks)
    seo_score = round(sum(c["weight"] for c in checks if c["passed"]) / total_weight * 100)

    return {
        "video": {
            "id": info.get("id"),
            "title": info.get("title"),
            "channel": info.get("channel") or info.get("uploader"),
            "channel_url": info.get("channel_url"),
            "verified": bool(info.get("channel_is_verified")),
            "published": published.date().isoformat() if published else None,
            "duration": info.get("duration"),
            "categories": info.get("categories") or [],
            "tags": info.get("tags") or [],
            "language": info.get("language"),
            "resolution": info.get("resolution"),
            "is_short": bool(info.get("duration") and info["duration"] <= 60),
        },
        "metrics": {
            "views": views,
            "likes": likes,
            "comments": comments,
            "subscribers": subscribers,
            "days_live": days_live,
            "views_per_day": views_per_day,
        },
        "engagement": {
            "like_rate": like_rate,
            "comment_rate": comment_rate,
            "engagement_rate": engagement,
            "like_rate_status": _rate_status(like_rate, LIKE_RATE_TYPICAL),
            "comment_rate_status": _rate_status(comment_rate, COMMENT_RATE_TYPICAL),
            "engagement_status": _rate_status(engagement, ENGAGEMENT_TYPICAL),
            "benchmarks": {
                "like_rate": LIKE_RATE_TYPICAL,
                "comment_rate": COMMENT_RATE_TYPICAL,
                "engagement_rate": ENGAGEMENT_TYPICAL,
            },
        },
        "reach": {
            "views_to_subscribers": reach_ratio,
            "tier": reach_tier,
        },
        "seo": {
            "score": seo_score,
            "checks": checks,
            "keywords": keywords,
        },
    }
