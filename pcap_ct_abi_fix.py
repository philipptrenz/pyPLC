# pcap_ct_abi_fix.py
# Fix libpcap ctypes ABI for 32-bit time64, rebuild callback + prototypes,
# and provide a safe_dispatch() that uses the corrected types.

import ctypes as C
import importlib

L = importlib.import_module("libpcap")   # low-level binding used by pcap-ct

# ---- 1) Decide if we need a fix
ptr_sz = C.sizeof(C.c_void_p)
long_sz = C.sizeof(C.c_long)

# Names present on your box (you printed these earlier)
TV_NAME = "timeval"
PH_NAME = "pkthdr"

TV_orig = getattr(L, TV_NAME, None)
PH_orig = getattr(L, PH_NAME, None)

# ---- 2) Correct struct layouts (time64 on 32-bit is common on OE/musl)
class _timeval_64_32(C.Structure):
    _fields_ = [
        ("tv_sec",  C.c_longlong),  # 64-bit time_t
        ("tv_usec", C.c_long),      # 32-bit suseconds_t
    ]

class _timeval_64_64(C.Structure):
    _fields_ = [
        ("tv_sec",  C.c_longlong),
        ("tv_usec", C.c_longlong),
    ]

def _mk_pkthdr(Timeval):
    # bpf_u_int32 is 32-bit (unsigned)
    class _pkthdr_fixed(C.Structure):
        _fields_ = [
            ("ts",     Timeval),
            ("caplen", C.c_uint),
            ("len",    C.c_uint),
        ]
    return _pkthdr_fixed

def _apply_struct_fix():
    # If timeval < 16, try 64/32 first, then 64/64
    for TV in (_timeval_64_32, _timeval_64_64):
        PH = _mk_pkthdr(TV)
        try:
            if TV_orig and C.sizeof(TV_orig) < 16:
                setattr(L, TV_NAME, TV)
                setattr(L, PH_NAME, PH)
                if C.sizeof(getattr(L, TV_NAME)) == 16 and C.sizeof(getattr(L, PH_NAME)) in (24, 32):
                    return True
        except Exception:
            pass
    # If already >=16, leave as-is
    return C.sizeof(getattr(L, TV_NAME)) >= 16

_need_fix = (ptr_sz == 4 and long_sz == 4 and TV_orig and C.sizeof(TV_orig) < 16)
if _need_fix:
    ok = _apply_struct_fix()
else:
    ok = True

# ---- 3) Rebuild callback type and refresh prototypes to use new pkthdr
def _rebind_prototypes():
    # Rebuild pcap_handler with CURRENT pkthdr type
    PH = getattr(L, PH_NAME)
    L.pcap_handler = C.CFUNCTYPE(None,
                                 C.c_void_p,             # user
                                 C.POINTER(PH),          # const struct pcap_pkthdr*
                                 C.POINTER(C.c_ubyte))   # const u_char*

    # Update common function prototypes that take pcap_handler
    # Some bindings use 'dispatch'/'loop'; others prefix with 'pcap_'
    for fname in ("dispatch", "pcap_dispatch", "loop", "pcap_loop"):
        fn = getattr(L, fname, None)
        if fn is None:
            continue
        try:
            fn.argtypes = [C.c_void_p, C.c_int, L.pcap_handler, C.c_void_p]
            fn.restype  = C.c_int
        except Exception:
            pass

if ok:
    _rebind_prototypes()

# ---- 4) Provide a safe dispatch that uses the corrected low-level API
def safe_dispatch(pcap_obj, cnt, py_callback, user=None):
    """
    Call libpcap's dispatch with the corrected abi.
    pcap_obj: a pcap-ct pcap() instance (we pull out the pcap_t*)
    cnt: number of packets (<=0 for infinite)
    py_callback: function(ts, bytes, user)  [user optional]
    """
    pcap_t_ptr = getattr(pcap_obj, "_pcap__pcap")  # from pcap-ct
    CBTYPE = L.pcap_handler

    def _bridge(user_ptr, hdr_p, data_p):
        try:
            hdr = hdr_p.contents
            # tv_usec may be 32 or 64; ctypes gives Python ints anyway
            ts = int(hdr.ts.tv_sec) + (int(hdr.ts.tv_usec) / 1_000_000.0)
            pkt = C.string_at(data_p, int(hdr.caplen))
            if user is None:
                py_callback(ts, pkt)
            else:
                py_callback(ts, pkt, user)
        except Exception:
            # Never leak exceptions into C
            pass

    cbinst = CBTYPE(_bridge)        # INSTANCE of the (new) callback type
    # Keep it alive for the duration of the call
    pcap_obj.__dict__["_keep_cb"] = cbinst

    # Prefer whichever name exists
    fn = getattr(L, "dispatch", None) or getattr(L, "pcap_dispatch", None)
    if fn is None:
        raise RuntimeError("libpcap binding missing dispatch()")

    return fn(pcap_t_ptr, int(cnt), cbinst, None)
