"""Exploratory simulators: small gradient-boosting models over PSI tabulated trials (config/predict_models.yaml).

* Trained in-process on the PUBLIC export in well under a second; cached per database and config version.
* Uncertainty: quantile models (10 %, 50 %, 90 %) for regressions, class probabilities for classifications.
* Validation is grouped by test day (GroupKFold): it measures performance on held-out campaigns, compared with a
  baseline that ignores the inputs. If a model does not beat the baseline, the verdict says so.
* Inputs outside the training range are flagged; unseen categories are refused. No gravity input exists.
* The language model never produces these numbers: it can only call this tool and explain its output.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .common import CONFIG, investigation_withheld, load_yaml

QUANTILES = (0.1, 0.5, 0.9)
MISSING = {"", "none", "-", "–", "—", "n/a", "na", "nan"}
CONFIG_FILE = CONFIG / "predict_models.yaml"


class PredictError(ValueError):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def specs() -> dict[str, Any]:
    return load_yaml(CONFIG_FILE)


def _num(v: Any) -> float:
    if v is None:
        return math.nan
    s = str(v).strip().replace(",", ".")
    if s.lower() in MISSING:
        return math.nan
    try:
        return float(s)
    except ValueError:
        return math.nan


def _cat(v: Any, normalize: str | None = None) -> str | None:
    if v is None or str(v).strip().lower() in MISSING:
        return None
    s = str(v).strip()
    return s.lower() if normalize == "lower" else s


def _dataset(con, spec: dict[str, Any]) -> dict[str, Any]:
    lic = con.execute("SELECT license_status FROM investigation_rights WHERE inv_id = ?", [spec["inv_id"]]).fetchone()
    if not lic or investigation_withheld(lic[0]):
        raise PredictError("licence_withheld", "Los datos por ensayo de esta investigación no se publican.", 403)
    rows = con.execute("SELECT trial_key, trial_id, original_columns_json FROM trials WHERE inv_id = ? "
                       "ORDER BY trial_key", [spec["inv_id"]]).fetchall()
    tgt, feats, flt = spec["target"], spec["features"], spec.get("filter")
    classes = list((tgt.get("classes") or {}).keys())
    excluded: dict[str, int] = {}
    out = {"raw": [], "y": [], "groups": [], "keys": []}
    for key, tid, js in rows:
        o = json.loads(js) if js else {}
        if flt and _cat(o.get(flt["column"]), flt.get("normalize")) != flt["equals"]:
            continue
        if spec["task"] == "regression":
            y = _num(o.get(tgt["column"]))
            if math.isnan(y):
                excluded["target_missing"] = excluded.get("target_missing", 0) + 1
                continue
        else:
            y = _cat(o.get(tgt["column"]), tgt.get("normalize"))
            if y is None or y in (tgt.get("exclude") or []) or (classes and y not in classes):
                reason = "target_missing" if y is None else f"target_excluded:{y}"
                excluded[reason] = excluded.get(reason, 0) + 1
                continue
        values = {}
        for f in feats:
            raw = o.get(f["column"])
            values[f["column"]] = _cat(raw, f.get("normalize")) if f.get("type") == "category" else _num(raw)
        out["raw"].append(values)
        out["y"].append(y)
        out["groups"].append(" | ".join(str(o.get(g, "")) for g in spec["group"]))
        out["keys"].append({"trial_key": key, "trial_id": tid, "target": y})
    out["excluded"] = excluded
    return out


def _encode(raw: list[dict], feats: list[dict], vocab: dict[str, list[str]]):
    import numpy as np

    X = np.full((len(raw), len(feats)), np.nan)
    for i, r in enumerate(raw):
        for j, f in enumerate(feats):
            v = r.get(f["column"])
            if f.get("type") == "category":
                X[i, j] = vocab[f["column"]].index(v) if v in vocab[f["column"]] else np.nan
            else:
                X[i, j] = v if v is not None else np.nan
    return X


def _estimators(spec: dict[str, Any], mask: list[bool]):
    from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor

    common = {"max_iter": 140, "learning_rate": 0.08, "max_depth": 3, "min_samples_leaf": 8,
              "categorical_features": mask, "random_state": 0}
    if spec["task"] == "regression":
        return {q: HistGradientBoostingRegressor(loss="quantile", quantile=q, **common) for q in QUANTILES}
    return {"clf": HistGradientBoostingClassifier(**common)}


def _cv(spec, X, y, groups, mask) -> dict[str, Any]:
    import numpy as np
    from sklearn.model_selection import GroupKFold

    n_groups = len(set(groups))
    if n_groups < 3:
        return {"status": "not_enough_groups", "n_groups": n_groups}
    cv = GroupKFold(n_splits=min(5, n_groups))
    if spec["task"] == "regression":
        y = np.asarray(y, dtype=float)
        pred = np.zeros((len(y), len(QUANTILES)))
        base = np.zeros(len(y))
        for tr, te in cv.split(X, y, groups):
            models = _estimators(spec, mask)
            for k, q in enumerate(QUANTILES):
                pred[te, k] = models[q].fit(X[tr], y[tr]).predict(X[te])
            base[te] = np.median(y[tr])
        pred.sort(axis=1)
        mae, mae_base = float(np.mean(np.abs(pred[:, 1] - y))), float(np.mean(np.abs(base - y)))
        skill = 1 - mae / mae_base if mae_base else 0.0
        raw_cov = float(np.mean((y >= pred[:, 0]) & (y <= pred[:, 2])))
        # Conformalized quantile regression: widen the 10-90 % band by the 80 % quantile of the out-of-fold
        # non-conformity scores, so the band reaches its nominal coverage on held-out test days.
        scores = np.maximum(pred[:, 0] - y, y - pred[:, 2])
        level = min(1.0, math.ceil((len(y) + 1) * 0.8) / len(y))
        pad = max(0.0, float(np.quantile(scores, level)))
        cov = float(np.mean((y >= pred[:, 0] - pad) & (y <= pred[:, 2] + pad)))
        return {"status": "ok", "n_groups": n_groups, "folds": cv.n_splits, "mae": round(mae, 3),
                "mae_baseline": round(mae_base, 3), "skill": round(skill, 3),
                "interval_80_coverage_raw": round(raw_cov, 3), "interval_80_coverage": round(cov, 3),
                "conformal_pad": round(pad, 4)}
    labels = sorted(set(y))
    yi = np.array([labels.index(v) for v in y])
    proba = np.zeros((len(y), len(labels)))
    base = np.zeros((len(y), len(labels)))
    for tr, te in cv.split(X, yi, groups):
        m = _estimators(spec, mask)["clf"].fit(X[tr], yi[tr])
        p = np.zeros((len(te), len(labels)))
        p[:, m.classes_] = m.predict_proba(X[te])
        proba[te] = p
        freq = np.bincount(yi[tr], minlength=len(labels)) / len(tr)
        base[te] = freq
    eps = 1e-6
    ll = float(-np.mean(np.log(np.clip(proba[np.arange(len(yi)), yi], eps, 1))))
    ll_base = float(-np.mean(np.log(np.clip(base[np.arange(len(yi)), yi], eps, 1))))
    acc, acc_base = float(np.mean(proba.argmax(1) == yi)), float(np.mean(base.argmax(1) == yi))
    skill = 1 - ll / ll_base if ll_base else 0.0
    return {"status": "ok", "n_groups": n_groups, "folds": cv.n_splits, "log_loss": round(ll, 3),
            "log_loss_baseline": round(ll_base, 3), "accuracy": round(acc, 3), "accuracy_baseline": round(acc_base, 3),
            "skill": round(skill, 3)}


def verdict(cv: dict[str, Any]) -> dict[str, str]:
    if cv.get("status") != "ok":
        return {"code": "not_validated", "text": "No hay suficientes días de ensayo distintos para validarlo."}
    s = cv["skill"]
    if s >= 0.2:
        return {"code": "beats_baseline", "text": "En días de ensayo no vistos, el modelo mejora claramente a una "
                "referencia que ignora las condiciones. Sigue siendo exploratorio."}
    if s >= 0.05:
        return {"code": "marginal", "text": "Mejora poco a la referencia en días no vistos: úsalo solo para explorar "
                "tendencias."}
    return {"code": "no_better", "text": "No mejora a la referencia en días no vistos: no lo uses para decidir."}


class Simulator:
    def __init__(self, spec: dict[str, Any], con):
        import numpy as np

        self.spec = spec
        self.feats = spec["features"]
        data = _dataset(con, spec)
        if len(data["y"]) < 30:
            raise PredictError("not_enough_data", f"Solo {len(data['y'])} ensayos utilizables.", 409)
        self.vocab = {f["column"]: sorted({r[f["column"]] for r in data["raw"] if r[f["column"]] is not None})
                      for f in self.feats if f.get("type") == "category"}
        self.mask = [f.get("type") == "category" for f in self.feats]
        X = _encode(data["raw"], self.feats, self.vocab)
        y = data["y"]
        self.cv = _cv(spec, X, y, data["groups"], self.mask)
        self.models = _estimators(spec, self.mask)
        self.domain_target_min = 0.0
        if spec["task"] == "regression":
            self.domain_target_min = float(np.min(y))
            for m in self.models.values():
                m.fit(X, np.asarray(y, dtype=float))
        else:
            self.labels = sorted(set(y))
            self.models["clf"].fit(X, np.array([self.labels.index(v) for v in y]))
        self.X, self.keys, self.raw = X, data["keys"], data["raw"]
        self.excluded = data["excluded"]
        self.domain = {}
        for j, f in enumerate(self.feats):
            if f.get("type") == "category":
                self.domain[f["column"]] = {"type": "category", "values": self.vocab[f["column"]]}
            else:
                col = X[:, j][~np.isnan(X[:, j])]
                self.domain[f["column"]] = {"type": "number", "min": float(col.min()), "max": float(col.max()),
                                            "p05": float(np.percentile(col, 5)), "p95": float(np.percentile(col, 95)),
                                            "median": float(np.median(col)), "n": int(col.size)}
        self.scale = np.array([np.nanstd(X[:, j]) or 1.0 for j in range(len(self.feats))])

    # --- public description --------------------------------------------------------------------------------------
    def describe(self) -> dict[str, Any]:
        s = self.spec
        return {"id": s["id"], "inv_id": s["inv_id"], "title": s["title"], "question": s.get("question"),
                "task": s["task"], "target": s["target"], "n_trials": len(self.keys), "excluded": self.excluded,
                "features": [f | {"domain": self.domain[f["column"]]} for f in self.feats],
                "validation": self.cv, "verdict": verdict(self.cv), "status": "exploratory",
                "group_by": s["group"]}

    # --- prediction ----------------------------------------------------------------------------------------------
    def _vector(self, inputs: dict[str, Any]):
        import numpy as np

        x = np.full(len(self.feats), np.nan)
        flags = []
        for j, f in enumerate(self.feats):
            col = f["column"]
            v = inputs.get(col)
            if v is None or v == "":
                flags.append({"feature": col, "flag": "missing", "text": "Sin valor: el modelo usa su manejo de "
                              "valores faltantes."})
                continue
            if f.get("type") == "category":
                v = _cat(v, f.get("normalize"))
                if v not in self.vocab[col]:
                    raise PredictError("unknown_category", f"'{v}' no aparece en los ensayos de {col}.")
                x[j] = self.vocab[col].index(v)
            else:
                try:
                    v = float(v)
                except (TypeError, ValueError):
                    raise PredictError("invalid_number", f"{col}: valor numérico inválido.") from None
                d = self.domain[col]
                if v < d["min"] or v > d["max"]:
                    flags.append({"feature": col, "flag": "outside_training_range",
                                  "text": f"Fuera del rango de los ensayos ({d['min']:g}–{d['max']:g}): el resultado "
                                          "es una extrapolación sin respaldo."})
                x[j] = v
        return x, flags

    def _predict_x(self, X) -> list[dict[str, Any]]:
        import numpy as np

        if self.spec["task"] == "regression":
            p = np.column_stack([self.models[q].predict(X) for q in QUANTILES])
            p.sort(axis=1)
            pad = self.cv.get("conformal_pad", 0.0)
            floor = 0.0 if self.domain_target_min >= 0 else -math.inf  # durations cannot be negative
            return [{"low": round(max(floor, float(a) - pad), 3), "median": round(float(b), 3),
                     "high": round(float(c) + pad, 3)} for a, b, c in p]
        proba = np.zeros((X.shape[0], len(self.labels)))
        m = self.models["clf"]
        proba[:, m.classes_] = m.predict_proba(X)
        return [{"probabilities": {self.labels[k]: round(float(v), 3) for k, v in enumerate(row)},
                 "most_likely": self.labels[int(row.argmax())]} for row in proba]

    def neighbours(self, x, k: int = 5) -> list[dict[str, Any]]:
        import numpy as np

        d = np.zeros(len(self.X))
        for j, f in enumerate(self.feats):
            if math.isnan(x[j]):
                continue
            col = self.X[:, j]
            if f.get("type") == "category":
                d += np.where(np.isnan(col) | (col != x[j]), 1.0, 0.0)
            else:
                d += np.where(np.isnan(col), 1.0, np.abs(col - x[j]) / self.scale[j])
        out = []
        for i in np.argsort(d, kind="stable")[:k]:
            out.append(self.keys[i] | {"distance": round(float(d[i]), 3), "conditions": self.raw[i]})
        return out

    def predict(self, inputs: dict[str, Any]) -> dict[str, Any]:
        x, flags = self._vector(inputs)
        return {"model_id": self.spec["id"], "prediction": self._predict_x(x.reshape(1, -1))[0], "flags": flags,
                "neighbours": self.neighbours(x), "verdict": verdict(self.cv), "status": "exploratory",
                "warnings": ["Simulación exploratoria basada en ensayos con mapeo en borrador; no es un modelo físico.",
                             "No incluye gravedad: ningún ensayo la registra. No extrapola a la Luna ni a Marte."]}

    def sweep(self, inputs: dict[str, Any], feature: str, points: int = 30) -> dict[str, Any]:
        import numpy as np

        j = next((i for i, f in enumerate(self.feats) if f["column"] == feature), None)
        if j is None or self.feats[j].get("type") == "category":
            raise PredictError("invalid_feature", "Solo se pueden recorrer variables numéricas del modelo.")
        x, flags = self._vector(inputs)
        d = self.domain[feature]
        grid = np.linspace(d["min"], d["max"], max(5, min(points, 80)))
        X = np.repeat(x.reshape(1, -1), len(grid), axis=0)
        X[:, j] = grid
        observed = [float(v) for v in self.X[:, j] if not math.isnan(v)]
        return {"model_id": self.spec["id"], "feature": feature, "grid": [round(float(g), 4) for g in grid],
                "predictions": self._predict_x(X), "flags": [f for f in flags if f["feature"] != feature],
                "observed_values": observed, "status": "exploratory"}


def _stamp(db: Path) -> tuple:
    st = Path(db).stat()
    return (st.st_mtime_ns, st.st_size, hashlib.sha256(CONFIG_FILE.read_bytes()).hexdigest())


def _cache_file(db: str, stamp: tuple) -> Path:
    from .common import data_root

    key = hashlib.sha256(repr((Path(db).name, stamp)).encode()).hexdigest()[:16]
    cache_root = Path(os.environ["FIF_MODEL_CACHE"]) if os.environ.get("FIF_MODEL_CACHE") else data_root(Path(db)) / "models"
    return cache_root / f"simulators-{key}.pkl"


@lru_cache(maxsize=4)
def _simulators(db: str, stamp: tuple) -> dict[str, Any]:
    """Train (or load the models this process trained earlier for the same database + config)."""
    import pickle

    import duckdb

    cache = _cache_file(db, stamp)
    if cache.exists():  # written below by this module only; keyed by database and config hashes
        try:
            return pickle.loads(cache.read_bytes())
        except Exception:  # noqa: BLE001 - a stale or partial cache is simply rebuilt
            cache.unlink(missing_ok=True)
    con = duckdb.connect(db, read_only=True)
    try:
        out = {}
        for spec in specs().get("models") or []:
            try:
                out[spec["id"]] = Simulator(spec, con)
            except PredictError as exc:
                out[spec["id"]] = exc
    finally:
        con.close()
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(out))
    tmp.replace(cache)
    return out


def simulators(db: Path) -> dict[str, Any]:
    return _simulators(str(db), _stamp(db))


def get(db: Path, model_id: str) -> Simulator:
    sims = simulators(db)
    if model_id not in sims:
        raise PredictError("unknown_model", f"Modelo desconocido: {model_id}", 404)
    sim = sims[model_id]
    if isinstance(sim, PredictError):
        raise sim
    return sim


def catalog(db: Path) -> dict[str, Any]:
    cfg = specs()
    items = []
    for mid, sim in simulators(db).items():
        if isinstance(sim, PredictError):
            items.append({"id": mid, "available": False, "reason": sim.code, "message": sim.message})
        else:
            items.append(sim.describe() | {"available": True})
    return {"version": cfg.get("version"), "status": cfg.get("status"), "models": items}
