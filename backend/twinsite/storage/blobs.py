"""Content-addressed filesystem artifact store (source binaries, committed artifacts).

Object keys are private and relative to a controlled root; public APIs expose
only `sha256:<hex>` artifact IDs, never paths.
"""
import hashlib
import os
from pathlib import Path
import tempfile


class BlobStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def object_key(sha256):
        if len(sha256) != 64 or any(c not in '0123456789abcdef' for c in sha256):
            raise ValueError('invalid sha256')
        return f'sha256/{sha256[:2]}/{sha256}'

    def _path(self, sha256):
        path = (self.root / self.object_key(sha256)).resolve()
        if not path.is_relative_to(self.root.resolve()):
            raise ValueError('object key escapes artifact root')
        return path

    def put(self, data: bytes):
        sha = hashlib.sha256(data).hexdigest()
        path = self._path(sha)
        if path.is_file() and path.stat().st_size == len(data):
            return sha
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise
        return sha

    def get(self, sha256):
        data = self._path(sha256).read_bytes()
        if hashlib.sha256(data).hexdigest() != sha256:
            raise IOError('artifact bytes changed since commit')
        return data

    def exists(self, sha256):
        return self._path(sha256).is_file()
