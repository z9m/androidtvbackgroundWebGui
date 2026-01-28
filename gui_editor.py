import os
import json
from flask import Blueprint, render_template_string, request, jsonify, send_from_directory, url_for

gui_editor_bp = Blueprint('gui_editor', __name__)
CONFIG_FILE = 'config.json'

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try: return json.load(f)
            except: pass
    return {
        "jellyfin": {"url": "", "api_key": "", "user_id": ""},
        "plex": {"url": "", "token": ""},
        "tmdb": {"api_key": "", "language": "de-DE"},
        "editor": {"resolution": "1080"}
    }

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

@gui_editor_bp.route('/api/settings', methods=['POST'])
def update_settings():
    save_config(request.json)
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/jellyfin/recent')
def get_jellyfin_recent():
    config = load_config().get('jellyfin', {})
    if not config.get('url') or not config.get('api_key'):
        return jsonify({"error": "Jellyfin not configured"}), 400
    
    headers = {"X-Emby-Token": config['api_key']}
    url = f"{config['url']}/Users/{config['user_id']}/Items"
    params = {
        "SortBy": "DateCreated",
        "SortOrder": "Descending",
        "IncludeItemTypes": "Movie",
        "Limit": 10,
        "Recursive": "true",
        "Fields": "ProductionYear,Overview,CommunityRating"
    }
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=5)
        r.raise_for_status()
        return jsonify(r.json().get('Items', []))
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@gui_editor_bp.route('/get_local_background')
def get_local_background():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_dir, 'background.jpg')

@gui_editor_bp.route('/editor')
def editor_index():
    config = load_config()
    data = {"title": "TV Background", "backdrop_url": url_for('gui_editor.get_local_background')}
    return render_template_string(EDITOR_TEMPLATE, data=data, config=config)

EDITOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TV Background Suite</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
    <style>
        :root { --primary: #2e7d32; --bg: #0a0a0a; --panel: #181818; --text: #eee; --sidebar-w: 320px; }
        body { background: var(--bg); color: var(--text); font-family: 'Segoe UI', sans-serif; margin: 0; display: flex; flex-direction: column; height: 100vh; overflow: hidden; }
        
        /* Navigation */
        .nav-tabs { display: flex; background: #000; padding: 0 20px; border-bottom: 1px solid #333; height: 50px; flex-shrink: 0; }
        .tab-link { padding: 15px 25px; cursor: pointer; border-bottom: 3px solid transparent; font-size: 14px; }
        .tab-link.active { border-bottom-color: var(--primary); background: var(--panel); }

        .tab-content { display: none; flex: 1; overflow: hidden; }
        .tab-content.active { display: flex; }

        /* Sidebar Layout */
        .sidebar { 
            width: var(--sidebar-w); background: var(--panel); border-right: 1px solid #333; 
            padding: 20px; box-sizing: border-box; overflow-y: auto; display: flex; flex-direction: column; gap: 20px;
        }
        .main-view { flex: 1; display: flex; align-items: center; justify-content: center; padding: 40px; background: #111; position: relative; overflow: auto; }

        /* Sidebar Controls */
        .control-group { border-bottom: 1px solid #333; padding-bottom: 15px; }
        .control-group:last-child { border: none; }
        h3 { font-size: 12px; text-transform: uppercase; color: #888; margin: 0 0 10px 0; letter-spacing: 1px; }
        
        label { font-size: 11px; color: #666; display: block; margin-top: 8px; }
        input, select, button { 
            padding: 8px; border-radius: 4px; border: 1px solid #444; 
            background: #222; color: white; width: 100%; margin-top: 5px; box-sizing: border-box; font-size: 13px;
        }
        input[type="range"] { padding: 0; }
        button { background: var(--primary); border: none; font-weight: bold; cursor: pointer; margin-top: 10px; }
        button:hover { background: #388e3c; }
        .btn-export { background: #1565c0; margin-top: 20px; }

        /* Canvas */
        #canvas-wrapper { 
            width: 100%; max-width: 1200px; aspect-ratio: 16 / 9; 
            background: #000; border: 2px solid #333; box-shadow: 0 20px 50px rgba(0,0,0,0.8);
        }
        .canvas-container { width: 100% !important; height: 100% !important; }
        canvas { width: 100% !important; height: 100% !important; }

        /* Settings Tab (Full width) */
        #settings-tab { padding: 40px; overflow-y: auto; align-items: center; }
        .settings-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; width: 100%; max-width: 1000px; }
    </style>
</head>
<body>

    <div class="nav-tabs">
        <div class="tab-link active" onclick="openTab(event, 'editor-tab')">🎨 Layout Editor</div>
        <div class="tab-link" onclick="openTab(event, 'settings-tab')">⚙️ Provider Settings</div>
    </div>

    <!-- TAB: EDITOR -->
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
                    <button onclick="addMetadataTag('overview', 'This is a sample movie description text...')">Overview</button>
                </div>
                <p style="font-size: 10px; color: #555; margin-top: 5px;">Click to add placeholder to canvas</p>
            </div>
            <div class="control-group">
                <h3>Leinwand</h3>
                <label>Ziel-Auflösung</label>
                <select id="resSelect" onchange="changeResolution()">
                    <option value="1080">1080p (Full HD)</option>
                    <option value="2160">2160p (4K)</option>
                </select>
                <label>Hintergrundfarbe</label>
                <input type="color" id="bgColor" oninput="updateBgColor()" value="#000000">
            </div>

            <div class="control-group">
                <h3>Fade-Out Kanten</h3>
                <label>Links</label>
                <input type="range" id="fadeLeft" min="0" max="1000" value="0" oninput="updateFades()">
                <label>Rechts</label>
                <input type="range" id="fadeRight" min="0" max="1000" value="0" oninput="updateFades()">
                <label>Oben</label>
                <input type="range" id="fadeTop" min="0" max="1000" value="0" oninput="updateFades()">
                <label>Unten</label>
                <input type="range" id="fadeBottom" min="0" max="1000" value="0" oninput="updateFades()">
            </div>

            <div class="control-group">
                <h3>Elemente</h3>
                <button onclick="addTitle()">+ Text hinzufügen</button>
            </div>

            <div style="margin-top:auto">
                <button class="btn-export" onclick="saveImage()">💾 Exportieren (JPG)</button>
                <p style="font-size:10px; color:#555; text-align:center; margin-top:10px;">Markierte Objekte mit Entf-Taste löschen</p>
            </div>
        </div>

        <div class="main-view">
            <div id="canvas-wrapper">
                <canvas id="mainCanvas"></canvas>
            </div>
        </div>
    </div>

    <!-- TAB: SETTINGS -->
    <div id="settings-tab" class="tab-content">
        <div class="settings-grid">
            <div class="sidebar" style="width:100%; border:1px solid #333; border-radius:8px;">
                <h3>Jellyfin</h3>
                <label>Server URL</label>
                <input type="text" id="set-jf-url" value="{{ config.jellyfin.url }}">
                <label>API Key</label>
                <input type="password" id="set-jf-key" value="{{ config.jellyfin.api_key }}">
                <label>User ID</label>
                <input type="text" id="set-jf-user" value="{{ config.jellyfin.user_id }}">
            </div>
            <div class="sidebar" style="width:100%; border:1px solid #333; border-radius:8px;">
                <h3>TMDB</h3>
                <label>Bearer Token</label>
                <input type="password" id="set-tmdb-key" value="{{ config.tmdb.api_key }}">
                <label>Sprache</label>
                <input type="text" id="set-tmdb-lang" value="{{ config.tmdb.language }}">
            </div>
            <button onclick="saveSettings()" style="grid-column: 1 / -1; max-width: 400px; margin: 20px auto;">Alle Einstellungen speichern</button>
        </div>
    </div>

    <script>
        let canvas;
        let mainBg = null;
        let fades = { left: null, right: null, top: null, bottom: null };

        /**
        * Fills all data-tags on canvas with real media data.
        * @param {Object} mediaData - Data fetched from Jellyfin API.
        */
        function previewTemplate(mediaData) {
            canvas.getObjects().forEach(obj => {
                if (obj.dataTag) {
                    switch(obj.dataTag) {
                        case 'title': obj.text = mediaData.Name; break;
                        case 'year': obj.text = mediaData.ProductionYear.toString(); break;
                        case 'rating': obj.text = `IMDb: ${mediaData.CommunityRating}`; break;
                        // Add more cases as needed...
                    }
                }
            });
            canvas.renderAll();
        }

        /**
        * Adds a metadata placeholder to the canvas.
        * @param {string} type - The Jellyfin metadata field name.
        * @param {string} placeholder - Default text to display in editor.
        */
        function addMetadataTag(type, placeholder) {
            const textObj = new fabric.IText(placeholder, {
                left: 200,
                top: 200,
                fontFamily: 'Segoe UI',
                fontSize: type === 'title' ? 80 : 30,
                fontWeight: type === 'title' ? 'bold' : 'normal',
                fill: 'white',
                shadow: '2px 2px 10px rgba(0,0,0,0.8)',
                // Custom property to identify the tag during export
                dataTag: type 
            });
            
            // Style specific tags differently by default
            if (type === 'overview') {
                textObj.set({
                    fontSize: 25,
                    width: 600,
                    splitByGrapheme: true // Enables word wrapping
                });
            }

            canvas.add(textObj);
            canvas.setActiveObject(textObj);
        }

        async function fetchJellyfinRecent() {
            const listContainer = document.getElementById('media-list');
            listContainer.innerHTML = '<p style="font-size:10px">Loading...</p>';
            
            try {
                const response = await fetch('/api/jellyfin/recent');
                const items = await response.json();
                
                if (items.error) throw new Error(items.error);

                listContainer.innerHTML = '';
                items.forEach(item => {
                    const btn = document.createElement('button');
                    btn.className = 'media-item-btn'; // Optional: add some CSS for this
                    btn.style.fontSize = '11px'; btn.style.textAlign = 'left'; btn.style.background = '#222';
                    btn.innerText = `${item.Name} (${item.ProductionYear || 'N/A'})`;
                    btn.onclick = () => loadJellyfinItem(item);
                    listContainer.appendChild(btn);
                });
            } catch (err) {
                listContainer.innerHTML = `<p style="color:red; font-size:10px">Error: ${err.message}</p>`;
            }
        }

        function loadJellyfinItem(item) {
            // Get current config values from settings inputs
            const baseUrl = document.getElementById('set-jf-url').value;
            const apiKey = document.getElementById('set-jf-key').value;
            
            // 1. Load Backdrop
            const backdropUrl = `${baseUrl}/Items/${item.Id}/Images/Backdrop?api_key=${apiKey}`;
            if (mainBg) canvas.remove(mainBg);
            
            fabric.Image.fromURL(backdropUrl, function(img) {
                mainBg = img;
                img.set({ left: 0, top: 0, selectable: true });
                img.scaleToWidth(canvas.width);
                canvas.add(img);
                canvas.sendToBack(img);
                updateFades();
            }, { crossOrigin: 'anonymous' });

            // 2. Add Title (as an editable text object)
            const title = new fabric.IText(item.Name.toUpperCase(), {
                left: 150, top: canvas.height - 250,
                fontFamily: 'Segoe UI', fontSize: 120, fontWeight: 'bold', fill: 'white',
                shadow: '2px 2px 20px rgba(0,0,0,0.8)'
            });
            canvas.add(title);
            
            // 3. Add Year/Rating Info
            const info = new fabric.IText(`${item.ProductionYear}  |  IMDb: ${item.CommunityRating || 'N/A'}`, {
                left: 150, top: canvas.height - 120,
                fontFamily: 'Segoe UI', fontSize: 40, fill: '#ccc'
            });
            canvas.add(info);
        }

        function openTab(evt, tabId) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active'));
            document.getElementById(tabId).classList.add('active');
            evt.currentTarget.classList.add('active');
        }

        async function saveSettings() {
            const config = {
                jellyfin: {
                    url: document.getElementById('set-jf-url').value,
                    api_key: document.getElementById('set-jf-key').value,
                    user_id: document.getElementById('set-jf-user').value
                },
                tmdb: {
                    api_key: document.getElementById('set-tmdb-key').value,
                    language: document.getElementById('set-tmdb-lang').value
                }
            };
            const resp = await fetch('/api/settings', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(config)
            });
            if(resp.ok) alert("Gespeichert!");
        }

        function init() {
            canvas = new fabric.Canvas('mainCanvas', {
                width: 1920, height: 1080, backgroundColor: '#000000', preserveObjectStacking: true
            });

            window.addEventListener('keydown', (e) => {
                if (e.key === "Delete" || e.key === "Backspace") {
                    canvas.getActiveObjects().forEach(obj => {
                        if (obj === mainBg) mainBg = null;
                        canvas.remove(obj);
                    });
                    canvas.discardActiveObject().requestRenderAll();
                }
            });

            canvas.on('object:moving', (e) => { if(e.target === mainBg) updateFades(); });
            canvas.on('object:scaling', (e) => { if(e.target === mainBg) updateFades(); });

            loadBackground("{{ data.backdrop_url }}");
        }

        function loadBackground(url) {
            fabric.Image.fromURL(url, function(img, isError) {
                if (isError) return;
                mainBg = img;
                img.set({ left: 0, top: 0, selectable: true });
                img.scaleToWidth(canvas.width);
                canvas.add(img);
                canvas.sendToBack(img);
                updateFades();
            }); 
        }

        function updateBgColor() {
            const color = document.getElementById('bgColor').value;
            canvas.setBackgroundColor(color, () => { updateFades(); canvas.renderAll(); });
        }

        function hexToRgba(hex, alpha) {
            let r = parseInt(hex.slice(1, 3), 16),
                g = parseInt(hex.slice(3, 5), 16),
                b = parseInt(hex.slice(5, 7), 16);
            return `rgba(${r}, ${g}, ${b}, ${alpha})`;
        }

        function createFadeRect(type, size) {
            if (!mainBg) return null;
            const bgColor = document.getElementById('bgColor').value;
            const imgWidth = mainBg.getScaledWidth();
            const imgHeight = mainBg.getScaledHeight();
            const bleed = 2;

            let w, h, x, y, coords;
            if (type === 'left') {
                w = parseInt(size) + bleed; h = imgHeight + (bleed*2); x = mainBg.left - bleed; y = mainBg.top - bleed;
                coords = { x1: 0, y1: 0, x2: 1, y2: 0 };
            } else if (type === 'right') {
                w = parseInt(size) + bleed; h = imgHeight + (bleed*2); x = mainBg.left + imgWidth - size; y = mainBg.top - bleed;
                coords = { x1: 1, y1: 0, x2: 0, y2: 0 };
            } else if (type === 'top') {
                w = imgWidth + (bleed*2); h = parseInt(size) + bleed; x = mainBg.left - bleed; y = mainBg.top - bleed;
                coords = { x1: 0, y1: 0, x2: 0, y2: 1 };
            } else if (type === 'bottom') {
                w = imgWidth + (bleed*2); h = parseInt(size) + bleed; x = mainBg.left - bleed; y = mainBg.top + imgHeight - size;
                coords = { x1: 0, y1: 1, x2: 0, y2: 0 };
            }

            return new fabric.Rect({
                left: x, top: y, width: w, height: h, selectable: false, evented: false,
                fill: new fabric.Gradient({
                    type: 'linear', gradientUnits: 'percentage', coords: coords,
                    colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }]
                })
            });
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

        function addTitle() {
            canvas.add(new fabric.IText("TEXT HIER", { left: 100, top: 100, fill: 'white', fontSize: 60, fontFamily: 'Segoe UI' }));
        }

        function changeResolution() {
            const res = document.getElementById('resSelect').value;
            const targetW = (res === '2160') ? 3840 : 1920;
            const targetH = (res === '2160') ? 2160 : 1080;
            const scale = targetW / canvas.width;
            canvas.setDimensions({ width: targetW, height: targetH });
            canvas.getObjects().forEach(obj => {
                obj.scaleX *= scale; obj.scaleY *= scale;
                obj.left *= scale; obj.top *= scale;
                obj.setCoords();
            });
            updateFades();
        }

        function saveImage() {
            const link = document.createElement('a');
            link.href = canvas.toDataURL({ format: 'jpeg', quality: 0.95 });
            link.download = 'tv-background.jpg';
            link.click();
        }

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