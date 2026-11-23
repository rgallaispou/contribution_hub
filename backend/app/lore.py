import gzip
from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urljoin, urlparse, unquote
from urllib.request import Request, urlopen

from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.ingest import import_mbox

USER_AGENT = "ContributionHub/0.1 (personal open-source contribution tracker)"
MAX_RESPONSE_BYTES = 25 * 1024 * 1024


class LoreSyncError(Exception):
    pass


class SearchResults(HTMLParser):
    def __init__(self, archive_url: str):
        super().__init__()
        self.archive_url = archive_url.rstrip("/") + "/"
        self.archive_path = urlparse(self.archive_url).path.rstrip("/")
        self.results: dict[str, str] = {}
        self._active_message_id: str | None = None
        self._active_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "a":
            return
        href = dict(attrs).get("href")
        if not href:
            return
        path = unquote(urlparse(urljoin(self.archive_url, href)).path)
        if not path.startswith(self.archive_path + "/"):
            return
        parts = path[len(self.archive_path) + 1:].strip("/").split("/")
        if not parts or "@" not in parts[0]:
            return
        if len(parts) > 1 and parts[1] != "T":
            return
        self._active_message_id = parts[0]
        self._active_text = []

    def handle_data(self, data: str) -> None:
        if self._active_message_id is not None:
            self._active_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._active_message_id is not None:
            subject = " ".join("".join(self._active_text).split())
            self.results.setdefault(self._active_message_id, subject)
            self._active_message_id = None
            self._active_text = []


def _request(url: str, timeout: int = 20) -> bytes:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/gzip,*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read(MAX_RESPONSE_BYTES + 1)
            if len(payload) > MAX_RESPONSE_BYTES:
                raise LoreSyncError("Lore response exceeded the 25 MiB safety limit")
            return payload
    except HTTPError as exc:
        if exc.code in (403, 429):
            raise LoreSyncError(f"Lore returned HTTP {exc.code}; search may be rate-limited or protected by an anti-bot challenge") from exc
        raise LoreSyncError(f"Lore returned HTTP {exc.code}") from exc
    except URLError as exc:
        raise LoreSyncError(f"Could not reach Lore: {exc.reason}") from exc
    except TimeoutError as exc:
        raise LoreSyncError("Lore request timed out") from exc


def search_threads(base_url: str, field: str, email: str, offset: int = 0) -> list[tuple[str, str]]:
    archive_url = base_url.rstrip("/") + "/"
    archive_path = urlparse(archive_url).path.rstrip("/")
    query = urlencode({"q": f"{field}:{email}", "o": offset})
    url = f"{archive_url}?{query}"
    body = _request(url).decode("utf-8", errors="replace")
    if "Making sure you" in body or "Anubis" in body:
        raise LoreSyncError("Lore returned an anti-bot challenge instead of search results")
    parser = SearchResults(archive_url)
    parser.feed(body)
    return list(parser.results.items())


def fetch_thread_mbox(base_url: str, message_id: str) -> bytes:
    archive_url = base_url.rstrip("/") + "/"
    url = urljoin(archive_url, f"{quote(message_id, safe='')}/t.mbox.gz")
    payload = _request(url)
    if not payload.startswith(b"\x1f\x8b"):
        if b"Anubis" in payload[:4096] or b"Making sure you" in payload[:4096]:
            raise LoreSyncError("Lore returned an anti-bot challenge instead of the thread archive")
        raise LoreSyncError("Lore returned an unexpected thread archive format")
    try:
        return gzip.decompress(payload)
    except OSError as exc:
        raise LoreSyncError("Lore returned a corrupt compressed thread archive") from exc


def sync_lore(db: Session, identities: list[str], max_per_query: int = 10) -> dict[str, int]:
    imported = skipped = threads = 0
    base_url = settings.lore_base_url
    with TemporaryDirectory(prefix="contribution-hub-lore-") as temp_dir:
        temp_path = Path(temp_dir)
        seen: set[str] = set()
        for email in identities:
            for field in ("f", "t"):
                fetched_for_query = 0
                offset = 0
                while fetched_for_query < max_per_query:
                    results = search_threads(base_url, field, email, offset)
                    if not results:
                        break
                    for message_id, _subject in results[:max_per_query - fetched_for_query]:
                        if message_id in seen:
                            continue
                        seen.add(message_id)
                        archive = fetch_thread_mbox(base_url, message_id)
                        mbox_path = temp_path / f"thread-{threads}.mbox"
                        mbox_path.write_bytes(archive)
                        result = import_mbox(db, mbox_path, identities)
                        imported += result["imported"]
                        skipped += result["skipped_duplicates_or_missing_id"]
                        threads += 1
                        fetched_for_query += 1
                        mbox_path.unlink(missing_ok=True)
                        if fetched_for_query >= max_per_query:
                            break
                    offset += len(results)
                    if len(results) < 25 or fetched_for_query >= max_per_query:
                        break
    return {"threads_fetched": threads, "messages_imported": imported, "messages_skipped": skipped}