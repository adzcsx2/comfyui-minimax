import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform.startswith("linux"), "Launcher uses Linux /proc and flock")
class LauncherTests(unittest.TestCase):
    def prepare(self, directory):
        root = Path(directory)
        (root / "scripts").mkdir()
        (root / ".local").mkdir()
        (root / "ComfyUI").mkdir()
        shutil.copyfile(ROOT / "scripts/launch_autodl.sh", root / "scripts/launch_autodl.sh")
        (root / ".env").write_text(f"COMFYUI_DIR={root}/ComfyUI\n")
        (root / "scripts/start.sh").write_text("printf started > .local/stub-started\n")
        return root

    def run_launcher(self, root):
        return subprocess.run(
            ["bash", str(root / "scripts/launch_autodl.sh")],
            check=True, capture_output=True, text=True, timeout=5,
        )

    def test_unrelated_live_pid_does_not_block_start(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare(directory)
            (root / ".local/server.pid").write_text(str(os.getpid()))
            self.run_launcher(root)
            for _ in range(100):
                if (root / ".local/stub-started").exists():
                    break
                time.sleep(0.01)
            self.assertTrue((root / ".local/stub-started").exists())

    def test_configured_live_server_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.prepare(directory)
            main = root / "ComfyUI/main.py"
            main.write_text("import time\ntime.sleep(30)\n")
            process = subprocess.Popen(
                [sys.executable, str(main)], stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            try:
                (root / ".local/server.pid").write_text(str(process.pid))
                self.run_launcher(root)
                self.assertFalse((root / ".local/stub-started").exists())
            finally:
                process.terminate()
                process.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
