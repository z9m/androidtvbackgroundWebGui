CURRENT_VERSION = "1.1.0"
import os
import sys
import json
import random
import traceback
import io
import requests
import time
import base64
import shutil
import re
import uuid
import subprocess
from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, jsonify, send_from_directory, url_for, send_file
from PIL import Image
from urllib.parse import quote

# Prevent Python from generating .pyc files and __pycache__ folders
sys.dont_write_bytecode = True

# --- IMPORT IMAGE ENGINE ---
from image_engine import ImageGenerator

# Blueprint Setup
gui_editor_bp = Blueprint('gui_editor', __name__)
CONFIG_FILE = 'config.json'
BATCH_LOGS = []

# Global to track latest image for preview
LATEST_GENERATED_IMAGE = None

# Global to track running cron process
CRON_PROCESS = None

# Initialize Image Generator for Proxy Processing
image_gen = ImageGenerator()

KNOWN_DIRS = [
    "layouts",
    "editor_backgrounds",
    "plex_backgrounds",
    "jellyfin_backgrounds",
    "trakt_backgrounds",
    "radarrsonarr_backgrounds",
    "tmdb_backgrounds",
    "plexfriend_backgrounds"
]

LAYOUTS_DIR = 'layouts'
LAYOUT_PREVIEWS_DIR = os.path.join(LAYOUTS_DIR, 'previews')
OVERLAYS_DIR = 'overlays'
OVERLAYS_JSON = 'overlays.json'
TEXTURES_DIR = 'textures'
TEXTURES_JSON = 'textures.json'
FONTS_DIR = 'fonts'
CUSTOM_ICONS_DIR = 'custom_icons'

if not os.path.exists(LAYOUTS_DIR):
    os.makedirs(LAYOUTS_DIR)
if not os.path.exists(LAYOUT_PREVIEWS_DIR):
    os.makedirs(LAYOUT_PREVIEWS_DIR)
if not os.path.exists(OVERLAYS_DIR):
    os.makedirs(OVERLAYS_DIR)
if not os.path.exists(TEXTURES_DIR):
    os.makedirs(TEXTURES_DIR)
if not os.path.exists(FONTS_DIR):
    os.makedirs(FONTS_DIR)
if not os.path.exists(CUSTOM_ICONS_DIR):
    os.makedirs(CUSTOM_ICONS_DIR)

# --- CONFIGURATION LOGIC ---
def load_config():
    defaults = {
        "general": {"overwrite_existing": False, "timezone_offset": 1},
        "jellyfin": {"url": "", "api_key": "", "user_id": "", "excluded_libraries": ""},
        "plex": {"url": "", "token": ""},
        "tmdb": {"api_key": "", "language": "de-DE"},
        "radarr": {"url": "", "api_key": ""},
        "sonarr": {"url": "", "api_key": ""},
        "jellyseerr": {"url": "", "api_key": ""},
        "trakt": {"api_key": "", "username": "", "listname": ""},
        "editor": {"resolution": "1080"},
        "cron": {"enabled": False, "start_time": "00:00", "frequency": "1"}
    }

    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            try:
                loaded = json.load(f)
                for key, value in loaded.items():
                    if key in defaults and isinstance(defaults[key], dict) and isinstance(value, dict):
                        defaults[key].update(value)
                    else:
                        defaults[key] = value
            except:
                pass
    return defaults

def save_config(config_data):
    with open(CONFIG_FILE, 'w') as f:
        json.dump(config_data, f, indent=4)

def clean_tmdb_url(path):
    """ Safely constructs a TMDB image URL from a path. """
    if not path:
        return None
    if path.startswith("http"):
        return path
    return f"https://image.tmdb.org/t/p/original/{path.lstrip('/')}"

# --- API ROUTES ---
@gui_editor_bp.route('/api/proxy/image')
def proxy_image():
    """ Proxies an image URL to bypass CORS/CORB blocks. """
    url = request.args.get('url')
    raw = request.args.get('raw', 'false').lower() == 'true'
    if not url:
        return "Missing URL", 400
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"}
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code != 200:
            return f"Upstream Error: {resp.status_code}", resp.status_code
            
        # Check if this is likely a logo (PNG or contains 'logo' in path)
        # This prevents processing backdrops (JPGs) which would turn white if dark.
        is_likely_logo = 'logo' in url.lower() or url.lower().endswith('.png')
        
        if is_likely_logo and not raw:
            try:
                img = Image.open(io.BytesIO(resp.content))
                # Apply the contrast logic from image_engine.py
                img = image_gen.ensure_high_contrast(img)
                output = io.BytesIO()
                img.save(output, format='PNG')
                output.seek(0)
                return send_file(output, mimetype='image/png')
            except Exception as e:
                print(f"Error processing proxy image: {e}")

        return send_file(
            io.BytesIO(resp.content),
            mimetype=resp.headers.get('Content-Type') or 'image/jpeg'
        )
    except requests.exceptions.RequestException as e:
        print(f"Proxy Connection Error for {url}: {e}", file=sys.stderr)
        return str(e), 502
    except Exception as e:
        print(f"Proxy Error for {url}: {e}", file=sys.stderr)
        traceback.print_exc()
        return str(e), 500

# --- NEW: Server-Side Generation Example ---
@gui_editor_bp.route('/api/generate_preview_server', methods=['POST'])
def generate_preview_server():
    """
    Example of using the ImageEngine to generate an image server-side.
    This keeps the main file clean and logic isolated.
    """
    data = request.json
    
    # Initialize Engine (Loads fonts/backgrounds once)
    engine = ImageGenerator()
    
    # Simulate getting an image (in reality you'd download it from data['backdrop_url'])
    # For demo, we use the base background as a placeholder for artwork
    artwork = engine.base_bg 
    
    # 1. Create Canvas
    engine.create_canvas(artwork)
    
    # 2. Draw Elements (Dynamic Layout happens automatically inside)
    engine.draw_logo_or_title(title_text=data.get('title', 'No Title'))
    engine.draw_info_text(f"{data.get('year')} • {data.get('rating')}")
    engine.draw_summary(data.get('overview', ''))
    engine.draw_custom_text_and_provider_logo("Preview Generated by Engine", "jellyfinlogo.png")
    
    # 3. Return Image
    return send_file(engine.get_bytes(), mimetype='image/jpeg')

def format_jellyfin_item(item, clean_url, api_key):
    # Check for Logo availability
    has_logo = 'Logo' in item.get('ImageTags', {})
    logo_url = f"{clean_url}/Items/{item['Id']}/Images/Logo?api_key={api_key}" if has_logo else None

    # Convert Ticks to Runtime
    ticks = item.get('RunTimeTicks', 0)
    minutes = (ticks // 600000000) if ticks else 0
    h, m = divmod(minutes, 60)
    runtime_str = f"{h}h {m}min" if h > 0 else f"{m}min"

    return {
        "id": item.get('Id'),
        "title": item.get('Name'),
        "original_title": item.get('OriginalTitle'),
        "year": item.get('ProductionYear'),
        "rating": item.get('CommunityRating'),
        "overview": item.get('Overview', ''),
        "genres": ", ".join(item.get('Genres', [])),
        "tags": item.get('Tags', []),
        "studios": [s.get('Name') for s in item.get('Studios', [])],
        "provider_ids": item.get('ProviderIds', {}),
        "runtime": runtime_str,
        "backdrop_url": f"{clean_url}/Items/{item['Id']}/Images/Backdrop?api_key={api_key}",
        "logo_url": logo_url,
        "officialRating": item.get('OfficialRating'),
        "inheritedParentalRatingValue": item.get('InheritedParentalRatingValue'),
        "imdb_id": item.get('ProviderIds', {}).get('Imdb'),
        "source": "Jellyfin"
    }

@gui_editor_bp.route('/api/media/random')
def get_random_media():
    config = load_config()
    jf = config.get('jellyfin', {})
    excluded_libs = jf.get('excluded_libraries', "")
    excluded_list = [x.strip() for x in excluded_libs.split(',') if x.strip()]
    
    if jf.get('url') and jf.get('api_key'):
        headers = {"X-Emby-Token": jf['api_key']}
        clean_url = jf['url'].rstrip('/')
        
        excluded_paths = []
        if excluded_list:
            try:
                r_libs = requests.get(f"{clean_url}/Library/VirtualFolders", headers=headers, timeout=5)
                if r_libs.status_code == 200:
                    libs = r_libs.json()
                    for lib in libs:
                        if lib.get('Name') in excluded_list:
                            excluded_paths.extend(lib.get('Locations', []))
            except Exception as e:
                print(f"Error fetching libraries: {e}")

        url = f"{clean_url}/Users/{jf['user_id']}/Items?Recursive=true&IncludeItemTypes=Movie,Series&ExcludeItemTypes=BoxSet&SortBy=Random&Limit=50&Fields=Type,Overview,Genres,CommunityRating,ProductionYear,RunTimeTicks,ImageTags,Path,ProviderIds,OfficialRating,InheritedParentalRatingValue"
        
        try:
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            items = r.json().get('Items', [])
            
            valid_items = []
            for item in items:
                if item.get('Type') == 'BoxSet':
                    continue
                if excluded_paths and item.get('Path') and any(ex in item['Path'] for ex in excluded_paths):
                    continue
                valid_items.append(item)
            
            if valid_items:
                item = random.choice(valid_items)
                return jsonify(format_jellyfin_item(item, clean_url, jf['api_key']))
        except Exception as e:
            print(f"DEBUG: Jellyfin Error: {e}")

    # Fallback Data
    mock_samples = [
        {"title": "Interstellar", "year": 2014, "rating": 8.7, "overview": "Ein Team von Entdeckern nutzt ein neu entdecktes Wurmloch, um die Grenzen der menschlichen Raumfahrt zu überwinden und die weiten Entfernungen einer interstellaren Reise zu bewältigen.", "backdrop_url": clean_tmdb_url("/5XNQBqnBwPA9yT0jZ0p3s8bbLh0.jpg"), "logo_url": clean_tmdb_url("/eJjFbfeOuZPuPJFnDP3YJ5daSsg.png")},
        {"title": "The Dark Knight", "year": 2008, "rating": 9.0, "overview": "Batman zieht im Kampf gegen das Verbrechen die Daumenschrauben an. Mit der Hilfe von Lieutenant Jim Gordon und Staatsanwalt Harvey Dent setzt er sein Vorhaben fort, die organisierten Verbrecherorganisationen in Gotham endgültig zu zerschlagen.", "backdrop_url": clean_tmdb_url("/6fA9nie4ROlkyZAUlgKNjGNCbHG.jpg"), "logo_url": clean_tmdb_url("/hdtvO84iZVAk848CoJmLMMTsQ9i.png")}
    ]
    sample = random.choice(mock_samples)
    sample["source"] = "Demo Mode"
    
    # Prevent browser caching of the random endpoint to ensure new URLs are loaded
    response = jsonify(sample)
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response

@gui_editor_bp.route('/api/media/list')
def get_media_list():
    config = load_config()
    filter_mode = request.args.get('mode', 'all')
    filter_val = request.args.get('val', '')
    jf = config.get('jellyfin', {})
    excluded_libs = jf.get('excluded_libraries', "")
    excluded_list = [x.strip() for x in excluded_libs.split(',') if x.strip()]

    if jf.get('url') and jf.get('api_key'):
        headers = {"X-Emby-Token": jf['api_key']}
        clean_url = jf['url'].rstrip('/')
        
        excluded_paths = []
        if excluded_list:
            try:
                r_libs = requests.get(f"{clean_url}/Library/VirtualFolders", headers=headers, timeout=5)
                if r_libs.status_code == 200:
                    libs = r_libs.json()
                    for lib in libs:
                        if lib.get('Name') in excluded_list:
                            excluded_paths.extend(lib.get('Locations', []))
            except Exception as e:
                print(f"Error fetching libraries: {e}")

        # Fetch all items sorted by name
        base_params = "Recursive=true&IncludeItemTypes=Movie,Series&ExcludeItemTypes=BoxSet&Fields=Name,Path,OfficialRating,InheritedParentalRatingValue&Limit=100000"
        sort_params = "&SortBy=SortName"
        
        if filter_mode == 'recent':
            sort_params = "&SortBy=DateCreated&SortOrder=Descending"
        elif filter_mode == 'year':
            sort_params = f"&SortBy=SortName&Years={filter_val}"
        elif filter_mode == 'genre':
            sort_params = f"&SortBy=SortName&Genres={filter_val}"
        elif filter_mode == 'rating':
            sort_params = f"&SortBy=CommunityRating&SortOrder=Descending&MinCommunityRating={filter_val}"
        elif filter_mode == 'imdb':
            # Jellyfin doesn't always allow sorting by ProviderIds directly in simple queries easily, 
            # but usually CommunityRating is the best proxy. We'll stick to CommunityRating for simplicity or custom filtering.
            sort_params = f"&SortBy=CommunityRating&SortOrder=Descending&MinCommunityRating={filter_val}"
        elif filter_mode == 'official_rating':
            # We filter in python to be more flexible with formats (e.g. "6" vs "FSK 6" vs "DE-6")
            pass
        elif filter_mode == 'custom':
            min_year = request.args.get('min_year')
            max_year = request.args.get('max_year')
            min_rating = request.args.get('min_rating')
            genre = request.args.get('genre')
            
            c_params = []
            if min_year or max_year:
                try:
                    current_year = time.localtime().tm_year
                    start = int(min_year) if min_year else 1900
                    end = int(max_year) if max_year else current_year
                    if start > end: start, end = end, start
                    # Jellyfin expects comma separated years for the Years parameter
                    years_str = ",".join(str(y) for y in range(start, end + 1))
                    c_params.append(f"Years={years_str}")
                except: pass
            
            if min_rating:
                c_params.append(f"MinCommunityRating={min_rating}")
            if genre:
                c_params.append(f"Genres={genre}")
            
            sort_params = "&SortBy=SortName"
            if c_params:
                sort_params += "&" + "&".join(c_params)

        url = f"{clean_url}/Users/{jf['user_id']}/Items?{base_params}{sort_params}"

        try:
            r = requests.get(url, headers=headers, timeout=10)
            r.raise_for_status()
            items = r.json().get('Items', [])
            
            valid_items = []
            for item in items:
                if excluded_paths and item.get('Path') and any(ex in item['Path'] for ex in excluded_paths):
                    continue
                
                if filter_mode == 'official_rating':
                    f_val = str(filter_val).strip().lower()
                    i_rating = item.get('InheritedParentalRatingValue')
                    o_rating = str(item.get('OfficialRating', '') or '').lower()
                    
                    match = False
                    # 1. Numeric Search (e.g. "6")
                    if f_val.isdigit():
                        # Check InheritedParentalRatingValue
                        if i_rating is not None and int(i_rating) == int(f_val):
                            match = True
                        # Check OfficialRating for exact number (e.g. "FSK 6", "DE-6") using Regex
                        # This finds "6" in "FSK 6" or "DE-6" but NOT in "16"
                        elif f_val in re.findall(r'\d+', o_rating):
                            match = True
                    # 2. String Search (e.g. "FSK 6")
                    else:
                        # Normalize both to alphanumeric only
                        f_norm = "".join(c for c in f_val if c.isalnum())
                        o_norm = "".join(c for c in o_rating if c.isalnum())
                        if f_norm and f_norm in o_norm:
                            match = True
                            
                    if not match:
                        continue

                valid_items.append({"Id": item['Id'], "Name": item['Name']})
            
            return jsonify(valid_items)
        except Exception as e:
            return jsonify({"error": str(e)}), 500
            
    return jsonify([])

@gui_editor_bp.route('/api/media/search')
def search_media():
    query = request.args.get('q')
    if not query: return jsonify([])
    
    config = load_config()
    jf = config.get('jellyfin', {})
    if not jf.get('url') or not jf.get('api_key'): return jsonify([])
    
    headers = {"X-Emby-Token": jf['api_key']}
    clean_url = jf['url'].rstrip('/')
    url = f"{clean_url}/Users/{jf['user_id']}/Items?Recursive=true&IncludeItemTypes=Movie,Series&ExcludeItemTypes=BoxSet&SearchTerm={query}&Limit=10&Fields=Name,ProductionYear"
    
    try:
        r = requests.get(url, headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify(r.json().get('Items', []))
    except:
        return jsonify([])

@gui_editor_bp.route('/api/media/item/<item_id>')
def get_media_item(item_id):
    config = load_config()
    jf = config.get('jellyfin', {})
    if jf.get('url') and jf.get('api_key'):
        headers = {"X-Emby-Token": jf['api_key']}
        clean_url = jf['url'].rstrip('/')
        url = f"{clean_url}/Users/{jf['user_id']}/Items/{item_id}?Fields=Type,Overview,Genres,CommunityRating,ProductionYear,RunTimeTicks,ImageTags,Path,ProviderIds,OfficialRating,InheritedParentalRatingValue"
        try:
            r = requests.get(url, headers=headers, timeout=5)
            r.raise_for_status()
            return jsonify(format_jellyfin_item(r.json(), clean_url, jf['api_key']))
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    return jsonify({"error": "Jellyfin not configured"}), 400

@gui_editor_bp.route('/api/settings', methods=['POST'])
def update_settings():
    global CRON_PROCESS
    config_data = request.json
    save_config(config_data)
    
    # Check if any job needs immediate execution
    jobs = config_data.get('cron_jobs', [])
    should_run = any(j.get('force_run') for j in jobs)
    
    if should_run:
        # Spawn cron_runner.py in background to handle the forced job
        # We use sys.executable to ensure we use the same python interpreter
        script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cron_runner.py')
        CRON_PROCESS = subprocess.Popen([sys.executable, script_path])
        
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/settings_full')
def get_settings_full():
    return jsonify(load_config())

@gui_editor_bp.route('/api/cron/log', methods=['POST'])
def receive_cron_log():
    data = request.json
    msg = data.get('message')
    if msg:
        try:
            config = load_config()
            offset = int(config.get('general', {}).get('timezone_offset', 1))
            now = datetime.utcnow() + timedelta(hours=offset)
            timestamp = now.strftime("%H:%M:%S")
        except:
            timestamp = time.strftime("%H:%M:%S")
        BATCH_LOGS.append(f"[{timestamp}] {msg}")
        # Keep log size manageable
        if len(BATCH_LOGS) > 1000:
            BATCH_LOGS.pop(0)
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/cron/stop', methods=['POST'])
def stop_cron_jobs():
    global CRON_PROCESS
    killed = False
    
    # 1. Try killing the child process we spawned directly
    if CRON_PROCESS:
        try:
            CRON_PROCESS.terminate()
            time.sleep(0.5)
            if CRON_PROCESS.poll() is None:
                CRON_PROCESS.kill()
            killed = True
        except: pass
        CRON_PROCESS = None
        
    # 2. System-wide kill (fallback for jobs started via system cron)
    try:
        if os.name != 'nt':
            ret = os.system("pkill -f cron_runner.py")
            if ret == 0: killed = True
    except: pass
            
    return jsonify({"status": "success", "message": "Stop signal sent" if killed else "No running jobs found"})

@gui_editor_bp.route('/api/batch/logs/clear', methods=['POST'])
def clear_batch_logs():
    global BATCH_LOGS
    BATCH_LOGS = []
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/batch/logs')
def get_batch_logs():
    return jsonify(BATCH_LOGS)

@gui_editor_bp.route('/api/test/jellyfin', methods=['POST'])
def test_jellyfin():
    data = request.json
    url = data.get('url')
    api_key = data.get('api_key')
    
    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key required"}), 400
        
    try:
        headers = {"X-Emby-Token": api_key}
        # Test connection by fetching system info
        r = requests.get(f"{url.rstrip('/')}/System/Info", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": f"Connected: {r.json().get('ServerName')}"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/plex', methods=['POST'])
def test_plex():
    data = request.json
    url = data.get('url')
    token = data.get('token')
    if not url or not token:
        return jsonify({"status": "error", "message": "URL and Token required"}), 400
    try:
        headers = {'X-Plex-Token': token, 'Accept': 'application/json'}
        # Check identity endpoint
        r = requests.get(f"{url.rstrip('/')}/identity", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": "Connected to Plex"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/tmdb', methods=['POST'])
def test_tmdb():
    data = request.json
    api_key = data.get('api_key')
    if not api_key:
        return jsonify({"status": "error", "message": "API Key required"}), 400
    try:
        # Try as Bearer Token first (v4)
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json;charset=utf-8"}
        r = requests.get("https://api.themoviedb.org/3/authentication", headers=headers, timeout=5)
        
        if r.status_code == 401:
            # Fallback: Try as v3 API Key query param
            r = requests.get(f"https://api.themoviedb.org/3/authentication?api_key={api_key}", timeout=5)
            
        r.raise_for_status()
        return jsonify({"status": "success", "message": "Connected to TMDB"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/radarr', methods=['POST'])
def test_radarr():
    data = request.json
    url = data.get('url')
    api_key = data.get('api_key')
    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key required"}), 400
    try:
        headers = {'X-Api-Key': api_key}
        r = requests.get(f"{url.rstrip('/')}/api/v3/system/status", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": f"Connected to Radarr ({r.json().get('version', 'Unknown')})"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/sonarr', methods=['POST'])
def test_sonarr():
    data = request.json
    url = data.get('url')
    api_key = data.get('api_key')
    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key required"}), 400
    try:
        headers = {'X-Api-Key': api_key}
        r = requests.get(f"{url.rstrip('/')}/api/v3/system/status", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": f"Connected to Sonarr ({r.json().get('version', 'Unknown')})"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/jellyseerr', methods=['POST'])
def test_jellyseerr():
    data = request.json
    url = data.get('url')
    api_key = data.get('api_key')
    if not url or not api_key:
        return jsonify({"status": "error", "message": "URL and API Key required"}), 400
    try:
        headers = {'X-Api-Key': api_key}
        r = requests.get(f"{url.rstrip('/')}/api/v1/status", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": f"Connected to Jellyseerr ({r.json().get('version', 'Unknown')})"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/test/trakt', methods=['POST'])
def test_trakt():
    data = request.json
    client_id = data.get('client_id')
    username = data.get('username')
    if not client_id or not username:
        return jsonify({"status": "error", "message": "Client ID and Username required"}), 400
    try:
        headers = {
            'Content-Type': 'application/json',
            'trakt-api-version': '2',
            'trakt-api-key': client_id
        }
        r = requests.get(f"https://api.trakt.tv/users/{username}/profile", headers=headers, timeout=5)
        r.raise_for_status()
        return jsonify({"status": "success", "message": f"Connected to Trakt (User: {r.json().get('username')})"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/layouts/list')
def list_layouts():
    layouts = []
    if os.path.exists(LAYOUTS_DIR):
        layouts = [f.replace('.json', '') for f in os.listdir(LAYOUTS_DIR) if f.endswith('.json')]
    return jsonify(sorted(layouts))

@gui_editor_bp.route('/api/overlays/list')
def list_overlays():
    if os.path.exists(OVERLAYS_JSON):
        with open(OVERLAYS_JSON, 'r') as f:
            return jsonify(json.load(f))
    return jsonify([])

@gui_editor_bp.route('/api/overlays/add', methods=['POST'])
def add_overlay():
    name = request.form.get('name')
    file_1080 = request.files.get('file_1080')
    file_4k = request.files.get('file_4k')
    
    if not name:
        return jsonify({"status": "error", "message": "Name required"}), 400

    overlay_id = str(uuid.uuid4())
    entry = {"id": overlay_id, "name": name, "file_1080": None, "file_4k": None}

    if file_1080:
        ext = os.path.splitext(file_1080.filename)[1]
        fname = f"{overlay_id}_1080{ext}"
        file_1080.save(os.path.join(OVERLAYS_DIR, fname))
        entry["file_1080"] = fname
        
    if file_4k:
        ext = os.path.splitext(file_4k.filename)[1]
        fname = f"{overlay_id}_4k{ext}"
        file_4k.save(os.path.join(OVERLAYS_DIR, fname))
        entry["file_4k"] = fname
        
    overlays = []
    if os.path.exists(OVERLAYS_JSON):
        with open(OVERLAYS_JSON, 'r') as f:
            try: overlays = json.load(f)
            except: pass
            
    overlays.append(entry)
    
    with open(OVERLAYS_JSON, 'w') as f:
        json.dump(overlays, f, indent=4)
        
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/overlays/delete/<overlay_id>', methods=['POST'])
def delete_overlay(overlay_id):
    overlays = []
    if os.path.exists(OVERLAYS_JSON):
        with open(OVERLAYS_JSON, 'r') as f:
            try: overlays = json.load(f)
            except: pass
            
    new_overlays = []
    for o in overlays:
        if o['id'] == overlay_id:
            # Delete files
            if o.get('file_1080'):
                p = os.path.join(OVERLAYS_DIR, o['file_1080'])
                if os.path.exists(p): os.remove(p)
            if o.get('file_4k'):
                p = os.path.join(OVERLAYS_DIR, o['file_4k'])
                if os.path.exists(p): os.remove(p)
        else:
            new_overlays.append(o)
            
    with open(OVERLAYS_JSON, 'w') as f:
        json.dump(new_overlays, f, indent=4)
        
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/overlays/image/<path:filename>')
def get_overlay_image(filename):
    return send_from_directory(OVERLAYS_DIR, filename)

@gui_editor_bp.route('/api/overlays/update_margins', methods=['POST'])
def update_overlay_margins():
    data = request.json
    overlay_id = data.get('id')
    blocked_areas = data.get('blocked_areas')
    
    if not overlay_id:
        return jsonify({"status": "error", "message": "ID required"}), 400

    overlays = []
    if os.path.exists(OVERLAYS_JSON):
        with open(OVERLAYS_JSON, 'r') as f:
            try: 
                data = json.load(f)
                if isinstance(data, list): overlays = data
            except: pass
    
    updated = False
    for o in overlays:
        if o['id'] == overlay_id:
            o['blocked_areas'] = blocked_areas
            updated = True
            break
    
    if updated:
        with open(OVERLAYS_JSON, 'w') as f:
            json.dump(overlays, f, indent=4)
        return jsonify({"status": "success"})
    
    return jsonify({"status": "error", "message": "Overlay not found"}), 404

@gui_editor_bp.route('/api/textures/list')
def list_textures():
    if os.path.exists(TEXTURES_JSON):
        with open(TEXTURES_JSON, 'r') as f:
            return jsonify(json.load(f))
    return jsonify([])

@gui_editor_bp.route('/api/textures/add', methods=['POST'])
def add_texture():
    name = request.form.get('name')
    file = request.files.get('file')
    
    if not name or not file:
        return jsonify({"status": "error", "message": "Name and file required"}), 400

    texture_id = str(uuid.uuid4())
    ext = os.path.splitext(file.filename)[1]
    fname = f"{texture_id}{ext}"
    file.save(os.path.join(TEXTURES_DIR, fname))
    
    entry = {"id": texture_id, "name": name, "filename": fname}
    
    textures = []
    if os.path.exists(TEXTURES_JSON):
        with open(TEXTURES_JSON, 'r') as f:
            try: textures = json.load(f)
            except: pass
            
    textures.append(entry)
    
    with open(TEXTURES_JSON, 'w') as f:
        json.dump(textures, f, indent=4)
        
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/textures/delete/<texture_id>', methods=['POST'])
def delete_texture(texture_id):
    textures = []
    if os.path.exists(TEXTURES_JSON):
        with open(TEXTURES_JSON, 'r') as f:
            try: textures = json.load(f)
            except: pass
            
    new_textures = []
    for t in textures:
        if t['id'] == texture_id:
            p = os.path.join(TEXTURES_DIR, t['filename'])
            if os.path.exists(p): os.remove(p)
        else:
            new_textures.append(t)
            
    with open(TEXTURES_JSON, 'w') as f:
        json.dump(new_textures, f, indent=4)
        
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/textures/image/<path:filename>')
def get_texture_image(filename):
    return send_from_directory(TEXTURES_DIR, filename)

# --- FONT PARSING LOGIC START ---

def parse_font_filename(filename):
    """
    Analyzes the filename and extracts family, weight, and style.
    Example: "Inter_18pt-BoldItalic.ttf" -> Family: "Inter", Weight: 700, Style: "italic"
    """
    name_part = os.path.splitext(filename)[0]
    
    # 1. Default values
    weight = 'normal' # 400
    style = 'normal'
    
    # 2. Detect style (Italic/Oblique)
    if re.search(r'(italic|oblique)', name_part, re.IGNORECASE):
        style = 'italic'
    
    # 3. Detect weight (Keywords & Mapping to CSS numbers)
    # Order is important: Check 'ExtraBold' before 'Bold'!
    weight_map = {
        r'(thin|hairline|100)': '100',
        r'(extra[-]?light|ultra[-]?light|200)': '200',
        r'(light|300)': '300',
        r'(normal|regular|book|400)': '400',
        r'(medium|500)': '500',
        r'(semi[-]?bold|demi[-]?bold|600)': '600',
        r'(extra[-]?bold|ultra[-]?bold|800)': '800', # Check ExtraBold before Bold
        r'(bold|700)': '700',                         # Bold as the last of the bold variants
        r'(black|heavy|900)': '900'
    }
    
    lower_name = name_part.lower()
    for pattern, w_val in weight_map.items():
        if re.search(pattern, lower_name):
            weight = w_val
            break # First match wins (hence order above is important)

    # 4. Cleaning up the family name
    # We remove all keywords found above from the name
    remove_patterns = [
        r'(italic|oblique)',
        r'(thin|hairline|100)',
        r'(extra[-]?light|ultra[-]?light|200)',
        # r'(light|300)', # Removed aggressive match that breaks "Highlight"
        r'[-_ ](light|300)', # Only remove if preceded by separator (Fixes Highlight -> High)
        r'(normal|regular|book|400)',
        r'(medium|500)',
        r'(semi[-]?bold|demi[-]?bold|600)',
        r'(extra[-]?bold|ultra[-]?bold|800)',
        r'(bold|700)',
        r'(black|heavy|900)',
        r'(_\d+pt)', # Removes e.g. "_18pt" or "_24pt" (like in Inter)
        r'(variablefont_wght)'
    ]
    
    clean_name = name_part
    for p in remove_patterns:
        clean_name = re.sub(p, '', clean_name, flags=re.IGNORECASE)
        
    # Clean up separators (underscores, hyphens at the end/beginning)
    clean_name = re.sub(r'[-_ ]+', ' ', clean_name).strip()
    
    # Fallback: If everything was deleted (e.g. filename was just "Bold.ttf"), use original
    if not clean_name:
        clean_name = name_part

    return {
        'family': clean_name,
        'weight': weight,
        'style': style,
        'src': filename
    }

def get_font_metadata():
    if not os.path.exists(FONTS_DIR):
        return []
        
    fonts = []
    for f in os.listdir(FONTS_DIR):
        if f.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
            meta = parse_font_filename(f)
            fonts.append(meta)
    return fonts

@gui_editor_bp.route('/dynamic_fonts.css')
def dynamic_fonts_css():
    """Generates CSS @font-face rules that group families."""
    fonts = get_font_metadata()
    css = []
    
    for font in fonts:
        # Here is the trick: We use the same 'font-family' name for different files
        rule = (
            f"@font-face {{\n"
            f"    font-family: '{font['family']}';\n"
            f"    src: url('{url_for('gui_editor.get_font_file', filename=font['src'])}');\n"
            f"    font-weight: {font['weight']};\n"
            f"    font-style: {font['style']};\n"
            f"    font-display: swap;\n"
            f"}}"
        )
        css.append(rule)
        
    return "\n".join(css), 200, {'Content-Type': 'text/css'}

@gui_editor_bp.route('/api/fonts/list')
def list_fonts():
    """Returns only the unique family names for the dropdown."""
    fonts = get_font_metadata()
    # Use Set to remove duplicates, then sort
    families = sorted(list(set(f['family'] for f in fonts)))
    return jsonify(families)

@gui_editor_bp.route('/api/fonts/grouped')
def list_fonts_grouped():
    """Returns fonts grouped by family for the manager UI."""
    fonts = get_font_metadata()
    grouped = {}
    for f in fonts:
        fam = f['family']
        if fam not in grouped:
            grouped[fam] = []
        grouped[fam].append(f)
    
    # Sort families alphabetically
    sorted_keys = sorted(grouped.keys())
    result = {k: grouped[k] for k in sorted_keys}
    return jsonify(result)

# --- FONT PARSING LOGIC END ---

@gui_editor_bp.route('/api/fonts/add', methods=['POST'])
def add_font():
    file = request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "File required"}), 400
    
    filename = file.filename
    # Basic sanitization
    filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip()
    
    if not filename.lower().endswith(('.ttf', '.otf', '.woff', '.woff2')):
         return jsonify({"status": "error", "message": "Invalid font file type"}), 400

    file.save(os.path.join(FONTS_DIR, filename))
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/fonts/delete/<filename>', methods=['POST'])
def delete_font(filename):
    # sanitize filename to prevent directory traversal
    filename = os.path.basename(filename)
    path = os.path.join(FONTS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/fonts/file/<path:filename>')
def get_font_file(filename):
    return send_from_directory(FONTS_DIR, filename)

@gui_editor_bp.route('/api/custom-icons/list')
def list_custom_icons():
    icons = []
    if os.path.exists(CUSTOM_ICONS_DIR):
        icons = [f for f in os.listdir(CUSTOM_ICONS_DIR) if f.lower().endswith(('.png', '.svg', '.jpg', '.jpeg'))]
    return jsonify(sorted(icons))

@gui_editor_bp.route('/api/custom-icons/add', methods=['POST'])
def add_custom_icon():
    file = request.files.get('file')
    if not file:
        return jsonify({"status": "error", "message": "File required"}), 400
    
    filename = file.filename
    # Basic sanitization
    filename = "".join(c for c in filename if c.isalnum() or c in "._-").strip()
    
    if not filename.lower().endswith(('.png', '.svg', '.jpg', '.jpeg')):
         return jsonify({"status": "error", "message": "Invalid file type"}), 400

    file.save(os.path.join(CUSTOM_ICONS_DIR, filename))
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/custom-icons/delete/<filename>', methods=['POST'])
def delete_custom_icon(filename):
    filename = os.path.basename(filename)
    path = os.path.join(CUSTOM_ICONS_DIR, filename)
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/custom-icons/image/<path:filename>')
def get_custom_icon_image(filename):
    return send_from_directory(CUSTOM_ICONS_DIR, filename)

@gui_editor_bp.route('/api/layouts/save', methods=['POST'])
def save_layout():
    data = request.json
    name = data.get('name')
    layout = data.get('layout')
    preview_image = data.get('preview_image')
    action_url = data.get('action_url')
    media_title = data.get('media_title')
    metadata = data.get('metadata')
    if not name or not layout:
        return jsonify({"status": "error", "message": "Missing name or layout data"}), 400
    
    safe_name = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    if not safe_name: return jsonify({"status": "error", "message": "Invalid name"}), 400

    path = os.path.join(LAYOUTS_DIR, f"{safe_name}.json")
    
    if metadata:
        layout['metadata'] = metadata

    with open(path, 'w') as f:
        json.dump(layout, f)
    
    # Clear existing previews for this layout to avoid mixing old and new images
    preview_dir_path = os.path.join(LAYOUT_PREVIEWS_DIR, safe_name)
    if os.path.exists(preview_dir_path):
        shutil.rmtree(preview_dir_path)
    
    # Save Preview Image (Thumbnail)
    if preview_image:
        if ',' in preview_image:
            preview_image = preview_image.split(',')[1]
        try:
            preview_path = os.path.join(LAYOUT_PREVIEWS_DIR, f"{safe_name}.jpg")
            with open(preview_path, "wb") as f:
                f.write(base64.b64decode(preview_image))
        except Exception as e:
            print(f"Error saving layout preview: {e}")
            
    # Save status.json for Android App Deep Link
    bg_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'editor_backgrounds', safe_name)
    if not os.path.exists(bg_dir):
        os.makedirs(bg_dir)
        
    status_data = {
        "action_url": action_url,
        "title": media_title,
        "timestamp": int(time.time())
    }
    with open(os.path.join(bg_dir, 'status.json'), 'w') as f:
        json.dump(status_data, f)

    return jsonify({"status": "success"})

@gui_editor_bp.route('/api/layouts/load/<name>')
def load_layout(name):
    safe_name = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    path = os.path.join(LAYOUTS_DIR, f"{safe_name}.json")
    if os.path.exists(path):
        with open(path, 'r') as f:
            return jsonify(json.load(f))
    return jsonify({"status": "error", "message": "Layout not found"}), 404

@gui_editor_bp.route('/api/layouts/preview/<name>')
def get_layout_preview(name):
    safe_name = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    filename = f"{safe_name}.jpg"
    return send_from_directory(LAYOUT_PREVIEWS_DIR, filename)

@gui_editor_bp.route('/api/layouts/for-app')
def list_layouts_for_app():
    layouts = []
    if os.path.exists(LAYOUTS_DIR):
        files = [f for f in os.listdir(LAYOUTS_DIR) if f.endswith('.json')]
        for f in sorted(files):
            name = f.replace('.json', '')
            preview_url = url_for('gui_editor.get_layout_preview', name=name, _external=True)
            layouts.append({"name": name, "preview_url": preview_url})
    return jsonify(layouts)

@gui_editor_bp.route('/api/wallpaper/status')
def get_wallpaper_status():
    # --- Search Engine Logic ---
    layout_name = request.args.get('layout', 'Default')
    genre_filter = request.args.get('genre')
    age_rating_filter = request.args.get('age_rating') or request.args.get('age')
    sort_mode = request.args.get('sort', 'random') # random, year, rating

    safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
    base_path = os.path.dirname(os.path.abspath(__file__))
    target_dir = os.path.join(base_path, 'editor_backgrounds', safe_layout)
    
    response = {
        "imageUrl": None,
        "actionUrl": None,
        "title": None
    }

    if not os.path.exists(target_dir):
        return jsonify(response) # Return empty if layout not found

    # 1. Collect Candidates
    candidates = []
    for f in os.listdir(target_dir):
        if f.endswith('.json') and f != 'status.json':
            full_path = os.path.join(target_dir, f)
            try:
                with open(full_path, 'r') as json_file:
                    data = json.load(json_file)
                    meta = data.get('metadata', {})
                    
                    item = {
                        "path": full_path,
                        "data": data,
                        "year": int(meta.get('year', 0)) if str(meta.get('year', '0')).isdigit() else 0,
                        "rating": float(meta.get('rating', 0)) if str(meta.get('rating', '0')).replace('.','',1).isdigit() else 0.0,
                        "genres": str(meta.get('genres', '')),
                        "officialRating": str(meta.get('officialRating', '')),
                        "mtime": os.path.getmtime(full_path)
                    }
                    candidates.append(item)
            except: continue

    if not candidates:
        return jsonify(response)

    # 2. Filter
    filtered = candidates
    if genre_filter:
        g_search = genre_filter.lower().strip()
        filtered = [c for c in filtered if g_search in c['genres'].lower()]
        
    if age_rating_filter:
        # Normalize: remove spaces and dashes for comparison (e.g. "FSK-16" -> "fsk16")
        a_search = "".join(c for c in age_rating_filter.lower() if c.isalnum())
        filtered = [c for c in filtered if a_search in "".join(k for k in c['officialRating'].lower() if k.isalnum())]

    # Fallback if filter too strict
    if not filtered:
        filtered = candidates

    # 3. Sort / Pick
    selected = None
    if sort_mode == 'year':
        filtered.sort(key=lambda x: x['year'], reverse=True)
        selected = filtered[0]
    elif sort_mode == 'rating':
        filtered.sort(key=lambda x: x['rating'], reverse=True)
        selected = filtered[0]
    elif sort_mode == 'latest':
        filtered.sort(key=lambda x: x['mtime'], reverse=True)
        selected = filtered[0]
    else: # random
        selected = random.choice(filtered)

    # 4. Construct Response
    if selected:
        data = selected['data']
        filename = os.path.basename(selected['path']).replace('.json', '.jpg')
        # Use layout subfolder logic for URL
        folder_param = f"Layout: {safe_layout}"
        response["imageUrl"] = url_for('gui_editor.get_gallery_image', folder=folder_param, filename=filename, _external=True)
        response["actionUrl"] = data.get("metadata", {}).get("action_url") or data.get("action_url")
        response["title"] = data.get("metadata", {}).get("title")
            
    return jsonify(response)

@gui_editor_bp.route('/api/current-background')
def get_current_background():
    layout_name = request.args.get('layout', 'Default')
    safe_name = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
    
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # 1. Try High-Res Render (e.g. rendered_LayoutName.jpg in editor_backgrounds)
    high_res_path = os.path.join(base_path, 'editor_backgrounds', f"rendered_{safe_name}.jpg")
    if os.path.exists(high_res_path):
        return send_file(high_res_path)
        
    # 2. Fallback: Layout Preview
    preview_path = os.path.join(LAYOUT_PREVIEWS_DIR, f"{safe_name}.jpg")
    if os.path.exists(preview_path):
        return send_from_directory(LAYOUT_PREVIEWS_DIR, f"{safe_name}.jpg")
        
    return jsonify({"error": "Background not found"}), 404

@gui_editor_bp.route('/api/layouts/delete/<name>', methods=['POST'])
def delete_layout(name):
    safe_name = "".join(c for c in name if c.isalnum() or c in " ._-").strip()
    if not safe_name:
        return jsonify({"status": "error", "message": "Invalid name"}), 400

    json_path = os.path.join(LAYOUTS_DIR, f"{safe_name}.json")
    preview_path = os.path.join(LAYOUT_PREVIEWS_DIR, f"{safe_name}.jpg")
    preview_dir_path = os.path.join(LAYOUT_PREVIEWS_DIR, safe_name)

    try:
        if os.path.exists(json_path):
            os.remove(json_path)
        if os.path.exists(preview_path):
            os.remove(preview_path)
        if os.path.exists(preview_dir_path):
            shutil.rmtree(preview_dir_path)
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/gallery/delete_all', methods=['POST'])
def delete_all_gallery_images():
    data = request.json
    folder = data.get('folder')
    if not folder:
        return jsonify({"status": "error", "message": "Missing folder"}), 400

    base_path = os.path.dirname(os.path.abspath(__file__))
    target_dir = None

    if folder.startswith("Layout: "):
        layout_name = folder.replace("Layout: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        target_dir = os.path.join(base_path, "editor_backgrounds", safe_layout)
    elif folder.startswith("LayoutPreview: "):
        layout_name = folder.replace("LayoutPreview: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        target_dir = os.path.join(base_path, "layouts", "previews", safe_layout)
    elif folder == "Editor (Unsorted)":
        target_dir = os.path.join(base_path, "editor_backgrounds")
    elif folder in KNOWN_DIRS:
        target_dir = os.path.join(base_path, folder)
    
    if not target_dir or not os.path.exists(target_dir):
        return jsonify({"status": "error", "message": "Invalid or non-existent folder"}), 400

    try:
        for filename in os.listdir(target_dir):
            file_path = os.path.join(target_dir, filename)
            if os.path.isfile(file_path) and filename.lower().endswith(('.jpg', '.jpeg', '.png', '.json')):
                os.remove(file_path)
        
        # Check if directory is empty and remove it if so (only for subfolders)
        if not os.listdir(target_dir) and target_dir != os.path.join(base_path, "editor_backgrounds"):
            os.rmdir(target_dir)
            
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/save_image', methods=['POST'])
def save_editor_image():
    global LATEST_GENERATED_IMAGE
    data = request.json
    image_data = data.get('image')
    metadata = data.get('metadata', {})
    layout_name = data.get('layout_name', 'Default')
    canvas_json = data.get('canvas_json')
    overwrite_filename = data.get('overwrite_filename')
    target_type = data.get('target_type', 'gallery')
    organize_by_genre = data.get('organize_by_genre', False)

    if not image_data:
        return jsonify({"status": "error", "message": "No image data"}), 400
    
    if ',' in image_data:
        image_data = image_data.split(',')[1]
    
    if target_type == 'layout_preview':
        folder = os.path.join("layouts", "previews")
    else:
        folder = "editor_backgrounds"
        
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
    if not safe_layout: safe_layout = "Default"
    
    full_path = os.path.join(base_path, folder, safe_layout)
    
    # Genre Sorting Logic
    if organize_by_genre and metadata and metadata.get('genres'):
        # Get the first genre from the comma-separated list
        first_genre = str(metadata.get('genres', '')).split(',')[0].strip()
        safe_genre = "".join(c for c in first_genre if c.isalnum() or c in " ._-").strip()
        if safe_genre:
            full_path = os.path.join(full_path, safe_genre)
    
    if not os.path.exists(full_path):
        os.makedirs(full_path)
    
    if overwrite_filename:
        filename = overwrite_filename
    else:
        filename = f"custom_{int(time.time())}.jpg"
        
        if metadata and metadata.get('title'):
            safe_title = "".join(c for c in metadata['title'] if c.isalnum() or c in " ._-").strip()
            parts = [safe_title]
            if metadata.get('year') and str(metadata['year']) != 'N/A':
                parts.append(str(metadata['year']))
            if metadata.get('imdb_id'):
                parts.append(str(metadata['imdb_id']))
            
            filename = " - ".join(parts) + ".jpg"

    filepath = os.path.join(full_path, filename)
    
    try:
        with open(filepath, "wb") as f:
            f.write(base64.b64decode(image_data))
            
        # Save JSON data if provided
        if canvas_json:
            json_path = os.path.splitext(filepath)[0] + ".json"
            with open(json_path, "w") as f:
                json.dump(canvas_json, f)
                
        # Update JSON with action_url if provided in metadata
        if metadata and metadata.get('action_url'):
            # Re-read or just update the dict before dumping if we hadn't dumped yet.
            # Since we dumped canvas_json above, let's load it back or just append to it if canvas_json was a dict.
            # Better: Modify canvas_json before dumping.
            pass # Logic moved below to be cleaner
            
        final_json_data = canvas_json if canvas_json else {}
        if metadata:
            final_json_data['metadata'] = metadata
            final_json_data['action_url'] = metadata.get('action_url')
            
        json_path = os.path.splitext(filepath)[0] + ".json"
        with open(json_path, "w") as f:
            json.dump(final_json_data, f)

        # Update global variable for preview
        LATEST_GENERATED_IMAGE = filepath

        return jsonify({"status": "success", "filename": filename})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@gui_editor_bp.route('/api/gallery/data/<folder>/<path:filename>')
def get_gallery_image_data(folder, filename):
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Determine target directory (logic shared with get_gallery_image)
    target_dir = ""
    if folder.startswith("Layout: "):
        layout_name = folder.replace("Layout: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        target_dir = os.path.join(base_path, "editor_backgrounds", safe_layout)
    elif folder.startswith("LayoutPreview: "):
        layout_name = folder.replace("LayoutPreview: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        target_dir = os.path.join(base_path, "layouts", "previews", safe_layout)
    elif folder == "Editor (Unsorted)":
        target_dir = os.path.join(base_path, "editor_backgrounds")
    elif folder in KNOWN_DIRS:
        target_dir = os.path.join(base_path, folder)
    else:
        return jsonify({"status": "error", "message": "Invalid folder"}), 400

    json_filename = os.path.splitext(filename)[0] + ".json"
    json_path = os.path.join(target_dir, json_filename)
    
    if os.path.exists(json_path):
        with open(json_path, 'r') as f:
            return jsonify(json.load(f))
    
    return jsonify({"status": "error", "message": "No layout data found for this image"}), 404

@gui_editor_bp.route('/api/certification/<path:filename>')
def get_certification_image(filename):
    cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'certification')
    return send_from_directory(cert_dir, filename)

@gui_editor_bp.route('/get_local_background')
def get_local_background():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    return send_from_directory(current_dir, 'background.jpg')

@gui_editor_bp.route('/editor')
def editor_index():
    config = load_config()
    fonts = get_font_metadata()
    families = sorted(list(set(f['family'] for f in fonts)))
    data = {"title": "TV Background", "backdrop_url": url_for('gui_editor.get_local_background'), "version": CURRENT_VERSION, "font_families": families}
    return render_template('editor.html', data=data, config=config)

@gui_editor_bp.route('/api/gallery/list')
def list_gallery_images():
    gallery = {}
    base_path = os.path.dirname(os.path.abspath(__file__))
    for folder in KNOWN_DIRS:
        folder_path = os.path.join(base_path, folder)
        if os.path.exists(folder_path):
            if folder == "editor_backgrounds":
                # Scan subdirectories for layouts
                try:
                    subdirs = [d for d in os.listdir(folder_path) if os.path.isdir(os.path.join(folder_path, d))]
                    if not subdirs:
                        # Fallback for root files
                        images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                        if images: gallery["Editor (Unsorted)"] = sorted(images)
                    else:
                        for subdir in subdirs:
                            sub_path = os.path.join(folder_path, subdir)
                            images = [f for f in os.listdir(sub_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                            if images: gallery[f"Layout: {subdir}"] = sorted(images)
                except: pass
            elif folder == "layouts":
                # Scan previews subdirectory
                previews_dir = os.path.join(folder_path, "previews")
                if os.path.exists(previews_dir):
                    try:
                        subdirs = [d for d in os.listdir(previews_dir) if os.path.isdir(os.path.join(previews_dir, d))]
                        for subdir in subdirs:
                            sub_path = os.path.join(previews_dir, subdir)
                            images = [f for f in os.listdir(sub_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                            if images: gallery[f"LayoutPreview: {subdir}"] = sorted(images)
                    except: pass
            elif folder != "layouts":
                images = [f for f in os.listdir(folder_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
                if images:
                    gallery[folder] = sorted(images)
    return jsonify(gallery)

@gui_editor_bp.route('/api/gallery/image/<folder>/<path:filename>')
def get_gallery_image(folder, filename):
    base_path = os.path.dirname(os.path.abspath(__file__))
    
    # Handle Layout subfolders
    if folder.startswith("Layout: "):
        layout_name = folder.replace("Layout: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        return send_from_directory(os.path.join(base_path, "editor_backgrounds", safe_layout), filename)
    
    if folder.startswith("LayoutPreview: "):
        layout_name = folder.replace("LayoutPreview: ", "").strip()
        safe_layout = "".join(c for c in layout_name if c.isalnum() or c in " ._-").strip()
        return send_from_directory(os.path.join(base_path, "layouts", "previews", safe_layout), filename)
    
    if folder == "Editor (Unsorted)":
        return send_from_directory(os.path.join(base_path, "editor_backgrounds"), filename)

    if folder not in KNOWN_DIRS:
        return "Invalid folder", 400
         
    return send_from_directory(os.path.join(base_path, folder), filename)

@gui_editor_bp.route('/api/batch/preview/latest_image')
def get_latest_batch_image():
    global LATEST_GENERATED_IMAGE
    if LATEST_GENERATED_IMAGE and os.path.exists(LATEST_GENERATED_IMAGE):
        return send_file(LATEST_GENERATED_IMAGE)
    return "", 404

if __name__ == '__main__':
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(gui_editor_bp)
    app.run(debug=True, host='0.0.0.0', port=5000)