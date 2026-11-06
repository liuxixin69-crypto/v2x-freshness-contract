# -*- coding: utf-8 -*-
"""C2 真实 trace 验证 · 第一步：拓扑与链路识别。

数据：NIST Outdoor C-V2X Interoperability Testing Datasets (mds2-4003)
      PCAP，Ethernet/WSMP(0x88dc)，tx 与 rx 由同一 sniffer 同时抓，时钟一致。
思路：同一条广播报文在 tx 与 rx 抓包中**字节完全相同** → 用 payload SHA1 做集合交集，
      交集大小即可判定 (发送方, 接收方) 链路，无需解析 ASN.1/BSM 字段。
"""
import os, sys, json, hashlib, collections, zipfile, struct

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(BASE, "数据", "C2_trace", "raw")
OUT = os.path.join(BASE, "数据", "C2_trace")

WSMP_ETHERTYPE = 0x88DC


def read_pcap_stream(fp):
    """从已打开的文件对象读经典 pcap，yield (ts, linktype, data)"""
    gh = fp.read(24)
    if len(gh) < 24:
        return
    magic = gh[:4]
    if magic in (b"\xd4\xc3\xb2\xa1", b"\x4d\x3c\xb2\xa1"):
        e = "<"
    elif magic in (b"\xa1\xb2\xc3\xd4", b"\xa1\xb2\x3c\x4d"):
        e = ">"
    else:
        raise ValueError("bad magic %r" % magic)
    linktype = struct.unpack(e + "I", gh[20:24])[0]
    while True:
        rh = fp.read(16)
        if len(rh) < 16:
            break
        ts_s, ts_us, caplen, _ = struct.unpack(e + "IIII", rh)
        data = fp.read(caplen)
        if len(data) < caplen:
            break
        yield ts_s + ts_us / 1e6, linktype, data


def iter_wsmp(path_or_zipfile, member=None):
    """yield (ts, src_mac, payload_bytes) 仅保留 WSMP 帧"""
    if member is None:
        f = open(path_or_zipfile, "rb")
    else:
        f = path_or_zipfile.open(member, "r")
    with f:
        for ts, lt, data in read_pcap_stream(f):
            if lt != 1 or len(data) < 14:
                continue
            if struct.unpack(">H", data[12:14])[0] != WSMP_ETHERTYPE:
                continue
            yield ts, data[6:12].hex(), data[14:]


def collect():
    zips = sorted(f for f in os.listdir(RAW) if f.endswith(".zip"))
    index = {}   # key -> dict
    for z in zips:
        zp = zipfile.ZipFile(os.path.join(RAW, z))
        members = [m for m in zp.namelist() if m.endswith(".pcap")]
        for m in sorted(members):
            name = os.path.basename(m)[:-5]
            hashes = {}
            ts_first = ts_last = None
            n = 0
            srcs = collections.Counter()
            for ts, src, payload in iter_wsmp(zp, m):
                n += 1
                srcs[src] += 1
                h = hashlib.sha1(payload).hexdigest()[:16]
                hashes.setdefault(h, ts)      # 重传/重复抓取只记首次
                if ts_first is None:
                    ts_first = ts
                ts_last = ts
            index[name] = dict(zip=z, n=n, t0=ts_first, t1=ts_last,
                               nh=len(hashes), hashes=hashes,
                               srcs=dict(srcs))
            print(f"{name:44s} wsmp={n:6d} uniq={len(hashes):6d} "
                  f"span={0 if ts_first is None else ts_last - ts_first:7.1f}s "
                  f"srcs={dict(srcs)}")
    return index


def main():
    print("== 逐个抓包文件 ==")
    idx = collect()
    names = sorted(idx)
    print("\n== 发送方 -> 接收方 交集矩阵（交集>=20 视为一条链路）==")
    links = []
    for a in names:
        for b in names:
            if a == b:
                continue
            inter = set(idx[a]["hashes"]) & set(idx[b]["hashes"])
            if len(inter) >= 20:
                links.append((a, b, len(inter)))
                print(f"{a:44s} -> {b:44s} matched={len(inter):6d} "
                      f"({len(inter)/idx[a]['nh']*100:5.1f}% of tx)")
    with open(os.path.join(OUT, "topology.json"), "w", encoding="utf-8") as f:
        json.dump({"files": {k: {kk: vv for kk, vv in v.items() if kk != "hashes"}
                             for k, v in idx.items()},
                   "links": links}, f, indent=2)
    print("\n写出 topology.json，链路数 =", len(links))


if __name__ == "__main__":
    main()
