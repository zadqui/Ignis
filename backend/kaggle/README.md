# M4 en Kaggle

Solo sube **texto CC0 de PSI y textos con licencia abierta explícita**. Los abstracts de editores
(OpenAlex, Semantic Scholar) nunca se exportan: `export` y `export-classify` los excluyen por construcción.

| Script | Uso |
| --- | --- |
| `fif_compat_check.py` | Sin datos del proyecto (texto sintético ficticio). NLI: velocidad por lote, memoria, deriva fp16/fp32. Qwen3-8B con el prompt y esquema reales: vLLM preinstalado → vLLM en venv aislado en `/tmp` → transformers fp16 en 2×T4 (solo si vLLM falla). Plantilla: se construye con `fif-findings kaggle-compat`. |
| `fif_kaggle.py` | Autocontenido. Lee un dataset privado con `job.json` y ejecuta los pasos `env`, `classify`, `extract`. Las salidas son reanudables y solo se agregan, nunca se sobrescriben. |

## Flujo

```bash
# 0. Una vez: autenticar la CLI (OAuth); `kaggle.json` antiguo no es aceptado por la API nueva
uvx --with six kaggle auth login

# 0b. Compatibilidad (sin datos; ~30-45 min de GPU) → compat3/compat.json + salidas crudas
uv run fif-findings kaggle-compat --owner <usuario>
uvx --with six kaggle kernels push -p data/findings/kaggle_compat/fif-m4-compat-check

# 1. Clasificador (GPU)
uv run fif-findings export-classify
uv run fif-findings kaggle-input --owner <usuario> --name fif-m4-classify-1 --classify classify-<hash>
uvx --with six kaggle datasets create -p data/findings/kaggle_input/fif-m4-classify-1 -r tar
#    notebook con fif_kaggle.py + ese dataset (GPU T4 x2, internet) → classify_out/
uv run fif-findings import-scores <descarga>/classify_out
uv run fif-findings select

# 2. Piloto de extracción (20 unidades) → revisar → lote completo
uv run fif-findings export --limit 20
uv run fif-findings kaggle-input --owner <usuario> --name fif-m4-pilot-2 --extract sel-<id>-pilot20
#    ... notebook → run_out/
uv run fif-findings import <descarga>/run_out
uv run fif-findings verify
```

## vLLM en Kaggle

La imagen de Kaggle no trae vLLM, y un `pip install vllm` sobre ella falla al importar por la versión de triton.
`fif_kaggle.py` crea un venv aislado en `/tmp/vllm-env` (uv, Python 3.12, `vllm==0.33.0` con su propio torch y
triton) y ejecuta la extracción en un subproceso con ese Python; la imagen base no se modifica. Los pesos se
descargan en `/tmp/hf`, nunca en `/kaggle/working`. Validado en la prueba de compatibilidad v2 (2×T4, TP=2, fp16).
Claves de `job.json`: `vllm_version`, `json_whitespace` (`default` | `none`), `gpu_memory_utilization`, `enforce_eager`.

Contrato de salida: `run_out/{run_manifest.json, raw.jsonl, prompt.json}`. Al importar se exige que
`units_sha256` y `prompt_sha256` coincidan con el export, y que `prompt.json` coincida con su hash.
