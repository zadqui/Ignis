"""PSI media: representative images (downloaded, shown as published by PSI) and visual evidence by METADATA only.

* Images: only files PSI lists under "Representative Image(s)" of investigations whose licence is not withheld
  (publication policy). Logos are skipped (no agency or project insignia). Images are displayed, never analysed.
* Visual evidence (videos, camera metadata ``.mdipsug``, event logs ``TP.txt``, image archives): names, counts and
  sizes from the M1 inventory. Nothing is downloaded or opened.
The manifest lives in ``data/media/manifest.json`` (generated data, never versioned).
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from .common import investigation_withheld

IMAGE_CATEGORY = "Representative Image(s)"
IMAGE_EXT = ("jpg", "jpeg", "png")
MAX_IMAGE_BYTES = 3_000_000
VISUAL = {"video": ("mp4", "ts"), "camera_metadata": ("mdipsug",), "image_archive": ("zip",)}
MANIFEST_VERSION = "media-1"


def manifest_path(data: Path) -> Path:
    return data / "media" / "manifest.json"


def caption(file_name: str, inv_id: str) -> str:
    stem = Path(file_name).stem
    stem = re.sub(rf"^{re.escape(inv_id)}_", "", stem)
    stem = stem.replace(f"{IMAGE_CATEGORY}_", "").replace("_", " · ")
    return re.sub(r"\s+", " ", stem).strip()


def is_logo(file_name: str) -> bool:
    return bool(re.search(r"\blogo\b", file_name, re.IGNORECASE))


def fetch_images(data: Path, client=None) -> dict[str, Any]:
    """Download representative images (size-capped, URL never logged) and write the media manifest."""
    from ...psi.client import PsiClient
    from ...psi.download import download_selected

    psi_dir = data / "psi"
    con = duckdb.connect(str(psi_dir / "inventory.duckdb"), read_only=True)
    try:
        lic = dict(con.execute("SELECT inv_id, license_status FROM investigation_rights").fetchall())
    finally:
        con.close()
    allowed = sorted(i for i, s in lic.items() if not investigation_withheld(s))
    rep = download_selected(client or PsiClient(), psi_dir, categories=(IMAGE_CATEGORY,), extensions=IMAGE_EXT,
                            only=allowed, max_bytes=MAX_IMAGE_BYTES)
    items, skipped = [], []
    for row in rep.manifest:
        if row["category"] != IMAGE_CATEGORY:
            continue
        if row["inv_id"] not in allowed:
            skipped.append({"file_name": row["file_name"], "reason": "licence_withheld"})
            continue
        if is_logo(row["file_name"]):
            skipped.append({"file_name": row["file_name"], "reason": "logo_not_shown"})
            continue
        items.append({
            "media_id": row["sha256"][:16], "inv_id": row["inv_id"], "file_name": row["file_name"],
            "caption": caption(row["file_name"], row["inv_id"]), "sha256": row["sha256"],
            "size_bytes": row["size_bytes"], "local_path": (Path("psi") / row["local_path"]).as_posix(),
            "psi_path": row["path"], "license_status": lic.get(row["inv_id"]), "source": "NASA PSI",
            "kind": "representative",
        })
    curated, curated_skipped = fetch_curated(data, client)
    out = {"version": MANIFEST_VERSION, "generated_at": datetime.now(UTC).isoformat(), "images": items + curated,
           "skipped": skipped + curated_skipped, "failed": [{"path": t.path, "error": e} for t, e in rep.failed],
           "too_large": [{"path": t.path, "reason": r} for t, r in rep.skipped]}
    path = manifest_path(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)
    return {"images": len(items), "curated": len(curated), "skipped": len(out["skipped"]), "failed": len(out["failed"]),
            "fetched": len(rep.fetched), "cached": len(rep.cached)}


# ----------------------------------------------------------------------------------------------- frames from ZIPs
# PSI storage accepts HTTP Range requests, so a single frame can be read out of a multi-GB image archive: the ZIP
# central directory (a few KB at the end of the file) lists every member and its offset, then only that member's
# bytes are requested. Nothing else of the archive is downloaded.

FRAME_EXT = (".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff")
MAX_MEMBER_BYTES = 8_000_000
MAX_ARCHIVE_READ = 40_000_000


class RangeFile(io.RawIOBase):
    """Seekable read-only view of a remote file through HTTP Range requests (block-cached, byte-capped)."""

    BLOCK = 1 << 18

    def __init__(self, session, url: str, size: int, cap: int = MAX_ARCHIVE_READ):
        self.session, self._url, self.size, self.pos, self.cap = session, url, size, 0, cap
        self.cache: dict[int, bytes] = {}
        self.bytes_read = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = offset if whence == 0 else self.pos + offset if whence == 1 else self.size + offset
        return self.pos

    def _block(self, k: int) -> bytes:
        if k not in self.cache:
            start, end = k * self.BLOCK, min(self.size, (k + 1) * self.BLOCK) - 1
            if self.bytes_read + (end - start + 1) > self.cap:
                raise OSError(f"range read cap {self.cap} B reached")
            r = self.session.get(self._url, headers={"Range": f"bytes={start}-{end}"}, timeout=120)
            if r.status_code not in (200, 206):
                raise OSError(f"storage returned HTTP {r.status_code}")
            body = r.content if r.status_code == 206 else r.content[start:end + 1]
            self.bytes_read += len(body)
            self.cache[k] = body
        return self.cache[k]

    def read(self, n: int = -1) -> bytes:
        if self.pos >= self.size:
            return b""
        n = self.size - self.pos if n is None or n < 0 else min(n, self.size - self.pos)
        out = bytearray()
        while n > 0:
            k, off = divmod(self.pos, self.BLOCK)
            chunk = self._block(k)[off:off + n]
            if not chunk:
                break
            out += chunk
            self.pos += len(chunk)
            n -= len(chunk)
        return bytes(out)

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[:len(data)] = data
        return len(data)


def open_remote_zip(client, inv_id: str, file_name: str, file_version: int, size: int):
    """(ZipFile, RangeFile) over a PSI archive; the signed URL never leaves this function's objects."""
    url = client.get_download_url(inv_id, file_name, file_version)
    rf = RangeFile(client.session, url, size)
    return zipfile.ZipFile(rf), rf


def frame_members(zf: zipfile.ZipFile) -> list[zipfile.ZipInfo]:
    return sorted((i for i in zf.infolist() if i.filename.lower().endswith(FRAME_EXT) and not i.is_dir()
                   and 0 < i.compress_size <= MAX_MEMBER_BYTES and "__macosx" not in i.filename.lower()),
                  key=lambda i: i.filename)


def to_jpeg(raw: bytes, max_side: int = 1600, crop: list[float] | None = None) -> bytes:
    """Convert any frame format to a web JPEG (PyMuPDF; no new dependency). Pixels are not altered beyond format
    conversion, resizing and an optional crop given as fractions [x0, y0, x1, y1]."""
    import pymupdf

    pix = pymupdf.Pixmap(raw)
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
    if pix.alpha or crop:  # flatten transparency onto white (JPEG has no alpha) and/or crop, via a blank page
        doc = pymupdf.open()
        page = doc.new_page(width=pix.width, height=pix.height)
        page.insert_image(page.rect, stream=raw)
        x0, y0, x1, y1 = crop or (0.0, 0.0, 1.0, 1.0)
        pix = page.get_pixmap(clip=pymupdf.Rect(x0 * pix.width, y0 * pix.height, x1 * pix.width, y1 * pix.height),
                              alpha=False)
    if max(pix.width, pix.height) > max_side:
        shrink = 0
        while max(pix.width, pix.height) >> shrink > max_side:
            shrink += 1
        pix.shrink(shrink)
    return pix.tobytes("jpeg", jpg_quality=88)


def _curated_source(con, data: Path, item: dict[str, Any], client) -> tuple[bytes, str, str] | None:
    """Raw bytes of a curated item, verified against its recorded hash → (raw, file label, PSI path)."""
    kind = item.get("kind", "frame")
    if kind == "frame":
        res = con.execute("SELECT file_name, file_version, size_bytes, path FROM resources WHERE inv_id = ? AND "
                          "file_name = ? ORDER BY file_version DESC LIMIT 1", [item["inv_id"], item["archive"]]).fetchone()
        if not res:
            return None
        zf, _rf = open_remote_zip(client, item["inv_id"], res[0], res[1], res[2])
        with zf:
            raw = zf.read(item["member"])
        ok = hashlib.sha256(raw).hexdigest() == item["member_sha256"]
        return (raw, f"{res[0]} :: {item['member']}", f"{res[3]} :: {item['member']}") if ok else None
    if kind == "pdf_figure":
        import pymupdf

        row = con.execute("SELECT dl.local_path, d.title FROM documents d JOIN document_resources r USING (doc_id) "
                          "JOIN downloads dl ON dl.resource_id = r.resource_id WHERE d.doc_id = ? LIMIT 1",
                          [item["doc_id"]]).fetchone()
        if not row or not (data / "psi" / row[0]).exists():
            return None
        raw = pymupdf.Pixmap(pymupdf.open(data / "psi" / row[0]), int(item["xref"])).tobytes("png")
        ok = hashlib.sha256(raw).hexdigest() == item["source_sha256"]
        return (raw, f"{row[1]} · p. {item['page']}", row[0]) if ok else None
    if kind == "insignia":
        manifest = (data / "psi" / "downloads.parquet").as_posix()  # live download manifest (the DB copy may lag)
        row = con.execute(f"SELECT local_path, path FROM read_parquet('{manifest}') WHERE file_name = ? LIMIT 1",
                          [item["file_name"]]).fetchone()
        if not row or not (data / "psi" / row[0]).exists():
            return None
        return (data / "psi" / row[0]).read_bytes(), item["file_name"], row[1]
    return None


def fetch_curated(data: Path, client=None) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Materialise the visually checked selections of config/media_curation.yaml into data/media/frames.
    An item whose source no longer matches its recorded hash is skipped (never shown unchecked)."""
    from ...psi.client import PsiClient
    from .common import CONFIG, load_yaml

    cur = load_yaml(CONFIG / "media_curation.yaml")
    client = client or PsiClient()
    con = duckdb.connect(str(data / "psi" / "inventory.duckdb"), read_only=True)
    out, skipped = [], []
    try:
        lic = dict(con.execute("SELECT inv_id, license_status FROM investigation_rights").fetchall())
        for item in cur.get("frames") or []:
            if investigation_withheld(lic.get(item["inv_id"])):
                skipped.append({"id": item["id"], "reason": "licence_withheld"})
                continue
            try:
                src = _curated_source(con, data, item, client)
                if src is None:
                    skipped.append({"id": item["id"], "reason": "source_missing_or_changed"})
                    continue
                raw, label, psi_path = src
                body = to_jpeg(raw, crop=item.get("crop"))
            except Exception as exc:  # noqa: BLE001 - network/format errors skip one item, reported below
                skipped.append({"id": item["id"], "reason": type(exc).__name__})
                continue
            dest = data / "media" / "frames" / f"{item['id']}.jpg"
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(body)
            out.append({"media_id": hashlib.sha256(body).hexdigest()[:16], "inv_id": item["inv_id"], "file_name": label,
                        "caption": item["caption"], "sha256": hashlib.sha256(body).hexdigest(), "size_bytes": len(body),
                        "local_path": dest.relative_to(data).as_posix(), "psi_path": psi_path,
                        "license_status": lic.get(item["inv_id"]), "source": "NASA PSI",
                        "kind": item.get("kind", "frame"), "checked": item.get("checked"), "curation": cur.get("version")})
    finally:
        con.close()
    return out, skipped


def load_manifest(data: Path) -> dict[str, Any]:
    path = manifest_path(data)
    if not path.exists():
        return {"version": MANIFEST_VERSION, "images": [], "missing": True}
    return json.loads(path.read_text(encoding="utf-8"))


def images(data: Path, con, inv_id: str | None = None) -> list[dict[str, Any]]:
    """Images whose investigation is still publishable in the served database (re-checked at request time)."""
    lic = dict(con.execute("SELECT inv_id, license_status FROM investigation_rights").fetchall())
    order = {"representative": 0, "frame": 1, "pdf_figure": 2, "insignia": 3}
    out = []
    for m in load_manifest(data)["images"]:
        kind = m.get("kind", "representative")
        if inv_id and m["inv_id"] != inv_id:
            continue
        # logos are only shown when explicitly curated as a last-resort project insignia (never agency logos)
        if investigation_withheld(lic.get(m["inv_id"])) or (is_logo(m["file_name"]) and kind != "insignia"):
            continue
        out.append({k: m[k] for k in ("media_id", "inv_id", "caption", "file_name", "size_bytes", "source")}
                   | {"url": f"/media/file/{m['media_id']}", "license": "CC0 (NASA PSI)", "kind": kind})
    return sorted(out, key=lambda i: (i["inv_id"], order.get(i["kind"], 9)))


def image_file(data: Path, con, media_id: str) -> Path | None:
    for m in load_manifest(data)["images"]:
        if m["media_id"] == media_id and any(i["media_id"] == media_id for i in images(data, con, m["inv_id"])):
            # an insignia shared by several investigations is one file listed once per investigation
            p = (data / m["local_path"]).resolve()
            if data.resolve() in p.parents and p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest() == m["sha256"]:
                return p
    return None


def _kind(file_name: str) -> str | None:
    name = file_name.lower()
    if name.endswith("tp.txt"):
        return "event_log"
    ext = name.rsplit(".", 1)[-1]
    return next((k for k, exts in VISUAL.items() if ext in exts), None)


def visual_inventory(con, inv_id: str) -> dict[str, Any]:
    """What visual evidence PSI lists for an investigation, from inventory metadata only."""
    rows = con.execute("SELECT file_name, size_bytes FROM resources WHERE inv_id = ? AND coalesce(visible, true) "
                       "AND NOT coalesce(restricted, false)", [inv_id]).fetchall()
    summary: dict[str, dict[str, Any]] = {}
    for name, size in rows:
        k = _kind(name or "")
        if k:
            s = summary.setdefault(k, {"files": 0, "bytes": 0})
            s["files"] += 1
            s["bytes"] += int(size or 0)
    linked = con.execute("""
        SELECT l.trial_key, r.file_name, r.size_bytes FROM trial_resource_links l
        JOIN resources r ON r.resource_id = l.resource_id WHERE l.inv_id = ?""", [inv_id]).fetchall()
    per_trial: dict[str, dict[str, int]] = {}
    for key, name, _size in linked:
        k = _kind(name or "")
        if k:
            per_trial.setdefault(key, {}).setdefault(k, 0)
            per_trial[key][k] += 1
    return {"inv_id": inv_id, "summary": summary, "trials_with_visual_evidence": len(per_trial),
            "per_trial": per_trial,
            "note": ("Inventario por metadatos: PSI lista estos archivos; no se descargan ni se analizan. Los videos e "
                     "imágenes de ensayos se obtienen desde el repositorio de PSI.")}


def trial_visual(con, trial_key: str) -> list[dict[str, Any]]:
    rows = con.execute("""
        SELECT r.file_name, r.size_bytes, r.path FROM trial_resource_links l
        JOIN resources r ON r.resource_id = l.resource_id WHERE l.trial_key = ? ORDER BY r.file_name""",
                       [trial_key]).fetchall()
    return [{"kind": _kind(n or ""), "file_name": n, "size_bytes": s, "psi_path": p} for n, s, p in rows if _kind(n or "")]
