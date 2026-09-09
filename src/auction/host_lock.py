"""OS-released lock shared by scheduler, watchdog and sync retry."""

from contextlib import contextmanager


class AlreadyRunning(RuntimeError):
    pass


@contextmanager
def auction_lock(root, day):
    path = root / "data/auction_runs" / f"{day}.host.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    stream = path.open("a+b")
    if path.stat().st_size == 0:
        stream.write(b"0")
        stream.flush()
    stream.seek(0)
    acquired = False
    try:
        try:
            try:
                import msvcrt
            except ImportError:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            else:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        except (BlockingIOError, PermissionError) as exc:
            raise AlreadyRunning(str(path)) from exc
        acquired = True
        yield
    finally:
        if acquired:
            stream.seek(0)
            try:
                import msvcrt
            except ImportError:
                import fcntl

                fcntl.flock(stream, fcntl.LOCK_UN)
            else:
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        stream.close()
