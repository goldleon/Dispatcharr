# connect/handlers/script.py
import os
import select as _select
import signal as _signal
import stat
import time
from django.conf import settings
from .base import IntegrationHandler


import subprocess

def _run_script(path, env, timeout):
    try:
        res = subprocess.run(
            [path],
            env=env,
            capture_output=True,
            timeout=timeout,
            text=True,
            errors='replace'
        )
        return res.returncode, res.stdout, res.stderr
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"Script exceeded {timeout}s") from e


def _is_path_allowed(real_path: str) -> bool:
    # Ensure path is within one of the allowed directories
    for base in getattr(settings, "CONNECT_ALLOWED_SCRIPT_DIRS", []):
        base_abs = os.path.abspath(base) + os.sep
        if real_path.startswith(base_abs):
            return True
    return False


class ScriptHandler(IntegrationHandler):
    def execute(self):
        raw_path = self.integration.config.get("path")
        if not raw_path:
            raise ValueError("Missing 'path' in integration config")

        # Resolve and validate path
        real_path = os.path.abspath(os.path.realpath(raw_path))

        if not os.path.exists(real_path):
            raise FileNotFoundError(f"Script not found: {real_path}")

        if not _is_path_allowed(real_path):
            raise PermissionError(
                f"Script path '{real_path}' not within allowed directories: "
                f"{getattr(settings, 'CONNECT_ALLOWED_SCRIPT_DIRS', [])}"
            )

        if getattr(settings, "CONNECT_SCRIPT_REQUIRE_EXECUTABLE", True):
            if not os.access(real_path, os.X_OK):
                raise PermissionError(f"Script is not executable: {real_path}")

        if getattr(settings, "CONNECT_SCRIPT_DISALLOW_WORLD_WRITABLE", True):
            st = os.stat(real_path)
            if st.st_mode & stat.S_IWOTH:
                raise PermissionError(
                    f"Refusing to execute world-writable script: {real_path}"
                )

        # Build a sanitized minimal environment; avoid inheriting secrets
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        }
        for key, value in (self.payload or {}).items():
            env_key = f"DISPATCHARR_{str(key).upper()}"
            env[env_key] = "" if value is None else str(value)

        # Run with a timeout to prevent hanging scripts
        timeout = getattr(settings, "CONNECT_SCRIPT_TIMEOUT", 10)
        max_out = getattr(settings, "CONNECT_SCRIPT_MAX_OUTPUT", 65536)

        rc, stdout, stderr = _run_script(real_path, env, timeout)

        # Truncate outputs to avoid excessive memory/logging
        if len(stdout) > max_out:
            stdout = stdout[:max_out] + "... [truncated]"
        if len(stderr) > max_out:
            stderr = stderr[:max_out] + "... [truncated]"

        return {
            "exit_code": rc,
            "stdout": stdout,
            "stderr": stderr,
            "success": rc == 0,
        }
