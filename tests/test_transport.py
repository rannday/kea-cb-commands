"""Exercise real socket framing independently of an installed Kea server."""

# SPDX-License-Identifier: MPL-2.0
import socket
import threading
import unittest

from control import receive_response


class TransportTests(unittest.TestCase):
    def exchange(self, chunks, limit=1024, fragment=False):
        reader, writer = socket.socketpair()
        reader.settimeout(2)

        def send():
            with writer:
                for chunk in chunks:
                    writer.sendall(chunk)

        sender = threading.Thread(target=send)
        sender.start()

        def read(size):
            return reader.recv(min(size, 1) if fragment else size)

        try:
            with reader:
                return receive_response(read, limit)
        finally:
            sender.join(timeout=2)

    def test_fragmented_utf8_object(self):
        self.assertEqual(
            self.exchange(
                [b'  {"result":0,"text":"caf\xc3', b'\xa9"}\n'], fragment=True
            ),
            {"result": 0, "text": "caf\u00e9"},
        )

    def test_truncated_response(self):
        with self.assertRaisesRegex(ValueError, "closed"):
            self.exchange([b'{"result":'])

    def test_http_response_envelope(self):
        self.assertEqual(
            self.exchange([b'[{"result":0,"text":"ok"}]'], fragment=True),
            {"result": 0, "text": "ok"},
        )

    def test_bounded_response(self):
        with self.assertRaisesRegex(ValueError, "size limit"):
            self.exchange([b"x" * 20], limit=10)

    def test_rejects_non_response(self):
        with self.assertRaisesRegex(TypeError, "response object"):
            self.exchange([b'[{"result":0},{"result":0}]'])

    def test_rejects_trailing_data(self):
        with self.assertRaisesRegex(ValueError, "trailing"):
            self.exchange([b'{"result":0} garbage'])


if __name__ == "__main__":
    unittest.main()
