import gzip
import unittest
from urllib.error import HTTPError
from unittest.mock import patch

from backend.app import lore


class LoreSearchTests(unittest.TestCase):
    def test_extracts_thread_message_ids_and_subjects(self):
        parser = lore.SearchResults("/all")
        parser.feed(
            '<a href="/all/patch%40example.org/">'
            "[PATCH v2] demo: update &amp; verify</a>"
            '<a href="/all/reply%40example.org/T/#t">Re: follow-up</a>'
            '<a href="/all/not-a-thread/">ignore this</a>'
        )

        self.assertEqual(
            parser.results,
            {
                "patch@example.org": "[PATCH v2] demo: update & verify",
                "reply@example.org": "Re: follow-up",
            },
        )

    @patch.object(lore, "_request", return_value=b'<a href="/all/id%40example.org/T/#t">Patch</a>')
    def test_search_encodes_identity_query(self, request):
        results = lore.search_threads("https://lore.kernel.org/all/", "f", "dev+kernel@example.org")

        self.assertEqual(results, [("id@example.org", "Patch")])
        self.assertIn("q=f%3Adev%2Bkernel%40example.org", request.call_args.args[0])

    @patch.object(lore, "_request", return_value=b"<title>Anubis challenge</title>")
    def test_search_rejects_anti_bot_pages(self, _request):
        with self.assertRaisesRegex(lore.LoreSyncError, "anti-bot challenge"):
            lore.search_threads("https://lore.kernel.org/all/", "f", "dev@example.org")

    @patch.object(lore, "_request", return_value=gzip.compress(b"From mbox\n"))
    def test_fetches_gzipped_thread_archive(self, request):
        archive = lore.fetch_thread_mbox("https://lore.kernel.org/all/", "patch@example.org")

        self.assertEqual(archive, b"From mbox\n")
        self.assertEqual(
            request.call_args.args[0],
            "https://lore.kernel.org/all/patch%40example.org/t.mbox.gz",
        )

    @patch.object(lore, "urlopen", side_effect=HTTPError("https://lore.kernel.org/", 403, "Forbidden", {}, None))
    def test_http_403_is_reported_without_retrying(self, _urlopen):
        with self.assertRaisesRegex(lore.LoreSyncError, "HTTP 403"):
            lore._request("https://lore.kernel.org/all/")

    @patch.object(lore, "import_mbox", return_value={"imported": 2, "skipped_duplicates_or_missing_id": 1})
    @patch.object(lore, "fetch_thread_mbox", return_value=b"mbox")
    @patch.object(lore, "search_threads")
    def test_sync_searches_both_directions_and_deduplicates_threads(
        self, search, fetch, importer
    ):
        search.side_effect = [
            [("out@example.org", "outgoing")],
            [("out@example.org", "duplicate"), ("in@example.org", "incoming")],
            [],
        ]

        result = lore.sync_lore(None, ["dev@example.org"], max_per_query=2)

        self.assertEqual(
            result,
            {"threads_fetched": 2, "messages_imported": 4, "messages_skipped": 2},
        )
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(importer.call_count, 2)
        self.assertEqual(
            [(call.args[1], call.args[2]) for call in search.call_args_list],
            [("f", "dev@example.org"), ("t", "dev@example.org")],
        )


if __name__ == "__main__":
    unittest.main()
