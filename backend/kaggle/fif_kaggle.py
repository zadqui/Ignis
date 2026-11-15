"""Flame in Freefall · M4 batch runner for Kaggle (GPU). Self-contained: no project imports.

Input: one private Kaggle dataset produced by ``fif-findings export*`` containing ``job.json`` and, depending on
the steps, ``classify/`` (sentences.parquet, classifier_spec.json, export_manifest.json) and/or ``extract/``
(units.parquet, prompt.json, export_manifest.json).

A dataset may hold several job directories (e.g. p5/ and p4/ over the same units): each runs in order and writes
to /kaggle/working/<job dir>/ with the same layout.

Output (/kaggle/working): ``env.json``; ``classify_out/`` (scores.jsonl, classify_manifest.json);
``run_out/`` (raw.jsonl, run_manifest.json, prompt.json). Both outputs are append-only and resumable.
Model outputs are written untouched: parsing and verification happen on the laptop.

vLLM is NOT taken from the Kaggle image (it is absent there and a pip install over the image breaks on triton).
It runs in an isolated venv under /tmp (uv, Python 3.12, pinned vLLM with its own torch/triton), in a worker
subprocess; the base image is never modified. Compatibility check v2 validated vLLM 0.33.0 on 2x T4.

job.json keys: steps (["env", "classify", "extract"]), classify_limit, extract_limit, llm_model,
llm_backend ("vllm" | "transformers"), tensor_parallel (int|null), max_model_len, max_new_tokens, batch_size,
vllm_version (default "0.33.0"), json_whitespace ("default" | "none" | "indent2"; indent2 = schema grammar with
fixed 2-space indentation, the validated choice: "default" loops on whitespace, "none" suppresses findings),
enforce_eager (bool), gpu_memory_utilization (default 0.90), worker_timeout_s (default none),
max_bad_rate / max_bad_batches (circuit breaker, default 0.3 / 3), max_generation_s (generation budget).
Full vLLM worker log: /kaggle/working/logs/vllm_worker.log.
"""


import glob
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime

WORK = os.environ.get("FIF_WORK", "/kaggle/working")
VLLM_ENV = "/tmp/vllm-env"
VLLM_DEFAULT_VERSION = "0.33.0"
os.environ.setdefault("HF_HOME", "/tmp/hf")  # model weights never land in /kaggle/working (saved as output)


def now() -> str:
    return datetime.now(UTC).isoformat()


def find_inputs() -> list[str]:
    """FIF_INPUT, or every directory holding a job.json under /kaggle/input (sorted; several = one job each)."""
    if os.environ.get("FIF_INPUT"):
        return [os.environ["FIF_INPUT"]]
    hits = sorted(glob.glob("/kaggle/input/**/job.json", recursive=True))
    if not hits:
        raise SystemExit("job.json not found under /kaggle/input")
    return [os.path.dirname(h) for h in hits]


def sha_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sh(cmd: str, timeout: int = 600) -> str:
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()
    except Exception as e:
        return f"error: {e}"


def run_logged(cmd: list[str], log_path: str, timeout: float | None = None, env: dict | None = None) -> int:
    """Run cmd in its own process group with full stdout/stderr in log_path. On exit, timeout or error the whole
    group is killed, so no orphan vLLM EngineCore keeps holding GPU memory. Returns the exit code (-9 on timeout)."""
    import signal

    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as log:
        log.write(f"\n===== {now()} {' '.join(cmd)}\n")
        log.flush()
        p = subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
                             env={**os.environ, **(env or {})})
        try:
            rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            rc = -9
            log.write(f"\n===== TIMEOUT after {timeout}s\n")
        finally:
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
    return rc


def log_tail(path: str, n: int = 4000) -> str:
    try:
        with open(path, errors="replace") as fh:
            return fh.read()[-n:]
    except OSError:
        return ""


def resolve_revision(model: str, revision: str | None) -> str | None:
    """Exact commit sha of a Hub model (None if offline); pinned revisions are returned as given."""
    if revision and revision != "main":
        return revision
    try:
        from huggingface_hub import model_info

        return model_info(model, revision=revision or "main").sha
    except Exception:
        return None


# ------------------------------------------------------------------ env ----


def env_check(job: dict) -> dict:
    env: dict = {"at": now(), "python": sys.version, "platform": platform.platform()}
    env["nvidia_smi"] = sh("nvidia-smi --query-gpu=name,memory.total,compute_cap --format=csv,noheader")
    try:
        import torch

        env["torch"] = torch.__version__
        env["cuda_available"] = torch.cuda.is_available()
        env["gpus"] = [
            {"name": torch.cuda.get_device_name(i), "capability": list(torch.cuda.get_device_capability(i)),
             "mem_gb": round(torch.cuda.get_device_properties(i).total_memory / 2**30, 1)}
            for i in range(torch.cuda.device_count())
        ]
    except Exception as e:
        env["torch_error"] = repr(e)
    try:
        import transformers

        env["transformers"] = transformers.__version__
    except Exception as e:
        env["transformers_error"] = repr(e)
    env["internet"] = sh("curl -s -o /dev/null -w '%{http_code}' -m 10 https://huggingface.co") or "no"
    env["disk_working"] = sh("df -h /kaggle/working | tail -1")
    env["disk_tmp"] = sh("df -h /tmp | tail -1")
    env["ram"] = sh("free -g | head -2 | tail -1")
    return env


# ------------------------------------------------------------- classify ----


def classify(inp: str, job: dict) -> dict:
    import pandas as pd
    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    spec = json.load(open(os.path.join(inp, "classify", "classifier_spec.json")))
    sent_path = os.path.join(inp, "classify", "sentences.parquet")
    if os.path.exists(sent_path):
        df = pd.read_parquet(sent_path)
    else:  # pilot: throughput/compatibility test on the TARGET text of the extraction units
        units = pd.read_parquet(os.path.join(inp, "extract", "units.parquet"))
        texts = [m.split("\nTARGET:\n", 1)[1].split("\n\nAFTER:\n", 1)[0] for m in units["user_message"]]
        df = pd.DataFrame({"h": [hashlib.sha256(t.encode()).hexdigest()[:32] for t in texts], "text": texts})
    if job.get("classify_limit"):
        df = df.head(int(job["classify_limit"]))
    out_dir = os.path.join(WORK, "classify_out")
    os.makedirs(out_dir, exist_ok=True)
    scores_path = os.path.join(out_dir, "scores.jsonl")
    done = set()
    if os.path.exists(scores_path):
        done = {json.loads(line)["h"] for line in open(scores_path) if line.strip()}
    todo = df[~df["h"].isin(done)]
    commit = resolve_revision(spec["model"], spec["revision"])
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if dev == "cuda" else torch.float32
    tok = AutoTokenizer.from_pretrained(spec["model"], revision=commit)
    # dtype is explicit: transformers 5 otherwise loads the checkpoint's own dtype
    model = AutoModelForSequenceClassification.from_pretrained(spec["model"], revision=commit, dtype=dtype)
    model = model.to(dev).eval()
    entail = next(i for i, lab in model.config.id2label.items() if lab.lower().startswith("entail"))
    labels = spec["labels"]
    hyps = [spec["hypotheses"][lab] for lab in labels]
    bs = int(job.get("batch_size") or 32)  # sentences per batch (x len(labels) pairs)
    t0 = time.time()
    with open(scores_path, "a") as fh, torch.inference_mode():
        rows = list(todo.itertuples(index=False))
        for i in range(0, len(rows), bs):
            chunk = rows[i : i + bs]
            prem = [r.text for r in chunk for _ in hyps]
            hyp = [h for _ in chunk for h in hyps]
            enc = tok(prem, hyp, truncation="only_first", max_length=spec["max_length"], padding=True,
                      return_tensors="pt").to(dev)
            logits = model(**enc).logits[:, entail].float().view(len(chunk), len(labels))
            probs = torch.softmax(logits, dim=-1).tolist()
            fh.writelines(json.dumps({"h": r.h, "s": {lab: round(v, 6) for lab, v in zip(labels, p)}}) + "\n" for r, p in zip(chunk, probs))
            fh.flush()
    secs = time.time() - t0
    man = {"classifier_id": spec["classifier_id"], "model_commit": commit, "device": dev,
           "dtype": str(next(model.parameters()).dtype).replace("torch.", ""), "batch_size": bs,
           "n_scored_this_session": len(todo),
           "seconds": round(secs, 1), "sentences_per_s": round(len(todo) / secs, 1) if secs else None,
           "sentences_sha256": sha_file(sent_path) if os.path.exists(sent_path) else "pilot:from_units",
           "finished_at": now()}
    json.dump(man, open(os.path.join(out_dir, "classify_manifest.json"), "w"), indent=2)
    del model  # free the GPU before an extract step in the same job (vLLM reserves a fraction of total memory)
    if dev == "cuda":
        torch.cuda.empty_cache()
    return man


# -------------------------------------------------------------- extract ----

# Runs inside the isolated venv. Reads pending units (JSONL), appends one raw line per unit to raw.jsonl.
VLLM_WORKER = r'''
import json, sys, time
cfg = json.load(open(sys.argv[1]))
import torch, vllm
from vllm import LLM, SamplingParams
info = {"vllm": vllm.__version__, "torch": torch.__version__}
try:
    import triton
    info["triton"] = triton.__version__
except Exception as e:
    info["triton"] = repr(e)
t = time.time()
# vLLM 0.33: disable_any_whitespace is an ENGINE setting (StructuredOutputsConfig); the per-request field of
# StructuredOutputsParams is silently ignored (compat v4: identical outputs with and without it).
# It also requires an explicit backend (backend="auto" is rejected with disable_any_whitespace): xgrammar.
engine_kw = ({"structured_outputs_config": {"backend": "xgrammar", "disable_any_whitespace": True}}
             if cfg["disable_any_whitespace"] else {})
llm = LLM(model=cfg["model"], tensor_parallel_size=cfg["tp"], dtype=cfg["dtype"], max_model_len=cfg["max_model_len"],
          seed=0, gpu_memory_utilization=cfg["gpu_memory_utilization"], enforce_eager=cfg["enforce_eager"], **engine_kw)
info["load_s"] = round(time.time() - t, 1)
try:  # record the effective engine setting, not the requested one
    info["engine_structured_outputs_config"] = str(llm.llm_engine.vllm_config.structured_outputs_config)
except Exception as e:
    info["engine_structured_outputs_config"] = f"unavailable: {e!r}"
if cfg["json_format"] == "indent2":
    # Same JSON schema, but whitespace fixed by the grammar to 2-space pretty printing (the model's natural
    # format). Free whitespace caused runaway loops (compat v4/v5); compact JSON (disable_any_whitespace) made the
    # model close the array at once and return {"findings":[]} (pilot gate v2). Grammar built by xgrammar.
    import hashlib
    import xgrammar as xgr
    from vllm.sampling_params import StructuredOutputsParams
    ebnf = str(xgr.Grammar.from_json_schema(json.dumps(cfg["schema"]), any_whitespace=False, indent=2))
    so = {"structured_outputs": StructuredOutputsParams(grammar=ebnf)}
    info["xgrammar"] = getattr(xgr, "__version__", "?")
    info["grammar_sha256"] = hashlib.sha256(ebnf.encode()).hexdigest()
    info["structured_output"] = "vllm StructuredOutputsParams(grammar=xgrammar json_schema indent=2, any_whitespace=False)"
    open(cfg["info_path"] + ".grammar.ebnf", "w").write(ebnf)
else:
  try:
    from vllm.sampling_params import StructuredOutputsParams
    so = {"structured_outputs": StructuredOutputsParams(json=cfg["schema"])}
    info["structured_output"] = "vllm StructuredOutputsParams(json)" + (" + engine disable_any_whitespace" if engine_kw else "")
  except ImportError:
    from vllm.sampling_params import GuidedDecodingParams
    so = {"guided_decoding": GuidedDecodingParams(json=cfg["schema"])}
    info["structured_output"] = "vllm GuidedDecodingParams(json)" + (" + engine disable_any_whitespace" if engine_kw else "")
sp = SamplingParams(temperature=0, max_tokens=cfg["max_new_tokens"], seed=0, **so)
units = [json.loads(line) for line in open(cfg["units_path"]) if line.strip()]
def msgs(u):
    return [{"role": "system", "content": cfg["system"]}, {"role": "user", "content": u}]
if units:  # warm-up with one short request: the v4 harness (warm-up + chunks) was stable; v3 (no warm-up) died
    llm.chat([msgs(units[0]["user_message"])], SamplingParams(temperature=0, max_tokens=16, seed=0, **so),
             use_tqdm=False, chat_template_kwargs={"enable_thinking": False})
bs = cfg["batch_size"]; t0 = time.time(); n_tok = 0
# Circuit breaker: a batch is "bad" when invalid JSON + truncated outputs exceed max_bad_rate; after
# max_bad_batches consecutive bad batches the worker stops (exit 3). Everything written so far is kept and a rerun
# resumes. Per-batch quality metrics go to batch_metrics.jsonl (outside run_out/, contract unchanged).
max_bad_rate, max_bad_batches, bad_streak = float(cfg.get("max_bad_rate", 0.3)), int(cfg.get("max_bad_batches", 3)), 0
budget_s = cfg.get("max_generation_s")  # GPU-time limit for this session's generation
info["circuit_breaker"] = {"max_bad_rate": max_bad_rate, "max_bad_batches": max_bad_batches, "max_generation_s": budget_s}
with open(cfg["raw_path"], "a") as fh, open(cfg["metrics_path"], "a") as mh:
    for i in range(0, len(units), bs):
        if budget_s and time.time() - t0 > float(budget_s):
            info["stopped"] = f"generation budget of {budget_s}s reached (resumable)"
            break
        chunk = units[i:i + bs]
        c0 = time.time()
        outs = llm.chat([msgs(u["user_message"]) for u in chunk], sp, use_tqdm=False,
                        chat_template_kwargs={"enable_thinking": False})
        per = (time.time() - c0) / len(chunk)
        n_len = n_bad_json = 0
        for u, o in zip(chunk, outs):
            c = o.outputs[0]
            n_tok += len(c.token_ids)
            n_len += c.finish_reason == "length"
            try:
                json.loads(c.text)
            except Exception:
                n_bad_json += 1
            fh.write(json.dumps({"unit_id": u["unit_id"], "output": c.text, "error": None,
                                 "finish_reason": c.finish_reason, "n_tokens": len(c.token_ids),
                                 "seconds": round(per, 3)}, ensure_ascii=False) + "\n")
        fh.flush()
        bad_rate = (n_len + n_bad_json) / len(chunk)
        bad_streak = bad_streak + 1 if bad_rate > max_bad_rate else 0
        mh.write(json.dumps({"batch_start": i, "n": len(chunk), "truncated": n_len, "invalid_json": n_bad_json,
                             "bad_rate": round(bad_rate, 3), "seconds": round(time.time() - c0, 1)}) + "\n")
        mh.flush()
        print(f"extract {min(i + bs, len(units))}/{len(units)} ({time.time() - t0:.0f}s) "
              f"truncated={n_len} invalid_json={n_bad_json}", flush=True)
        if bad_streak >= max_bad_batches:
            info["stopped"] = f"circuit breaker: {bad_streak} consecutive batches with bad_rate > {max_bad_rate}"
            info["output_tokens"] = n_tok
            json.dump(info, open(cfg["info_path"], "w"), indent=2)
            sys.exit(3)
info["output_tokens"] = n_tok
json.dump(info, open(cfg["info_path"], "w"), indent=2)
'''


def ensure_vllm_env(version: str, env: dict) -> str:
    """Python of an isolated venv with the pinned vLLM (reused if already present). Never touches the image."""
    py = f"{VLLM_ENV}/bin/python"
    if os.path.exists(py):
        have = sh(f"{py} -c 'import vllm; print(vllm.__version__)'", 300).splitlines()[-1:]
        if have == [version]:
            env["vllm_env"] = {"reused": True, "vllm": version}
            return py
    t = time.time()
    log = sh(f"pip install -q uv && uv venv -q --clear --python 3.12 {VLLM_ENV} && "
             f"uv pip install -q --python {py} vllm=={version}", 1800)
    check = sh(f"{py} -c 'import vllm, torch, triton; print(vllm.__version__, torch.__version__, triton.__version__)'", 300)
    env["vllm_env"] = {"reused": False, "install_s": round(time.time() - t, 1), "check": check[-300:]}
    if not check.startswith(version):
        raise RuntimeError(f"vLLM venv install failed: {(log + check)[-1500:]}")
    return py


def extract(inp: str, job: dict, env: dict) -> dict:
    import pandas as pd

    ex_dir = os.path.join(inp, "extract")
    exp = json.load(open(os.path.join(ex_dir, "export_manifest.json")))
    prompt = json.load(open(os.path.join(ex_dir, "prompt.json")))
    units = pd.read_parquet(os.path.join(ex_dir, "units.parquet"))
    if job.get("extract_limit"):
        units = units.head(int(job["extract_limit"]))
    out_dir = os.path.join(WORK, "run_out")
    os.makedirs(out_dir, exist_ok=True)
    raw_path = os.path.join(out_dir, "raw.jsonl")
    done = set()
    if os.path.exists(raw_path):
        done = {json.loads(line)["unit_id"] for line in open(raw_path) if line.strip()}
    todo = units[~units["unit_id"].isin(done)]
    model_id = job.get("llm_model", "Qwen/Qwen3-8B")
    backend = job.get("llm_backend", "vllm")
    max_new = int(job.get("max_new_tokens") or 1536)
    run_id = job.get("run_id") or f"run-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-kaggle"
    manifest = {"run_id": run_id, "backend": backend, "export_name": exp["export_name"],
                "selection_id": exp["selection_id"], "model": model_id, "units_sha256": exp["units_sha256"],
                "prompt_version": prompt["version"], "prompt_sha256": prompt["sha256"],
                "sampling": {"temperature": 0, "max_new_tokens": max_new, "seed": 0}, "started_at": now(),
                "n_units": len(units)}
    json.dump(prompt, open(os.path.join(out_dir, "prompt.json"), "w"), indent=2, ensure_ascii=False)

    def messages(u):
        return [{"role": "system", "content": prompt["system"]}, {"role": "user", "content": u}]

    t0 = time.time()
    n_tokens = 0
    if backend == "vllm":
        version = job.get("vllm_version") or VLLM_DEFAULT_VERSION
        py = ensure_vllm_env(version, env)
        tp = job.get("tensor_parallel") or max(1, len(env.get("gpus") or [1]))
        dtype = "half" if any(g["capability"][0] < 8 for g in env.get("gpus") or []) else "auto"
        no_ws = job.get("json_whitespace", "default") == "none"
        units_path, cfg_path, info_path = "/tmp/fif_units.jsonl", "/tmp/fif_vllm_cfg.json", "/tmp/fif_vllm_info.json"
        with open(units_path, "w") as fh:
            fh.writelines(json.dumps({"unit_id": r.unit_id, "user_message": r.user_message}, ensure_ascii=False) + "\n" for r in todo.itertuples(index=False))
        json.dump({"model": model_id, "tp": tp, "dtype": dtype, "max_model_len": int(job.get("max_model_len") or 6144),
                   "enforce_eager": bool(job.get("enforce_eager", False)), "schema": prompt["output_schema"],
                   "gpu_memory_utilization": float(job.get("gpu_memory_utilization") or 0.90),
                   "metrics_path": os.path.join(WORK, "logs", "batch_metrics.jsonl"),
                   "max_bad_rate": float(job.get("max_bad_rate", 0.3)), "max_bad_batches": int(job.get("max_bad_batches", 3)),
                   "max_generation_s": job.get("max_generation_s"),
                   "disable_any_whitespace": no_ws, "max_new_tokens": max_new, "system": prompt["system"],
                   "json_format": "indent2" if job.get("json_whitespace") == "indent2" else "schema",
                   "batch_size": int(job.get("batch_size") or 64), "units_path": units_path, "raw_path": raw_path,
                   "info_path": info_path}, open(cfg_path, "w"))
        open("/tmp/fif_vllm_worker.py", "w").write(VLLM_WORKER)
        log_path = os.path.join(WORK, "logs", "vllm_worker.log")  # outside run_out/: the output contract is unchanged
        timeout = float(job["worker_timeout_s"]) if job.get("worker_timeout_s") else None
        rc = run_logged([py, "/tmp/fif_vllm_worker.py", cfg_path], log_path, timeout)
        print(log_tail(log_path, 1500), flush=True)
        info = json.load(open(info_path)) if os.path.exists(info_path) else {}
        manifest.update(stopped=info.get("stopped"), circuit_breaker=info.get("circuit_breaker"))
        manifest.update(tensor_parallel=tp, dtype=dtype, vllm=info.get("vllm"), vllm_env_torch=info.get("torch"),
                        vllm_env_triton=info.get("triton"), load_s=info.get("load_s"),
                        engine_structured_outputs_config=info.get("engine_structured_outputs_config"),
                        xgrammar=info.get("xgrammar"), grammar_sha256=info.get("grammar_sha256"),
                        structured_output=info.get("structured_output"))
        n_tokens = info.get("output_tokens", 0)
        if rc != 0:
            raise RuntimeError(f"vLLM worker exited with code {rc} (partial raw.jsonl is kept; rerun resumes). "
                               f"Full log: logs/vllm_worker.log. Tail: {log_tail(log_path, 2500)}")
    else:  # transformers fallback: no constrained decoding; the laptop validates the JSON
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tok = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float16, device_map="auto")
        manifest["structured_output"] = "none (JSON validated after generation)"
        with open(raw_path, "a") as fh:
            for r in todo.itertuples(index=False):
                c0 = time.time()
                fin = None
                try:
                    ids = tok.apply_chat_template(messages(r.user_message), add_generation_prompt=True,
                                                  enable_thinking=False, return_tensors="pt").to(model.device)
                    gen = model.generate(ids, max_new_tokens=max_new, do_sample=False)[0][ids.shape[1]:]
                    text, err = tok.decode(gen, skip_special_tokens=True), None
                    n_tokens += len(gen)
                    fin = "length" if len(gen) >= max_new else "stop"
                except Exception as e:
                    text, err = None, repr(e)[:300]
                fh.write(json.dumps({"unit_id": r.unit_id, "output": text, "error": err, "finish_reason": fin,
                                     "seconds": round(time.time() - c0, 2)}, ensure_ascii=False) + "\n")
                fh.flush()
    secs = time.time() - t0
    manifest.update(finished_at=now(), n_processed_this_session=len(todo), seconds=round(secs, 1),
                    units_per_s=round(len(todo) / secs, 3) if secs else None, output_tokens=n_tokens)
    json.dump(manifest, open(os.path.join(out_dir, "run_manifest.json"), "w"), indent=2)
    return manifest


def main() -> None:
    """One job → outputs in WORK (contract unchanged). Several jobs → WORK/<job dir name>/ each, run in order."""
    global WORK
    inputs = find_inputs()
    if len(inputs) == 1:
        run_job(inputs[0])
        return
    base = WORK
    for inp in inputs:
        WORK = os.path.join(base, os.path.basename(inp.rstrip("/")))
        run_job(inp)
    WORK = base


def run_job(inp: str) -> None:
    job = json.load(open(os.path.join(inp, "job.json")))
    os.makedirs(WORK, exist_ok=True)  # FIF_WORK may point to a fresh directory
    env = env_check(job)
    report = {"job": job, "env": env, "steps": {}}

    def save() -> None:
        json.dump(report, open(os.path.join(WORK, "env.json"), "w"), indent=2, default=str)

    save()
    for step in job.get("steps", []):
        t = time.time()
        try:
            if step == "classify":
                report["steps"][step] = {"ok": True, "result": classify(inp, job)}
            elif step == "extract":
                report["steps"][step] = {"ok": True, "result": extract(inp, job, env)}
        except Exception as e:
            report["steps"][step] = {"ok": False, "error": repr(e)[:1000], "trace": traceback.format_exc()[-3000:]}
        report["steps"].setdefault(step, {})["seconds"] = round(time.time() - t, 1)
        save()
    print(json.dumps(report, indent=2, default=str)[:4000])


if __name__ == "__main__":
    main()
