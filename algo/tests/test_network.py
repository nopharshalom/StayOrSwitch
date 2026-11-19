"""Credential protection and transport failures are integration boundaries."""

import tempfile
import unittest
from pathlib import Path

import httpx

from stayorswitch.network import HttpClient, NetworkError, read_local_settings
from stayorswitch.provider_client import query_routes


class NetworkTests(unittest.TestCase):
    def test_secret_stays_in_header_and_is_redacted_from_errors(self):
        key = "synthetic-test-credential"

        def handler(request):
            self.assertNotIn(key, str(request.url))
            self.assertEqual(request.headers["X-Goog-Api-Key"], key)
            return httpx.Response(403, json={"error": {
                "message": "Rejected " + key, "details": [{"reason": "ACCESS_DENIED"}]}})

        with HttpClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(NetworkError) as raised:
                query_routes(client, key)
        self.assertEqual(raised.exception.code, "ACCESS_DENIED")
        self.assertNotIn(key, str(raised.exception))
        self.assertEqual(raised.exception.status_code, 403)

    def test_invalid_json_and_oversized_response_fail_closed(self):
        with HttpClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"not json"))) as client:
            with self.assertRaises(NetworkError) as raised:
                query_routes(client, "synthetic")
            self.assertEqual(raised.exception.code, "INVALID_PROVIDER_JSON")
        with HttpClient(max_bytes=2, transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"long"))) as client:
            with self.assertRaises(NetworkError) as raised:
                client.get("https://example.invalid/feed")
            self.assertEqual(raised.exception.code, "RESPONSE_TOO_LARGE")

    def test_environment_file_is_data_not_shell_code(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text("# Test only\nGOOGLE_ROUTES_API_KEY='$(false)'\nFLAG=true\n")
            settings = read_local_settings(path)
            self.assertEqual(settings["GOOGLE_ROUTES_API_KEY"], "$(false)")
            self.assertEqual(settings["FLAG"], "true")

    def test_redirect_does_not_forward_secret(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://other.invalid/"})

        with HttpClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(NetworkError):
                query_routes(client, "synthetic")
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
