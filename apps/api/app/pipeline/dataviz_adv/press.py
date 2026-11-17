"""K70 newspaper-style *original* finance brief over licensed footage.

This is not a screenshot of a news outlet. The words are K70-authored
summaries linked to verifiable reporting, with a conspicuous source/date label.
An actual newspaper scan is only usable as footage after separate rights review.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from urllib.parse import urlparse

from PIL import Image, ImageDraw

from .core import ChartTheme, DataError, clamp, eo3, font, put, text_tile


@dataclass(frozen=True)
class NewsBrief:
    headline: str                 # original K70 summary, not a lifted article
    publisher: str                # source that supports the summary
    published: str                # ISO YYYY-MM-DD
    source_url: str               # retained in video manifest
    topic: str = "FINANCE"

    def validate(self) -> "NewsBrief":
        if not self.headline.strip() or len(self.headline) > 125:
            raise DataError("news brief needs a concise original headline (max 125 chars)")
        if not self.publisher.strip() or len(self.publisher) > 65:
            raise DataError("news brief needs a concise real publisher/source")
        try:
            day = date.fromisoformat(self.published)
        except ValueError as e:
            raise DataError("published must be a real ISO calendar date") from e
        if day > date.today():
            raise DataError("news brief cannot cite a future publication date")
        url = urlparse(self.source_url)
        if url.scheme != "https" or not url.netloc or url.username or url.password:
            raise DataError("news brief needs a valid HTTPS evidence URL")
        if not self.topic.strip() or len(self.topic) > 36:
            raise DataError("news brief topic missing or too long")
        return self


def _fit_lines(text: str, face: str, max_width: int, max_lines: int = 5):
    """Pixel-accurate word wrap, with a font size that always fits the card."""
    for size in (78, 72, 66, 60, 54):
        f = font(face, size)
        lines = []
        row = ""
        for word in text.upper().split():
            trial = (row + " " + word).strip()
            if f.getlength(trial) <= max_width:
                row = trial
            else:
                if row:
                    lines.append(row)
                row = word
                if f.getlength(word) > max_width:
                    raise DataError("headline contains an unbreakably long word")
        if row:
            lines.append(row)
        if len(lines) <= max_lines:
            return lines, size
    raise DataError("news brief headline does not fit the 9:16 layout")


def draw_news_brief(layer: Image.Image, th: ChartTheme, news: NewsBrief, t: float,
                    *, hold: float = 2.4) -> None:
    """Draw a calm 2.4-second newspaper clipping reveal on an RGBA frame.

    The press card floats over real moving stock footage. It does not change
    footage, music or narration. Date/source are on-screen; URL remains in
    the sidecar manifest and video description. No publisher masthead is forged.
    """
    news.validate()
    if hold <= 0:
        raise DataError("hold must be positive")
    a = clamp(eo3(t / 0.28) * eo3((hold - t) / 0.34))
    if a <= 0.003:
        return

    x0, y0, x1, y1 = 82, 365, 998, 1295
    off = round(20 * (1 - eo3(t / 0.34)))
    x0, x1 = x0 + off, x1 + off

    # Warm newsprint, shallow shadow, lightly ruled—an editorial card not a
    # fabricated media outlet front page.
    card = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((x0 + 14, y0 + 18, x1 + 14, y1 + 18), 19, fill=(0, 0, 0, 80))
    d.rounded_rectangle((x0, y0, x1, y1), 18, fill=(248, 244, 231, 248),
                        outline=(206, 199, 182, 255), width=3)
    d.line((x0 + 48, y0 + 164, x1 - 48, y0 + 164), fill=(45, 57, 68, 180), width=3)
    d.line((x0 + 48, y1 - 158, x1 - 48, y1 - 158), fill=(45, 57, 68, 150), width=2)

    navy = (24, 35, 51)
    dim = (85, 89, 94)
    lines, size = _fit_lines(news.headline, th.display, 792)
    y = y0 + 210
    for line in lines:
        put(card, text_tile(line, th.display, size, navy, None, 0, 0),
            x0 + 62, y, tag="press-headline", size=size)
        y += size + 32
    if y > y1 - 170:
        raise DataError("newspaper headline overflows source/footer area")

    topic = news.topic.upper()
    put(card, text_tile("K70  /  MARKET BRIEF", th.body, 39, navy, None, 0, 0),
        x0 + 50, y0 + 43, tag="press-brand", size=39)
    put(card, text_tile(topic, th.body, 32, (123, 75, 175), None, 0, 0),
        x0 + 50, y0 + 102, tag="press-topic", size=32)

    date_label = date.fromisoformat(news.published).strftime("%b %d, %Y").upper()
    put(card, text_tile("SOURCE: " + news.publisher.upper(), th.body, 30, dim, None, 0, 0),
        x0 + 52, y1 - 124, tag="press-source", size=30)
    put(card, text_tile(date_label + "  •  K70 ORIGINAL SUMMARY", th.body, 30, dim, None, 0, 0),
        x0 + 52, y1 - 76, tag="press-date", size=30)

    if a < 1:
        alpha = card.getchannel("A").point(lambda v: int(v * a))
        card.putalpha(alpha)
    layer.alpha_composite(card)
