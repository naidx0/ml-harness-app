import io
import unittest
from unittest.mock import patch

from app.client import HarnessRun


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class ClientTest(unittest.TestCase):
    @patch("urllib.request.urlopen")
    def test_create_log_complete(self, urlopen):
        urlopen.side_effect = [
            _Response(b'{"id": 7}'),
            _Response(b'{"run_id": 7, "step": 2, "name": "loss", "value": 0.4}'),
            _Response(b'{"id": 7, "status": "completed"}'),
        ]
        run = HarnessRun("http://local").create("demo", {"lr": 0.1})
        self.assertEqual(run.run_id, 7)
        self.assertEqual(run.log(2, "loss", 0.4)["value"], 0.4)
        self.assertEqual(run.complete()["status"], "completed")
        self.assertEqual(urlopen.call_count, 3)

    def test_requires_create(self):
        run = HarnessRun()
        with self.assertRaises(RuntimeError):
            run.log(0, "loss", 1.0)
        with self.assertRaises(RuntimeError):
            run.complete()


if __name__ == "__main__":
    unittest.main()
