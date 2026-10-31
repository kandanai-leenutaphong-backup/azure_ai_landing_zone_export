from __future__ import annotations

import contextlib
import ctypes
import errno
import json
import resource
import sys

sys.path.insert(0, "/runtime")
from _local_query import SQLiteReader


class ToolContext:
    def __init__(self, scope):
        self.scope = scope
        self.query_count = 0

    def query(self, sql, parameters=None, *, max_rows=200):
        if self.query_count >= 4:
            raise ValueError("At most four queries per Python tool")
        if not isinstance(sql, str) or len(sql) > 12_000 or type(max_rows) is not int or not 1 <= max_rows <= 200:
            raise ValueError("Query bounds: 12000 characters and 1 to 200 rows")
        self.query_count += 1
        result = SQLiteReader("/case.sqlite").query(sql, parameters, max_rows=max_rows,
                                                    timeout_seconds=2, tables={"evidence", "training_profile"})
        result["rows"] = [dict(zip(result["columns"], row)) for row in result["rows"]]
        if len(json.dumps(result)) > 20_000:
            raise ValueError("Query result exceeds 20 KB; aggregate or reduce rows")
        return result


def limit_process():
    resource.setrlimit(resource.RLIMIT_AS, (256 * 1024 * 1024, 256 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (65_536, 65_536))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    policy = library.seccomp_init(0x7FFF0000)
    if not policy:
        raise RuntimeError("Could not create Python syscall policy")
    try:
        for name in ("clone", "clone3", "fork", "vfork", "execve", "execveat", "socket", "socketpair",
                     "unshare", "setns", "mount", "ptrace", "process_vm_readv", "process_vm_writev",
                     "setrlimit", "prlimit64"):
            syscall = library.seccomp_syscall_resolve_name(name.encode())
            if syscall >= 0 and library.seccomp_rule_add(policy, 0x00050000 | errno.EPERM, syscall, 0) != 0:
                raise RuntimeError("Could not restrict Python syscall")
        if library.seccomp_load(policy) != 0:
            raise RuntimeError("Could not activate Python syscall policy")
    finally:
        library.seccomp_release(policy)


def main():
    payload = json.load(sys.stdin)
    try:
        limit_process()
        context = ToolContext(payload.get("scope", {}))
        namespace = {"__name__": "agent_tool", "ToolContext": ToolContext}
        with contextlib.redirect_stdout(sys.stderr):
            exec(compile(payload["code"], "agent_tool.py", "exec"), namespace)
            result = namespace["run"](context)
        if not isinstance(result, dict):
            raise ValueError("run(ctx) must return a JSON object")
        if len(json.dumps(result, allow_nan=False)) > 20_000:
            raise ValueError("Python tool output exceeds 20 KB")
        print(json.dumps({"ok": True, "result": {"kind": "optimization_tool_result", "historical_replay": True,
                                               "query_count": context.query_count, "data": result}}, allow_nan=False))
    except Exception as error:
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {str(error)[:400]}"}))


if __name__ == "__main__":
    main()