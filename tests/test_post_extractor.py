"""
Tests for PostExtractor (Module 2: Claimed-Profile Verification).
"""

from member2_verify.post_extractor import PostExtractor


def test_extract_opengraph_metadata():
    """Verify correct extraction of OpenGraph tags."""
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <meta property="og:title" content="Profile Picture 2026" />
        <meta property="og:image" content="https://cdn.example.com/user_123.jpg" />
        <meta property="og:description" content="Verified user identity photo." />
        <meta property="article:author" content="Alice Doe" />
        <meta property="article:published_time" content="2026-08-15T10:00:00Z" />
      </head>
      <body></body>
    </html>
    """
    extractor = PostExtractor()
    meta = extractor.extract(html, base_url="https://example.com/user/alice")

    assert meta.url == "https://example.com/user/alice"
    assert meta.image_url == "https://cdn.example.com/user_123.jpg"
    assert meta.title == "Profile Picture 2026"
    assert meta.caption == "Verified user identity photo."
    assert meta.author == "Alice Doe"
    assert meta.published_date == "2026-08-15T10:00:00Z"
    assert "opengraph" in meta.metadata


def test_extract_twitter_cards():
    """Verify fallback to Twitter cards when OpenGraph is absent."""
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <meta name="twitter:card" content="summary_large_image" />
        <meta name="twitter:title" content="Tweet by Bob" />
        <meta name="twitter:image" content="https://pbs.twimg.com/media/bob_face.jpg" />
        <meta name="twitter:description" content="Attending the hackathon today!" />
      </head>
      <body></body>
    </html>
    """
    extractor = PostExtractor()
    meta = extractor.extract(html, base_url="https://x.com/bob/status/98765")

    assert meta.image_url == "https://pbs.twimg.com/media/bob_face.jpg"
    assert meta.title == "Tweet by Bob"
    assert meta.caption == "Attending the hackathon today!"
    assert "twitter" in meta.metadata


def test_extract_json_ld():
    """Verify extraction of schema.org structured JSON-LD."""
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <script type="application/ld+json">
        {
          "@context": "https://schema.org",
          "@type": "SocialMediaPosting",
          "headline": "Conference selfie",
          "image": "https://social.org/media/selfie.png",
          "description": "Met so many awesome engineers!",
          "author": {
            "@type": "Person",
            "name": "Carol Smith"
          },
          "datePublished": "2026-09-01"
        }
        </script>
      </head>
      <body></body>
    </html>
    """
    extractor = PostExtractor()
    meta = extractor.extract(html, base_url="https://social.org/carol/posts/42")

    assert meta.image_url == "https://social.org/media/selfie.png"
    assert meta.title == "Conference selfie"
    assert meta.caption == "Met so many awesome engineers!"
    assert meta.author == "Carol Smith"
    assert meta.published_date == "2026-09-01"
    assert "json_ld" in meta.metadata


def test_extract_relative_image_url_resolution():
    """Verify that relative image paths are properly resolved to absolute URLs."""
    html = """
    <!DOCTYPE html>
    <html>
      <head>
        <meta property="og:image" content="/static/photos/me.jpg" />
      </head>
      <body></body>
    </html>
    """
    extractor = PostExtractor()
    meta = extractor.extract(html, base_url="https://personal-site.org/about/")

    assert meta.image_url == "https://personal-site.org/static/photos/me.jpg"


def test_extract_missing_fields_no_fabrication():
    """Verify that absent tags result in None, adhering strictly to no fabrication."""
    html = "<html><head><title>Just a Title</title></head><body>No images here</body></html>"
    extractor = PostExtractor()
    meta = extractor.extract(html, base_url="https://example.com/empty")

    assert meta.title == "Just a Title"
    assert meta.image_url is None
    assert meta.caption is None
    assert meta.author is None
    assert meta.published_date is None


def test_extract_empty_or_malformed_html():
    """Verify robust handling of empty or non-string input without raising exceptions."""
    extractor = PostExtractor()
    meta = extractor.extract("", base_url="https://example.com/broken")
    assert meta.url == "https://example.com/broken"
    assert meta.image_url is None
