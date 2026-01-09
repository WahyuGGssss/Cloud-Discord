import sys, os, discord, io, math, asyncio, base64, threading, gc, time
from discord.ext import commands
from flask import Flask, redirect, request, jsonify, render_template_string, session, Response, stream_with_context
from pymongo import MongoClient

if getattr(sys, 'frozen', False):
    os.chdir(sys._MEIPASS)

# --- CONFIGURATION (FILL THIS) ---
TOKEN = ""
MONGO_URI = ""
CHANNEL_ID = 0
USER_PIN = ""

# --- DATABASE SETUP ---
try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client['cloud_vault']['data']
except:
    sys.exit("Database connection failed.")

def get_db():
    res = db.find_one({"_id": "main_db"})
    return res if res else {"_id": "main_db", "files": []}

# --- SERVER SETUP ---
app = Flask(__name__)
app.secret_key = os.urandom(24).hex()
intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents)

HTML_PRO = """
<!DOCTYPE html>
<html lang="id">
<head>
    <meta charset="UTF-8">
    <title>Cloud Drive</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css">
    <style>
        body { background: #f0f2f5; font-family: 'Inter', sans-serif; }
        .sidebar { width: 260px; position: fixed; height: 100vh; background: white; border-right: 1px solid #ddd; padding: 20px; }
        .main { margin-left: 260px; padding: 40px; }
        .drive-card { background: white; border-radius: 15px; box-shadow: 0 4px 20px rgba(0,0,0,0.05); padding: 20px; }
        .file-list:hover { background: #f8f9fa; cursor: pointer; transition: 0.2s; }
        .btn-add { background: #0b57d0; color: white; border-radius: 25px; padding: 12px 25px; font-weight: 500; border: none; }
        #upBox { position: fixed; bottom: 20px; right: 20px; width: 320px; background: #202124; color: white; border-radius: 10px; padding: 15px; display: none; }
    </style>
</head>
<body>
    <div class="sidebar">
        <h4 class="text-primary fw-bold mb-5"><i class="bi bi-cloud-check-fill"></i> CloudDrive</h4>
        <button class="btn-add w-100 shadow-sm" onclick="document.getElementById('fi').click()"><i class="bi bi-plus-lg me-2"></i> Upload</button>
        <input type="file" id="fi" multiple style="display:none" onchange="gasUpload(this.files)">
    </div>
    <div class="main">
        <div class="drive-card">
            <h5 class="mb-4">Files</h5>
            <table class="table align-middle">
                <thead class="table-light"><tr><th>Name</th><th>Status</th><th>Action</th></tr></thead>
                <tbody>
                    {% for idx, f in files %}
                    <tr class="file-list" onclick="preview('{{ idx }}', '{{ f.name }}')">
                        <td><i class="bi bi-file-earmark-play-fill text-danger fs-5 me-2"></i> {{ f.name }}</td>
                        <td><span class="badge bg-success">Stored</span></td>
                        <td><button class="btn btn-sm btn-outline-danger" onclick="event.stopPropagation(); hapus('{{ idx }}')"><i class="bi bi-trash"></i></button></td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
    <div id="upBox">
        <div class="small mb-2" id="upName">File Name</div>
        <div class="progress" style="height: 6px;"><div id="upBar" class="progress-bar progress-bar-striped progress-bar-animated bg-primary" style="width: 0%"></div></div>
    </div>
    <div class="modal fade" id="vM" tabindex="-1"><div class="modal-dialog modal-xl modal-dialog-centered"><div class="modal-content bg-dark border-0">
        <div id="vB" class="modal-body p-0 d-flex justify-content-center align-items-center" style="min-height: 500px;"></div>
        <div class="p-3 d-flex gap-2">
            <button id="dL" class="btn btn-primary flex-grow-1 fw-bold py-2">DOWNLOAD</button>
            <button class="btn btn-secondary" data-bs-dismiss="modal">Close</button>
        </div>
    </div></div></div>
    <script>
        async function gasUpload(files) {
            document.getElementById('upBox').style.display = 'block';
            for(let f of files) {
                document.getElementById('upName').innerText = f.name;
                const chunk = 8 * 1024 * 1024; const total = Math.ceil(f.size/chunk); const fid = Date.now();
                for(let i=0; i<total; i++) {
                    const fd = new FormData();
                    fd.append('chunk', f.slice(i*chunk, (i+1)*chunk));
                    fd.append('name', f.name); fd.append('part', i+1); fd.append('total', total); fd.append('file_id', fid);
                    await fetch('/upload', {method:'POST', body:fd});
                    document.getElementById('upBar').style.width = ((i+1)/total*100)+'%';
                }
            }
            location.reload();
        }
        async function preview(id, name) {
            const m = new bootstrap.Modal(document.getElementById('vM')); m.show();
            document.getElementById('vB').innerHTML = '<div class="spinner-border text-primary"></div>';
            const r = await fetch('/view/'+id); const d = await r.json();
            document.getElementById('dL').onclick = () => window.location.href='/get/'+id;
            const ext = name.split('.').pop().toLowerCase();
            if(['mp4','webm','mov'].includes(ext)) document.getElementById('vB').innerHTML = `<video src="${d.url}" controls autoplay class="w-100"></video>`;
            else document.getElementById('vB').innerHTML = `<img src="${d.url}" class="img-fluid">`;
        }
        async function hapus(id) { if(confirm('Delete file?')) { await fetch('/del/'+id); location.reload(); } }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
</body>
</html>
"""

up_tmp = {}

@app.route('/')
def home():
    if not session.get('a'): return render_template_string('<body style="display:flex;justify-content:center;align-items:center;height:100vh;background:#f0f2f5"><div style="background:white;padding:40px;border-radius:20px;box-shadow:0 10px 30px rgba(0,0,0,0.1);text-align:center"><h3>Cloud Vault</h3><form action="/login" method="post"><input type="password" name="p" class="form-control mb-3" placeholder="Enter PIN" autofocus><button class="btn btn-primary w-100">Login</button></form></div></body>')
    data = get_db(); return render_template_string(HTML_PRO, files=list(enumerate(data['files'])))

@app.route('/login', methods=['POST'])
def login():
    if request.form.get('p') == USER_PIN: session['a'] = True
    return redirect('/')

@app.route('/upload', methods=['POST'])
def upload():
    f = request.files['chunk']; fid = request.form['file_id']; name = request.form['name']
    part = int(request.form['part']); total = int(request.form['total'])
    b64 = base64.b64encode(f.read()).decode('ascii')
    async def task():
        ch = await bot.fetch_channel(CHANNEL_ID)
        m = await ch.send(content=f"{name} P{part}/{total}", file=discord.File(io.StringIO(b64), f"p{part}.txt"))
        if fid not in up_tmp: up_tmp[fid] = []
        up_tmp[fid].append({"url": m.attachments[0].url, "part": part})
        if len(up_tmp[fid]) == total:
            data = get_db(); pts = sorted(up_tmp[fid], key=lambda x: x['part'])
            data['files'].append({"name": name, "parts": pts})
            db.replace_one({"_id": "main_db"}, data, upsert=True); del up_tmp[fid]
    asyncio.run_coroutine_threadsafe(task(), bot.loop).result()
    return "OK"

@app.route('/view/<int:id>')
def view(id):
    f = get_db()['files'][id]
    return jsonify({"url": f['parts'][0]['url']})

@app.route('/get/<int:id>')
def get(id):
    f = get_db()['files'][id]
    def gen():
        for p in f['parts']:
            mid = int(p['url'].split('/')[-2])
            ch = asyncio.run_coroutine_threadsafe(bot.fetch_channel(CHANNEL_ID), bot.loop).result()
            m = asyncio.run_coroutine_threadsafe(ch.fetch_message(mid), bot.loop).result()
            yield base64.b64decode(asyncio.run_coroutine_threadsafe(m.attachments[0].read(), bot.loop).result())
    return Response(gen(), mimetype='application/octet-stream', headers={"Content-Disposition":f"attachment;filename={f['name']}"})

@app.route('/del/<int:id>')
def delete(id):
    data = get_db(); data['files'].pop(id)
    db.replace_one({"_id": "main_db"}, data); return "OK"

if __name__ == "__main__":
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000, use_reloader=False)).start()
    bot.run(TOKEN)
