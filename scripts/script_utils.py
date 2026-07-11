"""
Shared utilities for WeWrite scripts.

Consolidates common helpers that were previously duplicated across scripts:
  - extract_title: extract H1 from Markdown
  - split_frontmatter: split YAML frontmatter from body
  - strip_markdown: remove Markdown formatting
  - YAML read/write helpers
  - HTTP defaults (User-Agent, timeout)
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from pathlib import Path

import yaml

# ============================================================
# Paths
# ============================================================

SKILL_DIR = Path(__file__).parent.parent
TOOLKIT_DIR = SKILL_DIR / "toolkit"

# ============================================================
# HTTP defaults
# ============================================================

BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

DEFAULT_HEADERS = {
    "User-Agent": BROWSER_UA,
    "Accept": "application/json, text/plain, */*",
}

DEFAULT_TIMEOUT = 10
API_TIMEOUT = 30


def get_default_headers(extra: dict = None) -> dict:
    """Return default HTTP headers, optionally merged with extra."""
    return {**DEFAULT_HEADERS, **(extra or {})}


# ============================================================
# Markdown utilities
# ============================================================

def extract_title(text: str) -> str:
    """Extract the H1 title from Markdown text.

    Matches lines starting with '# ' but not '## '.
    Returns empty string if no H1 found.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# ") and not stripped.startswith("## "):
            return stripped[2:].strip()
    return ""


def split_frontmatter(text: str) -> tuple[str, str]:
    """Split YAML frontmatter from Markdown body.

    Returns (frontmatter_str, body).
    frontmatter_str includes the --- delimiters, or is empty if none.
    """
    if not text.startswith("---"):
        return "", text
    end_idx = text.find("\n---", 3)
    if end_idx == -1:
        return "", text
    frontmatter = text[:end_idx + 4]
    body = text[end_idx + 4:].lstrip("\n")
    return frontmatter, body


def strip_markdown(text: str) -> str:
    """Remove Markdown formatting to plain text."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    text = re.sub(r"#{1,6}\s+", "", text)
    text = re.sub(r"\*{1,3}", "", text)
    text = re.sub(r"`{1,3}[^`]*`{1,3}", "", text)
    text = re.sub(r">\s+", "", text)
    text = re.sub(r"\|", "", text)
    text = re.sub(r":{3,}\w*", "", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def count_chinese_chars(text: str) -> int:
    """Count CJK characters in text."""
    return len(re.findall(r"[\u4e00-\u9fff]", text))


# ============================================================
# YAML utilities
# ============================================================

def load_yaml(path: str | Path) -> dict | list | None:
    """Load a YAML file safely. Returns None if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def save_yaml(path: str | Path, data: dict | list) -> None:
    """Write YAML atomically: write to temp file then rename."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(dir=p.parent, suffix=".tmp", prefix=p.stem)
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False)
        os.replace(tmp_path, str(p))
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ============================================================
# Config utilities
# ============================================================

def load_config() -> dict:
    """Load config via the unified toolkit/config.py module.

    This provides caching, env var overrides, and multi-path search.
    Falls back to direct YAML loading if toolkit module is unavailable.
    """
    try:
        import sys as _sys
        if str(TOOLKIT_DIR) not in _sys.path:
            _sys.path.insert(0, str(TOOLKIT_DIR))
        from config import load_config as _load
        return _load()
    except ImportError:
        # Fallback: direct file search
        for p in [
            SKILL_DIR / "config.yaml",
            TOOLKIT_DIR / "config.yaml",
            Path.home() / ".config" / "wewrite" / "config.yaml",
        ]:
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    return yaml.safe_load(f) or {}
        return {}


def get_wechat_credentials() -> tuple[str, str]:
    """Get WeChat appid/secret from unified config.

    Raises ValueError if credentials not found.
    """
    try:
        import sys as _sys
        if str(TOOLKIT_DIR) not in _sys.path:
            _sys.path.insert(0, str(TOOLKIT_DIR))
        from config import get_wechat_credentials as _get
        return _get()
    except ImportError:
        cfg = load_config()
        wechat = cfg.get("wechat", {})
        appid = wechat.get("appid", "")
        secret = wechat.get("secret", "")
        if not appid or not secret:
            raise ValueError(
                "WeChat credentials not found. Set WECHAT_APPID + WECHAT_SECRET "
                "environment variables, or configure wechat.appid/secret in config.yaml"
            )
        return appid, secret
