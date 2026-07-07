"""Archive helpers for sandbox file transfer."""

import io
from pathlib import Path
import tarfile


def tar_directory(source: Path) -> bytes:
    """Create a tar archive containing the contents of ``source``."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        for path in sorted(source.rglob('*')):
            if path.is_symlink():
                continue
            arcname = path.relative_to(source).as_posix()
            tar.add(path, arcname=arcname, recursive=False)
    stream.seek(0)
    return stream.getvalue()


def tar_file(name: str, data: bytes) -> bytes:
    """Create a tar archive containing a single file."""
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as tar:
        tarinfo = tarfile.TarInfo(name=name)
        tarinfo.size = len(data)
        tar.addfile(tarinfo, io.BytesIO(data))
    stream.seek(0)
    return stream.getvalue()
