# -*- coding: utf-8 -*-
"""Windows DPAPI user-bound storage for a branch's private connection settings.

Only the desktop superadmin screen calls save_config. Bytes on disk are DPAPI-
encrypted; a different Windows profile cannot decrypt them. This is a legacy-
Windows compatibility measure, not protection against a compromised OS admin.
"""
import ctypes
import ctypes.wintypes
import json
import os
import pathlib
import tempfile

BRANCHES = {
    "tehran": "تهران", "amol": "آمل", "babol": "بابل",
    "qaemshahr": "قائم‌شهر", "sari": "ساری"
}
HUB = "https://autobenzvahdat.ir"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", ctypes.wintypes.DWORD),
                ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _seal(raw, decrypt=False):
    if os.name != "nt":
        raise RuntimeError("Secure connection credentials require Windows DPAPI.")
    inp_buffer = ctypes.create_string_buffer(raw)
    inp = DATA_BLOB(len(raw), ctypes.cast(inp_buffer, ctypes.POINTER(ctypes.c_byte)))
    out = DATA_BLOB()
    crypt = ctypes.windll.crypt32
    kernel = ctypes.windll.kernel32
    if decrypt:
        method = crypt.CryptUnprotectData
        method.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        flag = 0
    else:
        method = crypt.CryptProtectData
        method.argtypes = [ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p,
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
            ctypes.wintypes.DWORD, ctypes.POINTER(DATA_BLOB)]
        flag = 0  # Do not use LOCAL_MACHINE: limit decryption to this Windows account.
    method.restype = ctypes.wintypes.BOOL
    if not method(ctypes.byref(inp), None, None, None, None, flag, ctypes.byref(out)):
        raise ctypes.WinError()
    try:
        return ctypes.string_at(out.pbData, out.cbData)
    finally:
        kernel.LocalFree.argtypes = [ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(out.pbData, ctypes.c_void_p))


def location(data_path):
    return pathlib.Path(data_path) / "branch-connection.dpapi"


def load_config(data_path):
    file = location(data_path)
    if not file.exists():
        return dict(enabled=False, branch_id="", branch_name="",
                    hub_url=HUB, token="")
    try:
        data = json.loads(_seal(file.read_bytes(), decrypt=True).decode("utf-8"))
    except Exception as exc:
        raise RuntimeError("Protected connection settings cannot be read by this Windows account.") from exc
    if data.get("branch_id") not in BRANCHES:
        raise ValueError("Unknown branch ID in protected connection settings.")
    if data.get("branch_name") != BRANCHES[data["branch_id"]]:
        raise ValueError("Stored branch identity is inconsistent.")
    if data.get("hub_url", "").rstrip("/") != HUB:
        raise ValueError("Central server address is not authorized.")
    return data


def save_config(data_path, branch_id, token, enabled=True):
    """Call only after verifying an active local superadmin session."""
    if branch_id not in BRANCHES:
        raise ValueError("Choose one of the five official branches.")
    token = str(token).strip()
    if len(token) < 20 or len(token) > 1024:
        raise ValueError("Enter the full branch connection key from central administration.")
    dest = location(data_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    obj = dict(enabled=bool(enabled), branch_id=branch_id,
               branch_name=BRANCHES[branch_id], hub_url=HUB, token=token)
    sealed = _seal(json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="branch-secret-", dir=str(dest.parent))
        with os.fdopen(fd, "wb") as stream:
            stream.write(sealed)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, str(dest))
    finally:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
    return dict(enabled=bool(enabled), branch_id=branch_id,
                branch_name=BRANCHES[branch_id], hub_url=HUB)
