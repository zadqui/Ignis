# Flame in Freefall · M4 · Kaggle compatibility check v5 (no project data: synthetic, fictional text only).
#
# Bounded acceptance test of two corrections, with criteria fixed BEFORE the run (ACCEPTANCE below):
#   A. one engine with vLLM default whitespace: prompt baseline (p-1) vs current prompt (p-2), same 72 units;
#   B. the real runner (fif_kaggle.py) with p-2 and json_whitespace="none" (engine-level disable_any_whitespace),
#      same 72 units: checks that the setting is really applied and what it changes.
# All raw outputs are kept (compat5/raw_*.jsonl). Models and the venv live in /tmp. Result: compat5/compat.json.
#
# Gate mode (CONFIG["gate"]): skip A (reference tokens from a previous run), run B, judge, and ONLY if every
# criterion passes run the real pilot: the runner on the attached private dataset, outputs in /kaggle/working
# (run_out/ contract unchanged). If any criterion fails, the pilot is not run.
#
# CONFIG (prompt bundles, runner source) is injected at build time: `fif-findings kaggle-compat --baseline-prompt`.
import json
import os
import re
import subprocess
import sys
import time
import traceback

CONFIG = {}  # __FIF_CONFIG__ (replaced at build time)

OUT = "/kaggle/working/compat5"
os.makedirs(OUT, exist_ok=True)
os.environ.setdefault("HF_HOME", "/tmp/hf")
R = {"version": "compat-5", "prompts": {"current": [CONFIG["prompt"]["version"], CONFIG["prompt"]["sha256"]],
                                         "baseline": [CONFIG["prompt_baseline"]["version"], CONFIG["prompt_baseline"]["sha256"]]}}
T0 = time.time()
GATE = CONFIG.get("gate") or {}
R["gate"] = GATE

ACCEPTANCE = {
    # disable_any_whitespace (B vs A/current)
    "W1_engine_setting_applied": "B: whitespace control effectively applied (engine disable_any_whitespace=True, or "
                                 "schema grammar with fixed indent=2)",
    "W2_no_whitespace_runaway": "B: no output contains a whitespace run longer than 20 characters",
    "W3_json_valid": "B: JSON valid in >= 71 of 72 units",
    "W4_not_more_tokens": "B mean output tokens <= A/current mean output tokens",
    # p-2 quality (B; A/current reported alongside)
    "Q1_future_work_recall": ">= 10 of 12 future_work units get a future_work finding",
    "Q2_limitation_recall": ">= 8 of 12 result+limitation units get a limitation finding",
    "Q3_result_recall": ">= 33 of 36 result-bearing units get a result finding (no regression)",
    "Q4_no_proposal_as_result": "<= 1 future_work unit gets a finding typed result",
    "Q5_no_false_positives": "<= 1 of 24 method/caption units get any finding",
    "Q6_quotes": "100% of quotes verbatim in the unit and >= 95% inside the TARGET",
    "Q7_numbers": "hallucinated numbers <= 2% of output numbers; gold number recall >= 75%",
    "Q8_duplicates": "<= 1 duplicate (same claim_type + claim_quote within a unit)",
    "Q9_truncation": "<= 1 of 72 outputs truncated (finish_reason=length)",
}
R["acceptance_criteria"] = ACCEPTANCE


def sh(c, timeout=1800):
    try:
        p = subprocess.run(c, shell=True, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()[-2000:]
    except Exception as e:
        return f"error: {e!r}"


def save():
    R["elapsed_s"] = round(time.time() - T0, 1)
    json.dump(R, open(f"{OUT}/compat.json", "w"), indent=2, default=str)


# ------------------------------------------------- synthetic units + gold ----
FUELS = ["n-heptane", "PMMA", "a cotton-fiberglass fabric", "ethanol", "a polyethylene wire insulation", "n-decane"]
GEOMS = ["droplet", "flat sheet", "cylindrical rod", "wire", "porous sphere", "thin film"]
KINDS = ("result_simple", "result_multi", "future_work", "method", "caption", "result_limitation")


def sentence(kind, i):
    """(text, gold) for one fictional sentence. gold: expected claim types and number strings."""
    f, g = FUELS[i % 6], GEOMS[(i // 6) % 6]
    v = f"{1 + (i % 17) * 0.7:.1f}"
    if kind == "result_simple":
        return f"In this fictional test the {g} of {f} burned for {v} s before extinction.", {
            "types": {"result"}, "numbers": [v]}
    if kind == "result_multi":
        v2, o2, p, u = f"{float(v) * 2:.1f}", str(21 + i % 9), str(50 + i % 50), str(1 + i % 12)
        return (f"The spread rate over the {g} increased from {v} to {v2} mm/s as the oxygen fraction rose from 18% "
                f"to {o2}% at {p} kPa, while the opposed flow was held at {u} cm/s."), {
            "types": {"result"}, "numbers": [v, v2, "18", o2, p, u]}
    if kind == "future_work":
        return f"Future experiments should repeat the {f} cases at lower pressure to separate radiative losses.", {
            "types": {"future_work"}, "numbers": []}
    if kind == "method":
        return f"The apparatus consisted of a {g} holder, a hot-wire igniter and two color cameras.", {
            "types": set(), "numbers": []}
    if kind == "caption":
        return f"Figure {i % 30 + 1}. Schematic of the {g} configuration.", {"types": set(), "numbers": []}
    r, unc = f"{1 + (i % 17) * 0.07:.2f}", str(i % 7 + 3)
    return (f"The measured flame standoff ratio of {r} was larger than predicted, which the authors attribute to soot "
            f"radiation, although the thermocouple uncertainty of about {unc}% limits this comparison."), {
        "types": {"result", "limitation"}, "numbers": [r, unc]}


def synthetic_units(n, tmpl):
    units = []
    for i in range(n):
        kind = KINDS[i % len(KINDS)]
        target, gold = sentence(kind, i)
        before = " ".join(sentence(KINDS[(i + k) % 6], i + 7 * k)[0] for k in (3, 4))
        after = sentence(KINDS[(i + 3) % 6], i + 11)[0]
        msg = tmpl.format(doc_title=f"Synthetic compatibility test {i} (fictional)", section_title="Results",
                          before=before, target=target, after=after)
        units.append({"unit_id": f"syn-{i:03d}", "kind": kind, "user_message": msg, "target": target,
                      "gold": {"types": sorted(gold["types"]), "numbers": gold["numbers"]}})
    return units


NUM_RE = re.compile(r"\d+(?:\.\d+)?")


def analyse(rows, units):
    by = {u["unit_id"]: u for u in units}
    a = {"n": len(rows), "finish": {}, "json_valid": 0, "tokens_mean": 0.0, "tokens_p95": 0, "max_ws_run": 0,
         "type_recall": {t: [0, 0] for t in ("result", "future_work", "limitation")},
         "future_work_units_with_result": 0, "false_positive_units": 0, "negatives": 0,
         "quotes": 0, "quotes_verbatim": 0, "quotes_in_target": 0, "gold_numbers": 0, "gold_numbers_found": 0,
         "numbers_out": 0, "numbers_hallucinated": 0, "findings_total": 0, "duplicates": 0,
         "types_by_kind": {}, "truncated": []}
    toks = sorted(r["n_tokens"] for r in rows)
    a["tokens_mean"] = round(sum(toks) / max(len(toks), 1), 1)
    a["tokens_p95"] = toks[int(0.95 * (len(toks) - 1))] if toks else 0
    for r in rows:
        u, text = by[r["unit_id"]], r["output"] or ""
        a["finish"][r["finish_reason"]] = a["finish"].get(r["finish_reason"], 0) + 1
        ws = max((len(m) for m in re.findall(r"\s+", text)), default=0)
        a["max_ws_run"] = max(a["max_ws_run"], ws)
        if r["finish_reason"] == "length":
            a["truncated"].append({"unit_id": r["unit_id"], "kind": u["kind"], "n_tokens": r["n_tokens"],
                                   "longest_ws_run": ws, "claim_count": text.count('"claim":'),
                                   "distinct_quotes": len(set(re.findall(r'"claim_quote":\s*"([^"]{0,200})', text))),
                                   "tail": text[-300:]})
        try:
            d = json.loads(text)
            finds = d.get("findings") if isinstance(d, dict) else None
        except Exception:
            finds = None
        if not isinstance(finds, list):
            continue
        finds = [f for f in finds if isinstance(f, dict)]
        a["json_valid"] += 1
        gold, pred = set(u["gold"]["types"]), [f.get("claim_type") for f in finds]
        tk = a["types_by_kind"].setdefault(u["kind"], {})
        key = "+".join(sorted(set(map(str, pred)))) or "none"
        tk[key] = tk.get(key, 0) + 1
        for t in gold:
            a["type_recall"][t][1] += 1
            a["type_recall"][t][0] += int(t in pred)
        if u["kind"] == "future_work" and "result" in pred:
            a["future_work_units_with_result"] += 1
        if not gold:
            a["negatives"] += 1
            a["false_positive_units"] += int(bool(finds))
        a["findings_total"] += len(finds)
        keys = [(f.get("claim_type"), f.get("claim_quote")) for f in finds]
        a["duplicates"] += len(keys) - len(set(keys))
        nums = []
        for f in finds:
            q = f.get("claim_quote") or ""
            a["quotes"] += 1
            a["quotes_verbatim"] += int(bool(q) and q in u["user_message"])
            a["quotes_in_target"] += int(bool(q) and q in u["target"])
            nums += [str(v.get("value_text", "")) for v in f.get("values") or [] if isinstance(v, dict)]
            nums += [str(c["value_text"]) for c in (f.get("conditions") or {}).values()
                     if isinstance(c, dict) and "value_text" in c]
        found = {n for s in nums for n in NUM_RE.findall(s)}
        a["gold_numbers"] += len(u["gold"]["numbers"])
        a["gold_numbers_found"] += sum(n in found for n in u["gold"]["numbers"])
        a["numbers_out"] += len(found)
        a["numbers_hallucinated"] += sum(n not in u["user_message"] for n in found)
    return a


def judge(b, a_cur, engine_cfg):
    tr = b["type_recall"]
    pct = lambda x, y: x / y if y else 0.0
    return {
        "W1_engine_setting_applied": "disable_any_whitespace=True" in (engine_cfg or "") or "indent=2" in (engine_cfg or ""),
        "W2_no_whitespace_runaway": b["max_ws_run"] <= 20,
        "W3_json_valid": b["json_valid"] >= 71,
        "W4_not_more_tokens": a_cur is not None and b["tokens_mean"] <= a_cur["tokens_mean"],
        "Q1_future_work_recall": tr["future_work"][0] >= 10,
        "Q2_limitation_recall": tr["limitation"][0] >= 8,
        "Q3_result_recall": tr["result"][0] >= 33,
        "Q4_no_proposal_as_result": b["future_work_units_with_result"] <= 1,
        "Q5_no_false_positives": b["false_positive_units"] <= 1,
        "Q6_quotes": b["quotes"] > 0 and b["quotes_verbatim"] == b["quotes"] and pct(b["quotes_in_target"], b["quotes"]) >= 0.95,
        "Q7_numbers": pct(b["numbers_hallucinated"], b["numbers_out"]) <= 0.02 and pct(b["gold_numbers_found"], b["gold_numbers"]) >= 0.75,
        "Q8_duplicates": b["duplicates"] <= 1,
        "Q9_truncation": b["finish"].get("length", 0) <= 1,
    }


# ------------------------------------------------------------- setup ----
R["env"] = {"gpu": sh("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader")}
open("/tmp/fif_kaggle.py", "w").write(CONFIG["runner_source"])
sys.path.insert(0, "/tmp")
import fif_kaggle

try:
    env_info = {}
    VPY = fif_kaggle.ensure_vllm_env(CONFIG["vllm_version"], env_info)
    R["vllm_env"] = env_info
except Exception as e:
    VPY = None
    R["vllm_env"] = {"ok": False, "error": repr(e)[:1500]}
save()
R["model_download_s"] = time.time()
sh(f"{sys.executable} -c \"from huggingface_hub import snapshot_download as s; s('{CONFIG['llm_model']}', "
   f"allow_patterns=['*.json','*.safetensors','*.txt','*.model','tokenizer*'])\"", 1800)
R["model_download_s"] = round(time.time() - R["model_download_s"], 1)
PROMPTS = {"current": CONFIG["prompt"], "baseline": CONFIG["prompt_baseline"]}
UNITS = synthetic_units(72, CONFIG["prompt"]["user_template"])
assert CONFIG["prompt"]["user_template"] == CONFIG["prompt_baseline"]["user_template"]
json.dump(UNITS, open(f"{OUT}/synthetic_units.json", "w"), indent=1)
save()

# ------------------------------------------- A: default engine, p-1 vs p-2 ----
BENCH = r'''
import json, os, sys, time, traceback
cfg = json.load(open(sys.argv[1])); out = cfg["out"]; units = cfg["units"]
res = {"variants": {}}
def dump(): json.dump(res, open(f"{out}/bench_A.json", "w"), indent=2)
try:
    import torch, vllm
    from vllm import LLM, SamplingParams
    from vllm.sampling_params import StructuredOutputsParams
    t = time.time()
    llm = LLM(model=cfg["model"], tensor_parallel_size=torch.cuda.device_count(), dtype="half", max_model_len=6144,
              gpu_memory_utilization=0.88, seed=0)
    res["load_s"] = round(time.time() - t, 1)
    res["engine_structured_outputs_config"] = str(llm.llm_engine.vllm_config.structured_outputs_config)
except Exception as e:
    res["fatal"] = repr(e)[:800]; res["trace"] = traceback.format_exc()[-3000:]; dump(); os._exit(2)
KW = {"chat_template_kwargs": {"enable_thinking": False}, "use_tqdm": False}
for name, P in cfg["prompts"].items():
    sp = SamplingParams(temperature=0, max_tokens=1536, seed=0, structured_outputs=StructuredOutputsParams(json=P["output_schema"]))
    msgs = lambda u: [{"role": "system", "content": P["system"]}, {"role": "user", "content": u}]
    v = res["variants"][name] = {"ok": None, "prompt": P["version"]}
    try:
        llm.chat([msgs(units[0]["user_message"])], SamplingParams(temperature=0, max_tokens=16, seed=0), **KW)
        t0 = time.time(); rows = []
        for i in range(0, len(units), 24):
            chunk = units[i:i + 24]
            for u, o in zip(chunk, llm.chat([msgs(u["user_message"]) for u in chunk], sp, **KW)):
                c = o.outputs[0]
                rows.append({"unit_id": u["unit_id"], "finish_reason": c.finish_reason, "n_tokens": len(c.token_ids), "output": c.text})
        v.update(ok=True, s=round(time.time() - t0, 1), units_per_s=round(len(units) / (time.time() - t0), 3))
        with open(f"{out}/raw_A_{name}.jsonl", "w") as fh:
            fh.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    except Exception as e:
        v.update(ok=False, error=repr(e)[:800], trace=traceback.format_exc()[-3000:]); dump(); os._exit(3)
    dump()
dump(); os._exit(0)
'''
if VPY and not GATE.get("skip_a"):
    open("/tmp/fif_bench.py", "w").write(BENCH)
    json.dump({"model": CONFIG["llm_model"], "out": OUT, "units": UNITS,
               "prompts": {"baseline": PROMPTS["baseline"], "current": PROMPTS["current"]}}, open("/tmp/fif_bench_A.json", "w"))
    t = time.time()
    rc = fif_kaggle.run_logged([VPY, "/tmp/fif_bench.py", "/tmp/fif_bench_A.json"], f"{OUT}/logs/bench_A.log", 1800)
    try:
        R["A"] = json.load(open(f"{OUT}/bench_A.json"))
    except Exception:
        R["A"] = {"fatal": "no result"}
    R["A"]["rc"], R["A"]["wall_s"] = rc, round(time.time() - t, 1)
    for name in ("baseline", "current"):
        p = f"{OUT}/raw_A_{name}.jsonl"
        if os.path.exists(p):
            R["A"]["variants"][name]["analysis"] = analyse([json.loads(x) for x in open(p)], UNITS)
    save()

# ------------------------------- B: real runner, p-2, engine no-whitespace ----
try:
    import pandas as pd

    inp = "/tmp/fif_v5_input"
    os.makedirs(f"{inp}/extract", exist_ok=True)
    pd.DataFrame({"unit_id": [u["unit_id"] for u in UNITS], "user_message": [u["user_message"] for u in UNITS]}
                 ).to_parquet(f"{inp}/extract/units.parquet")
    json.dump(PROMPTS["current"], open(f"{inp}/extract/prompt.json", "w"))
    json.dump({"export_name": "synthetic-v5", "selection_id": "synthetic", "units_sha256": "synthetic"},
              open(f"{inp}/extract/export_manifest.json", "w"))
    json.dump({"steps": ["env", "extract"], "llm_model": CONFIG["llm_model"], "llm_backend": "vllm", "max_model_len": 6144,
               "max_new_tokens": 1536, "batch_size": 24, "vllm_version": CONFIG["vllm_version"], "json_whitespace": GATE.get("json_whitespace", "none"),
               "run_id": "run-synthetic-v5", "gpu_memory_utilization": 0.88, "worker_timeout_s": 1500},
              open(f"{inp}/job.json", "w"))
    work = f"{OUT}/B"
    t = time.time()
    sh(f"FIF_INPUT={inp} FIF_WORK={work} {sys.executable} /tmp/fif_kaggle.py", 2400)
    rep = json.load(open(f"{work}/env.json"))
    ex = rep["steps"].get("extract", {})
    man = ex.get("result") or {}
    R["B"] = {"wall_s": round(time.time() - t, 1), "ok": ex.get("ok"), "error": ex.get("error"),
              "engine_structured_outputs_config": man.get("engine_structured_outputs_config"),
              "structured_output": man.get("structured_output"), "load_s": man.get("load_s"),
              "seconds": man.get("seconds"), "units_per_s": man.get("units_per_s")}
    raw = f"{work}/run_out/raw.jsonl"
    if os.path.exists(raw):
        R["B"]["analysis"] = analyse([json.loads(x) for x in open(raw)], UNITS)
except Exception as e:
    R["B"] = {"ok": False, "error": repr(e)[:800], "trace": traceback.format_exc()[-1500:]}
save()

# ----------------------------------------------------------- verdict ----
if R.get("B", {}).get("analysis"):
    a_cur = R.get("A", {}).get("variants", {}).get("current", {}).get("analysis")
    if a_cur is None and GATE.get("a_current_tokens_ref") is not None:
        a_cur = {"tokens_mean": GATE["a_current_tokens_ref"]}
    verdict = judge(R["B"]["analysis"], a_cur, (R["B"].get("engine_structured_outputs_config") or "") + " "
                    + (R["B"].get("structured_output") or ""))
    R["verdict"] = {"criteria": verdict, "all_pass": all(verdict.values())}
else:
    R["verdict"] = {"all_pass": False, "reason": "B produced no outputs"}
save()
print(json.dumps(R["verdict"], indent=1))

# ------------------------------------------------- gated real pilot ----
if GATE.get("pilot"):
    if not R["verdict"].get("all_pass"):
        R["pilot"] = {"ran": False, "reason": "acceptance criteria not met"}
    else:
        import glob

        hits = glob.glob("/kaggle/input/**/job.json", recursive=True)
        if len(hits) != 1:
            R["pilot"] = {"ran": False, "reason": f"expected one job.json under /kaggle/input, found {hits}"}
        else:
            t = time.time()
            sh(f"FIF_INPUT={os.path.dirname(hits[0])} FIF_WORK=/kaggle/working {sys.executable} /tmp/fif_kaggle.py", 3000)
            try:
                rep = json.load(open("/kaggle/working/env.json"))
                R["pilot"] = {"ran": True, "wall_s": round(time.time() - t, 1),
                              "steps": {k: {"ok": v.get("ok"), "error": v.get("error")} for k, v in rep["steps"].items()}}
            except Exception as e:
                R["pilot"] = {"ran": True, "error": repr(e)}
    save()
    print(json.dumps(R["pilot"], indent=1))
