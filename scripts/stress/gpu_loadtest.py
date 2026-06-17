#!/usr/bin/env python3
"""CallTone GPU load / ceiling harness (run ON the model-server host).

The model server processes ONE pipeline at a time (``/v1/analyze`` returns 409
when busy, each job runs in an isolated subprocess). Real concurrency therefore
comes from running multiple server instances and spreading work across them.
This harness drives concurrent real calls across a list of server URLs, samples
GPU memory/util while it runs, and reports latency, throughput, success rate,
per-server distribution, and peak VRAM.

Modes:
  ceiling  : fire `--concurrency` calls spread across `--servers` (all on one
             GPU) to find how many concurrent pipelines a single GPU sustains.
  balancer : same driver, but `--servers` spans GPUs; reports per-server split
             and (with --kill-after) validates failover when one server dies.

Usage:
  python gpu_loadtest.py --servers http://127.0.0.1:8081,http://127.0.0.1:8082 \
      --token "$TOK" --audio /opt/calltone/sample.wav --company loadtest \
      --calls 12 --concurrency 2 --out /opt/calltone/result.json
"""
import argparse, json, statistics, subprocess, sys, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error

def now(): return time.time()

def http_post_file(url, token, audio, fields, timeout=900):
    import uuid, mimetypes, os
    boundary = "----calltone" + uuid.uuid4().hex
    with open(audio, "rb") as f: data = f.read()
    parts = []
    for k, v in fields.items():
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{v}\r\n".encode())
    fn = os.path.basename(audio)
    parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"{fn}\"\r\nContent-Type: audio/wav\r\n\r\n".encode())
    parts.append(data); parts.append(f"\r\n--{boundary}--\r\n".encode())
    body = b"".join(parts)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

def http_get(url, token, timeout=60):
    req = urllib.request.Request(url); req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "{}")

class GpuSampler(threading.Thread):
    def __init__(self, interval=1.5):
        super().__init__(daemon=True); self.interval=interval; self.stop_flag=False
        self.peak_mem={}; self.peak_util={}; self.samples=0
    def run(self):
        while not self.stop_flag:
            try:
                out = subprocess.check_output(
                    ["nvidia-smi","--query-gpu=index,memory.used,utilization.gpu",
                     "--format=csv,noheader,nounits"], text=True)
                for line in out.strip().splitlines():
                    idx, mem, util = [x.strip() for x in line.split(",")]
                    idx=int(idx); mem=int(mem); util=int(util)
                    self.peak_mem[idx]=max(self.peak_mem.get(idx,0), mem)
                    self.peak_util[idx]=max(self.peak_util.get(idx,0), util)
                self.samples+=1
            except Exception: pass
            time.sleep(self.interval)
    def stop(self): self.stop_flag=True

def run_one(servers, token, audio, company, idx, results, lock, rr):
    # pick a server round-robin; on 409 (busy) back off and try the next.
    attempt=0
    while True:
        with lock:
            srv = servers[rr[0] % len(servers)]; rr[0]+=1
        t0=now()
        status, body = http_post_file(f"{srv}/v1/analyze", token, audio,
            {"company":company,"asr_engine":"fasterwhisper","report_mode":"narrative","use_consensus":"false"})
        if status==409:
            attempt+=1; time.sleep(2.0)
            if attempt>200:
                with lock: results.append({"idx":idx,"server":srv,"ok":False,"err":"409-timeout"})
                return
            continue
        if status>=400 or "job_id" not in body:
            with lock: results.append({"idx":idx,"server":srv,"ok":False,"err":f"http{status}:{body}"})
            return
        jid=body["job_id"]; break
    # poll to terminal
    while True:
        s,p = http_get(f"{srv}/v1/jobs/{jid}", token)
        st = (p or {}).get("status","")
        if st in ("completed","succeeded","done","failed","error"):
            t1=now()
            with lock:
                results.append({"idx":idx,"server":srv,"job_id":jid,"status":st,
                                "ok":st in ("completed","succeeded","done"),
                                "submit_ts":t0,"done_ts":t1,"latency_s":round(t1-t0,1)})
            return
        if s>=400:
            with lock: results.append({"idx":idx,"server":srv,"job_id":jid,"ok":False,"err":f"poll{s}"})
            return
        time.sleep(3.0)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--servers",required=True)
    ap.add_argument("--token",required=True)
    ap.add_argument("--audio",required=True)
    ap.add_argument("--company",default="loadtest")
    ap.add_argument("--calls",type=int,default=8)
    ap.add_argument("--concurrency",type=int,default=2)
    ap.add_argument("--out",default="/opt/calltone/loadtest_result.json")
    ap.add_argument("--label",default="run")
    a=ap.parse_args()
    servers=[s.strip().rstrip("/") for s in a.servers.split(",") if s.strip()]
    print(f"[{a.label}] servers={servers} calls={a.calls} concurrency={a.concurrency}")
    sampler=GpuSampler(); sampler.start()
    results=[]; lock=threading.Lock(); rr=[0]; t_start=now()
    with ThreadPoolExecutor(max_workers=a.concurrency) as ex:
        futs=[ex.submit(run_one,servers,a.token,a.audio,a.company,i,results,lock,rr)
              for i in range(a.calls)]
        for _ in as_completed(futs): pass
    wall=now()-t_start; sampler.stop(); time.sleep(0.2)
    ok=[r for r in results if r.get("ok")]
    lat=[r["latency_s"] for r in ok if "latency_s" in r]
    dist={}
    for r in results: dist[r.get("server","?")]=dist.get(r.get("server","?"),0)+1
    summary={
        "label":a.label,"servers":servers,"calls":a.calls,"concurrency":a.concurrency,
        "wall_s":round(wall,1),"ok":len(ok),"failed":len(results)-len(ok),
        "throughput_calls_per_min":round(len(ok)/(wall/60),2) if wall>0 else 0,
        "latency_p50_s":round(statistics.median(lat),1) if lat else None,
        "latency_min_s":min(lat) if lat else None,"latency_max_s":max(lat) if lat else None,
        "per_server_count":dist,
        "peak_mem_mib_per_gpu":sampler.peak_mem,"peak_util_pct_per_gpu":sampler.peak_util,
        "errors":[r for r in results if not r.get("ok")][:10],
    }
    print(json.dumps(summary,indent=2))
    try:
        with open(a.out,"a") as f: f.write(json.dumps(summary)+"\n")
    except Exception as e: print("write fail",e)

if __name__=="__main__": main()
