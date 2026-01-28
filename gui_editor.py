from nicegui import ui, app, events
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageFont, ImageOps, ImageStat
import os

# --- KONFIGURATION ---
INPUT_FILE = 'background.jpg'
INTERNAL_WIDTH = 1280 
INTERNAL_HEIGHT = 720

if not os.path.exists(INPUT_FILE):
    img = Image.new('RGB', (1920, 1080), color='gray')
    img.save(INPUT_FILE)

app.add_static_files('/static', '.')

# --- JAVASCRIPT (Responsive, Drag & Overlays) ---
ui.add_head_html('<script src="https://cdn.jsdelivr.net/npm/interactjs/dist/interact.min.js"></script>')

# CSS für die Overlays (Fade & Blur)
# Wir nutzen pointer-events-none, damit man "durch" die Effekte hindurch das Bild greifen kann
ui.add_head_html('''
<style>
    .overlay-effect {
        position: absolute;
        pointer-events: none;
        z-index: 10; /* Über dem Bild, unter dem Text */
    }
    .blur-layer {
        backdrop-filter: blur(var(--blur-strength));
        -webkit-backdrop-filter: blur(var(--blur-strength));
        z-index: 11;
    }
</style>
''')

drag_script = f"""
<script>
    var canvasScale = 1.0;

    function fitCanvas() {{
        const container = document.getElementById('canvas-container');
        const canvas = document.getElementById('editor-canvas');
        if (!container || !canvas) return;

        const availWidth = container.clientWidth - 40; 
        const availHeight = container.clientHeight - 40;
        const baseWidth = {INTERNAL_WIDTH};
        const baseHeight = {INTERNAL_HEIGHT};

        canvasScale = Math.min(availWidth / baseWidth, availHeight / baseHeight); 
        canvas.style.transform = 'translate(-50%, -50%) scale(' + canvasScale + ')';
    }}

    window.addEventListener('resize', fitCanvas);
    setTimeout(fitCanvas, 50);
    new ResizeObserver(fitCanvas).observe(document.body);

    // --- DRAG LOGIK ---
    interact('.draggable-element').draggable({{
        listeners: {{
            move (event) {{
                var target = event.target;
                var x = (parseFloat(target.getAttribute('data-x')) || 0) + (event.dx / canvasScale);
                var y = (parseFloat(target.getAttribute('data-y')) || 0) + (event.dy / canvasScale);
                target.style.transform = 'translate(' + x + 'px, ' + y + 'px)';
                target.setAttribute('data-x', x);
                target.setAttribute('data-y', y);
            }},
            end (event) {{
                var el_id = event.target.id.replace('el-', '');
                emitEvent('element_drag_end', {{
                    id: parseInt(el_id),
                    x: parseFloat(event.target.getAttribute('data-x')), 
                    y: parseFloat(event.target.getAttribute('data-y'))
                }});
            }}
        }}
    }});

    interact('#bg-img').draggable({{
        listeners: {{
            move (event) {{
                var target = event.target;
                var x = (parseFloat(target.getAttribute('data-x')) || 0) + (event.dx / canvasScale);
                var y = (parseFloat(target.getAttribute('data-y')) || 0) + (event.dy / canvasScale);
                var s = parseFloat(target.getAttribute('data-scale')) || 1.0;
                
                // Wir bewegen nur das Bild, die Overlays (Fade/Blur) bleiben am Canvas-Rand fixiert
                target.style.transform = 'translate(' + x + 'px, ' + y + 'px) scale(' + s + ')';
                target.setAttribute('data-x', x);
                target.setAttribute('data-y', y);
            }},
            end (event) {{
                emitEvent('bg_drag_end', {{
                    x: parseFloat(event.target.getAttribute('data-x')),
                    y: parseFloat(event.target.getAttribute('data-y'))
                }});
            }}
        }}
    }});
</script>
"""

# --- STATE ---
state = {
    'elements': [],
    'selected_id': None,
    'bg': {
        'x': 0.0, 'y': 0.0, 'scale': 1.0, 
        'blur': 0, 'brightness': 100
    },
    'canvas': {
        'color': '#000000', # Standard Schwarz
        'fade': {'top': 0, 'bottom': 0, 'left': 0, 'right': 0}, # 0-100% Breite des Übergangs
        'edge_blur': {'top': False, 'bottom': False, 'left': False, 'right': False, 'strength': 10}
    }
}

# --- HELPER FUNCTIONS ---

def get_dominant_color():
    """Berechnet die dominante Farbe des Hintergrundbildes"""
    try:
        img = Image.open(INPUT_FILE).convert('RGB')
        # Wir verkleinern extrem, um den Durchschnitt zu bekommen
        img = img.resize((1, 1), resample=Image.Resampling.LANCZOS)
        color = img.getpixel((0, 0))
        return '#{:02x}{:02x}{:02x}'.format(*color)
    except:
        return '#000000'

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def add_element(label, type='text'):
    new_id = len(state['elements']) + 1
    state['elements'].append({
        'id': new_id, 'label': label, 'x': INTERNAL_WIDTH/2 - 50, 'y': INTERNAL_HEIGHT/2 - 20,
        'size': 60, 'color': '#FFFFFF', 'type': type
    })
    render_ui.refresh()
    select_element(new_id)

def select_element(el_id):
    state['selected_id'] = el_id
    for el in state['elements']:
        is_selected = (el['id'] == el_id)
        ui.run_javascript(f"""
            var el = document.getElementById('el-{el['id']}');
            if (el) {{
                if ({str(is_selected).lower()}) el.classList.add('outline', 'outline-2', 'outline-yellow-400');
                else el.classList.remove('outline', 'outline-2', 'outline-yellow-400');
            }}
        """)
    
    # Sidebar Umschaltung
    if el_id:
        el = get_element(el_id)
        sidebar_color.value = el['color']
        sidebar_size.value = el['size']
        bg_controls.set_visibility(False)
        canvas_controls.set_visibility(False)
        el_controls.set_visibility(True)
        label_header.text = "Element bearbeiten"
    else:
        # Wenn nichts gewählt ist -> Canvas/Hintergrund Settings
        bg_controls.set_visibility(True)
        canvas_controls.set_visibility(True)
        el_controls.set_visibility(False)
        label_header.text = "Bild & Canvas"

def get_element(el_id):
    return next((e for e in state['elements'] if e['id'] == el_id), None)

def update_element_prop(prop, value):
    el = get_element(state['selected_id'])
    if not el: return
    el[prop] = value
    if prop == 'color': ui.run_javascript(f"document.getElementById('el-{el['id']}').style.color = '{value}'")
    elif prop == 'size': ui.run_javascript(f"document.getElementById('el-{el['id']}').style.fontSize = '{value}px'")

# --- UPDATE LOGIK FÜR JS (LIVE PREVIEW) ---

def update_bg():
    s = state['bg']
    ui.run_javascript(f"""
        var bg = document.getElementById('bg-img');
        if(bg) {{
            // Globaler Blur Filter für das Bild selbst
            bg.style.filter = 'blur({s['blur']}px) brightness({s['brightness']}%)';
            bg.style.transform = 'translate({s['x']}px, {s['y']}px) scale({s['scale']})';
            bg.setAttribute('data-scale', {s['scale']});
        }}
    """)

def update_canvas_effects():
    c = state['canvas']['color']
    f = state['canvas']['fade']
    b = state['canvas']['edge_blur']
    
    # 1. Canvas Farbe
    ui.run_javascript(f"document.getElementById('editor-canvas').style.backgroundColor = '{c}';")

    # 2. Fade Overlays (Wir nutzen CSS Gradients von 'transparent' zu 'canvas_color')
    # Die Overlays liegen am Rand und simulieren das "Verschwinden" des Bildes
    # Wir konvertieren Hex zu RGB für CSS rgba() Transparenz
    # (Einfacher Trick: Overlay ist solid color mit Gradient-Mask oder Gradient zu Transparent)
    
    # Hier bauen wir 4 Divs für die Fade-Ränder
    # Top Fade
    ui.run_javascript(f"""
        document.getElementById('fade-top').style.height = '{f['top']}%';
        document.getElementById('fade-top').style.background = 'linear-gradient(to bottom, {c}, transparent)';
        
        document.getElementById('fade-bottom').style.height = '{f['bottom']}%';
        document.getElementById('fade-bottom').style.background = 'linear-gradient(to top, {c}, transparent)';
        
        document.getElementById('fade-left').style.width = '{f['left']}%';
        document.getElementById('fade-left').style.background = 'linear-gradient(to right, {c}, transparent)';
        
        document.getElementById('fade-right').style.width = '{f['right']}%';
        document.getElementById('fade-right').style.background = 'linear-gradient(to left, {c}, transparent)';
    """)

    # 3. Edge Blur Overlays
    # Wir setzen die Stärke als CSS Variable
    ui.run_javascript(f"document.getElementById('editor-canvas').style.setProperty('--blur-strength', '{b['strength']}px');")
    
    # Sichtbarkeit der Blur-Ebenen
    ui.run_javascript(f"""
        document.getElementById('blur-top').style.display = '{'block' if b['top'] else 'none'}';
        document.getElementById('blur-bottom').style.display = '{'block' if b['bottom'] else 'none'}';
        document.getElementById('blur-left').style.display = '{'block' if b['left'] else 'none'}';
        document.getElementById('blur-right').style.display = '{'block' if b['right'] else 'none'}';
    """)


# --- EVENTS ---
def handle_element_drag_end(e: events.GenericEventArguments):
    el = get_element(e.args['id'])
    if el:
        el['x'] = e.args['x']; el['y'] = e.args['y']
        select_element(el['id'])

def handle_bg_drag_end(e: events.GenericEventArguments):
    state['bg']['x'] = e.args['x']; state['bg']['y'] = e.args['y']
    select_element(None)

def set_auto_color():
    c = get_dominant_color()
    state['canvas']['color'] = c
    color_picker_ui.set_value(c) # UI Sync
    update_canvas_effects()

# --- EXPORT LOGIK (PILLOW) ---
def export_image():
    try:
        base = Image.open(INPUT_FILE).convert('RGB')
        
        # 1. Canvas erstellen
        canvas_color = ImageColor.getrgb(state['canvas']['color'])
        final_canvas = Image.new('RGB', (INTERNAL_WIDTH, INTERNAL_HEIGHT), canvas_color)
        
        # 2. Hintergrund bearbeiten (Resize/Scale)
        bg = base.copy().resize((INTERNAL_WIDTH, INTERNAL_HEIGHT))
        if state['bg']['scale'] != 1.0:
            new_w = int(INTERNAL_WIDTH * state['bg']['scale'])
            new_h = int(INTERNAL_HEIGHT * state['bg']['scale'])
            bg = bg.resize((new_w, new_h), resample=Image.Resampling.LANCZOS)
        
        # Globale Filter
        if state['bg']['blur'] > 0: 
            bg = bg.filter(ImageFilter.GaussianBlur(state['bg']['blur']))
        bg = ImageEnhance.Brightness(bg).enhance(state['bg']['brightness'] / 100.0)
        
        # 3. Compositing Vorbereitung (für Positionierung)
        # Wir erstellen einen temporären Layer, so groß wie das skalierte Bild
        layer = Image.new('RGBA', bg.size, (0,0,0,0))
        layer.paste(bg, (0,0))
        
        # 4. KANTEN UNSCHÄRFE (Edge Blur)
        # Wenn aktiv, erstellen wir eine unscharfe Kopie und maskieren sie
        edge_b = state['canvas']['edge_blur']
        if any([edge_b['top'], edge_b['bottom'], edge_b['left'], edge_b['right']]):
            blurred_bg = bg.filter(ImageFilter.GaussianBlur(edge_b['strength']))
            
            # Maske für den Blur (Weiß = Blur sichtbar)
            blur_mask = Image.new('L', (INTERNAL_WIDTH, INTERNAL_HEIGHT), 0)
            draw = ImageDraw.Draw(blur_mask)
            
            # Zonen definieren (feste 15% Breite für den Blur-Effekt am Rand, kann man anpassen)
            bw_h = int(INTERNAL_HEIGHT * 0.15) 
            bw_w = int(INTERNAL_WIDTH * 0.15)
            
            if edge_b['top']: draw.rectangle([0, 0, INTERNAL_WIDTH, bw_h], fill=255)
            if edge_b['bottom']: draw.rectangle([0, INTERNAL_HEIGHT - bw_h, INTERNAL_WIDTH, INTERNAL_HEIGHT], fill=255)
            if edge_b['left']: draw.rectangle([0, 0, bw_w, INTERNAL_HEIGHT], fill=255)
            if edge_b['right']: draw.rectangle([INTERNAL_WIDTH - bw_w, 0, INTERNAL_WIDTH, INTERNAL_HEIGHT], fill=255)
            
            # Wir müssen das skalierte Bild an die richtige Position im Canvas bringen, um den Blur anzuwenden
            # Da es komplex ist, Pixelgenau im exportierten State zu arbeiten, wenden wir den Blur
            # hier vereinfacht auf den sichtbaren Bereich des Canvas an.
            
            # Wir pasten das normale Bild auf den Canvas
            temp_comp = Image.new('RGB', (INTERNAL_WIDTH, INTERNAL_HEIGHT), canvas_color)
            temp_comp.paste(bg, (int(state['bg']['x']), int(state['bg']['y'])))
            
            # Wir pasten das unscharfe Bild auf den Canvas
            temp_blur = Image.new('RGB', (INTERNAL_WIDTH, INTERNAL_HEIGHT), canvas_color)
            temp_blur.paste(blurred_bg, (int(state['bg']['x']), int(state['bg']['y'])))
            
            # Composite mit Maske
            final_canvas = Image.composite(temp_blur, temp_comp, blur_mask)
            
        else:
            # Kein Edge Blur, einfach das Bild auf den Canvas (noch ohne Fading)
            final_canvas.paste(bg, (int(state['bg']['x']), int(state['bg']['y'])))

        # 5. KANTEN ÜBERGÄNGE (Fade to Color)
        # Wir zeichnen die Fades DIREKT auf das Final Canvas, indem wir Gradienten der Canvas-Farbe drüberlegen
        # Das ist einfacher als Alpha-Maskierung des Source-Bildes, wenn der Hintergrund einfarbig ist.
        
        fade = state['canvas']['fade']
        draw = ImageDraw.Draw(final_canvas, 'RGBA')
        
        # Helper für Gradienten
        def draw_gradient(draw, rect, color_rgb, direction):
            # direction: 'top', 'bottom', 'left', 'right'
            # rect: (x1, y1, x2, y2)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            
            # Gradient erstellen
            base = Image.new('RGBA', (w, h), color_rgb + (0,))
            gradient = Image.new('L', (w, h), 0)
            g_draw = ImageDraw.Draw(gradient)
            
            if direction == 'top': # Fade von Oben (Farbe) nach Unten (Transparent)
                for y in range(h):
                    alpha = int(255 * (1 - y/h))
                    g_draw.line([(0, y), (w, y)], fill=alpha)
            elif direction == 'bottom':
                for y in range(h):
                    alpha = int(255 * (y/h))
                    g_draw.line([(0, y), (w, y)], fill=alpha)
            elif direction == 'left':
                for x in range(w):
                    alpha = int(255 * (1 - x/w))
                    g_draw.line([(x, 0), (x, h)], fill=alpha)
            elif direction == 'right':
                for x in range(w):
                    alpha = int(255 * (x/w))
                    g_draw.line([(x, 0), (x, h)], fill=alpha)
            
            # Farbe + Alpha Kanal
            solid = Image.new('RGBA', (w, h), color_rgb + (255,))
            base = Image.composite(solid, base, gradient)
            final_canvas.paste(base, rect, base)

        if fade['top'] > 0:
            h = int(INTERNAL_HEIGHT * (fade['top']/100))
            draw_gradient(draw, (0, 0, INTERNAL_WIDTH, h), canvas_color, 'top')
            
        if fade['bottom'] > 0:
            h = int(INTERNAL_HEIGHT * (fade['bottom']/100))
            draw_gradient(draw, (0, INTERNAL_HEIGHT-h, INTERNAL_WIDTH, INTERNAL_HEIGHT), canvas_color, 'bottom')
            
        if fade['left'] > 0:
            w = int(INTERNAL_WIDTH * (fade['left']/100))
            draw_gradient(draw, (0, 0, w, INTERNAL_HEIGHT), canvas_color, 'left')
            
        if fade['right'] > 0:
            w = int(INTERNAL_WIDTH * (fade['right']/100))
            draw_gradient(draw, (INTERNAL_WIDTH-w, 0, INTERNAL_WIDTH, INTERNAL_HEIGHT), canvas_color, 'right')

        # 6. Texte Rendern
        draw_txt = ImageDraw.Draw(final_canvas)
        for el in state['elements']:
            try: font = ImageFont.truetype("arial.ttf", int(el['size']))
            except: font = ImageFont.load_default()
            draw_txt.text((el['x'], el['y']), el['label'], fill=el['color'], font=font)
            
        final_canvas.save('preview_render.jpg')
        ui.notify('Export erfolgreich!')
        
        with ui.dialog() as dialog, ui.card():
            ui.image('/static/preview_render.jpg').classes('w-full').style('max-width: 800px')
            ui.button('Schließen', on_click=dialog.close)
        dialog.open()
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        ui.notify(f'Fehler: {str(e)}', type='negative')

from PIL import ImageColor

# --- UI LAYOUT ---
@ui.refreshable
def render_ui():
    ui.add_body_html(drag_script)
    ui.on('element_drag_end', handle_element_drag_end)
    ui.on('bg_drag_end', handle_bg_drag_end)

    with ui.column().props('id=canvas-container').classes('w-full h-full relative bg-gray-900 overflow-hidden'):
        
        # EDITOR CANVAS
        # Wir fügen hier die Overlay-Divs für die Effekte ein
        with ui.card().props('id=editor-canvas').classes('p-0 absolute top-1/2 left-1/2 shrink-0 shadow-2xl origin-center') \
            .style(f'width: {INTERNAL_WIDTH}px; height: {INTERNAL_HEIGHT}px; background-color: {state["canvas"]["color"]};'):
            
            # --- OVERLAYS FÜR BLUR (Liegen oben auf) ---
            # CSS Variable --blur-strength wird via JS gesetzt
            # Wir nutzen feste Breiten (z.B. 15%) oder die ganze Seite für den Effekt
            
            # Top Blur
            ui.element('div').props('id=blur-top').classes('overlay-effect blur-layer absolute top-0 left-0 w-full h-1/6 hidden')
            # Bottom Blur
            ui.element('div').props('id=blur-bottom').classes('overlay-effect blur-layer absolute bottom-0 left-0 w-full h-1/6 hidden')
            # Left Blur
            ui.element('div').props('id=blur-left').classes('overlay-effect blur-layer absolute top-0 left-0 h-full w-1/6 hidden')
            # Right Blur
            ui.element('div').props('id=blur-right').classes('overlay-effect blur-layer absolute top-0 right-0 h-full w-1/6 hidden')

            # --- OVERLAYS FÜR FADE (Liegen über Bild, unter Blur/Text) ---
            ui.element('div').props('id=fade-top').classes('overlay-effect absolute top-0 left-0 w-full').style('height: 0%;')
            ui.element('div').props('id=fade-bottom').classes('overlay-effect absolute bottom-0 left-0 w-full').style('height: 0%;')
            ui.element('div').props('id=fade-left').classes('overlay-effect absolute top-0 left-0 h-full').style('width: 0%;')
            ui.element('div').props('id=fade-right').classes('overlay-effect absolute top-0 right-0 h-full').style('width: 0%;')


            # --- HINTERGRUND BILD ---
            ui.image('/static/background.jpg') \
                .props(f"id=bg-img data-x={state['bg']['x']} data-y={state['bg']['y']} data-scale={state['bg']['scale']}") \
                .classes('absolute w-full h-full object-cover origin-top-left cursor-move') \
                .style(f"filter: blur({state['bg']['blur']}px) brightness({state['bg']['brightness']}%); transform: translate({state['bg']['x']}px, {state['bg']['y']}px) scale({state['bg']['scale']});") \
                .on('click', lambda: select_element(None))

            # --- TEXTE ---
            for el in state['elements']:
                with ui.element('div') \
                    .props(f"id=el-{el['id']} data-x={el['x']} data-y={el['y']}") \
                    .classes('draggable-element absolute cursor-move p-2 border border-transparent hover:border-white whitespace-nowrap z-20') \
                    .style(f"transform: translate({el['x']}px, {el['y']}px); color: {el['color']}; font-size: {el['size']}px; font-family: Arial;") \
                    .on('click', lambda _, id=el['id']: select_element(id)):
                    ui.label(el['label'])
            
    # Initial Update der Effekte beim Rendern
    ui.timer(0.1, update_canvas_effects, once=True)

# --- APP START ---
with ui.row().classes('w-full h-screen no-wrap bg-gray-800 p-0 m-0 gap-0 overflow-hidden'):
    
    with ui.card().classes('w-96 h-full rounded-none shadow-xl z-20 flex flex-col bg-white shrink-0 overflow-y-auto'):
        label_header = ui.label('Editor Pro').classes('text-xl font-bold mb-4 sticky top-0 bg-white z-10 py-2')
        
        # 1. Bild Kontrollen
        with ui.column().classes('w-full mb-4') as bg_controls:
            ui.label('Hintergrundbild').classes('text-sm font-bold text-gray-500 uppercase')
            with ui.grid(columns=2).classes('w-full items-center gap-2'):
                ui.label('Zoom')
                ui.slider(min=0.1, max=3.0, step=0.1, value=1.0, on_change=lambda e: [state['bg'].update({'scale': e.value}), update_bg()])
                ui.label('Helligkeit')
                ui.slider(min=0, max=200, value=100, on_change=lambda e: [state['bg'].update({'brightness': e.value}), update_bg()])
                ui.label('Global Blur')
                ui.slider(min=0, max=20, value=0, on_change=lambda e: [state['bg'].update({'blur': e.value}), update_bg()])

        ui.separator()

        # 2. Canvas & Effekte
        with ui.column().classes('w-full mt-4 mb-4') as canvas_controls:
            ui.label('Canvas & Ränder').classes('text-sm font-bold text-gray-500 uppercase')
            
            # Farbe
            ui.label('Hintergrundfarbe').classes('text-xs font-bold')
            with ui.row().classes('items-center w-full'):
                color_picker_ui = ui.color_picker(on_pick=lambda e: [state['canvas'].update({'color': e.value}), update_canvas_effects()])
                ui.button('Auto Color', on_click=set_auto_color).props('flat dense icon=colorize').tooltip('Farbe aus Bild übernehmen')

            # Fades (Übergänge)
            ui.label('Weiche Übergänge (Fade)').classes('text-xs font-bold mt-2')
            with ui.grid(columns=[1, 4]).classes('w-full items-center gap-1'):
                ui.label('Oben')
                ui.slider(min=0, max=50, value=0, on_change=lambda e: [state['canvas']['fade'].update({'top': e.value}), update_canvas_effects()])
                ui.label('Unten')
                ui.slider(min=0, max=50, value=0, on_change=lambda e: [state['canvas']['fade'].update({'bottom': e.value}), update_canvas_effects()])
                ui.label('Links')
                ui.slider(min=0, max=50, value=0, on_change=lambda e: [state['canvas']['fade'].update({'left': e.value}), update_canvas_effects()])
                ui.label('Rechts')
                ui.slider(min=0, max=50, value=0, on_change=lambda e: [state['canvas']['fade'].update({'right': e.value}), update_canvas_effects()])

            # Edge Blur
            ui.label('Rand-Unschärfe (Blur)').classes('text-xs font-bold mt-2')
            ui.slider(min=0, max=20, value=10, on_change=lambda e: [state['canvas']['edge_blur'].update({'strength': e.value}), update_canvas_effects()]).tooltip('Stärke')
            with ui.row().classes('w-full justify-between'):
                ui.checkbox('Oben', on_change=lambda e: [state['canvas']['edge_blur'].update({'top': e.value}), update_canvas_effects()])
                ui.checkbox('Unten', on_change=lambda e: [state['canvas']['edge_blur'].update({'bottom': e.value}), update_canvas_effects()])
            with ui.row().classes('w-full justify-between'):
                ui.checkbox('Links', on_change=lambda e: [state['canvas']['edge_blur'].update({'left': e.value}), update_canvas_effects()])
                ui.checkbox('Rechts', on_change=lambda e: [state['canvas']['edge_blur'].update({'right': e.value}), update_canvas_effects()])

        # 3. Element Kontrollen (Hidden)
        with ui.column().classes('w-full hidden') as el_controls:
            ui.label('Element').classes('text-sm font-bold text-gray-500 uppercase')
            sidebar_size = ui.slider(min=10, max=300, on_change=lambda e: update_element_prop('size', e.value))
            sidebar_color = ui.color_picker(on_pick=lambda e: update_element_prop('color', e.value))
            ui.button('Löschen', on_click=lambda: [state['elements'].remove(get_element(state['selected_id'])), render_ui.refresh()]).classes('bg-red-500 mt-4 w-full')
            ui.button('Zurück zu Bild', on_click=lambda: select_element(None)).props('flat w-full')

        ui.element('div').classes('flex-grow')
        with ui.grid(columns=2).classes('w-full gap-2 mb-4'):
            ui.button('Titel', on_click=lambda: add_element('TITEL'))
            ui.button('Text', on_click=lambda: add_element('Text...'))
        ui.button('EXPORT BILD', on_click=export_image).classes('bg-blue-600 w-full font-bold py-3 rounded-none')

    with ui.column().classes('flex-grow h-full bg-gray-900 relative overflow-hidden'):
        render_ui()

if __name__ in {"__main__", "__mp_main__"}:
    ui.run(title="Editor Pro Effects", port=8080)