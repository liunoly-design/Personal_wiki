#!/usr/bin/env python3
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print('busy', flush=True)
    sys.exit(2)
print('ready', flush=True)
sys.stdin.buffer.read()
os.close(fd)
