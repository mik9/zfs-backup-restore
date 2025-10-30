from dataclasses import dataclass
from typing import Optional

@dataclass
class Compressor:
    """Defines the properties and commands for a compression tool."""
    name: str
    compress_cmd: str
    decompress_cmd: str
    extension: str

COMPRESSORS = [
    Compressor(name='gzip', compress_cmd='gzip -c', decompress_cmd='gzip -d', extension='gz'),
    Compressor(name='pigz', compress_cmd='pigz -c', decompress_cmd='pigz -d', extension='gz'),
    Compressor(name='zstd', compress_cmd='zstd -T0', decompress_cmd='zstd -d', extension='zst'),
]

DEFAULT_COMPRESSOR = 'pigz'

_by_name = {c.name: c for c in COMPRESSORS}
_by_extension = {c.extension: c for c in COMPRESSORS}

def get_compressor_by_name(name: str) -> Compressor:
    """Get a compressor by its name, falling back to the default."""
    return _by_name.get(name, _by_name[DEFAULT_COMPRESSOR])

def get_compressor_by_filename(filename: str) -> Optional[Compressor]:
    """Get a compressor by the file extension in a filename."""
    for ext, compressor in _by_extension.items():
        if filename.endswith(f'.{ext}'):
            return compressor
    return None
