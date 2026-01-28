import os
import json
import random
import io
import requests
from flask import Blueprint, render_template_string, request, jsonify, send_from_directory, url_for, send_file

# Blueprint Setup
gui_editor_bp = Blueprint('gui_editor', __name__)
CONFIG_FILE = 'config.json'

# --- CONFIGURATION LOGIC ---
def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                return json.load(f)
            except:
                pass
    return {
        "jellyfin": {"url": "", "api_key": "", "user_id": ""},
        "plex": {"url": "", "token": ""},
        "tmdb": {"api_key": "", "language": "de-DE"},
        "editor": {"resolution": "1080"}
    }

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

# --- API ROUTES ---
@gui_editor_bp.route('/api/proxy/image')
def proxy_image():
    """ Proxies an image URL to bypass CORS/CORB blocks. """
    url = request.args.get('url')
    if not url:
        return "Missing URL", 400
    try:
        resp = requests.get(url, stream=True, timeout=10)
        resp.raise_for_status()
        return send_file(
            io.BytesIO(resp.content),
            mimetype=resp.headers.get('Content-Type', 'image/jpeg')
        )
    except Exception as e:
        return str(e), 500

@gui_editor_bp.route('/api/media/random')
def get_random_media():
    config = load_config()
    jf = config.get('jellyfin', {})
    
    if jf.get('url') and jf.get('api_key'):
        headers = {"X-Emby-Token": jf['api_key']}
        clean_url = jf['url'].rstrip('/')
        url = f"{clean_url}/Users/{jf['user_id']}/Items?Recursive=true&IncludeItemTypes=Movie&Limit=50&Fields=Overview,Genres,CommunityRating,ProductionYear,RunTimeTicks"
        
        try:
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            items = r.json().get('Items', [])
            
            if items:
                item = random.choice(items)
                ticks = item.get('RunTimeTicks', 0)
                minutes = (ticks // 600000000) if ticks else 0
                h = minutes // 60
                m = minutes % 60
                runtime_str = f"{h}h {m}min" if h > 0 else f"{m}min"

                return jsonify({
                    "title": item.get('Name'),
                    "year": item.get('ProductionYear', 'N/A'),
                    "rating": item.get('CommunityRating', 'N/A'),
                    "overview": item.get('Overview', ''),
                    "genres": ", ".join(item.get('Genres', [])),
                    "runtime": runtime_str,
                    "backdrop_url": f"{clean_url}/Items/{item['Id']}/Images/Backdrop?api_key={jf['api_key']}",
                    "source": "Jellyfin"
                })
        except Exception as e:
            print(f"DEBUG: Jellyfin Error: {e}")

    # Fallback to Mock Data
    mock_samples = [
        {"title": "Interstellar", "year": 2014, "rating": 8.7, "overview": "A team of explorers travel through a wormhole in space...", "backdrop_url": "https://image.tmdb.org/t/p/original/gEU2vRuvmER7pG97uCqb9hHbp22.jpg"},
        {"title": "The Dark Knight", "year": 2008, "rating": 9.0, "overview": "When the menace known as the Joker wreaks havoc...", "backdrop_url": "https://image.tmdb.org/t/p/original/nMKdUUepR0At5Iu98TjPLuOwwvM.jpg"}
    ]
    sample = random.choice(mock_samples)
    sample["source"] = "Demo Mode"
    return jsonify(sample)

@gui_editor_bp.route('/api/settings', methods=['POST'])
def update_settings():
    save_config(request.json)
    return jsonify({"status": "success"})

@gui_editor_bp.route('/get_local_background')
def get_local_background():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_dir, 'background.jpg')

@gui_editor_bp.route('/editor')
def editor_index():
    config = load_config()
    data = {"title": "TV Background", "backdrop_url": url_for('gui_editor.get_local_background')}
    return render_template_string(EDITOR_TEMPLATE, data=data, config=config)

# --- HTML/JS TEMPLATE ---
EDITOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TV Background Suite</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
    <style>
        :root { --primary: #2e7d32; --bg: #0a0a0a; --panel: #181818; --text: #eee; --sidebar-w: 320px; }
        body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        
        .nav-tabs { display: flex; background: #000; padding: 0 20px; border-bottom: 1px solid #333; height: 50px; flex-shrink: 0; }
        .tab-link { padding: 15px 25px; cursor: pointer; border-bottom: 3px solid transparent; font-size: 14px; }
        .tab-link.active { border-bottom-color: var(--primary); background: var(--panel); }

        .tab-content { display: none; flex: 1; overflow: hidden; }
        .tab-content.active { display: flex; }

        .sidebar { width: var(--sidebar-w); background: var(--panel); border-right: 1px solid #333; padding: 20px; box-sizing: border-box; overflow-y: auto; display: flex; flex-direction: column; gap: 20px; }
        .main-view { flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px; background: #111; position: relative; overflow: auto; }

        .control-group { border-bottom: 1px solid #333; padding-bottom: 15px; }
        h3 { font-size: 12px; text-transform: uppercase; color: #888; margin: 0 0 10px 0; }
        label { font-size: 11px; color: #666; display: block; margin-top: 8px; }
        input, select, button { padding: 8px; border-radius: 4px; border: 1px solid #444; background: #222; color: white; width: 100%; margin-top: 5px; box-sizing: border-box; }
        button { background: var(--primary); border: none; font-weight: bold; cursor: pointer; }
        .btn-export { background: #1565c0; margin-top: 20px; }

        #canvas-wrapper { width: 100%; max-width: 1200px; aspect-ratio: 16 / 9; background: #000; border: 2px solid #333; box-shadow: 0 20px 50px rgba(0,0,0,0.8); }
        .canvas-container { width: 100% !important; height: 100% !important; }
        canvas { width: 100% !important; height: 100% !important; }

        #settings-tab { padding: 40px; overflow-y: auto; flex-direction: column; align-items: center;}
        .settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; width: 100%; max-width: 1000px; }
    </style>
</head>
<body>

    <div class="nav-tabs">
        <div class="tab-link active" onclick="openTab(event, 'editor-tab')">🎨 Layout Editor</div>
        <div class="tab-link" onclick="openTab(event, 'settings-tab')">⚙️ Provider Settings</div>
    </div>

    <div id="editor-tab" class="tab-content active">
        <div class="sidebar">
            <div class="control-group">
                <h3>Metadata Tags</h3>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px;">
                    <button onclick="addMetadataTag('title', 'MOVIE TITLE')">Title</button>
                    <button onclick="addMetadataTag('year', '2024')">Year</button>
                    <button onclick="addMetadataTag('rating', 'IMDb: 8.5')">Rating</button>
                    <button onclick="addMetadataTag('runtime', '2h 15m')">Runtime</button>
                    <button onclick="addMetadataTag('genres', 'Action, Sci-Fi')">Genres</button>
                    <button onclick="addMetadataTag('overview', 'Movie description placeholder...')">Overview</button>
                </div>
            </div>

            <div class="control-group">
                <h3>Preview Controls</h3>
                <button onclick="fetchRandomPreview()" style="background: #1565c0;">🎲 Shuffle Preview</button>
                <p id="source-indicator" style="font-size: 9px; color: #555; text-align: center; margin-top: 5px;">Source: None</p>
            </div>

            <div class="control-group">
                <h3>Leinwand</h3>
                <label for="resSelect">Ziel-Auflösung</label>
                <select id="resSelect" onchange="changeResolution()">
                    <option value="1080">1080p (Full HD)</option>
                    <option value="2160">2160p (4K)</option>
                </select>
                <label for="bgColor">Hintergrundfarbe</label>
                <input type="color" id="bgColor" oninput="updateBgColor()" value="#000000">
            </div>

            <div class="control-group">
                <h3>Fade-Out Kanten</h3>
                <label for="fadeLeft">Links</label>
                <input type="range" id="fadeLeft" min="0" max="1000" value="0" oninput="updateFades()">
                <label for="fadeRight">Rechts</label>
                <input type="range" id="fadeRight" min="0" max="1000" value="0" oninput="updateFades()">
                <label for="fadeTop">Oben</label>
                <input type="range" id="fadeTop" min="0" max="1000" value="0" oninput="updateFades()">
                <label for="fadeBottom">Unten</label>
                <input type="range" id="fadeBottom" min="0" max="1000" value="0" oninput="updateFades()">
            </div>

            <div class="control-group" id="text-properties" style="display:none;">
                <h3>Text Properties</h3>
                <label for="fontSizeInput">Font Size</label>
                <input type="number" id="fontSizeInput" min="10" max="200" oninput="updateSelectedFontSize()">
            </div>

            <div style="margin-top:auto">
                <button class="btn-export" onclick="saveImage()">💾 Exportieren (JPG)</button>
            </div>
        </div>

        <div class="main-view">
            <div id="canvas-wrapper">
                <canvas id="mainCanvas"></canvas>
            </div>
        </div>
    </div>

    <div id="settings-tab" class="tab-content">
        <div class="settings-grid">
            <div class="sidebar" style="width:100%; border:1px solid #333; border-radius:8px;">
                <h3>Jellyfin</h3>
                <label for="set-jf-url">Server URL</label>
                <input type="text" id="set-jf-url" value="{{ config.jellyfin.url }}">
                <label for="set-jf-key">API Key</label>
                <input type="password" id="set-jf-key" value="{{ config.jellyfin.api_key }}">
                <label for="set-jf-user">User ID</label>
                <input type="text" id="set-jf-user" value="{{ config.jellyfin.user_id }}">
            </div>
            <div class="sidebar" style="width:100%; border:1px solid #333; border-radius:8px;">
                <h3>TMDB</h3>
                <label for="set-tmdb-key">Bearer Token</label>
                <input type="password" id="set-tmdb-key" value="{{ config.tmdb.api_key }}">
                <label for="set-tmdb-lang">Sprache</label>
                <input type="text" id="set-tmdb-lang" value="{{ config.tmdb.language }}">
            </div>
            <button onclick="saveSettings()" style="grid-column: 1 / -1; max-width: 400px; margin: 20px auto;">Alle Einstellungen speichern</button>
        </div>
    </div>

    <script>
        let canvas;
        let mainBg = null;
        let fades = { left: null, right: null, top: null, bottom: null };

        function updateSelectionUI() {
            const activeObj = canvas.getActiveObject();
            const panel = document.getElementById('text-properties');
            if (activeObj && (activeObj.type === 'i-text' || activeObj.type === 'textbox')) {
                panel.style.display = 'block';
                document.getElementById('fontSizeInput').value = activeObj.fontSize;
            } else {
                panel.style.display = 'none';
            }
        }

        function updateSelectedFontSize() {
            const activeObj = canvas.getActiveObject();
            if (activeObj) {
                activeObj.set("fontSize", parseInt(document.getElementById('fontSizeInput').value));
                canvas.renderAll();
            }
        }

        function applyTruncation(textbox, textToDisplay) {
            const textSource = textToDisplay || textbox.fullMediaText || "";
            if (!textSource) { textbox.set('text', ''); return; }

            // Wir setzen zuerst den vollen Text, um die Zeilen zu berechnen
            textbox.set('text', textSource);
            
            // Falls der Text höher ist als die vom User gezogene Box
            if (textbox.height > textbox.fixedHeight) {
                let words = textSource.split(' ');
                let currentText = textSource;

                while (textbox.height > textbox.fixedHeight && words.length > 0) {
                    words.pop();
                    currentText = words.join(' ') + '...';
                    textbox.set('text', currentText);
                    // Wir müssen Fabric zwingen, die Höhe nach Textänderung neu zu berechnen
                    textbox.initDimensions(); 
                }
            }
            canvas.renderAll();
        }

        async function fetchRandomPreview() {
            const indicator = document.getElementById('source-indicator');
            indicator.innerText = "Fetching...";
            try {
                const response = await fetch('/api/media/random');
                const data = await response.json();
                if (data.backdrop_url) loadBackground(data.backdrop_url);

                canvas.getObjects().forEach(obj => {
                    if (obj.dataTag) {
                        let val = "";
                        switch(obj.dataTag) {
                            case 'title': val = data.title; break;
                            case 'year': val = data.year; break;
                            case 'rating': val = (data.rating !== 'N/A') ? `IMDb: ${data.rating}` : ''; break;
                            case 'overview': 
                                if (obj.type === 'textbox') {
                                    obj.fullMediaText = data.overview; // Speicher das Original
                                    applyTruncation(obj, data.overview); // Zeige nur was passt
                                } else {
                                    obj.set({ text: data.overview });
                                }
                                break;
                            case 'genres': val = data.genres; break;
                            case 'runtime': val = data.runtime; break;
                        }
                        if (val) obj.set({ text: String(val) });
                    }
                });
                indicator.innerText = "Source: " + data.source;
                canvas.renderAll();
            } catch (err) { indicator.innerText = "Error loading preview"; }
        }

        function addMetadataTag(type, placeholder) {
            let textObj;
            const props = { left: 200, top: 200, fontFamily: 'Segoe UI', fontSize: type === 'title' ? 80 : 35, fill: 'white', shadow: '2px 2px 10px rgba(0,0,0,0.8)', dataTag: type };
            if (type === 'overview') {
                textObj = new fabric.Textbox(placeholder, {
                    ...props,
                    width: 600,
                    height: 300,
                    fixedHeight: 300, // Unsere Referenz für das Abschneiden
                    splitByGrapheme: true,
                    lockScalingY: false,
                    fullMediaText: placeholder
                });
            } else {
                textObj = new fabric.IText(placeholder, props);
            }
            canvas.add(textObj);
            canvas.setActiveObject(textObj);
        }

        function init() {
            canvas = new fabric.Canvas('mainCanvas', { width: 1920, height: 1080, backgroundColor: '#000000', preserveObjectStacking: true });

            canvas.on('object:scaling', (e) => {
                const t = e.target;
                if (t instanceof fabric.Textbox) {
                    const newWidth = t.width * t.scaleX;
                    const newHeight = t.height * t.scaleY;
                    
                    // Wir speichern die neue Wunsch-Größe
                    t.set({
                        width: newWidth,
                        fixedHeight: newHeight, // Update der Grenze
                        scaleX: 1,
                        scaleY: 1
                    });

                    if (t.dataTag === 'overview') {
                        applyTruncation(t, t.fullMediaText);
                    }
                }
                if (t === mainBg) updateFades();
            });

            canvas.on('selection:created', updateSelectionUI);
            canvas.on('selection:updated', updateSelectionUI);
            canvas.on('selection:cleared', updateSelectionUI);
            canvas.on('object:moving', (e) => { if(e.target === mainBg) updateFades(); });

            window.addEventListener('keydown', (e) => {
                if (e.key === "Delete" || e.key === "Backspace") {
                    canvas.getActiveObjects().forEach(obj => { if (obj === mainBg) mainBg = null; canvas.remove(obj); });
                    canvas.discardActiveObject().requestRenderAll();
                }
            });

            loadBackground("{{ data.backdrop_url }}");
        }

        function loadBackground(url) {
            const proxiedUrl = `/api/proxy/image?url=${encodeURIComponent(url)}`;
            fabric.Image.fromURL(proxiedUrl, function(img, isError) {
                if (isError) return;
                if (mainBg) canvas.remove(mainBg);
                mainBg = img;
                img.set({ left: 0, top: 0, selectable: true });
                img.scaleToWidth(canvas.width);
                canvas.add(img);
                canvas.sendToBack(img);
                updateFades();
            }, { crossOrigin: 'anonymous' });
        }

        function updateFades() {
            if (!mainBg) return;
            ['left', 'right', 'top', 'bottom'].forEach(side => {
                if (fades[side]) canvas.remove(fades[side]);
                const val = document.getElementById('fade' + side.charAt(0).toUpperCase() + side.slice(1)).value;
                if (val > 0) {
                    fades[side] = createFadeRect(side, val);
                    canvas.add(fades[side]);
                    fades[side].moveTo(canvas.getObjects().indexOf(mainBg) + 1);
                }
            });
            canvas.renderAll();
        }

        function createFadeRect(type, size) {
            const bgColor = document.getElementById('bgColor').value;
            const b = 2; // bleed
            const wImg = mainBg.getScaledWidth();
            const hImg = mainBg.getScaledHeight();
            let w, h, x, y, c;
            if (type === 'left') { w = parseInt(size) + b; h = hImg + b*2; x = mainBg.left - b; y = mainBg.top - b; c = { x1: 0, y1: 0, x2: 1, y2: 0 }; }
            else if (type === 'right') { w = parseInt(size) + b; h = hImg + b*2; x = mainBg.left + wImg - size; y = mainBg.top - b; c = { x1: 1, y1: 0, x2: 0, y2: 0 }; }
            else if (type === 'top') { w = wImg + b*2; h = parseInt(size) + b; x = mainBg.left - b; y = mainBg.top - b; c = { x1: 0, y1: 0, x2: 0, y2: 1 }; }
            else if (type === 'bottom') { w = wImg + b*2; h = parseInt(size) + b; x = mainBg.left - b; y = mainBg.top + hImg - size; c = { x1: 0, y1: 1, x2: 0, y2: 0 }; }

            return new fabric.Rect({
                left: x, top: y, width: w, height: h, selectable: false, evented: false,
                fill: new fabric.Gradient({ type: 'linear', gradientUnits: 'percentage', coords: c, colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }] })
            });
        }

        function hexToRgba(hex, a) {
            let r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${a})`;
        }

        function updateBgColor() { canvas.setBackgroundColor(document.getElementById('bgColor').value, () => { updateFades(); canvas.renderAll(); }); }
        function openTab(evt, tabId) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }
        async function saveSettings() {
            const config = { jellyfin: { url: document.getElementById('set-jf-url').value, api_key: document.getElementById('set-jf-key').value, user_id: document.getElementById('set-jf-user').value }, tmdb: { api_key: document.getElementById('set-tmdb-key').value, language: document.getElementById('set-tmdb-lang').value } };
            const resp = await fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config) });
            if(resp.ok) alert("Gespeichert!");
        }
        function changeResolution() {
            const res = document.getElementById('resSelect').value;
            const targetW = (res === '2160') ? 3840 : 1920;
            const scale = targetW / canvas.width;
            canvas.setDimensions({ width: targetW, height: (res === '2160' ? 2160 : 1080) });
            canvas.getObjects().forEach(obj => { obj.scaleX *= scale; obj.scaleY *= scale; obj.left *= scale; obj.top *= scale; obj.setCoords(); });
            updateFades();
        }
        function saveImage() { const l = document.createElement('a'); l.href = canvas.toDataURL({ format: 'jpeg', quality: 0.95 }); l.download = 'tv-background.jpg'; l.click(); }
        window.onload = init;
    </script>
</body>
</html>
"""

if __name__ == '__main__':
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(gui_editor_bp)
    app.run(debug=True, port=5000)