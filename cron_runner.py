import os
import sys
import json
import requests
import time
import subprocess
import tempfile
import logging

# Pfad zum eigenen Modulordner
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gui_editor import load_config

# Config
API_URL = "http://127.0.0.1:5000/api/save_image"
STATUS_URL = "http://127.0.0.1:5000/api/cron/update"
LOG_URL = "http://127.0.0.1:5000/api/cron/log"
STOP_SIGNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cron_stop.signal')

def log(msg):
    print(msg)
    try:
        requests.post(LOG_URL, json={"message": msg}, timeout=1)
    except:
        pass

def fetch_library_items(config):
    """Holt neue Filme von Jellyfin"""
    jf = config.get('jellyfin', {})
    if not jf.get('url') or not jf.get('api_key'):
        log("Jellyfin not configured.")
        return []

    headers = {"X-Emby-Token": jf['api_key']}
    base_url = jf['url'].rstrip('/')
    user_id = jf['user_id']
    
    # Query: Neueste Filme, inkl. Overview & Genres
    url = f"{base_url}/Users/{user_id}/Items?IncludeItemTypes=Movie&Recursive=true&SortBy=DateCreated&SortOrder=Descending&Limit=20&Fields=Overview,Genres,OfficialRating,CommunityRating,ProviderIds,ProductionYear,RunTimeTicks"
    
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json().get('Items', [])
        else:
            log(f"Jellyfin Error: {r.status_code}")
            return []
    except Exception as e:
        log(f"Connection Error: {e}")
        return []

def render_with_node(layout_data, metadata):
    """Ruft Node.js auf, um das Bild zu bauen"""
    
    # Temporäre Dateien für Node
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f_layout:
        json.dump(layout_data, f_layout)
        layout_path = f_layout.name

    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json') as f_meta:
        json.dump(metadata, f_meta)
        meta_path = f_meta.name

    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as f_out:
        output_path = f_out.name
    f_out.close() # Wichtig: Schließen, damit Node darauf zugreifen kann

    try:
        # Pfad zu render_task.js
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render_task.js')
        
        # Node Kommando: node render_task.js layout.json meta.json out.jpg
        cmd = ['node', script_path, layout_path, meta_path, output_path]
        
        # Ausführen
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if "SUCCESS" in result.stdout:
            # Bild einlesen und base64 codieren
            with open(output_path, 'rb') as f:
                image_data = f.read()
            import base64
            b64_str = base64.b64encode(image_data).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_str}"
        else:
            log(f"Node Log: {result.stderr}") # Fehler ausgeben
            return None

    except Exception as e:
        log(f"Render Exception: {e}")
        return None
    finally:
        # Temp-Dateien löschen
        try:
            if os.path.exists(layout_path): os.remove(layout_path)
            if os.path.exists(meta_path): os.remove(meta_path)
            if os.path.exists(output_path): os.remove(output_path)
        except: pass

def run_batch():
    log("Batch started (Node.js Engine).")
    config = load_config()
    
    # 1. Layout suchen
    layout_dir = os.path.join(os.path.dirname(__file__), 'layouts')
    if not os.path.exists(layout_dir):
        log("No layouts folder found.")
        return

    layout_files = [f for f in os.listdir(layout_dir) if f.endswith('.json')]
    if not layout_files:
        log("No layouts found! Please save a layout in the editor first.")
        return

    # Nimm das erste Layout (Du kannst das später erweitern)
    selected_layout = layout_files[0]
    layout_path = os.path.join(layout_dir, selected_layout)
    
    with open(layout_path, 'r') as f:
        layout_data = json.load(f)

    log(f"Using Layout: {selected_layout}")

    # 2. Filme holen
    items = fetch_library_items(config)
    log(f"Found {len(items)} items.")

    processed = 0
    for item in items:
        if os.path.exists(STOP_SIGNAL_FILE):
            log("Stopped by user.")
            break

        # Metadaten vorbereiten
        meta = {
            'title': item.get('Name'),
            'year': item.get('ProductionYear'),
            'overview': item.get('Overview'),
            'rating': item.get('CommunityRating'),
            'genres': ", ".join(item.get('Genres', [])),
            # Token anhängen für Zugriff
            'backdrop_url': f"{config['jellyfin']['url']}/Items/{item['Id']}/Images/Backdrop?api_key={config['jellyfin']['api_key']}",
            'logo_url': f"{config['jellyfin']['url']}/Items/{item['Id']}/Images/Logo?api_key={config['jellyfin']['api_key']}"
        }

        log(f"Processing: {meta['title']}...")
        
        # 3. Rendern lassen!
        image_b64 = render_with_node(layout_data, meta)

        if image_b64:
            # 4. Speichern via API
            payload = {
                "image": image_b64,
                "layout_name": selected_layout.replace('.json', ''),
                "metadata": meta,
                "overwrite_filename": f"{item['Name']} ({item.get('ProductionYear')})",
                "target_type": "gallery"
            }
            try:
                requests.post(API_URL, json=payload)
                processed += 1
            except Exception as e:
                log(f"Upload failed: {e}")
        else:
            log("Rendering failed.")

    log(f"Finished. {processed} images created.")
    if os.path.exists(STOP_SIGNAL_FILE): os.remove(STOP_SIGNAL_FILE)

if __name__ == "__main__":
    run_batch()