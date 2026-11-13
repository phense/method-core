"""Bound subprocesses and cancel their process groups before returning."""
from __future__ import annotations

import os
import signal
import subprocess


def stop_group(process: subprocess.Popen) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.communicate(timeout=2)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # Descendants may close their pipes or ignore SIGTERM after the wrapper
        # exits. Kill the group even when communicate returned successfully.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()


def run_bounded(command, *, cwd, env=None, timeout, text=False):
    process = None
    previous = {}
    def cancel(signum, frame):
        if process is not None:
            stop_group(process)
        raise SystemExit(128 + signum)
    # Install handlers before spawning: an outer release timeout must propagate
    # through a clean-install wrapper to its separately grouped native host.
    for signum in (signal.SIGTERM, signal.SIGINT):
        previous[signum] = signal.signal(signum, cancel)
    try:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=text, start_new_session=True)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_group(process)
            raise
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
