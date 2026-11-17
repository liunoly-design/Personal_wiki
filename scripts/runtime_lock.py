"""An advisory lock lives exactly as long as the parent command's stdin pipe."""
import fcntl, os, sys
fd = os.open(sys.argv[1], os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
try:
    mode = fcntl.LOCK_SH if sys.argv[2] == 'shared' else fcntl.LOCK_EX
    fcntl.flock(fd, mode | fcntl.LOCK_NB)
except BlockingIOError:
    print('busy', flush=True)
    sys.exit(2)
print('ready', flush=True)
sys.stdin.buffer.read()
os.close(fd)
