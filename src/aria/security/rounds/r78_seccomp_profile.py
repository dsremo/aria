"""R78 — seccomp-bpf syscall profile generator (Linux).

Threat: an RCE inside the Python worker can call any syscall the
container allows — ``ptrace``, ``mount``, ``unshare``, ``modify_ldt``
etc.  Default Docker seccomp profile is permissive enough.  Custom
profiles narrow the surface massively.  Banks routinely run service
containers with a seccomp profile that allows only ~ 80 of the ~ 350
Linux syscalls.

Defence: a generator that emits a JSON seccomp profile (Docker / podman
compatible) from a known-good allow-list for ARIA's runtime.  Tested
allow-list mirrors the ``read``/``write``/``mmap``/``futex``/``sendto``/
``recvfrom`` core that aiohttp + numpy + sqlite need; everything else
returns ``EPERM``.
"""

from __future__ import annotations

import json
from typing import Dict, List

from aria.security.plugins import DefencePlugin, register


_DEFAULT_ALLOWED = sorted({
    # File / IO
    "read", "write", "readv", "writev", "pread64", "pwrite64",
    "open", "openat", "openat2", "close", "lseek", "stat", "lstat",
    "fstat", "newfstatat", "statx", "access", "faccessat", "faccessat2",
    "rename", "renameat", "renameat2", "unlink", "unlinkat",
    "mkdir", "mkdirat", "rmdir", "fchmod", "chmod", "fchmodat",
    "fchown", "chown", "fchownat", "umask", "dup", "dup2", "dup3",
    "pipe", "pipe2", "fcntl", "fadvise64", "ftruncate",
    # Memory
    "mmap", "munmap", "mprotect", "brk", "madvise", "mremap",
    "mlock", "munlock", "mlock2",
    # Process / thread
    "clone", "clone3", "fork", "vfork", "execve", "execveat", "exit",
    "exit_group", "wait4", "waitid",
    "getpid", "getppid", "gettid", "getuid", "geteuid", "getgid",
    "getegid", "setuid", "setgid", "setreuid", "setregid", "setpgid",
    "getpgid", "setsid", "getsid", "getrusage",
    "rt_sigaction", "rt_sigprocmask", "rt_sigreturn", "rt_sigpending",
    "rt_sigsuspend", "rt_sigtimedwait", "kill", "tgkill", "tkill",
    # Time / ID
    "gettimeofday", "clock_gettime", "clock_getres", "clock_nanosleep",
    "nanosleep", "time", "times",
    "set_robust_list", "get_robust_list",
    "set_tid_address", "set_thread_area", "arch_prctl",
    # Socket / network
    "socket", "socketpair", "bind", "listen", "accept", "accept4",
    "connect", "shutdown", "sendto", "recvfrom", "sendmsg", "recvmsg",
    "send", "recv", "getsockname", "getpeername", "setsockopt", "getsockopt",
    # epoll / poll / select
    "poll", "ppoll", "select", "pselect6",
    "epoll_create", "epoll_create1", "epoll_ctl", "epoll_wait", "epoll_pwait",
    "eventfd", "eventfd2", "signalfd", "signalfd4", "timerfd_create",
    "timerfd_settime", "timerfd_gettime",
    # Misc
    "getrandom", "uname", "getcwd", "chdir", "fchdir",
    "futex", "membarrier", "rseq",
    "prlimit64", "getrlimit", "setrlimit", "sched_yield", "sched_getaffinity",
    "sched_setaffinity", "ioctl",
})


def generate_docker_seccomp_profile(*, extra_allow: List[str] | None = None) -> Dict:
    allow = sorted(set(_DEFAULT_ALLOWED) | set(extra_allow or []))
    return {
        "defaultAction": "SCMP_ACT_ERRNO",
        "defaultErrno": "EPERM",
        "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_X86", "SCMP_ARCH_X32",
                          "SCMP_ARCH_AARCH64"],
        "syscalls": [
            {"names": allow, "action": "SCMP_ACT_ALLOW"},
        ],
    }


def write_profile(path: str, *, extra_allow: List[str] | None = None) -> str:
    profile = generate_docker_seccomp_profile(extra_allow=extra_allow)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2)
    return path


register(DefencePlugin(
    round_id="R78",
    name="seccomp_profile",
    description="Generate a tight Docker/podman seccomp JSON profile.",
))
