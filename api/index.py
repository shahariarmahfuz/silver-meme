from flask import Flask, Response, request, render_template_string, jsonify
import requests
import uuid
from urllib.parse import urljoin, urlparse

app = Flask(__name__)

# --- কনফিগারেশন ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "mypassword123" # আপনার পাসওয়ার্ড দিন
APP_TITLE = "Python IPTV Panel (Vercel)"

# --- মেমোরি ডাটাবেস (Temporary Storage) ---
# Vercel রিস্টার্ট হলে এই ডাটা মুছে যাবে
channels = [] 

# --- অথেন্টিকেশন চেকার ---
def check_auth():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
        return False
    return True

def auth_fail():
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

# --- ১. হোমপেজ ---
@app.route('/')
def home():
    return "IPTV Proxy Server is Running on Vercel..."

# --- ২. এডমিন প্যানেল (HTML UI) ---
@app.route('/admin')
def admin_panel():
    if not check_auth():
        return auth_fail()

    # HTML টেমপ্লেট (এডমিন পেজ)
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{APP_TITLE}</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>body{{padding:20px; background:#f4f4f4;}}</style>
    </head>
    <body>
        <div class="container">
            <h2 class="mb-4">📡 Channel Manager (RAM Storage)</h2>
            <div class="alert alert-warning">Warning: Data will be lost if Vercel restarts!</div>
            
            <div class="card p-3 mb-4">
                <h5>Add New Channel</h5>
                <form id="addForm">
                    <div class="row">
                        <div class="col-md-3"><input type="text" id="name" class="form-control" placeholder="Name" required></div>
                        <div class="col-md-3"><input type="text" id="group" class="form-control" placeholder="Group"></div>
                        <div class="col-md-3"><input type="text" id="logo" class="form-control" placeholder="Logo URL"></div>
                        <div class="col-md-3"><input type="text" id="url" class="form-control" placeholder="Source URL (http ok)" required></div>
                    </div>
                    <button type="submit" class="btn btn-primary mt-3">Add Channel</button>
                </form>
            </div>

            <div class="card p-3">
                <h5>Current Channels ({len(channels)})</h5>
                <table class="table table-striped">
                    <thead><tr><th>Logo</th><th>Name</th><th>Proxy Link</th><th>Action</th></tr></thead>
                    <tbody id="list">
                        </tbody>
                </table>
                <div class="mt-3">
                    <strong>Your Playlist URL:</strong> 
                    <a href="/playlist.m3u" target="_blank">/playlist.m3u</a>
                </div>
            </div>
        </div>

        <script>
            // পেজ লোড হলে চ্যানেল লিস্ট আনবে
            async function loadChannels() {{
                const res = await fetch('/api/list');
                const data = await res.json();
                const tbody = document.getElementById('list');
                tbody.innerHTML = '';
                
                data.forEach(c => {{
                    const row = `<tr>
                        <td><img src="${{c.logo}}" height="30"></td>
                        <td>${{c.name}}</td>
                        <td style="font-size:12px; color:gray">/play/${{c.id}}/index.m3u8</td>
                        <td><button onclick="deleteCh('${{c.id}}')" class="btn btn-danger btn-sm">Delete</button></td>
                    </tr>`;
                    tbody.innerHTML += row;
                }});
            }}
            loadChannels();

            // চ্যানেল অ্যাড করা
            document.getElementById('addForm').addEventListener('submit', async (e) => {{
                e.preventDefault();
                const data = {{
                    name: document.getElementById('name').value,
                    group: document.getElementById('group').value,
                    logo: document.getElementById('logo').value,
                    url: document.getElementById('url').value
                }};
                await fetch('/api/save', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify(data)
                }});
                document.getElementById('addForm').reset();
                loadChannels();
            }});

            // চ্যানেল ডিলেট করা
            async function deleteCh(id) {{
                if(confirm('Delete this channel?')) {{
                    await fetch('/api/delete', {{
                        method: 'POST',
                        headers: {{'Content-Type': 'application/json'}},
                        body: JSON.stringify({{id}})
                    }});
                    loadChannels();
                }}
            }}
        </script>
    </body>
    </html>
    """
    return render_template_string(html)

# --- ৩. API Endpoints (ডাটা সেভ/ডিলেট) ---
@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    new_channel = {
        "id": str(uuid.uuid4())[:8],
        "name": data.get("name"),
        "group": data.get("group", "General"),
        "logo": data.get("logo", ""),
        "url": data.get("url")
    }
    channels.append(new_channel)
    return jsonify({"status": "success", "id": new_channel["id"]})

@app.route('/api/delete', methods=['POST'])
def api_delete():
    data = request.json
    global channels
    channels = [c for c in channels if c['id'] != data.get('id')]
    return jsonify({"status": "deleted"})

@app.route('/api/list')
def api_list():
    return jsonify(channels)

# --- ৪. M3U প্লেলিস্ট জেনারেটর ---
@app.route('/playlist.m3u')
def playlist():
    host_url = request.url_root.rstrip('/')
    # HTTPS ফোর্স করা (যদি Vercel HTTP তে থাকে)
    if "http://" in host_url and "localhost" not in host_url:
        host_url = host_url.replace("http://", "https://")

    content = "#EXTM3U\n"
    for ch in channels:
        # প্রক্সি লিঙ্ক ফরম্যাট: /play/<id>/index.m3u8
        proxy_link = f"{host_url}/play/{ch['id']}/index.m3u8"
        content += f'#EXTINF:-1 tvg-logo="{ch["logo"]}" group-title="{ch["group"]}", {ch["name"]}\n'
        content += f"{proxy_link}\n"
    
    return Response(content, mimetype='text/plain')

# --- ৫. প্রক্সি স্ট্রিমিং লজিক (সবচেয়ে গুরুত্বপূর্ণ) ---
@app.route('/play/<channel_id>/<path:filename>')
def proxy_stream(channel_id, filename):
    # চ্যানেল খোঁজা
    channel = next((c for c in channels if c['id'] == channel_id), None)
    if not channel:
        return "Channel not found or Server Restarted (Data Lost)", 404

    # টার্গেট URL তৈরি (Relative Path Support)
    # মেইন URL: http://server.com/live/stream.m3u8
    # Base URL: http://server.com/live/
    
    original_url = channel['url']
    base_url = original_url.rsplit('/', 1)[0] + '/'

    if filename == "index.m3u8":
        target_url = original_url
    else:
        # যদি সাব-ফোল্ডার বা TS ফাইল হয়
        target_url = urljoin(base_url, filename)

    try:
        # 1. সোর্স থেকে ডাটা আনা (Python Requests দিয়ে, তাই যেকোনো পোর্ট সাপোর্ট করবে)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": base_url
        }
        
        resp = requests.get(target_url, headers=headers, stream=True, timeout=10, verify=False)
        
        if resp.status_code != 200:
            return Response(f"Source Error: {resp.status_code}", status=resp.status_code)

        # 2. রেসপন্স প্রসেস করা
        content = resp.content
        response_headers = {
            'Access-Control-Allow-Origin': '*'
        }

        # 3. যদি M3U8 ফাইল হয়, লিংক রিরাইট (Rewrite) করতে হবে
        if filename.endswith('.m3u8') or 'mpegurl' in resp.headers.get('Content-Type', ''):
            text_content = content.decode('utf-8', errors='ignore')
            new_lines = []
            
            for line in text_content.splitlines():
                line = line.strip()
                if line and not line.startswith('#'):
                    # লিংক পেলে সেটার নাম বা পাথ রেখে দেওয়া, যাতে ব্রাউজার আবার আমাদের কাছেই চায়
                    # ব্রাউজার অটোমেটিক বর্তমান URL (i.e. /play/id/...) এর সাথে এই নাম যোগ করবে
                    new_lines.append(line) 
                else:
                    new_lines.append(line)
            
            content = "\n".join(new_lines).encode('utf-8')
            response_headers['Content-Type'] = 'application/vnd.apple.mpegurl'
        else:
            # TS ফাইল বা ভিডিও ডাটা
            response_headers['Content-Type'] = resp.headers.get('Content-Type', 'video/mp2t')

        return Response(content, status=200, headers=response_headers)

    except Exception as e:
        return Response(f"Proxy Error: {str(e)}", status=500)

# লোকাল টেস্টের জন্য
if __name__ == '__main__':
    app.run(debug=True, port=5000)
    
