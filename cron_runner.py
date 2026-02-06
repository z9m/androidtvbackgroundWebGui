import os
import sys
import json
import requests
import subprocess
import tempfile
import base64
from urllib.parse import quote

# Path to own module folder
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from gui_editor import load_config

# Config
API_URL = "http://127.0.0.1:5000/api/save_image"
LOG_URL = "http://127.0.0.1:5000/api/cron/log"
STOP_SIGNAL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cron_stop.signal')

def log(msg):
    print(msg)
    try:
        requests.post(LOG_URL, json={"message": msg}, timeout=1)
    except:
        pass

def run_node_renderer(layout_path, metadata):
    # 1. Prepare Data - DIRECT PASS-THROUGH
    # We simply pass the Jellyfin URLs directly to Node.js.
    # Node.js will fetch them internally.
    
    payload = {
        "layout_file": layout_path,
        "metadata": metadata,
        "assets": {
            # Pass the raw URL including the api_key
            "backdrop_url": metadata.get('backdrop_url'),
            "logo_url": metadata.get('logo_url')
        }
    }
    
    # 2. Write Payload to temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.json', encoding='utf-8') as f:
        json.dump(payload, f, ensure_ascii=False)
        payload_path = f.name

    # Prepare Output paths
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as f:
        output_image_path = f.name
    f.close()
    
    output_json_path = output_image_path + ".json"

    # 3. Execute Node
    image_b64 = None
    final_json = None
    
    try:
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'render_task.js')
        
        # Run Node
        cmd = ['node', script_path, payload_path, output_image_path]
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
        
        if "SUCCESS" in result.stdout:
            # Read Resulting Image
            with open(output_image_path, 'rb') as img_f:
                file_b64 = base64.b64encode(img_f.read()).decode('utf-8')
                image_b64 = f"data:image/jpeg;base64,{file_b64}"
            
            # Read Resulting JSON
            if os.path.exists(output_json_path):
                with open(output_json_path, 'r', encoding='utf-8') as json_f:
                    final_json = json.load(json_f)
        else:
            log(f"Node Error: {result.stderr}")
            # log(f"Node Output: {result.stdout}")

    except Exception as e:
        log(f"Render Execution Error: {e}")
    
    finally:
        # Cleanup
        for p in [payload_path, output_image_path, output_json_path]:
            if p and os.path.exists(p):
                try: os.remove(p)
                except: pass

    return image_b64, final_json

def fetch_items_and_process():
    log("Batch Job Started (Direct URL Mode)")
    config = load_config()
    
    layout_dir = os.path.join(os.path.dirname(__file__), 'layouts')
    if not os.path.exists(layout_dir): return
    layout_files = [f for f in os.listdir(layout_dir) if f.endswith('.json')]
    if not layout_files:
        log("No layouts found!")
        return
    
    selected_layout_name = layout_files[0].replace('.json', '')
    layout_full_path = os.path.join(layout_dir, layout_files[0])
    log(f"Using Layout: {selected_layout_name}")

    jf = config.get('jellyfin', {})
    if not jf.get('url'): return

    headers = {"X-Emby-Token": jf['api_key']}
    base_url = jf['url'].rstrip('/')
    url = f"{base_url}/Users/{jf['user_id']}/Items?IncludeItemTypes=Movie&Recursive=true&SortBy=DateCreated&SortOrder=Descending&Limit=10&Fields=Overview,Genres,OfficialRating,CommunityRating,ProviderIds,ProductionYear,RunTimeTicks,OriginalTitle,Tags,Studios,InheritedParentalRatingValue,ImageTags"
    
    try:
        req = requests.get(url, headers=headers)
        items = req.json().get('Items', [])
    except Exception as e:
        log(f"Jellyfin Error: {e}")
        return

    log(f"Processing {len(items)} items...")

    for item in items:
        if os.path.exists(STOP_SIGNAL_FILE): break
        
        safe_title = "".join(c for c in item.get('Name', '') if c.isalnum() or c in " ._-").strip()
        filename = f"{safe_title} - {item.get('ProductionYear')}.jpg"
        
        ticks = item.get('RunTimeTicks', 0)
        minutes = (ticks // 600000000) if ticks else 0
        h, m = divmod(minutes, 60)
        runtime = f"{h}h {m}min" if h > 0 else f"{m}min"

        meta = {
            "title": item.get('Name'),
            "year": item.get('ProductionYear'),
            "overview": item.get('Overview'),
            "rating": item.get('CommunityRating'),
            "officialRating": item.get('OfficialRating'),
            "genres": ", ".join(item.get('Genres', [])),
            "runtime": runtime,
            "backdrop_url": f"{base_url}/Items/{item['Id']}/Images/Backdrop?api_key={jf['api_key']}",
            "logo_url": f"{base_url}/Items/{item['Id']}/Images/Logo?api_key={jf['api_key']}" if 'Logo' in item.get('ImageTags', {}) else None,
            "action_url": f"jellyfin://items/{item['Id']}",
            "provider_ids": item.get('ProviderIds', {})
        }

        log(f"Rendering: {meta['title']}")
        img_b64, json_data = run_node_renderer(layout_full_path, meta)
        
        if img_b64 and json_data:
            payload = {
                "image": img_b64,
                "layout_name": selected_layout_name,
                "metadata": meta,
                "canvas_json": json_data,
                "overwrite_filename": filename,
                "target_type": "gallery"
            }
            try:
                requests.post(API_URL, json=payload)
            except Exception as e:
                log(f"Upload failed: {e}")
        else:
            log("Rendering failed.")

    if os.path.exists(STOP_SIGNAL_FILE): os.remove(STOP_SIGNAL_FILE)
    log("Batch Finished.")

if __name__ == "__main__":
    fetch_items_and_process()