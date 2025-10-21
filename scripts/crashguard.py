import faulthandler, signal, os, sys, atexit, platform

LOG_PATH = os.environ.get("CRASHGUARD_LOG", "crashguard.log")
_f = open(LOG_PATH, "w")

# 1) Always dump all thread stacks on fatal signals
faulthandler.enable(file=_f, all_threads=True)

# 2) Register handlers for native faults (Python will dump stacks before dying)
_SIGS = [signal.SIGSEGV, signal.SIGFPE, signal.SIGABRT, getattr(signal, "SIGBUS", None), signal.SIGILL]
for sig in filter(None, _SIGS):
    try:
        faulthandler.register(sig, file=_f, all_threads=True, chain=True)
    except Exception:
        pass  # some platforms may refuse certain signals

# 3) On-demand dump: `kill -USR1 <pid>` to snapshot all thread stacks
try:
    faulthandler.register(signal.SIGUSR1, file=_f, all_threads=True, chain=True)
except Exception:
    pass

# 4) Optional watchdog: periodic stack dumps if the process stalls
#    export CRASHGUARD_WATCHDOG=60  (seconds) to enable; 0 disables
try:
    timeout = float(os.environ.get("CRASHGUARD_WATCHDOG", "0") or 0)
    if timeout > 0:
        faulthandler.dump_traceback_later(timeout, file=_f, repeat=True)
except Exception:
    pass

def annotate_run_context():
    print("=== CrashGuard Runtime Context ===", file=_f)
    print(f"PID: {os.getpid()}", file=_f)
    print(f"Exec: {sys.executable}", file=_f)
    print(f"Python: {sys.version}", file=_f)
    print(f"Platform: {platform.platform()}", file=_f)
    print(f"CWD: {os.getcwd()}", file=_f)
    # List C extensions (likely segfault culprits)
    ce = []
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None)
        if path and path.endswith((".so", ".pyd", ".dylib")):
            ce.append((name, path))
    ce.sort()
    print("Loaded C extensions:", file=_f)
    for name, path in ce:
        print(f" - {name}: {path}", file=_f)
    _f.flush()

annotate_run_context()
atexit.register(_f.flush)
