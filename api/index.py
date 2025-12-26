from flask import Flask, Response, request, render_template_string, jsonify
import requests
import uuid
import base64
from urllib.parse import urljoin

app = Flask(__name__)

# --- কনফিগারেশন ---
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "mypassword123" 
APP_TITLE = "Pro Hidden IPTV (Vercel)"

# --- মেমোরি ডাটাবেস ---
channels = [] 

# --- অথেন্টিকেশন ---
def check_auth():
    auth = request.authorization
    if not auth or auth.username != ADMIN_USERNAME or auth.password != ADMIN_PASSWORD:
        return False
    return True

def auth_fail():
    return Response('Login Required', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

# --- ১. হোম ও এডমিন প্যানেল ---
@app.route('/')
def home():
    return "Hidden Proxy Active"

@app.route('/admin')
def admin_panel():
    if not check_auth(): return auth_fail()
    html = f"""
    <!DOCTYPE html>
    <html>
    <head><title>{APP_TITLE}</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"></head>
    <body class="p-4 bg-light">
        <div class="container">
            <h3>🛡️ Fully Hidden Channel Manager</h3>
            <div class="alert alert-info">Now supports hiding inner absolute URLs!</div>
            <div class="card p-3 mb-3">
                <form id="addForm">
                    <div class="row">
                        <div class="col-md-3"><input id="name" class="form-control" placeholder="Name" required></div>
                        <div class="col-md-3"><input id="group" class="form-control" placeholder="Group"></div>
                        <div class="col-md-3"><input id="logo" class="form-control" placeholder="Logo URL"></div>
                        <div class="col-md-3"><input id="url" class="form-control" placeholder="Source URL" required></div>
                    </div>
                    <button type="submit" class="btn btn-primary mt-3">Add Channel</button>
                </form>
            </div>
            <table class="table table-striped bg-white">
                <tbody id="list"></tbody>
            </table>
            <a href="/playlist.m3u" target="_blank" class="btn btn-success">Download Playlist</a>
        </div>
        <script>
            async function load() {{
                const res = await fetch('/api/list');
                const data = await res.json();
                document.getElementById('list').innerHTML = data.map(c => `
                    <tr><td><img src="${{c.logo}}" height="30"></td><td>${{c.name}}</td>
                    <td><small>/play/${{c.id}}/master.m3u8</small></td>
                    <td><button onclick="del('${{c.id}}')" class="btn btn-danger btn-sm">Del</button></td></tr>
                `).join('');
            }}
            load();
            document.getElementById('addForm').onsubmit = async (e) => {{
                e.preventDefault();
                await fetch('/api/save', {{
                    method: 'POST', headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        name: document.getElementById('name').value,
                        group: document.getElementById('group').value,
                        logo: document.getElementById('logo').value,
                        url: document.getElementById('url').value
                    }})
                }});
                e.target.reset(); load();
            }};
            async function del(id) {{ await fetch('/api/delete', {{ method: 'POST', headers: {{'Content-Type': 'application/json'}}, body: JSON.stringify({{id}}) }}); load(); }}
        </script>
    </body></html>
    """
    return render_template_string(html)

# --- API Endpoints ---
@app.route('/api/save', methods=['POST'])
def api_save():
    data = request.json
    channels.append({ "id": str(uuid.uuid4())[:8], **data })
    return jsonify({"status": "ok"})

@app.route('/api/delete', methods=['POST'])
def api_delete():
    data = request.json
    global channels
    channels = [c for c in channels if c['id'] != data.get('id')]
    return jsonify({"status": "deleted"})

@app.route('/api/list')
def api_list(): return jsonify(channels)

# --- ২. M3U প্লেলিস্ট জেনারেটর ---
@app.route('/playlist.m3u')
def playlist():
    host = request.url_root.rstrip('/').replace("http://", "https://")
    content = "#EXTM3U\n"
    for ch in channels:
        content += f'#EXTINF:-1 tvg-logo="{ch.get("logo")}" group-title="{ch.get("group")}", {ch.get("name")}\n'
        content += f"{host}/play/{ch['id']}/master.m3u8\n"
    return Response(content, mimetype='text/plain')

# --- ৩. পাওয়ারফুল প্রক্সি ও রিরাইটার ---
@app.route('/play/<channel_id>/<path:filename>')
def proxy_stream(channel_id, filename):
    channel = next((c for c in channels if c['id'] == channel_id), None)
    if not channel: return "Channel Not Found", 404

    # টার্গেট URL ডিটেকশন
    target_url = ""
    
    # ক) যদি এনক্রিপ্ট করা লিংক হয় (__enc__)
    if filename.startswith("__enc__"):
        try:
            # এনক্রিপ্ট অংশটুকু বের করা (__enc__ এর পরেরটুকু)
            # ফাইলের এক্সটেনশন (.m3u8/.ts) ফেলে দেওয়া হতে পারে, বা রাখা হতে পারে
            encoded_part = filename.replace("__enc__", "").split(".")[0] # এক্সটেনশন বাদে
            
            # Base64 ডিকোড করা
            decoded_bytes = base64.urlsafe_b64decode(encoded_part + "==") # প্যাডিং ফিক্স
            target_url = decoded_bytes.decode('utf-8')
        except Exception as e:
            return f"Decryption Error: {str(e)}", 400
            
    # খ) যদি সাধারণ রিকোয়েস্ট হয় (যেমন master.m3u8)
    elif filename == "master.m3u8":
        target_url = channel['url']
        
    # গ) যদি রিলেটিভ পাথ হয়
    else:
        # মেইন চ্যানেলের বেস URL বের করা
        base_url = channel['url'].rsplit('/', 1)[0] + '/'
        target_url = urljoin(base_url, filename)

    # --- রিকোয়েস্ট পাঠানো ---
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": target_url
        }
        
        # SSL ভেরিফিকেশন বন্ধ রাখা হয়েছে (স্পিড ও কম্প্যাটিবিলিটির জন্য)
        resp = requests.get(target_url, headers=headers, stream=True, timeout=20, verify=False)
        
        # --- M3U8 রিরাইট লজিক (সব লিংক হাইড করা) ---
        if filename.endswith('.m3u8') or 'mpegurl' in resp.headers.get('Content-Type', ''):
            text_content = resp.text
            new_lines = []
            
            # হোস্ট URL (যেমন: https://myapp.vercel.app)
            host_url = request.url_root.rstrip('/').replace("http://", "https://")
            base_proxy_path = f"{host_url}/play/{channel_id}"

            for line in text_content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    new_lines.append(line)
                    continue
                
                # এখন লাইনটি একটি লিংক (URI)
                original_link = line
                
                # যদি লিংকটি Absolute হয় (http দিয়ে শুরু)
                if original_link.startswith('http'):
                    # লিংকটিকে Base64 এ কনভার্ট করা
                    encoded = base64.urlsafe_b64encode(original_link.encode('utf-8')).decode('utf-8')
                    # নতুন লিংক তৈরি: /play/id/__enc__XYZ.m3u8
                    # শেষে .m3u8 বা .ts যোগ করা ভালো যেন প্লেয়ার কনফিউজ না হয়
                    ext = ".m3u8" if ".m3u8" in original_link else ".ts"
                    new_link = f"{base_proxy_path}/__enc__{encoded}{ext}"
                    new_lines.append(new_link)
                
                # যদি রিলেটিভ পাথ হয়
                else:
                    # রিলেটিভ পাথকেও আমরা প্রক্সির মধ্যে রাখব
                    # এটা অটোমেটিক কাজ করবে কারণ ব্রাউজার বর্তমান পাথের সাথে এটাকে যোগ করবে
                    new_lines.append(original_link)

            return Response("\n".join(new_lines), headers={
                'Content-Type': 'application/vnd.apple.mpegurl',
                'Access-Control-Allow-Origin': '*'
            })

        # --- TS বা ভিডিও ফাইল সরাসরি পাস করা ---
        return Response(resp.content, status=resp.status_code, headers={
            'Content-Type': resp.headers.get('Content-Type', 'video/mp2t'),
            'Access-Control-Allow-Origin': '*'
        })

    except Exception as e:
        return Response(str(e), 500)
        
