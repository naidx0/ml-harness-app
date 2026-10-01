"""The publish step, and the refusal that is the half worth testing.

`scripts/publish_the_adapter.py` is the first thing in this repository that can
put an artefact on the internet. Before it existed, three separate plans said
publishing was "one command away, blocked on a credential" - because the string
`huggingface_hub` appears in four `app/` modules as a CAPABILITY LABEL inside
`reads=(...)`, and a grep read a permissions annotation as an import.
`push_to_hub`, `HfApi`, `create_repo` and `upload_folder` appeared zero times.

So the thing under test here is not the upload. It is everything around it:

**The refusal a person actually meets.** No token means exit 2, naming the
variable to set. That is testable with no credential at all, which is the whole
reason it is shaped this way rather than left to fail inside somebody's library.

**That the card never invents a number.** Every figure comes from the adapter's
own `adapter_config.json` or the run record beside it, and anything absent is
printed as **not recorded** rather than omitted or guessed. A card that silently
dropped the peak would read as though nothing had been measured.

**That it will not upload whatever happens to be in the directory.** An adapter
folder collects checkpoints, logs and optimizer state. `UPLOADABLE` is a closed
list, and this pins that a stray file beside the weights is not published.
"""

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import support  # noqa: F401  - installs the suite's sandbox fences

REPO_ROOT = Path(__file__).resolve().parent.parent

import importlib.util as _util

_spec = _util.spec_from_file_location(
    "publish_the_adapter", REPO_ROOT / "scripts" / "publish_the_adapter.py"
)
publish = _util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(publish)


def an_adapter(directory: Path, *, with_run_record: bool) -> Path:
    """A minimal but REAL adapter directory: a config and weights beside it."""
    home = directory / "run_1" / "adapter"
    home.mkdir(parents=True)
    (home / "adapter_config.json").write_text(
        json.dumps({
            "base_model_name_or_path": "HuggingFaceTB/SmolLM2-1.7B",
            "r": 32,
            "lora_alpha": 64,
            "target_modules": ["v_proj", "q_proj"],
        }),
        encoding="utf-8",
    )
    (home / "adapter_model.safetensors").write_bytes(b"\0" * 2048)
    if with_run_record:
        (home.parent / "job.json").write_text(
            json.dumps({"config": {"max_seq_len": 512, "batch_size": 1,
                                   "max_steps": 700, "load_in_4bit": True}}),
            encoding="utf-8",
        )
        (home.parent / "job.log").write_text(
            'MLH_EVENT {"step": 5, "peak_vram_gb": 1.79}\n'
            'MLH_EVENT {"step": 10, "peak_vram_gb": 2.94}\n',
            encoding="utf-8",
        )
    return home


class WithoutATokenItRefusesAndSaysWhichVariableTest(unittest.TestCase):
    def setUp(self):
        self._saved = {n: os.environ.pop(n, None) for n in publish.TOKEN_VARIABLES}

    def tearDown(self):
        for name, value in self._saved.items():
            if value is not None:
                os.environ[name] = value
            else:
                os.environ.pop(name, None)

    def test_no_token_is_exit_two_and_not_a_crash(self):
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=True)
            code = publish.main(["--adapter", str(home), "--repo", "someone/thing"])
        self.assertEqual(
            code, 2,
            "publishing without a token must refuse with its own exit code. A "
            "zero here would report success for an upload that never happened.",
        )

    def test_the_refusal_names_every_variable_it_accepts(self):
        """The message is the product. If it does not name the variable, the
        person reading it has to read this file to find out what to set."""
        # THE RENDERED MESSAGE, not the template. `NO_TOKEN` carries a
        # `{variables}` placeholder, so asserting against it directly passes
        # while the person sees the literal word "{variables}" - which is how a
        # test can pin a message nobody could act on.
        rendered = publish.NO_TOKEN.format(
            variables=" or ".join(publish.TOKEN_VARIABLES)
        )
        for name in publish.TOKEN_VARIABLES:
            self.assertIn(name, rendered)
        self.assertNotIn("{variables}", rendered)
        self.assertIn("huggingface.co/settings/tokens", rendered)
        self.assertIn("--dry-run", rendered)

    def test_the_token_reader_returns_a_NAME_and_never_a_value(self):
        """A secret that reaches a return value reaches a log eventually."""
        self.assertIsNone(publish.the_token())
        os.environ["HF_TOKEN"] = "hf_this_must_never_be_returned"
        try:
            self.assertEqual(publish.the_token(), "HF_TOKEN")
        finally:
            os.environ.pop("HF_TOKEN", None)

    def test_a_dry_run_needs_no_token_and_writes_the_card(self):
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=True)
            code = publish.main(
                ["--adapter", str(home), "--repo", "someone/thing", "--dry-run"]
            )
            self.assertEqual(code, 0)
            self.assertTrue((home / "README.md").is_file())


class TheCardSaysOnlyWhatWasMeasuredTest(unittest.TestCase):
    def test_it_carries_the_figures_from_the_config_and_the_run(self):
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=True)
            adapter = publish.read_adapter(home)
            record = publish.read_run_record(home)
            card = publish.model_card(adapter, record, "someone/thing")
        self.assertIn("HuggingFaceTB/SmolLM2-1.7B", card)
        self.assertIn("| LoRA rank (r) | 32 |", card)
        self.assertIn("| LoRA alpha | 64 |", card)
        self.assertIn("`q_proj`, `v_proj`", card)
        # THE LAST peak in the log, not the first: the run's peak is its
        # high-water mark, and reading the first line would report the cost of
        # step five as the cost of the run.
        self.assertIn("2.94 GiB", card)
        self.assertNotIn("1.79 GiB", card)

    def test_a_missing_figure_is_NOT_RECORDED_and_never_a_guess(self):
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=False)
            card = publish.model_card(
                publish.read_adapter(home), publish.read_run_record(home), "a/b"
            )
        self.assertIn("**not recorded**", card)
        # The RULE is what this test is for - a missing figure renders as
        # `not recorded` and never as a guess - and the rule is unchanged. The
        # LABEL moved on 2026-09-10, from one unqualified "measured peak VRAM"
        # to three peaks under their own names, because `peak_vram_gb` became
        # the process high-water mark and the training peak got its own key.
        # Pinning a label in a test about a rule is what made this line break
        # for a change that strengthened the thing it protects.
        self.assertIn("| peak VRAM, training | **not recorded** |", card)

    def test_it_refuses_to_claim_the_adapter_is_any_good(self):
        """The one sentence that must survive every edit to this card."""
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=True)
            card = publish.model_card(
                publish.read_adapter(home), publish.read_run_record(home), "a/b"
            )
        self.assertIn("has not been scored", card)
        self.assertIn("not a demonstrated improvement", card)


class ItPublishesTheADAPTERAndNotTheDirectoryTest(unittest.TestCase):
    def test_a_stray_file_beside_the_weights_is_not_uploaded(self):
        with TemporaryDirectory() as tmp:
            home = an_adapter(Path(tmp), with_run_record=True)
            (home / "optimizer.pt").write_bytes(b"\0" * 16)
            (home / "private-notes.txt").write_text("not for the internet", encoding="utf-8")
            sendable = [n for n in publish.UPLOADABLE if (home / n).is_file()]
        self.assertIn("adapter_config.json", sendable)
        self.assertIn("adapter_model.safetensors", sendable)
        self.assertNotIn("optimizer.pt", sendable)
        self.assertNotIn("private-notes.txt", sendable)

    def test_an_adapter_with_no_weights_is_refused(self):
        with TemporaryDirectory() as tmp:
            home = Path(tmp) / "adapter"
            home.mkdir()
            (home / "adapter_config.json").write_text("{}", encoding="utf-8")
            with self.assertRaises(SystemExit):
                publish.read_adapter(home)


if __name__ == "__main__":
    unittest.main()
