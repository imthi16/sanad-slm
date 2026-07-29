"""P5 — prove the app end to end on this CPU-only box, against our own fine-tuned GGUF.

Chain: llama-server (our Q4_K_M) ← sanad-api (FastAPI, ModelRouter) ← HTTP client.
No Docker and no GPU, which is the point: this is the ADR-0004 edge shape running for real.
Writes ml/evals/reports/p5_e2e.json.
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

REPO = Path(__file__).resolve().parent
ART = Path("/home/imthiyas/sanad-artifacts")
LLAMA = ART / "llamacpp" / "llama-b10107"
GGUF = ART / "sanad-slm" / "ml" / "out" / "sanad-Q4_K_M.gguf"
LOG = REPO / ".p5-log.txt"
IST = timezone(timedelta(hours=5, minutes=30))

ALIAS = "sanad-bank-gguf"


def free_port() -> int:
    """Bind :0 and let the OS pick.

    The first attempt used the documented defaults 8080/8000, both of which were already held by
    unrelated processes on this machine. Both health checks then passed *against the squatters* —
    one of them cheerfully answered `{"status":"ok"}` — and the whole run reported success while
    talking to someone else's service. Never assume a port is yours because something answered.
    """
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


LLAMA_PORT = free_port()
API_PORT = free_port()


def say(msg: str) -> None:
    line = f"[{datetime.now(IST).strftime('%H:%M:%S')}] {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def get(url: str, timeout: int = 30) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def post(url: str, payload: dict, timeout: int = 600) -> tuple[int, str]:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


results: dict[str, object] = {"platform": "x86-local", "gpu": False}
procs: list[subprocess.Popen] = []

try:
    # ── 1. llama-server: our own fine-tuned, quantized model ────────────────────────────
    say(f"P5/1 — starting llama-server with our Q4_K_M on :{LLAMA_PORT}")
    llama_proc = subprocess.Popen(
        [str(LLAMA / "llama-server"), "-m", str(GGUF), "-t", "6", "-c", "1024",
         "--host", "127.0.0.1", "--port", str(LLAMA_PORT), "--jinja",
         "--alias", ALIAS, "-np", "1", "--metrics"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={**os.environ, "LD_LIBRARY_PATH": str(LLAMA)},
    )
    procs.append(llama_proc)
    for _ in range(120):
        if llama_proc.poll() is not None:
            raise SystemExit(f"llama-server exited rc={llama_proc.returncode}")
        if get(f"http://127.0.0.1:{LLAMA_PORT}/health", 3)[0] == 200:
            break
        time.sleep(2)
    else:
        raise SystemExit("llama-server never became healthy")
    # Identity check: it must be OUR model, not merely something that answers 200.
    code, body = get(f"http://127.0.0.1:{LLAMA_PORT}/v1/models")
    if ALIAS not in body:
        raise SystemExit(f"port {LLAMA_PORT} answered but is not our llama-server: {body[:200]}")
    say(f"  llama-server healthy and serving {ALIAS}")
    results["llamacpp_models"] = body[:300]

    # ── 2. sanad-api pointed at it ───────────────────────────────────────────────────────
    say("P5/2 — starting sanad-api (mode=edge) against the local llama.cpp")
    api_env = {
        **os.environ,
        "SANAD_MODE": "edge",
        "SANAD_LLAMACPP_BASE_URL": f"http://127.0.0.1:{LLAMA_PORT}/v1",
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "TMPDIR": str(ART / "tmp"),
        # The fertility endpoint reads tokenizer.json files from here. Our merged model ships one,
        # so point at a dir holding it: a partial table is honest, an empty 500 is not.
        "SANAD_TOKENIZERS_DIR": str(ART / "tokenizers"),
    }
    # Lay out one real tokenizer under the layout services/fertility.py expects.
    tok_dir = ART / "tokenizers" / "Qwen__Qwen3-4B-Instruct-2507"
    tok_dir.mkdir(parents=True, exist_ok=True)
    src_tok = ART / "sanad-slm" / "ml" / "out" / "merged-bf16" / "tokenizer.json"
    if src_tok.is_file() and not (tok_dir / "tokenizer.json").exists():
        (tok_dir / "tokenizer.json").write_bytes(src_tok.read_bytes())
        say(f"  staged tokenizer for the fertility endpoint at {tok_dir.name}")
    # stderr to a file, not a pipe: a 500 needs its traceback, and reading a live pipe deadlocks.
    api_err = REPO / ".p5-api-stderr.log"
    api_err_fh = api_err.open("w", encoding="utf-8")
    api_proc = subprocess.Popen(
        ["uv", "run", "uvicorn", "sanad_api.main:app", "--host", "127.0.0.1",
         "--port", str(API_PORT), "--log-level", "info"],
        cwd=str(REPO / "apps" / "api"), env=api_env,
        stdout=api_err_fh, stderr=api_err_fh, text=True,
    )
    procs.append(api_proc)
    for _ in range(120):
        if api_proc.poll() is not None:
            raise SystemExit(f"api exited rc={api_proc.returncode}\n{api_err.read_text()[-1500:]}")
        if get(f"http://127.0.0.1:{API_PORT}/healthz", 3)[0] == 200:
            break
        time.sleep(2)
    else:
        raise SystemExit("sanad-api never became healthy")
    # Identity check: our instance runs in edge mode. 'dev' means we hit somebody else's service.
    code, body = get(f"http://127.0.0.1:{API_PORT}/v1/models")
    if '"mode": "edge"' not in body and '"mode":"edge"' not in body:
        raise SystemExit(f"port {API_PORT} is not our edge-mode api: {body[:250]}")
    say(f"  api healthy on :{API_PORT}, mode=edge confirmed")

    base = f"http://127.0.0.1:{API_PORT}"

    # ── 3. contract endpoints ────────────────────────────────────────────────────────────
    for name, path in (("healthz", "/healthz"), ("readyz", "/readyz"), ("models", "/v1/models")):
        code, body = get(base + path)
        say(f"P5/3 {name:8} → {code}  {body[:150]}")
        results[f"GET {path}"] = {"status": code, "body": body[:600]}

    # ── 4. non-streaming chat through the router ─────────────────────────────────────────
    say("P5/4 — non-streaming chat (Arabic) through the ModelRouter")
    code, body = post(base + "/v1/chat/completions", {
        "model": ALIAS,
        "messages": [{"role": "user", "content": "ما هي أنواع الحسابات المصرفية المتاحةؗ"}],
        "max_tokens": 80, "temperature": 0.7, "stream": False,
    })
    say(f"  → {code}")
    try:
        parsed = json.loads(body)
        content = parsed["choices"][0]["message"]["content"]
        say(f"  content: {' '.join(content.split())[:200]}")
        say(f"  x_sanad: {json.dumps(parsed.get('x_sanad'), ensure_ascii=False)[:250]}")
        results["chat_nonstream"] = {
            "status": code, "content": content, "x_sanad": parsed.get("x_sanad"),
        }
    except Exception as exc:
        say(f"  unparsed: {type(exc).__name__} — {body[:300]}")
        results["chat_nonstream"] = {"status": code, "raw": body[:600]}
        tb = [ln for ln in api_err.read_text(errors="replace").splitlines()
              if "Error" in ln or "error" in ln or ln.startswith("  ") or "Traceback" in ln]
        for ln in tb[-18:]:
            say(f"    api| {ln[:220]}")

    # ── 5. streaming chat — the bidi-safe SSE path ───────────────────────────────────────
    say("P5/5 — streaming chat (SSE), the path §7.3 specifies")
    req = urllib.request.Request(
        base + "/v1/chat/completions",
        data=json.dumps({
            "model": ALIAS,
            "messages": [{"role": "user", "content": "اشرح الحد الأدنى للرصيد بإيجاز."}],
            "max_tokens": 60, "temperature": 0.7, "stream": True,
        }).encode(),
        headers={"Content-Type": "application/json"},
    )
    chunks, text = 0, ""
    final_frame = None
    try:
        with urllib.request.urlopen(req, timeout=600) as r:
            for raw in r:
                line = raw.decode(errors="replace").strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if payload == "[DONE]":
                    break
                chunks += 1
                try:
                    obj = json.loads(payload)
                    delta = obj.get("choices", [{}])[0].get("delta", {}).get("content")
                    if delta:
                        text += delta
                    if "x_sanad" in obj:
                        final_frame = obj["x_sanad"]
                except Exception:
                    pass
    except Exception as exc:
        say(f"  stream failed: {type(exc).__name__}: {exc}")
    say(f"  chunks={chunks} chars={len(text)}")
    say(f"  streamed: {' '.join(text.split())[:200]}")
    say(f"  final x_sanad frame: {json.dumps(final_frame, ensure_ascii=False)[:250]}")
    results["chat_stream"] = {"chunks": chunks, "text": text, "x_sanad": final_frame}

    # ── 6. the fertility endpoint that powers the hero ───────────────────────────────────
    say("P5/6 — POST /v1/tokenize/fertility")
    code, body = post(base + "/v1/tokenize/fertility",
                      {"text": "الحد الأدنى للرصيد في حساب التوفير هو 3000 درهم"})
    say(f"  → {code}  {body[:220]}")
    results["fertility"] = {"status": code, "body": body[:600]}

    out = REPO / "ml" / "evals" / "reports" / "p5_e2e.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    say(f"P5 DONE — wrote {out}")

finally:
    for p in reversed(procs):
        p.send_signal(signal.SIGTERM)
        try:
            p.wait(timeout=25)
        except subprocess.TimeoutExpired:
            p.kill()
    say("  stopped api + llama-server")
