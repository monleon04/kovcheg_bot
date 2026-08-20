"""Entry point kept separate so the archive can be launched as `python bot.py`."""

from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).with_name("kovcheg_bot.py")), run_name="__main__")