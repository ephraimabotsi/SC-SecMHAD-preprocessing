from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path

import yaml

LOG = logging.getLogger("srbh_prep")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S")


def load_config(path: str | os.PathLike, root: str | os.PathLike | None = None) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError("Configuration file not found: %s" % path)
    with open(path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    root = Path(root) if root else path.resolve().parent.parent
    cfg["paths"] = {k: str(Path(v) if Path(v).is_absolute() else root / v) for k, v in cfg["paths"].items()}
    cfg["root"] = str(root)
    return cfg


def md5sum(path: str | os.PathLike, chunk: int = 1 << 20) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def text_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def atomic_write(path: str | os.PathLike, write) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".part")
    write(tmp)
    os.replace(tmp, path)


def write_csv(df, path, **kw) -> None:
    atomic_write(path, lambda p: df.to_csv(p, index=False, lineterminator="\n", **kw))


def write_json(obj, path) -> None:
    def _w(p):
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    atomic_write(path, _w)
