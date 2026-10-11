"""检测 CPU 型号信息（跨平台，无需第三方库即可运行）。"""

import platform
import os
import re


def get_cpu_name() -> str:
    """不依赖第三方库，获取 CPU 型号名称。"""
    system = platform.system()

    # 1) 大多数 Linux 上的 /proc/cpuinfo
    if system == "Linux":
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    if line.lower().startswith("model name"):
                        return line.split(":", 1)[1].strip()
        except OSError:
            pass

    # 2) macOS 用 sysctl
    if system == "Darwin":
        try:
            import subprocess
            out = subprocess.check_output(
                ["sysctl", "-n", "machdep.cpu.brand_string"], text=True
            )
            return out.strip()
        except Exception:
            pass

    # 3) Windows 用注册表
    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"HARDWARE\DESCRIPTION\System\CentralProcessor\0",
            )
            value, _ = winreg.QueryValueEx(key, "ProcessorNameString")
            return value.strip()
        except Exception:
            pass

    # 4) 兜底
    return platform.processor() or platform.machine() or "Unknown"


def get_cpu_info_pycpuinfo() -> dict:
    """使用 py-cpuinfo（pip install py-cpuinfo）获取更详细信息。"""
    try:
        from cpuinfo import get_cpu_info
        info = get_cpu_info()
        return {
            "brand": info.get("brand_raw", "Unknown"),
            "arch": info.get("arch", ""),
            "bits": info.get("bits", ""),
            "logical_cores": info.get("count", ""),
            "hz": info.get("hz_advertised_friendly", ""),
        }
    except ImportError:
        return {}


if __name__ == "__main__":
    print("=== 系统信息 ===")
    print(f"操作系统 : {platform.system()} {platform.release()}")
    print(f"机器架构 : {platform.machine()}")
    print(f"Python   : {platform.python_version()}")
    print(f"逻辑核心 : {os.cpu_count()}")

    print("\n=== CPU 型号 ===")
    cpu_name = re.sub(r"\s+", " ", get_cpu_name()).strip()
    print(f"型号: {cpu_name}")

    # 若安装了 py-cpuinfo，则打印更详细信息
    detail = get_cpu_info_pycpuinfo()
    if detail:
        print("\n=== 详细信息 (py-cpuinfo) ===")
        for k, v in detail.items():
            print(f"{k:14}: {v}")
