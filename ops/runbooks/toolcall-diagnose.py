"""Isolate the <tool_call> leak: chat template (applied) vs raw completion (no template).

If raw completion is clean, the tokens come from template application. If raw completion also
emits them, they are baked into the fine-tuned weights.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

ART = Path("/home/imthiyas/sanad-artifacts")
LLAMA = ART / "llamacpp" / "llama-b10107"
GGUF = ART / "sanad-slm" / "ml" / "out" / "sanad-Q4_K_M.gguf"
Q = "ما هو الحد الأدنى للرصيد المطلوب لفتح حساب توفير؟"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


port = free_port()
p = subprocess.Popen(
    [str(LLAMA / "llama-server"), "-m", str(GGUF), "-t", "6", "-c", "512",
     "--host", "127.0.0.1", "--port", str(port), "--alias", "sanad-bank-gguf", "-np", "1"],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    env={**os.environ, "LD_LIBRARY_PATH": str(LLAMA)},
)


def call(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read().decode())


try:
    for _ in range(90):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
                if r.status == 200:
                    break
        except Exception:
            time.sleep(2)

    results = []

    # A. chat endpoint — template applied by the server
    chat = call("/v1/chat/completions", {
        "messages": [{"role": "user", "content": Q}],
        "temperature": 0.0, "seed": 3407, "max_tokens": 60, "stream": False,
    })["choices"][0]["message"]["content"]
    results.append(("A chat (template applied)", chat))

    # B. raw completion — NO chat template at all
    raw = call("/completion", {
        "prompt": Q, "temperature": 0.0, "seed": 3407, "n_predict": 60,
    })["content"]
    results.append(("B raw completion (no template)", raw))

    # C. raw completion with the ChatML turns written by hand, no tool scaffolding
    manual = (
        "<|im_start|>user\n" + Q + "<|im_end|>\n<|im_start|>assistant\n"
    )
    manual_out = call("/completion", {
        "prompt": manual, "temperature": 0.0, "seed": 3407, "n_predict": 60,
    })["content"]
    results.append(("C manual ChatML (no tool scaffolding)", manual_out))

    for label, text in results:
        print(f"\n=== {label} ===", flush=True)
        print(f"  tool_call present: {'tool_call' in text}", flush=True)
        print(f"  text: {' '.join(text.split())[:260]}", flush=True)

    Path(ART / "toolcall_isolation.json").write_text(
        json.dumps([{"case": k, "tool_call": "tool_call" in v, "text": v} for k, v in results],
                   ensure_ascii=False, indent=2), encoding="utf-8")
finally:
    p.send_signal(signal.SIGTERM)
    try:
        p.wait(timeout=25)
    except subprocess.TimeoutExpired:
        p.kill()
