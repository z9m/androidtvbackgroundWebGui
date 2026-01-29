import requests
import os
import time
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import unicodedata
import shutil
import textwrap
import json
from dotenv import load_dotenv
load_dotenv(verbose=True)
# --- IMPORT IMAGE ENGINE ---
from image_engine import ImageGenerator
# Jellyfin Server Configuration (Global Parameters)
baseurl = os.getenv('JELLYFIN_BASEURL')
token = os.getenv('JELLYFIN_TOKEN')
user_id = os.getenv('JELLYFIN_USER_ID')
# try to connect to the server and get the user name

try:
    print('Trying to connect to JellyFin')
    print(f'baseurl:{baseurl}')
    print(f'token:{token}')
    print(f'user_id:{user_id}')
    url = f"{baseurl}/Users/{user_id}"
    response = requests.get(url, headers={"X-Emby-Token": token})
    response.raise_for_status()
    data = response.json()
    print(f"Connected to Jellyfin! User name: {data.get('Name')}")
except requests.exceptions.RequestException as e:
    print(f"Failed to connect to Jellyfin: {e}")
    exit(1)

# Save font locally
truetype_url = 'https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf'
truetype_path = 'Roboto-Light.ttf'

if not os.path.exists(truetype_path):
    try:
        response = requests.get(truetype_url, timeout=10)
        if response.status_code == 200:
            with open(truetype_path, 'wb') as f:
                f.write(response.content)
            print("Roboto-Light font saved")
        else:
            print(f"Failed to download Roboto-Light font. Status code: {response.status_code}")
    except Exception as e:
        print(f"An error occurred while downloading the Roboto-Light font: {e}")

# Set the order_by parameter to 'aired' or 'added'
order_by = 'DateCreated' # 'DateCreated', 'DateLastContentAdded', 'PremiereDate'
download_movies = True
download_series = True
limit = 10
overwrite_existing = False

if os.path.exists('config.json'):
    try:
        with open('config.json', 'r') as f:
            overwrite_existing = json.load(f).get('general', {}).get('overwrite_existing', False)
    except: pass

excluded_genres = ['Horror', 'Thriller']
excluded_tags = ['Adult', 'Violence']
excluded_libraries = ['Web Videos']

# Create a directory to save the backgrounds and clear its contents if it exists
background_dir = "jellyfin_backgrounds"
if os.path.exists(background_dir):
    shutil.rmtree(background_dir)
os.makedirs(background_dir, exist_ok=True)

# Initialize the engine once
engine = ImageGenerator()
def clean_filename(filename):
    cleaned_filename = "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
    return cleaned_filename

def download_logo_in_memory(media_item):
    logo_url = f"{baseurl}/Items/{media_item['Id']}/Images/Logo?api_key={token}"
    
    try:
        response = requests.get(logo_url, timeout=10)
        if response.status_code == 200:
            logo_image = Image.open(BytesIO(response.content))
            return logo_image  # Return the logo as a PIL Image object
        else:
            print(f"Failed to retrieve logo for {media_item['Name']}. Status code: {response.status_code}")
            return None
    except Exception as e:
        print(f"An error occurred while downloading the logo for {media_item['Name']}: {e}")
        return None

def get_excluded_library_paths():
    """Fetch library IDs based on excluded library names."""
    headers = {'X-Emby-Token': token}
    response = requests.get(f"{baseurl}/Library/VirtualFolders", headers=headers)
    
    if response.status_code == 200:
        libraries = response.json()
        # print(json.dumps(libraries,indent=4))
        locs = [lib['Locations'] for lib in libraries if lib['Name'] in excluded_libraries]
        locs = [item for sublist in locs for item in sublist]
        return set(locs)
    else:
        print("Failed to retrieve library information.")
        return set()

excluded_library_paths = get_excluded_library_paths()

def download_latest_media(order_by, limit, media_type):
    headers = {'X-Emby-Token': token}
    params = {
        'SortBy': order_by,
        'Limit': limit,
        'IncludeItemTypes': media_type,
        'Recursive': 'true',
        'SortOrder': 'Descending',
        'Fields': 'Path,Overview,Genres,CommunityRating,PremiereDate,Tags',
        'ExcludeItemTypes': 'BoxSet'
    }
    response = requests.get(f"{baseurl}/Users/{user_id}/Items", headers=headers, params=params)

    if response.status_code == 200:
        media_items = response.json()['Items']
    else:
        print(f"Failed to retrieve media items. Status code: {response.status_code}")
        return

    # Filter out excluded genres, tags, and libraries
    filtered_items = []

    for item in media_items:
        if item.get('Type') == 'BoxSet':
            continue
        if any(genre in excluded_genres for genre in item.get('Genres', [])):
            continue
        if any(tag in excluded_tags for tag in item.get('Tags', [])):
            continue
        if any(excluded_path in item.get('Path') for excluded_path in excluded_library_paths):
            continue
        filtered_items.append(item)

    # Process the sorted media
    for item in filtered_items:
        # Get the URL of the background image
        background_url = f"{baseurl}/Items/{item['Id']}/Images/Backdrop?api_key={token}"

        if background_url:
            try:
                filename_safe_title = unicodedata.normalize('NFKD', item['Name']).encode('ASCII', 'ignore').decode('utf-8')
                filename_safe_title = clean_filename(filename_safe_title)
                background_filename = os.path.join(background_dir, f"{filename_safe_title}_{item['ProductionYear']}.jpg")
                
                if not overwrite_existing and os.path.exists(background_filename):
                    print(f"Skipping {item['Name']} - Background already exists.")
                    continue

                # Download the background image with a timeout of 10 seconds
                response = requests.get(background_url, timeout=10)

                if response.status_code == 200:
                    artwork_image = Image.open(BytesIO(response.content)).convert("RGB")
                    logo_image = download_logo_in_memory(item)

                    # 1. Create Canvas using the engine's color method
                    engine.create_color_canvas(artwork_image, target_width=3000)

                    # 2. Draw Elements
                    engine.draw_logo_or_title(logo_image=logo_image, title_text=item.get('Name'))

                    # 3. Prepare and Draw Info Text
                    tags = []
                    
                    # Year
                    tags.append(item.get('PremiereDate', 'N/A')[:4])
                    
                    # Genres
                    if 'Genres' in item:
                        tags.append(', '.join(item.get('Genres', [])[:3]))

                    if media_type == 'Movie':
                        duration_ticks = item.get('RunTimeTicks', 0)
                        if duration_ticks:
                            duration_minutes = duration_ticks // (10**7 * 60)
                            tags.append(f"{duration_minutes // 60}h{duration_minutes % 60}min")
                    else:  # Series
                        seasons_response = requests.get(f"{baseurl}/Shows/{item['Id']}/Seasons?api_key={token}", timeout=10)
                        if seasons_response.ok:
                            seasons_count = len([s for s in seasons_response.json().get('Items', []) if s.get('Type') == 'Season' and s.get('IndexNumber', 0) > 0])
                            if seasons_count > 0:
                                tags.append(f"{seasons_count} {'Season' if seasons_count == 1 else 'Seasons'}")

                    # Rating (Rounded)
                    if 'CommunityRating' in item:
                        try:
                            rating_val = float(item['CommunityRating'])
                            tags.append(f"IMDb: {rating_val:.1f}")
                        except (ValueError, TypeError):
                            pass
                    
                    engine.draw_horizontal_tags(tags)

                    # 4. Draw Summary
                    summary_text = item.get('Overview', '')
                    engine.draw_summary(summary_text)

                    # 5. Draw Footer
                    engine.draw_custom_text_and_provider_logo("Now Available on", "jellyfinlogo.png")

                    # 6. Save the final image
                    engine.save(background_filename)
                    print(f"Image saved: {background_filename}")

                else:
                    print(f"Failed to download background for {item['Name']}")
            except Exception as e:
                print(f"An error occurred while processing {item['Name']}: {e}")

        time.sleep(1)

# Download the latest movies according to the specified order and limit
if download_movies:
    download_latest_media(order_by, limit, 'Movie')

# Download the latest TV series according to the specified order and limit
if download_series:
    download_latest_media(order_by, limit, 'Series')
