# -*- coding: utf-8 -*-
"""通用 pcap 读取 + 首包结构探查（无第三方依赖）。"""
import struct, sys, collections, os, zipfile

MAGIC = {b"\xd4\xc3\xb2\xa1": "<", b"\xa1\xb2\xc3\xd4": ">",
         b"\x4d\x3c\xb2\xa1": "<", b"\xa1\xb2\x3c\x4d": ">"}


def read_pcap(path):
    """yield (ts_float, linktype, raw_bytes)"""
    with open(path, "rb") as f:
        gh = f.read(24)
        if len(gh) < 24:
            return
        magic = gh[:4]
        endian = MAGIC.get(magic)
        if endian is None:
            raise ValueError("not a classic pcap: %r" % magic)
        linktype = struct.unpack(endian + "I", gh[20:24])[0]
        while True:
            rh = f.read(16)
            if len(rh) < 16:
                break
            ts_s, ts_us, caplen, wirelen = struct.unpack(endian + "IIII", rh)
            data = f.read(caplen)
            if len(data) < caplen:
                break
            yield ts_s + ts_us / 1e6, linktype, data


def describe():
    base = r"C:\Users\喜哈哈\Desktop\03_项目与工具\综合项目\智能驾驶研究\数据\C2_trace\raw"
    zpath = os.path.join(base, "C-V2I-outdoor-testcase1-datasets-PCAP.zip")
    z = zipfile.ZipFile(zpath)
    names = [n for n in z.namelist() if n.endswith(".pcap")]
    for n in sorted(names):
        raw = z.read(n)
        tmp = os.path.join(base, "_tmp.pcap")
        open(tmp, "wb").write(raw)
        lts = collections.Counter()
        cnt = 0
        firsts = []
        for ts, lt, data in read_pcap(tmp):
            lts[lt] += 1
            cnt += 1
            if len(firsts) < 3:
                firsts.append((ts, lt, data[:96].hex()))
        print("=" * 90)
        print(n, "| packets:", cnt, "| linktypes:", dict(lts))
        for ts, lt, h in firsts:
            print(f"  ts={ts:.6f} lt={lt}\n    {h}")
        os.remove(tmp)


if __name__ == "__main__":
    describe()
