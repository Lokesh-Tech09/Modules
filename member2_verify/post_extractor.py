"""
Post and metadata extractor for Module 2: Claimed-Profile Verification (Self-Match).
Extracts primary image, caption, title, author, and structured metadata from public URLs.
Priority chain: OpenGraph -> JSON-LD -> Twitter Cards -> HTML Meta -> Title/Snippet fallback.
Strict truthfulness: No fabrication, nulls/None for missing fields.
"""

import json
import logging
from typing import Any, Dict, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .models import ExtractedPostMetadata

logger = logging.getLogger(__name__)


class PostExtractor:
    """
    Extracts post content, media, and metadata from HTML using standard semantic tags.
    """

    def extract(self, html_content: str, base_url: str) -> ExtractedPostMetadata:
        """
        Parse HTML and return structured post metadata.
        Never fabricates data; returns None for any unpopulated field.
        """
        if not html_content or not isinstance(html_content, str):
            return ExtractedPostMetadata(url=base_url)

        try:
            soup = BeautifulSoup(html_content, "html.parser")
        except Exception as e:
            logger.warning(f"Failed to parse HTML for {base_url}: {e}")
            return ExtractedPostMetadata(url=base_url)

        metadata: Dict[str, Any] = {}

        # 1. Extract OpenGraph metadata
        og_data = self._extract_opengraph(soup)
        if og_data:
            metadata["opengraph"] = og_data

        # 2. Extract Twitter Card metadata
        twitter_data = self._extract_twitter_cards(soup)
        if twitter_data:
            metadata["twitter"] = twitter_data

        # 3. Extract JSON-LD schema.org metadata
        json_ld_data = self._extract_json_ld(soup)
        if json_ld_data:
            metadata["json_ld"] = json_ld_data

        # 4. Synthesize primary image URL (Priority: OpenGraph -> Twitter -> JSON-LD -> <img> tag)
        image_url = (
            og_data.get("image")
            or twitter_data.get("image")
            or json_ld_data.get("image")
            or self._extract_fallback_image(soup)
        )
        if image_url:
            image_url = urljoin(base_url, image_url.strip())

        # 5. Synthesize caption / description (Priority: OpenGraph -> Twitter -> JSON-LD -> meta description)
        caption = (
            og_data.get("description")
            or twitter_data.get("description")
            or json_ld_data.get("description")
            or self._extract_meta_description(soup)
        )
        if caption:
            caption = caption.strip()

        # 6. Synthesize title (Priority: OpenGraph -> Twitter -> JSON-LD -> <title>)
        title = (
            og_data.get("title")
            or twitter_data.get("title")
            or json_ld_data.get("headline")
            or self._extract_title(soup)
        )
        if title:
            title = title.strip()

        # 7. Synthesize author & published date
        author = (
            og_data.get("article:author")
            or json_ld_data.get("author")
            or self._extract_meta_tag(soup, "author")
        )
        published_date = (
            og_data.get("article:published_time")
            or json_ld_data.get("datePublished")
        )

        return ExtractedPostMetadata(
            url=base_url,
            image_url=image_url if image_url else None,
            caption=caption if caption else None,
            title=title if title else None,
            author=author if author else None,
            published_date=published_date if published_date else None,
            metadata=metadata,
        )

    def _extract_opengraph(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract OpenGraph meta properties."""
        og = {}
        for tag in soup.find_all("meta", property=True):
            prop = tag.get("property", "").strip().lower()
            if prop.startswith("og:"):
                key = prop[3:]  # strip 'og:'
                content = tag.get("content", "").strip()
                if content and key not in og:
                    og[key] = content
            elif prop.startswith("article:"):
                content = tag.get("content", "").strip()
                if content and prop not in og:
                    og[prop] = content
        return og

    def _extract_twitter_cards(self, soup: BeautifulSoup) -> Dict[str, str]:
        """Extract Twitter card meta properties."""
        twitter = {}
        for tag in soup.find_all("meta"):
            name = (tag.get("name") or tag.get("property") or "").strip().lower()
            if name.startswith("twitter:"):
                key = name[8:]  # strip 'twitter:'
                content = tag.get("content", "").strip()
                if content and key not in twitter:
                    twitter[key] = content
        return twitter

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict[str, Any]:
        """Extract schema.org structured data from <script type='application/ld+json'>."""
        for script in soup.find_all("script", type="application/ld+json"):
            if not script.string:
                continue
            try:
                data = json.loads(script.string.strip())
                # If wrapped in a list or @graph
                items = []
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    if "@graph" in data and isinstance(data["@graph"], list):
                        items = data["@graph"]
                    else:
                        items = [data]

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    schema_type = str(item.get("@type", "")).lower()
                    # Look for relevant types
                    if any(t in schema_type for t in ("socialmediaposting", "article", "imageobject", "person", "webpage")):
                        extracted = {}
                        # Extract image
                        img = item.get("image")
                        if isinstance(img, str):
                            extracted["image"] = img
                        elif isinstance(img, dict) and "url" in img:
                            extracted["image"] = img["url"]
                        elif isinstance(img, list) and img and isinstance(img[0], str):
                            extracted["image"] = img[0]

                        # Extract description / headline
                        if "description" in item and isinstance(item["description"], str):
                            extracted["description"] = item["description"]
                        if "headline" in item and isinstance(item["headline"], str):
                            extracted["headline"] = item["headline"]

                        # Extract author
                        author = item.get("author")
                        if isinstance(author, str):
                            extracted["author"] = author
                        elif isinstance(author, dict) and "name" in author:
                            extracted["author"] = str(author["name"])

                        # Extract date
                        if "datePublished" in item:
                            extracted["datePublished"] = str(item["datePublished"])

                        if extracted:
                            return extracted
            except Exception:
                continue
        return {}

    def _extract_meta_description(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract standard <meta name='description' content='...'>."""
        tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == "description"})
        if tag and tag.get("content"):
            return tag.get("content", "").strip()
        return None

    def _extract_meta_tag(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        """Extract any meta tag by name."""
        tag = soup.find("meta", attrs={"name": lambda v: v and v.lower() == name.lower()})
        if tag and tag.get("content"):
            return tag.get("content", "").strip()
        return None

    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract text from <title> tag."""
        if soup.title and soup.title.string:
            return soup.title.string.strip()
        return None

    def _extract_fallback_image(self, soup: BeautifulSoup) -> Optional[str]:
        """
        Extract first significant <img> tag if no OpenGraph or Twitter image exists.
        Ignores tracking pixels or zero-sized icons.
        """
        for img in soup.find_all("img"):
            src = img.get("src") or img.get("data-src")
            if not src:
                continue
            src = src.strip()
            # Filter out tiny icon / data URI tracking pixel / spacer
            if src.startswith("data:image/svg") or "1x1" in src or "spacer" in src:
                continue
            width = img.get("width")
            height = img.get("height")
            if width and str(width).isdigit() and int(width) < 50:
                continue
            if height and str(height).isdigit() and int(height) < 50:
                continue
            return src
        return None
