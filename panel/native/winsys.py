#
# MCServer by Derpchees - datos del sistema en Windows (sin /proc)
#
# Memoria, CPU, tiempo encendido y procesos con las funciones de Windows
# (ctypes, sin librerias extra). Los "job objects" limitan la memoria y la
# CPU de un servidor como lo hace Docker en Linux.
#

import ctypes
from ctypes import wintypes

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

STILL_ACTIVE = 259
PROCESS_TERMINATE = 0x0001
PROCESS_SET_QUOTA = 0x0100
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000

JOB_EXTENDED_LIMITS = 9
JOB_CPU_RATE = 15
LIMIT_JOB_MEMORY = 0x0200
LIMIT_BREAKAWAY_OK = 0x0800
LIMIT_KILL_ON_JOB_CLOSE = 0x2000
CPU_RATE_ENABLE = 0x1
CPU_RATE_HARD_CAP = 0x4


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in
                ("ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                 "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_longlong), ("PerJobUserTimeLimit", ctypes.c_longlong),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION), ("IoInfo", IO_COUNTERS),
                ("ProcessMemoryLimit", ctypes.c_size_t), ("JobMemoryLimit", ctypes.c_size_t),
                ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t)]


class JOBOBJECT_CPU_RATE_CONTROL_INFORMATION(ctypes.Structure):
    _fields_ = [("ControlFlags", wintypes.DWORD), ("CpuRate", wintypes.DWORD)]


kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
kernel32.TerminateProcess.argtypes = (wintypes.HANDLE, wintypes.UINT)
kernel32.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
kernel32.GetSystemTimes.argtypes = (ctypes.POINTER(wintypes.FILETIME),) * 3
kernel32.GetTickCount64.restype = ctypes.c_ulonglong
kernel32.K32GetProcessMemoryInfo.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
                                             wintypes.DWORD)
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)


def filetime(ft):
    return (ft.dwHighDateTime << 32) | ft.dwLowDateTime


def memory():
    # (total, en uso) en bytes
    status = MEMORYSTATUSEX()
    status.dwLength = ctypes.sizeof(status)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return status.ullTotalPhys, status.ullTotalPhys - status.ullAvailPhys


def cpu_times():
    # (total, inactivo) en unidades de 100 ns; el tiempo de kernel incluye el inactivo
    idle, kernel, user = wintypes.FILETIME(), wintypes.FILETIME(), wintypes.FILETIME()
    kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
    return filetime(kernel) + filetime(user), filetime(idle)


def uptime():
    return int(kernel32.GetTickCount64() // 1000)


class Process:
    # Manija de un proceso por su PID (None si ya no existe)

    def __init__(self, pid, access=PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE):
        self.handle = kernel32.OpenProcess(access, False, int(pid)) if pid else None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        if self.handle:
            kernel32.CloseHandle(self.handle)

    def times(self):
        # (creado, cpu en segundos)
        created, ended, kern, user = (wintypes.FILETIME() for _ in range(4))

        if not kernel32.GetProcessTimes(self.handle, ctypes.byref(created), ctypes.byref(ended),
                                        ctypes.byref(kern), ctypes.byref(user)):
            return None, None

        return filetime(created), (filetime(kern) + filetime(user)) / 1e7


def pid_alive(pid, created=None):
    # created evita confundirlo con otro proceso que reuso el mismo PID
    with Process(pid) as proc:
        if not proc.handle:
            return False

        code = wintypes.DWORD()

        if not kernel32.GetExitCodeProcess(proc.handle, ctypes.byref(code)) or code.value != STILL_ACTIVE:
            return False

        return created is None or proc.times()[0] == created


def created_at(pid):
    with Process(pid) as proc:
        return proc.times()[0] if proc.handle else None


def usage(pid):
    # (segundos de CPU usados, memoria en uso) o None
    with Process(pid) as proc:
        if not proc.handle:
            return None

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(counters)
        kernel32.K32GetProcessMemoryInfo(proc.handle, ctypes.byref(counters), counters.cb)
        return proc.times()[1] or 0.0, counters.WorkingSetSize


def kill(pid):
    with Process(pid, PROCESS_TERMINATE) as proc:
        return bool(proc.handle) and bool(kernel32.TerminateProcess(proc.handle, 1))


def limit_job(pid, memory_bytes=0, cpu_cores=0, total_cores=1):
    # Mete el proceso en un "job": se cierra con quien lo creo y, si se
    # pide, tiene tope de memoria y de CPU. Devuelve la manija (hay que
    # guardarla: al cerrarse termina el proceso).
    job = kernel32.CreateJobObjectW(None, None)

    if not job:
        return None

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = LIMIT_KILL_ON_JOB_CLOSE | LIMIT_BREAKAWAY_OK

    if memory_bytes:
        info.BasicLimitInformation.LimitFlags |= LIMIT_JOB_MEMORY
        info.JobMemoryLimit = int(memory_bytes)

    kernel32.SetInformationJobObject(job, JOB_EXTENDED_LIMITS, ctypes.byref(info), ctypes.sizeof(info))

    if cpu_cores and cpu_cores < total_cores:
        rate = JOBOBJECT_CPU_RATE_CONTROL_INFORMATION()
        rate.ControlFlags = CPU_RATE_ENABLE | CPU_RATE_HARD_CAP
        rate.CpuRate = max(1, min(10000, int(cpu_cores * 10000 / total_cores)))
        kernel32.SetInformationJobObject(job, JOB_CPU_RATE, ctypes.byref(rate), ctypes.sizeof(rate))

    with Process(pid, PROCESS_SET_QUOTA | PROCESS_TERMINATE) as proc:
        if not proc.handle or not kernel32.AssignProcessToJobObject(job, proc.handle):
            kernel32.CloseHandle(job)
            return None

    return job
