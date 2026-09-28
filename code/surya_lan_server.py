#!/usr/bin/env python3
"""Dependency-free, same-Wi-Fi UI for the existing resumable Surya pipeline."""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


CODE_ROOT = Path(__file__).resolve().parent
ROOT = CODE_ROOT.parent
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
RUNNER = CODE_ROOT / "run_surya.py"
EXPORTER = CODE_ROOT / "export_documents.py"
JOBS_ROOT = ROOT / "runtime" / "lan_jobs"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024
JOBS: dict[str, dict] = {}
LOCK = threading.RLock()
QUEUE: queue.Queue[str] = queue.Queue()


def safe_pdf_name(name: str) -> str:
    name = Path(name or "upload.pdf").name
    stem = re.sub(r"[^A-Za-z0-9._()\- ]+", "_", Path(name).stem).strip(" ._")
    return f"{stem or 'upload'}.pdf"


def local_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def add_log(job_id: str, line: str) -> None:
    with LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job["log"] = (job["log"] + line)[-50000:]
        if line.startswith("PIPELINE_STAGE: "):
            stage = line.strip().split(": ", 1)[1]
            messages = {"analyzing": "Identifying question structure.",
                        "validating": "Checking extracted questions against source text.",
                        "exporting": "Creating Word and dynamic Excel files."}
            if stage in messages:
                job.update(state=stage, message=messages[stage], active_page=0)
        total_match = re.search(r"Pages selected:\s*(\d+)", line, re.IGNORECASE)
        if total_match:
            job["progress_total"] = int(total_match.group(1))
        progress = re.search(r"Page\s+(\d+)\s*/\s*(\d+).*?([\d.]+)%.*?\|\s*(.*)$", line, re.IGNORECASE)
        if progress:
            current, total, percent, status = progress.groups()
            job.update(progress_current=int(current), progress_total=int(total), progress_percent=float(percent), page_status=status.strip())
        detail = re.search(r"Page\s+(\d+):\s*(.+)", line, re.IGNORECASE)
        if detail:
            job["active_page"] = int(detail.group(1))
            job["page_status"] = f"Page {detail.group(1)}: {detail.group(2).strip()}"
        job["updated_at"] = time.time()


def run_command(job_id: str, command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    with LOCK:
        JOBS[job_id]["process_id"] = process.pid
    assert process.stdout is not None
    for line in process.stdout:
        add_log(job_id, line)
    return process.wait()


def public_job(job: dict) -> dict:
    return {key: job.get(key) for key in (
        "id", "filename", "state", "message", "log", "outputs", "progress_current",
        "progress_total", "progress_percent", "page_status", "active_page", "created_at", "started_at", "updated_at"
    )}


def worker() -> None:
    while True:
        job_id = QUEUE.get()
        with LOCK:
            job = JOBS[job_id]
            job.update(state="ocr", message="Mintbook OCR is processing the PDF.", started_at=time.time(), updated_at=time.time())
        try:
            # The browser demo must show actual OCR work every time.  ``--force``
            # ignores completed page-cache entries, while still keeping the cache
            # available for a future resumable-mode release.
            command = [str(PYTHON), "-u", str(RUNNER), job["pdf_path"], "--force"]
            if job.get("dense_recovery"):
                command.extend(["--dense-page-policy", "recover"])
            code = run_command(job_id, command)
            if code != 0:
                raise RuntimeError(f"OCR processing stopped with code {code}. The run can be resumed safely.")
            json_path = ROOT / "output" / "surya" / f"{Path(job['filename']).stem}_surya.json"
            if not json_path.is_file():
                raise FileNotFoundError(f"Expected OCR result was not created: {json_path.name}")
            with LOCK:
                job.update(state="exporting", message="OCR completed; creating Word and Excel files.", progress_percent=100, page_status="OCR complete", updated_at=time.time())
            code = run_command(job_id, [str(PYTHON), "-u", str(EXPORTER), str(json_path), "--destination", job["output_dir"]])
            if code != 0:
                raise RuntimeError(f"Document export exited with code {code}.")
            outputs = sorted(p.name for p in Path(job["output_dir"]).iterdir() if p.suffix.lower() in {".docx", ".xlsx", ".json"})
            if not outputs:
                raise RuntimeError("Document export finished without Word or Excel output.")
            with LOCK:
                job.update(state="completed", message="Your Word and Excel files are ready.", outputs=outputs, updated_at=time.time())
        except Exception as error:
            add_log(job_id, f"\nUI ERROR: {error}\n")
            with LOCK:
                job.update(state="failed", message=str(error), updated_at=time.time())
        finally:
            QUEUE.task_done()


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Mintbook OCR</title><style>
:root{font-family:Inter,Segoe UI,sans-serif;color:#203047;background:#f3f6fb}body{margin:0;min-height:100vh}.wrap{max-width:760px;margin:48px auto;padding:20px}.card{background:#fff;border-radius:18px;padding:32px;box-shadow:0 12px 34px #243b5a18}.brand{display:flex;align-items:center;gap:14px}.logo{display:grid;place-items:center;width:50px;height:50px;border-radius:13px;background:#215a88;color:#fff;font-size:25px;font-weight:800}h1{margin:0;color:#173f62}.tag,.hint,.detail{color:#607086}.tag{margin-top:3px}.steps{display:flex;gap:10px;margin:25px 0 5px}.step{flex:1;padding:11px;border-radius:9px;background:#edf4fa;color:#315978;text-align:center;font-size:14px;font-weight:650}.mode{display:flex;gap:20px;margin-top:20px}.mode label,.check{font-weight:500;margin:0}.field{margin-top:18px}.hidden{display:none}.destination{display:flex;align-items:center;gap:12px}.destination button{margin:0;background:#e5eff7;color:#174d73}.destination span{color:#607086;overflow-wrap:anywhere}
label{display:block;font-weight:700;margin:0 0 8px}input,button{font:inherit}input[type=file]{width:100%;box-sizing:border-box;padding:13px;border:1px solid #b9c8d8;border-radius:9px;background:#fbfdff}.check{display:block;margin-top:14px}button{margin-top:20px;background:#215a88;color:#fff;border:0;border-radius:9px;padding:13px 24px;font-weight:750;cursor:pointer}button:disabled{opacity:.6}#status{display:none;margin-top:24px;padding:18px;background:#f7faff;border:1px solid #d6e1eb;border-radius:11px}.track{height:15px;background:#dbe5ee;border-radius:20px;overflow:hidden;margin:14px 0 9px}.bar{height:100%;width:0;background:#2c77ad;transition:width .4s}.activity{height:5px;background:#dbe5ee;border-radius:20px;overflow:hidden;margin:8px 0}.activity span{display:block;width:35%;height:100%;background:linear-gradient(90deg,transparent,#2c77ad,transparent);transform:translateX(-120%)}.activity.live span{animation:working 1.3s linear infinite}@keyframes working{to{transform:translateX(360%)}}.downloads a{display:inline-block;margin:12px 10px 0 0;padding:10px 14px;background:#dceefa;color:#164c72;border-radius:8px;text-decoration:none;font-weight:700}details{margin-top:14px;color:#607086}pre{max-height:260px;overflow:auto;background:#172638;color:#f4f8fb;padding:14px;border-radius:9px;white-space:pre-wrap}
</style></head><body><main class="wrap"><section class="card"><div class="brand"><div class="logo">M</div><div><h1>Mintbook OCR</h1><div class="tag">Convert question papers into editable files</div></div></div>
<div class="steps"><div class="step">1. Select PDFs</div><div class="step">2. Choose output</div><div class="step">3. Process</div></div><form id="form"><div class="mode"><label><input type="radio" name="upload_mode" value="file" checked> One PDF</label><label><input type="radio" name="upload_mode" value="folder"> PDF folder</label></div><div id="singleField" class="field"><label>Select a PDF</label><input id="singlePdf" type="file" accept="application/pdf,.pdf"></div><div id="folderField" class="field hidden"><label>Select a folder of PDFs</label><input id="pdfFolder" type="file" accept="application/pdf,.pdf" webkitdirectory multiple></div><div class="field"><label>Save generated files</label><div class="destination"><button id="chooseOutput" type="button">Browse folder</button><span id="outputName">No folder selected</span></div></div><label class="check"><input id="denseRecovery" type="checkbox"> Improve difficult pages</label><button id="submit">Create Word and Excel</button></form>
<div id="status"><strong id="message"></strong><div class="track"><div class="bar" id="bar"></div></div><div class="activity" id="activity"><span></span></div><div class="detail" id="progressText">Waiting…</div><div class="detail" id="timingText"></div><div class="downloads" id="downloads"></div><details><summary>Processing details</summary><pre id="log"></pre></details></div></section></main><script>
const token=new URLSearchParams(location.search).get('token')||'';let outputDirectory=null;
const singleField=document.getElementById('singleField'),folderField=document.getElementById('folderField');document.querySelectorAll('input[name="upload_mode"]').forEach(r=>r.onchange=()=>{const folder=r.value==='folder'&&r.checked;singleField.classList.toggle('hidden',folder);folderField.classList.toggle('hidden',!folder)});
document.getElementById('chooseOutput').onclick=async()=>{if(!window.showDirectoryPicker){alert('Folder saving requires current Microsoft Edge or Google Chrome over localhost or HTTPS.');return}try{outputDirectory=await window.showDirectoryPicker({mode:'readwrite'});document.getElementById('outputName').textContent=outputDirectory.name}catch(x){if(x.name!=='AbortError')alert(x.message)}};
function duration(seconds){seconds=Math.max(0,Math.floor(seconds||0));return String(Math.floor(seconds/3600)).padStart(2,'0')+':'+String(Math.floor(seconds/60)%60).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0')}
function selectedPdfs(){const mode=document.querySelector('input[name="upload_mode"]:checked').value;const source=mode==='folder'?document.getElementById('pdfFolder').files:document.getElementById('singlePdf').files;return Array.from(source).filter(f=>f.name.toLowerCase().endsWith('.pdf')).sort((a,b)=>a.webkitRelativePath.localeCompare(b.webkitRelativePath)||a.name.localeCompare(b.name))}
async function saveOutput(id,name){const r=await fetch('/api/jobs/'+id+'/files/'+encodeURIComponent(name)+'?token='+encodeURIComponent(token));if(!r.ok)throw new Error('Could not download '+name);const handle=await outputDirectory.getFileHandle(name,{create:true});const writable=await handle.createWritable();await writable.write(await r.blob());await writable.close()}
async function waitForJob(id,batchLabel){for(;;){const r=await fetch('/api/jobs/'+id+'?token='+encodeURIComponent(token));const d=await r.json();if(!r.ok)throw new Error(d.error||'Status unavailable');const working=['queued','ocr','analyzing','validating','exporting'].includes(d.state),total=d.progress_total||0,done=d.progress_current||0,active=d.active_page||0,percent=d.progress_percent||0,started=d.started_at||d.created_at;document.getElementById('message').textContent=batchLabel+' — '+d.message;document.getElementById('bar').style.width=percent+'%';document.getElementById('activity').className='activity'+(working?' live':'');document.getElementById('progressText').textContent=total?('Completed '+done+' of '+total+' pages ('+percent+'%). '+(active?'Processing page '+active+'. ':'')+(d.page_status||'')):(d.state==='queued'?'Waiting to start…':'Preparing the first page…');document.getElementById('timingText').textContent='Elapsed: '+duration(Date.now()/1000-started);document.getElementById('log').textContent=d.log||'Waiting…';if(d.state==='failed')throw new Error(d.message||'Processing failed');if(!working)return d;await new Promise(resolve=>setTimeout(resolve,2000))}}
document.getElementById('form').onsubmit=async e=>{e.preventDefault();const files=selectedPdfs(),b=document.getElementById('submit'),box=document.getElementById('downloads');if(!files.length){alert('Select at least one PDF.');return}if(!outputDirectory){alert('Choose where generated files should be saved.');return}b.disabled=true;box.innerHTML='';document.getElementById('status').style.display='block';try{for(let i=0;i<files.length;i++){b.textContent='Processing '+(i+1)+' of '+files.length;const form=new FormData();form.append('pdf',files[i],files[i].name);if(document.getElementById('denseRecovery').checked)form.append('dense_recovery','on');const r=await fetch('/api/jobs?token='+encodeURIComponent(token),{method:'POST',body:form});const created=await r.json();if(!r.ok)throw new Error(created.error||'Upload failed');const completed=await waitForJob(created.id,'PDF '+(i+1)+' of '+files.length+': '+files[i].name);for(const name of completed.outputs||[]){await saveOutput(created.id,name);const item=document.createElement('div');item.textContent='Saved: '+name;box.appendChild(item)}}document.getElementById('message').textContent='Batch completed. '+files.length+' PDF'+(files.length===1?'':'s')+' processed.';document.getElementById('bar').style.width='100%';document.getElementById('activity').className='activity'}catch(x){document.getElementById('message').textContent=x.message;alert(x.message)}finally{b.disabled=false;b.textContent='Process selected PDFs'}};
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "MintbookOCR/1.0"

    def token_ok(self):
        if self.server.access_token is None:
            return True
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
        return secrets.compare_digest(query.get("token", [""])[0], self.server.access_token)

    def send_bytes(self, data, content_type, status=HTTPStatus.OK, disposition=None):
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Content-Length", str(len(data))); self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
        if disposition: self.send_header("Content-Disposition", disposition)
        self.end_headers(); self.wfile.write(data)

    def send_json(self, value, status=HTTPStatus.OK):
        self.send_bytes(json.dumps(value, ensure_ascii=False).encode(), "application/json; charset=utf-8", status)

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/" and self.token_ok(): return self.send_bytes(PAGE.encode(), "text/html; charset=utf-8")
        if not self.token_ok(): return self.send_json({"error":"Invalid or missing access token."}, HTTPStatus.FORBIDDEN)
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{16})", path)
        if match:
            with LOCK: response = public_job(JOBS[match.group(1)]) if match.group(1) in JOBS else None
            return self.send_json(response) if response else self.send_json({"error":"Job not found."}, HTTPStatus.NOT_FOUND)
        match = re.fullmatch(r"/api/jobs/([a-f0-9]{16})/files/(.+)", path)
        if match:
            with LOCK: job = JOBS.get(match.group(1))
            if not job: return self.send_json({"error":"Job not found."}, HTTPStatus.NOT_FOUND)
            name = Path(match.group(2)).name; path_obj = Path(job["output_dir"]) / name
            if name not in job.get("outputs",[]) or not path_obj.is_file(): return self.send_json({"error":"File not found."}, HTTPStatus.NOT_FOUND)
            kind = {".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", ".json": "application/json"}.get(path_obj.suffix.lower(), "application/octet-stream")
            return self.send_bytes(path_obj.read_bytes(), kind, disposition=f"attachment; filename*=UTF-8''{urllib.parse.quote(name)}")
        self.send_json({"error":"Not found."}, HTTPStatus.NOT_FOUND)

    def do_POST(self):
        if urllib.parse.urlsplit(self.path).path != "/api/jobs" or not self.token_ok(): return self.send_json({"error":"Not found or unauthorized."}, HTTPStatus.FORBIDDEN)
        try:
            length=int(self.headers.get("Content-Length","0")); content_type=self.headers.get("Content-Type","")
            if length<=0 or length>MAX_UPLOAD_BYTES: return self.send_json({"error":"PDF must be smaller than 200 MB."}, HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
            if "multipart/form-data" not in content_type: return self.send_json({"error":"Expected a form upload."}, HTTPStatus.BAD_REQUEST)
            raw=self.rfile.read(length); message=BytesParser(policy=default).parsebytes((f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode()+raw); upload=None; dense_recovery=False
            for part in message.iter_parts():
                if part.get_param("name",header="content-disposition")=="pdf" and part.get_filename(): upload=(part.get_filename(),part.get_payload(decode=True))
                if part.get_param("name",header="content-disposition")=="dense_recovery": dense_recovery=True
            if not upload or not upload[1].startswith(b"%PDF-"): return self.send_json({"error":"The selected file is not a valid PDF."}, HTTPStatus.BAD_REQUEST)
            filename=safe_pdf_name(upload[0]); job_id=secrets.token_hex(8); job_dir=JOBS_ROOT/job_id; input_dir=job_dir/"input"; output_dir=job_dir/"output"; input_dir.mkdir(parents=True); output_dir.mkdir(); pdf_path=input_dir/filename; pdf_path.write_bytes(upload[1]); now=time.time()
            job={"id":job_id,"filename":filename,"state":"queued","message":"Waiting to start.","log":"","outputs":[],"progress_current":0,"progress_total":0,"progress_percent":0,"active_page":0,"page_status":"","pdf_path":str(pdf_path),"output_dir":str(output_dir),"dense_recovery":dense_recovery,"created_at":now,"started_at":None,"updated_at":now}
            with LOCK: JOBS[job_id]=job
            QUEUE.put(job_id); self.send_json({"id":job_id},HTTPStatus.ACCEPTED)
        except Exception as error: self.send_json({"error":f"Upload could not be accepted: {error}"},HTTPStatus.BAD_REQUEST)

    def log_message(self, fmt, *args): sys.stdout.write("Mintbook OCR UI: "+fmt%args+"\n")


def main():
    parser=argparse.ArgumentParser(description="Run Mintbook OCR for trusted devices on the same Wi-Fi."); parser.add_argument("--host",default="0.0.0.0"); parser.add_argument("--port",type=int,default=8502); parser.add_argument("--token",default=os.environ.get("SURYA_OCR_ACCESS_TOKEN") or secrets.token_urlsafe(18)); parser.add_argument("--no-token",action="store_true",help="Disable access tokens for localhost use"); args=parser.parse_args()
    if args.no_token:
        args.token = None
    if not PYTHON.is_file(): raise SystemExit(f"Virtual environment Python not found: {PYTHON}")
    JOBS_ROOT.mkdir(parents=True,exist_ok=True); threading.Thread(target=worker,daemon=True,name="surya-lan-worker").start(); server=ThreadingHTTPServer((args.host,args.port),Handler); server.access_token=args.token
    display_host = "127.0.0.1" if args.host in ("127.0.0.1", "localhost") else local_ip()
    audience = "Open on this computer:" if display_host == "127.0.0.1" else "Open or share on the same Wi-Fi:"
    suffix = f"?token={urllib.parse.quote(args.token)}" if args.token is not None else ""
    url=f"http://{display_host}:{args.port}/{suffix}"; print(f"Mintbook OCR is running.\n{audience}\n{url}\nPress Ctrl+C to stop.")
    try: server.serve_forever()
    except KeyboardInterrupt: print("\nMintbook OCR stopped.")
    finally: server.server_close()
    return 0


if __name__=="__main__": raise SystemExit(main())
