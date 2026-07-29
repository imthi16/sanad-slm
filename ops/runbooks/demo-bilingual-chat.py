"""Bilingual demo through llama-server's OpenAI-compatible endpoint (the §6.2 serving path).

llama-cli ignores -no-cnv on this build and falls into an interactive loop, so the CLI is the wrong
tool for an unattended transcript. llama-server is also what the project actually deploys at the
edge, which makes this a demo of the real path rather than a convenience shortcut.
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

DEST = Path("/home/imthiyas/sanad-artifacts")
LLAMA = DEST / "llamacpp" / "llama-b10107"
GGUF = DEST / "sanad-slm" / "ml" / "out" / "sanad-Q4_K_M.gguf"
LOG = Path(__file__).resolve().parent / ".finish-log.txt"
IST = timezone(timedelta(hours=5, minutes=30))
PORT = 8099
BASE = f"http://127.0.0.1:{PORT}"


def say(msg: str) -> None:
    line = f"[{datetime.now(IST).strftime('%H:%M:%S')}] {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def post(path: str, payload: dict, timeout: int = 600) -> dict:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


env = {**os.environ, "LD_LIBRARY_PATH": str(LLAMA)}
say("DEMO — llama-server (OpenAI-compatible), CPU only, pinned build c0bc8591e")
say(f"  model {GGUF.name} {GGUF.stat().st_size / 1e9:.2f} GB")

srv = subprocess.Popen(
    [str(LLAMA / "llama-server"), "-m", str(GGUF), "-t", "6", "-c", "1024",
     "--host", "127.0.0.1", "--port", str(PORT), "--jinja", "-np", "1"],
    stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, env=env, text=True,
)

try:
    ready = False
    for _ in range(120):
        if srv.poll() is not None:
            say(f"!! server exited early rc={srv.returncode}")
            break
        try:
            with urllib.request.urlopen(BASE + "/health", timeout=3) as r:
                if r.status == 200:
                    ready = True
                    break
        except Exception:
            time.sleep(2)
    if not ready:
        say("!! server never became healthy")
        raise SystemExit(1)
    say("  server healthy")

    PROMPTS = [
        ("ar", "ما هو الحد الأدنى للرصيد المطلوب لفتح حساب توفير؟"),
        ("en", "What documents are required to open a corporate bank account in the UAE?"),
        ("mixed", "هل يمكنني استخدام الـ mobile banking app لتحويل الأموال دولياً؟"),
    ]
    demo = []
    for lang, prompt in PROMPTS:
        t0 = time.time()
        try:
            resp = post("/v1/chat/completions", {
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7, "seed": 3407, "max_tokens": 160, "stream": False,
            })
            text = resp["choices"][0]["message"]["content"]
            usage = resp.get("usage", {})
        except Exception as exc:
            text, usage = f"<error: {type(exc).__name__}: {exc}>", {}
        dt = time.time() - t0
        gen = usage.get("completion_tokens") or 0
        demo.append({
            "lang": lang, "prompt": prompt, "response": text,
            "seconds": round(dt, 1), "usage": usage,
            "tok_s": round(gen / dt, 2) if gen and dt else None,
        })
        say(f"  [{lang}] {dt:.1f}s  {gen} tok  {(gen / dt if gen and dt else 0):.2f} tok/s")
        say(f"    > {' '.join(text.split())[:260]}")
    (DEST / "demo.json").write_text(json.dumps(demo, ensure_ascii=False, indent=2), encoding="utf-8")
    say("DEMO DONE")
finally:
    srv.send_signal(signal.SIGTERM)
    try:
        srv.wait(timeout=30)
    except subprocess.TimeoutExpired:
        srv.kill()
    say("  server stopped")
