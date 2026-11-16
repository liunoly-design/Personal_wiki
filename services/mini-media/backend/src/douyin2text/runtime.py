"""Runtime locations are shared by API, pipeline and artifact storage."""
import json
import hashlib
import os
from pathlib import Path

from .providers.registry import effective_config

DATA = Path(os.environ.get("DOUYIN2TEXT_DATA_DIR", str(Path.home()/".local/share/personal-wiki-media"))).expanduser().resolve()
CONFIG_PATH = Path(os.environ.get("DOUYIN2TEXT_CONFIG", str(DATA / "state/config.json")))


def load_config():
    config=effective_config(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    source_root=Path(__file__).resolve().parents[3]
    if config.get('translation',{}).get('enabled'):config['translation']['script']=str(source_root/'shared/translate_segments_mlx.py')
    fingerprint=hashlib.sha256()
    for path in sorted(source_root.rglob('*.py')):
        fingerprint.update(path.relative_to(source_root).as_posix().encode());fingerprint.update(path.read_bytes())
    for key in ('asr_fingerprint','output_fingerprint'):
        config[key]=hashlib.sha256((config[key]+fingerprint.hexdigest()).encode()).hexdigest()
    return config
