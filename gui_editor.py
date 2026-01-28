import os
from flask import Blueprint, render_template_string, send_from_directory, url_for

gui_editor_bp = Blueprint('gui_editor', __name__)

@gui_editor_bp.route('/get_local_background')
def get_local_background():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if not os.path.exists(os.path.join(current_dir, 'background.jpg')):
        return "background.jpg nicht gefunden", 404
    return send_from_directory(current_dir, 'background.jpg')

@gui_editor_bp.route('/editor')
def editor_index():
    mock_data = {
        "title": "Android TV Hintergrund",
        "backdrop_url": url_for('gui_editor.get_local_background'), 
    }
    return render_template_string(EDITOR_TEMPLATE, data=mock_data)

EDITOR_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>TV Layout Editor Pro</title>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/fabric.js/5.3.1/fabric.min.js"></script>
    <style>
        body { background: #121212; color: white; font-family: 'Segoe UI', sans-serif; margin: 0; padding: 10px; display: flex; flex-direction: column; align-items: center; }
        .toolbar { 
            background: #1f1f1f; padding: 15px; width: 100%; max-width: 1250px;
            display: flex; gap: 15px; justify-content: center; align-items: center; 
            border-radius: 8px; margin-bottom: 15px; flex-wrap: wrap; box-shadow: 0 4px 10px rgba(0,0,0,0.5);
        }
        .fade-controls { 
            display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px; 
            background: #252525; padding: 10px; border-radius: 6px; border: 1px solid #333;
        }
        .control-item { display: flex; flex-direction: column; align-items: center; gap: 2px; }
        .control-item label { font-size: 10px; color: #aaa; text-transform: uppercase; }

        #canvas-wrapper {
            width: 100%; max-width: 1200px; aspect-ratio: 16 / 9;
            background: #000; border: 1px solid #333; position: relative;
        }
        .canvas-container { width: 100% !important; height: 100% !important; }
        canvas { width: 100% !important; height: 100% !important; }

        button, select, input[type="color"] { padding: 8px; border-radius: 4px; border: 1px solid #444; background: #333; color: white; cursor: pointer; }
        input[type="range"] { width: 80px; cursor: pointer; }
        .btn-save { background: #2e7d32; border: none; font-weight: bold; padding: 8px 15px; }
    </style>
</head>
<body>

    <div class="toolbar">
        <select id="resSelect" onchange="changeResolution()">
            <option value="1080">1080p</option>
            <option value="2160">4K</option>
        </select>
        
        <input type="color" id="bgColor" oninput="updateBgColor()" value="#000000">

        <div class="fade-controls">
            <div class="control-item"><label>Links</label><input type="range" id="fadeLeft" min="0" max="1000" value="0" oninput="updateFades()"></div>
            <div class="control-item"><label>Rechts</label><input type="range" id="fadeRight" min="0" max="1000" value="0" oninput="updateFades()"></div>
            <div class="control-item"><label>Oben</label><input type="range" id="fadeTop" min="0" max="1000" value="0" oninput="updateFades()"></div>
            <div class="control-item"><label>Unten</label><input type="range" id="fadeBottom" min="0" max="1000" value="0" oninput="updateFades()"></div>
        </div>

        <button onclick="addTitle()">Text +</button>
        <button class="btn-save" onclick="saveImage()">Export JPG</button>
    </div>

    <div id="canvas-wrapper">
        <canvas id="mainCanvas"></canvas>
    </div>

    <script>
        let canvas;
        let mainBg = null;
        let fades = { left: null, right: null, top: null, bottom: null };

        function init() {
            canvas = new fabric.Canvas('mainCanvas', {
                width: 1920, height: 1080,
                backgroundColor: '#000000',
                preserveObjectStacking: true
            });

            // Überwachung von Bewegungen und Skalierungen
            canvas.on('object:moving', (e) => { if(e.target === mainBg) updateFades(); });
            canvas.on('object:scaling', (e) => { if(e.target === mainBg) updateFades(); });

            window.addEventListener('keydown', (e) => {
                if (e.key === "Delete" || e.key === "Backspace") {
                    canvas.getActiveObjects().forEach(obj => {
                        if (obj === mainBg) mainBg = null;
                        canvas.remove(obj);
                    });
                    canvas.discardActiveObject().requestRenderAll();
                }
            });

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
            canvas.setBackgroundColor(color, () => {
                updateFades();
                canvas.renderAll();
            });
        }

        function createFadeRect(type, size) {
            if (!mainBg) return null;
            
            const bgColor = document.getElementById('bgColor').value;
            const imgWidth = mainBg.getScaledWidth();
            const imgHeight = mainBg.getScaledHeight();
            const imgLeft = mainBg.left;
            const imgTop = mainBg.top;
            
            let w, h, x, y, coords;
            
            // Wir fügen einen "Bleed" (Überlappung) von 2 Pixeln hinzu, 
            // um die Kante des Bildes sicher abzudecken.
            const bleed = 2;

            if (type === 'left') {
                w = parseInt(size) + bleed; 
                h = imgHeight + (bleed * 2); 
                x = imgLeft - bleed; 
                y = imgTop - bleed;
                coords = { x1: 0, y1: 0, x2: 1, y2: 0 };
            } else if (type === 'right') {
                w = parseInt(size) + bleed; 
                h = imgHeight + (bleed * 2); 
                x = imgLeft + imgWidth - size; 
                y = imgTop - bleed;
                coords = { x1: 1, y1: 0, x2: 0, y2: 0 };
            } else if (type === 'top') {
                w = imgWidth + (bleed * 2); 
                h = parseInt(size) + bleed; 
                x = imgLeft - bleed; 
                y = imgTop - bleed;
                coords = { x1: 0, y1: 0, x2: 0, y2: 1 };
            } else if (type === 'bottom') {
                w = imgWidth + (bleed * 2); 
                h = parseInt(size) + bleed; 
                x = imgLeft - bleed; 
                y = imgTop + imgHeight - size;
                coords = { x1: 0, y1: 1, x2: 0, y2: 0 };
            }

            return new fabric.Rect({
                left: x,
                top: y,
                width: w,
                height: h,
                selectable: false,
                evented: false,
                strokeWidth: 0, // Wichtig: keinen Rahmen zeichnen
                fill: new fabric.Gradient({
                    type: 'linear',
                    gradientUnits: 'percentage',
                    coords: coords,
                    colorStops: [
                        { offset: 0, color: bgColor }, // Startet mit voller Hintergrundfarbe
                        { offset: 1, color: hexToRgba(bgColor, 0) } // Fadet aus
                    ]
                })
            });
        }

        function updateFades() {
            if (!mainBg) return;

            ['left', 'right', 'top', 'bottom'].forEach(side => {
                // Bestehendes Fade-Objekt löschen
                if (fades[side]) canvas.remove(fades[side]);
                
                const val = document.getElementById('fade' + side.charAt(0).toUpperCase() + side.slice(1)).value;
                if (val > 0) {
                    fades[side] = createFadeRect(side, val);
                    canvas.add(fades[side]);
                    
                    // Sicherstellen, dass die Fades genau ÜBER dem Bild liegen
                    const bgIndex = canvas.getObjects().indexOf(mainBg);
                    fades[side].moveTo(bgIndex + 1);
                }
            });
            canvas.renderAll();
        }

        function hexToRgba(hex, alpha) {
            let r = parseInt(hex.slice(1, 3), 16),
                g = parseInt(hex.slice(3, 5), 16),
                b = parseInt(hex.slice(5, 7), 16);
            // 0.01 statt 0 hilft manchmal gegen Aliasing-Artefakte
            let finalAlpha = (alpha === 0) ? 0.005 : alpha; 
            return `rgba(${r}, ${g}, ${b}, ${finalAlpha})`;
        }

        function addTitle() {
            const t = new fabric.IText("NEUER TITEL", { 
                left: 200, top: 200, fill: 'white', fontSize: 80, fontWeight: 'bold', fontFamily: 'sans-serif' 
            });
            canvas.add(t);
            canvas.setActiveObject(t);
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
            const dataURL = canvas.toDataURL({ format: 'jpeg', quality: 0.95 });
            const link = document.createElement('a');
            link.href = dataURL; link.download = 'tv-background.jpg'; link.click();
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