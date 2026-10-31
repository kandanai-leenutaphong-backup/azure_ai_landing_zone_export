"""Network decisions use fake DNS/transports; no sockets or real delays are needed."""

from __future__ import annotations

import io
import socket
import sys
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import webres


def public_dns(host, port, **kwargs):
    address = host if host in {"127.0.0.1", "10.0.0.1", "224.0.0.1"} else "8.8.8.8"
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, port or 443))]


class Network(unittest.TestCase):
    def setUp(self) -> None:
        resolver = patch.object(webres.socket, "getaddrinfo", side_effect=public_dns)
        resolver.start()
        self.addCleanup(resolver.stop)
        webres._robots_cache.clear()
        webres._last_request.clear()
        webres._crawl_delays.clear()

    def test_redirects_recheck_addresses_and_robots(self) -> None:
        handler = webres.GuardedRedirects()
        request = urllib.request.Request("https://example.test/start")
        for target in ("http://127.0.0.1/", "http://10.0.0.1/", "https://user:pass@example.test/"):
            with self.assertRaises(webres.AcquisitionError):
                handler.redirect_request(request, None, 302, "Found", {}, target)
        with patch.object(webres, "robots_allows", return_value=False):
            with self.assertRaises(webres.RobotsDisallowed):
                handler.redirect_request(request, None, 302, "Found", {}, "https://example.test/private")

    def test_socket_connects_to_validated_numeric_address_with_original_tls_name(self) -> None:
        context = Mock()
        with patch.object(webres.socket, "create_connection") as connect:
            connection = webres.PublicHTTPSConnection("example.test", context=context)
            connection.connect()
            self.assertEqual(connect.call_args.args[0], ("8.8.8.8", 443))
            context.wrap_socket.assert_called_once_with(connect.return_value, server_hostname="example.test")
        with patch.object(webres.socket, "getaddrinfo", side_effect=socket.gaierror("missing")):
            with self.assertRaises(webres.AcquisitionError):
                webres.validate_url("https://unresolved.test/")

    def test_multicast_and_mixed_private_answers_refuse(self) -> None:
        with self.assertRaises(webres.AcquisitionError):
            webres.validate_url("http://224.0.0.1/")
        replies = public_dns("example.test", 443) + public_dns("127.0.0.1", 443)
        with patch.object(webres.socket, "getaddrinfo", return_value=replies):
            with self.assertRaises(webres.AcquisitionError):
                webres.validate_url("https://example.test/")

    def test_robots_403_is_denied_404_is_missing(self) -> None:
        for status, expected in ((403, False), (401, False), (503, False), (404, True)):
            webres._robots_cache.clear()
            with patch.object(webres, "open_public", side_effect=urllib.error.HTTPError("https://example.test/robots.txt", status, "fixture", {}, None)):
                self.assertEqual(webres.robots_allows("https://example.test/page"), expected)

    def test_rate_floor_and_response_size_are_enforced(self) -> None:
        webres._last_request["example.test"] = 10
        with patch.object(webres.time, "monotonic", return_value=10.5), patch.object(webres.time, "sleep") as delay:
            webres.throttle("example.test", minimum=0)
            delay.assert_called_once_with(1.5)
        policy = webres.urllib.robotparser.RobotFileParser()
        policy.parse(["User-agent: *", "Crawl-delay: 10", "Allow: /"])
        webres._robots_cache["https://example.test"] = policy
        self.assertTrue(webres.robots_allows("https://example.test/page"))
        webres._last_request["example.test"] = 10
        with patch.object(webres.time, "monotonic", return_value=10.5), patch.object(webres.time, "sleep") as delay:
            webres.throttle("example.test", minimum=0)
            delay.assert_called_once_with(9.5)
        with patch.object(webres, "MAX_RESPONSE_BYTES", 4):
            self.assertEqual(webres.read_bounded(io.BytesIO(b"four")), b"four")
            with self.assertRaises(webres.AcquisitionError):
                webres.read_bounded(io.BytesIO(b"longer"))

    def test_non_read_methods_refuse_before_transport(self) -> None:
        with patch.object(webres.urllib.request, "build_opener") as opener:
            with self.assertRaises(webres.AcquisitionError):
                webres.open_public(urllib.request.Request("https://example.test/", method="POST"))
            opener.assert_not_called()

    def test_concurrent_requests_reserve_distinct_host_slots(self) -> None:
        with patch.object(webres.time, "monotonic", return_value=10), patch.object(webres.time, "sleep") as delay:
            with ThreadPoolExecutor(max_workers=3) as workers:
                list(workers.map(webres.throttle, ["example.test"] * 3))
            self.assertEqual(sorted(call.args[0] for call in delay.call_args_list), [2, 4])
            self.assertEqual(webres._last_request["example.test"], 14)
            webres.throttle("other.test")
            self.assertEqual(delay.call_count, 2)

    def test_deadline_refuses_unbounded_crawl_delay_without_reserving_slot(self) -> None:
        webres._last_request["example.test"] = 10
        webres._crawl_delays["example.test"] = 86400
        with patch.object(webres.time, "monotonic", return_value=10), patch.object(webres.time, "sleep") as delay:
            with self.assertRaises(TimeoutError):
                webres.throttle("example.test", deadline=30)
            delay.assert_not_called()
            self.assertEqual(webres._last_request["example.test"], 10)

    def test_expired_deadline_refuses_before_opening_transport(self) -> None:
        with patch.object(webres.time, "monotonic", return_value=10), patch.object(webres.urllib.request, "build_opener") as opener:
            with self.assertRaises(TimeoutError):
                webres.open_public("https://example.test/", deadline=10)
            opener.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)