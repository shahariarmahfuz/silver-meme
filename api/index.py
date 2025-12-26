from flask import Flask, Response, request, render_template_string, jsonify
import requests
import json
from urllib.parse import urljoin, urlparse

app = Flask(__name__)

# --- কনফিগারেশন ---
ADMIN_USER = "admin"
ADMIN_PASS = "mypassword123" # পাসওয়ার্ড বদলান

# ইন-মেমোরি ডাটাবেস (Vercel এ ডাটা পার্মানেন্ট থাকে না, তাই টেস্টিং এর জন্য ঠিক আছে। 
# পার্মানেন্ট করার জন্য আপনাকে Vercel KV বা MongoDB Atlas এর ফ্রি টায়ার কানেক্ট করতে হবে।
# আপাতত কোডে হার্ডকোড করে বা JSON স্ট্রাকচার দিয়ে দেখাচ্ছি)

# উদাহরণ চ্যানেল (আপনি কোডেই চ্যানেল অ্যাড করতে পারেন অথবা পরে ডাটাবেস কানেক্ট করতে পারেন)
CHANNELS = [
    {
        "id": "ch1",
        "name": "BTV World",
        "group": "General",
        "logo": "http://example.com/btv.png",
        "url": "http://203.18.158.217:5010/neko/token=xyz/id=3/index.m3u8"
    },
    {
        "id": "ch2",
        "name": "Deepto TV",
        "group": "General",
        "logo": "http://example.com/deepto.png",
        "url": "http://203.18.158.217:5010/neko/token=abc/id=4/index.m3u8"
    }
]

@app.route('/')
def home():
    return "IPTV Proxy Server is Running on Vercel!"

# --- ১. M3U প্লেলিস্ট জেনারেটর ---
@app.route('/playlist.m3u')
def playlist():
    host_url = request.url_root.rstrip('/')
    m3u_content = "#EXTM3U\n"
    
    for ch in CHANNELS:
        # প্রক্সি লিঙ্ক তৈরি
        proxy_link = f"{host_url}/play/{ch['id']}/index.m3u8"
        m3u_content += f'#EXTINF:-1 tvg-logo="{ch["logo"]}" group-title="{ch["group"]}", {ch["name"]}\n'
        m3u_content += f"{proxy_link}\n"
        
    return Response(m3u_content, mimetype='text/plain')

# --- ২. স্ট্রিমিং প্রক্সি (মেইন লজিক) ---
@app.route('/play/<channel_id>/<path:filename>')
def proxy_stream(channel_id, filename):
    # চ্যানেল খুঁজে বের করা
    channel = next((c for c in CHANNELS if c['id'] == channel_id), None)
    if not channel:
        return "Channel not found", 404

    # টার্গেট URL তৈরি
    # বেস URL বের করা (যেমন: http://ip:5010/path/to/)
    base_url = channel['url'].rsplit('/', 1)[0] + '/'
    
    # যদি রিকোয়েস্ট হয় index.m3u8, তবে অরিজিনাল ইউআরএলই ব্যবহার হবে
    # আর যদি .ts বা অন্য কিছু হয়, তবে বেস ইউআরএল এর সাথে জোড়া লাগবে
    if filename == "index.m3u8":
        target_url = channel['url']
    else:
        target_url = urljoin(base_url, filename)

    try:
        # অরিজিনাল সার্ভারে রিকোয়েস্ট পাঠানো (Requests লাইব্রেরি অটোমেটিক পোর্ট হ্যান্ডেল করে)
        headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": base_url
        }
        
        # স্ট্রিম করা (Stream=True বড় ফাইলের জন্য ভালো)
        resp = requests.get(target_url, headers=headers, stream=True, timeout=10)
        
        # স্ট্যাটাস কোড চেক
        if resp.status_code != 200:
            return Response("Source Error", status=resp.status_code)

        # কনটেন্ট প্রসেস করা
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        headers = [(name, value) for (name, value) in resp.raw.headers.items()
                   if name.lower() not in excluded_headers]

        content = resp.content

        # যদি M3U8 ফাইল হয়, তবে ভেতরের লিঙ্ক রিরাইট করতে হবে
        if filename.endswith('.m3u8') or 'mpegurl' in resp.headers.get('Content-Type', ''):
            text_content = content.decode('utf-8')
            new_lines = []
            for line in text_content.splitlines():
                if line.strip() and not line.startswith('#'):
                    # প্রতিটি TS ফাইল বা সাব-স্ট্রিমকে আবার আমাদের প্রক্সির ভেতর দিয়ে চালাতে হবে
                    # শুধু ফাইলের নামটা রেখে দিব, যাতে পরবর্তী রিকোয়েস্ট /play/id/file.ts এ আসে
                    new_lines.append(line.strip()) 
                else:
                    new_lines.append(line)
            
            content = "\n".join(new_lines).encode('utf-8')
            # কনটেন্ট টাইপ সেট করা
            headers.append(('Content-Type', 'application/vnd.apple.mpegurl'))

        return Response(content, status=resp.status_code, headers=headers)

    except Exception as e:
        return Response(f"Error: {str(e)}", status=500)

# Vercel এর জন্য অ্যাপ এক্সপোর্ট
app.debug = True
