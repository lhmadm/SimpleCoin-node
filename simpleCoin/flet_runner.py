import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Dict, Optional

import flet as ft


ROOT = Path(__file__).resolve().parent


class ManagedProcess:
    def __init__(self, script_name: str):
        self.script_name = script_name
        self.process: Optional[subprocess.Popen] = None
        self.output_queue: "queue.Queue[str]" = queue.Queue()
        self._reader_thread: Optional[threading.Thread] = None

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def start(self) -> None:
        if self.running:
            return

        script_path = ROOT / self.script_name
        self.process = subprocess.Popen(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )

        self._reader_thread = threading.Thread(target=self._read_output, daemon=True)
        self._reader_thread.start()
        self.output_queue.put(f"[system] started {self.script_name} (pid={self.process.pid})")

    def _read_output(self) -> None:
        if not self.process or not self.process.stdout:
            return

        for line in self.process.stdout:
            self.output_queue.put(f"[{self.script_name}] {line.rstrip()}")

    def stop(self) -> None:
        if not self.running:
            return

        assert self.process is not None
        self.process.terminate()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

        self.output_queue.put(f"[system] stopped {self.script_name}")


def main(page: ft.Page) -> None:
    page.title = "SimpleCoin Runner"
    page.window_width = 980
    page.window_height = 700
    page.padding = 16

    miners: Dict[str, ManagedProcess] = {
        "miner.py": ManagedProcess("miner.py"),
        "wallet.py": ManagedProcess("wallet.py"),
    }

    log_output = ft.TextField(
        label="실행 로그",
        multiline=True,
        read_only=True,
        min_lines=20,
        max_lines=20,
        value="",
        expand=True,
    )

    status_text = {
        name: ft.Text(f"{name}: stopped", color=ft.Colors.RED) for name in miners
    }

    def refresh_status() -> None:
        for name, proc in miners.items():
            if proc.running:
                status_text[name].value = f"{name}: running"
                status_text[name].color = ft.Colors.GREEN
            else:
                status_text[name].value = f"{name}: stopped"
                status_text[name].color = ft.Colors.RED

    def append_log(message: str) -> None:
        if log_output.value:
            log_output.value += "\n"
        log_output.value += message

    def drain_logs() -> None:
        for proc in miners.values():
            while not proc.output_queue.empty():
                append_log(proc.output_queue.get())

    def start_target(target: str) -> None:
        miners[target].start()
        refresh_status()
        page.update()

    def stop_target(target: str) -> None:
        miners[target].stop()
        refresh_status()
        page.update()

    def start_all(_):
        for name in miners:
            miners[name].start()
        refresh_status()
        page.update()

    def stop_all(_):
        for name in miners:
            miners[name].stop()
        refresh_status()
        page.update()

    def on_timer(_):
        drain_logs()
        refresh_status()
        page.update()

    controls = []
    for name in miners:
        controls.append(
            ft.Row(
                [
                    status_text[name],
                    ft.ElevatedButton("Start", on_click=lambda _, n=name: start_target(n)),
                    ft.ElevatedButton("Stop", on_click=lambda _, n=name: stop_target(n)),
                ],
                alignment=ft.MainAxisAlignment.START,
            )
        )

    page.add(
        ft.Text("SimpleCoin 프로세스 실행기", style=ft.TextThemeStyle.HEADLINE_MEDIUM),
        ft.Row(
            [
                ft.ElevatedButton("Start All", on_click=start_all),
                ft.ElevatedButton("Stop All", on_click=stop_all),
            ]
        ),
        *controls,
        log_output,
    )

    page.run_task(_ticker, on_timer)


async def _ticker(callback):
    import asyncio

    while True:
        await asyncio.sleep(0.5)
        callback(None)


if __name__ == "__main__":
    ft.app(target=main)
