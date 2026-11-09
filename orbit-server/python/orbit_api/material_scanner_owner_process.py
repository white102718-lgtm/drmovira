"""Windows自有进程适配器；未显式调用spawn不会创建进程，缺Job支持即失败关闭。"""

import ctypes
import os
import socket
import subprocess
import time
from dataclasses import dataclass

import psutil

from orbit_api.material_scanner_owner_definition import check_budget, owner_error


class WindowsKillJob:
    """只操作本实例创建的Job句柄，不通过端口、进程名或外部PID寻找关闭对象。"""

    def __init__(self):
        if os.name != "nt":
            raise owner_error("SCANNER_OWNER_JOB_UNAVAILABLE")
        from ctypes import wintypes as w

        class Basic(ctypes.Structure):
            _fields_ = [
                ("process_time", ctypes.c_int64),
                ("job_time", ctypes.c_int64),
                ("flags", w.DWORD),
                ("minimum", ctypes.c_size_t),
                ("maximum", ctypes.c_size_t),
                ("active", w.DWORD),
                ("affinity", ctypes.c_size_t),
                ("priority", w.DWORD),
                ("scheduling", w.DWORD),
            ]

        class Io(ctypes.Structure):
            _fields_ = [
                (name, ctypes.c_uint64)
                for name in (
                    "read_operations",
                    "write_operations",
                    "other_operations",
                    "read_bytes",
                    "write_bytes",
                    "other_bytes",
                )
            ]

        class Extended(ctypes.Structure):
            _fields_ = [
                ("basic", Basic),
                ("io", Io),
                ("process_memory", ctypes.c_size_t),
                ("job_memory", ctypes.c_size_t),
                ("peak_process", ctypes.c_size_t),
                ("peak_job", ctypes.c_size_t),
            ]

        try:
            self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            self.native = ctypes.WinDLL("ntdll", use_last_error=True)
            self.kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, w.LPCWSTR]
            self.kernel.CreateJobObjectW.restype = w.HANDLE
            self.kernel.SetInformationJobObject.argtypes = [
                w.HANDLE,
                ctypes.c_int,
                ctypes.c_void_p,
                w.DWORD,
            ]
            self.kernel.SetInformationJobObject.restype = w.BOOL
            self.kernel.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            self.kernel.AssignProcessToJobObject.restype = w.BOOL
            self.kernel.TerminateProcess.argtypes = [w.HANDLE, w.UINT]
            self.kernel.TerminateProcess.restype = w.BOOL
            self.kernel.CloseHandle.argtypes = [w.HANDLE]
            self.kernel.CloseHandle.restype = w.BOOL
            self.native.NtResumeProcess.argtypes = [w.HANDLE]
            self.native.NtResumeProcess.restype = w.LONG
            self.extended = Extended
        except (OSError, AttributeError):
            raise owner_error("SCANNER_OWNER_JOB_UNAVAILABLE") from None

    def create(self):
        handle = self.kernel.CreateJobObjectW(None, None)
        if not handle:
            raise owner_error("SCANNER_OWNER_JOB_UNAVAILABLE")
        limits = self.extended()
        limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not self.kernel.SetInformationJobObject(
            handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)
        ):
            self.kernel.CloseHandle(handle)
            raise owner_error("SCANNER_OWNER_JOB_UNAVAILABLE")
        return handle

    def assign(self, job, process_handle):
        if not self.kernel.AssignProcessToJobObject(job, process_handle):
            raise owner_error("SCANNER_OWNER_JOB_UNAVAILABLE")

    def resume(self, process_handle):
        # 使用Popen保留的原生进程句柄，避免按已重用的数值PID恢复另一进程。
        if self.native.NtResumeProcess(process_handle) < 0:
            raise owner_error("SCANNER_OWNER_START_FAILED")

    def terminate_unassigned(self, process_handle):
        if not self.kernel.TerminateProcess(process_handle, 1):
            raise owner_error("SCANNER_OWNER_CLOSE_FAILED")

    def close(self, job):
        if not self.kernel.CloseHandle(job):
            raise owner_error("SCANNER_OWNER_CLOSE_FAILED")


@dataclass(repr=False)
class OwnedWindowsProcess:
    process: object
    job: object
    pid: int
    created_at_us: int
    closed: bool = False
    job_closed: bool = False


class WindowsOwnerProcessAdapter:
    """纯测可注入kernel/process/identity/socket；默认仅支持Windows Job所有权。"""

    def __init__(self, *, kernel=None, popen=None, identity=None, socket_factory=None):
        self._kernel = kernel
        self._popen = popen or subprocess.Popen
        self._identity = identity or self._process_identity
        self._socket_factory = socket_factory or socket.socket
        self._failed = []

    def require_job_support(self):
        if self._failed:
            raise owner_error("SCANNER_OWNER_CLEANUP_PENDING")
        if self._kernel is None:
            self._kernel = WindowsKillJob()
        return self._kernel

    @staticmethod
    def _process_identity(pid):
        process = psutil.Process(pid)
        return process.pid, round(process.create_time() * 1_000_000)

    def port_available(self, port, deadline):
        check_budget(deadline)
        try:
            with self._socket_factory(socket.AF_INET, socket.SOCK_STREAM) as connection:
                connection.settimeout(max(0.001, deadline - time.monotonic()))
                if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                connection.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False

    def spawn(self, executable, config_file, owned_root, deadline):
        check_budget(deadline)
        kernel = self.require_job_support()
        job, process = kernel.create(), None
        try:
            # 先挂起，成功加入kill-on-close Job后才恢复。标准流丢弃，不能无界缓存输出。
            process = self._popen(
                [str(executable), "--config-file=" + str(config_file)],
                cwd=str(owned_root),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
                shell=False,
                creationflags=0x08000000 | 0x00000004,
            )  # NO_WINDOW | CREATE_SUSPENDED
            pid, born = self._identity(process.pid)
            if pid != process.pid or type(born) is not int or born <= 0:
                raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
            kernel.assign(job, int(process._handle))
            check_budget(deadline)
            kernel.resume(int(process._handle))
            return OwnedWindowsProcess(process, job, pid, born)
        except BaseException:
            # 失败清理也保留原生句柄；清理未知不得丢弃句柄或允许下一次启动。
            failed = OwnedWindowsProcess(process, job, process.pid if process else 0, 0)
            try:
                self._abort_owned(failed, deadline)
            except BaseException:
                self._failed.append(failed)
            raise

    def _abort_owned(self, owned, deadline):
        try:
            if owned.process is not None and owned.process.poll() is None:
                self._kernel.terminate_unassigned(int(owned.process._handle))
        finally:
            if not owned.job_closed:
                self._kernel.close(owned.job)
                owned.job_closed = True
        if owned.process is not None:
            owned.process.wait(timeout=max(0.001, deadline - time.monotonic()))
        check_budget(deadline)
        owned.closed = True

    def cleanup_failed(self, deadline):
        for owned in list(self._failed):
            self._abort_owned(owned, deadline)
            self._failed.remove(owned)

    def alive(self, owned):
        if owned.closed or owned.job_closed or owned.process.poll() is not None:
            return False
        try:
            return self._identity(owned.pid) == (owned.pid, owned.created_at_us)
        except (OSError, psutil.Error):
            return False

    def close_owned(self, owned, expected, deadline):
        if owned.closed:
            return
        identity_matches = expected == (owned.pid, owned.created_at_us)
        try:
            identity_matches = identity_matches and self._identity(owned.pid) == expected
        except (OSError, psutil.Error):
            identity_matches = False
        # Job句柄只含自己曾创建的进程对象；即使数值PID已复用也不会关闭新的外部对象。
        if not owned.job_closed:
            self._kernel.close(owned.job)
            owned.job_closed = True
        try:
            owned.process.wait(timeout=max(0.001, deadline - time.monotonic()))
        except (TimeoutError, subprocess.TimeoutExpired):
            raise owner_error("SCANNER_OWNER_CLOSE_FAILED") from None
        check_budget(deadline)
        owned.closed = True
        if not identity_matches:
            raise owner_error("SCANNER_OWNER_IDENTITY_CHANGED")
