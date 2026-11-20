"""The input-only source freeze must survive later label-stage updates."""

import json
from pathlib import Path
import tempfile
import unittest

from data.scripts.freeze_november_2026_inputs import freeze_inputs


class InputFreezeTests(unittest.TestCase):
    def test_byte_exact_idempotent_freeze_and_changed_source_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source.json", Path(directory) / "frozen.json"
            source.write_text(json.dumps({"stage": "INPUTS_PREPARED", "days": []}) + "\n")
            digest = freeze_inputs(source, target)
            self.assertEqual(source.read_bytes(), target.read_bytes())
            self.assertEqual(digest, freeze_inputs(source, target))
            frozen = target.read_bytes()
            source.write_text(json.dumps({"stage": "INPUTS_PREPARED", "days": ["changed"]}))
            with self.assertRaisesRegex(ValueError, "must not be overwritten"):
                freeze_inputs(source, target)
            self.assertEqual(frozen, target.read_bytes())

    def test_final_labels_and_hidden_label_keys_cannot_enter_freeze(self):
        for value in ({"stage": "PREPARED"}, {"stage": "INPUTS_PREPARED", "labels": {}},
                      {"stage": "INPUTS_PREPARED", "daily_labels": {}}):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as directory:
                source, target = Path(directory) / "source.json", Path(directory) / "frozen.json"
                source.write_text(json.dumps(value))
                with self.assertRaisesRegex(ValueError, "input-only"):
                    freeze_inputs(source, target)
                self.assertFalse(target.exists())


if __name__ == "__main__":
    unittest.main()
