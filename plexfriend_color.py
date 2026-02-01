# Fetch friends' libraries 

# === Standard Library Imports ===
import os
import time
from datetime import datetime
import shutil
import unicodedata
from io import BytesIO
from typing import Tuple
import textwrap
import json

# === Third-Party Imports ===
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np
from plexapi.myplex import MyPlexAccount
from dotenv import load_dotenv
load_dotenv(verbose=True)

# === User Configurable Options ===
PLEX_TOKEN = locals().get('token', os.getenv('PLEX_TOKEN'))
TARGET_FRIEND = None  # e.g. "Alice Dupont"
order_by = 'added'      # 'aired', 'added', or 'mix'
download_movies = True
download_series = True
limit = 5
overwrite_existing = False

if os.path.exists('config.json'):
    try:
        with open('config.json', 'r') as f:
            overwrite_existing = json.load(f).get('general', {}).get('overwrite_existing', False)
    except: pass

debug = False

logo_variant = 'white'
plex_logo_horizontal_offset = 0
plex_logo_vertical_offset = 7

max_summary_chars = 175
max_summary_width = 1400
summary_max_lines = 3


added_label = 'Now shared on'
aired_label = 'Recent release, shared on'
random_label = 'Shared on'
default_label = 'Now shared on'

env_font_url = 'https://github.com/googlefonts/roboto/raw/main/src/hinted/Roboto-Light.ttf'
env_font_name = 'Roboto-Light.ttf'

main_color     = 'white'
info_color     = 'white'
summary_color  = 'white'
metadata_color = 'white'
shadow_color   = 'black'
shadow_offset  = 2

plex_api_delay_seconds = 1.0

# Prepare output directory
background_dir = 'plexfriend_backgrounds'
if os.path.exists(background_dir):
    shutil.rmtree(background_dir)
os.makedirs(background_dir, exist_ok=True)

# === Download Font ===
def download_font(url, path):
    try:
        if not os.path.exists(path):
            r = requests.get(url, timeout=10)
            if r.status_code == 200:
                with open(path, 'wb') as f: f.write(r.content)
                return True
            return False
        return True
    except:
        return False

# === Discover Friend Servers ===
def get_friend_servers(token, target_friend=None):
    account = MyPlexAccount(token=token)
    friend_map = {u.id: u.title for u in account.users()}
    servers = {}
    for res in account.resources():
        if res.provides == 'server' and not res.owned:
            owner = friend_map.get(res.ownerId)
            if not owner or (target_friend and owner != target_friend):
                continue
            try:
                plex = res.connect()
                servers[owner] = plex
                print(f"[INFO] Connected to {owner}'s server: {res.name}")
            except Exception as e:
                print(f"[WARN] Could not connect to {owner}: {e}")
    return servers

# === Utilities ===
def clean_filename(name):
    return ''.join(c if c.isalnum() or c in '._-' else '_' for c in name)

def resize_image(img, h):
    ratio = h / img.height
    return img.resize((int(img.width*ratio), h))

def resize_logo(img, w, h):
    aspect = img.width / img.height
    new_w = min(w, int(h*aspect))
    new_h = int(new_w/aspect)
    return img.resize((new_w, new_h))

def truncate_summary(summary, max_chars):
    return textwrap.shorten(summary or "", width=max_chars, placeholder="...")

def wrap_text_by_pixel_width(text, font, max_width, draw):
    words, lines, cur = text.split(), [], ''
    for w in words:
        test = (cur+' '+w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
    if cur: lines.append(cur)
    return lines

def draw_text_with_shadow(draw, pos, text, font, fill, shadow, offset=(2,2)):
    x,y = pos
    draw.text((x+offset[0], y+offset[1]), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill)

def wrap_summary_with_line_limit(text, font, max_width, draw, max_lines=3):
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if draw.textlength(test, font=font) <= max_width:
            cur = test
        else:
            if cur: lines.append(cur)
            cur = w
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)

    if len(lines) > max_lines:
        lines = lines[:max_lines]

    last_line = lines[-1]
    if draw.textlength(last_line + " ...", font=font) <= max_width:
        lines[-1] = last_line + " ..."
    else:
        while draw.textlength(last_line + "...", font=font) > max_width and last_line:
            last_line = last_line[:-1]
        lines[-1] = last_line + "..."
    return lines

def download_logo_in_memory(item, baseurl, token):
    url = f"{baseurl}/library/metadata/{item.ratingKey}/clearLogo?X-Plex-Token={token}"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            return Image.open(BytesIO(r.content))
    except:
        pass
    return None

# === Background Pipeline ===
def vignette_side(h, w, fade_ratio=0.3, fade_power=2.5, position="bottom-left"):
    y, x = np.ogrid[0:h, 0:w]
    rx, ry = w * fade_ratio, h * fade_ratio
    dist_x, dist_y = np.ones_like(x, dtype=np.float32), np.ones_like(y, dtype=np.float32)

    if "left" in position: dist_x = np.clip(x / rx, 0, 1)
    elif "right" in position: dist_x = np.clip((w - x) / rx, 0, 1)
    if "top" in position: dist_y = np.clip(y / ry, 0, 1)
    elif "bottom" in position: dist_y = np.clip((h - y) / ry, 0, 1)

    if any(corner in position for corner in ["left","right"]) and any(corner in position for corner in ["top","bottom"]):
        alpha = np.minimum(dist_x, dist_y)
    else:
        alpha = dist_x * dist_y

    return Image.fromarray((alpha ** fade_power * 255).astype(np.uint8))

def create_blurry_background(image, size=(3840,2160), blur_radius=800, dither_strength=16):
    bg = image.resize(size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=blur_radius))
    bg_array = np.array(bg).astype(np.float32)
    noise = np.random.uniform(-dither_strength, dither_strength, bg_array.shape)
    return Image.fromarray(np.clip(bg_array+noise,0,255).astype(np.uint8))

def generate_background_fast(input_img, target_width=3000):
    canvas_rgb = create_blurry_background(input_img, size=(3840,2160), blur_radius=800)
    canvas_array = (np.array(canvas_rgb).astype(np.float32)*0.4).clip(0,255).astype(np.uint8)
    canvas_rgb = Image.fromarray(canvas_array)

    canvas = Image.new("RGBA", canvas_rgb.size, (0,0,0,255))
    canvas.paste(canvas_rgb,(0,0))

    w_percent = target_width / input_img.width
    new_size = (target_width, int(input_img.height*w_percent))
    img_resized = input_img.resize(new_size, Image.LANCZOS).convert("RGBA")

    h, w = img_resized.height, img_resized.width
    mask = vignette_side(h, w, fade_ratio=0.3, fade_power=2.5, position="bottom-left")
    mask = mask.filter(ImageFilter.GaussianBlur(radius=50))
    img_resized.putalpha(mask)

    canvas.paste(img_resized, (3840-w,0), img_resized)
    return canvas.convert("RGB")

# === Core Image Processing ===
def generate_background_for_item(item, media_type, order_type, plex_logo, target_folder, friend, plex):
    art_url = item.artUrl
    if not art_url:
        print(f"[WARN] No art for {item.title}")
        return

    today = datetime.today().strftime("%Y%m%d")
    safe = clean_filename(unicodedata.normalize("NFKD",item.title).encode("ASCII","ignore").decode())
    out_path = os.path.join(target_folder,f"{safe}.jpg")
    if not overwrite_existing and os.path.exists(out_path):
        print(f"Skipping {item.title} - Background already exists.")
        return

    try:
        r = requests.get(art_url, timeout=10); r.raise_for_status()
        art = Image.open(BytesIO(r.content)).convert("RGB")
    except Exception as e:
        print(f"[ERROR] Could not fetch art for {item.title}: {e}")
        return

    canvas = generate_background_fast(art, target_width=2700)
    draw = ImageDraw.Draw(canvas)

    ft_title   = ImageFont.truetype(env_font_name, size=190)
    ft_info    = ImageFont.truetype(env_font_name, size=55)
    ft_summary = ImageFont.truetype(env_font_name, size=50)
    ft_custom  = ImageFont.truetype(env_font_name, size=60)

    # --- DYNAMIC LAYOUT ---
    padding = 25
    current_x = 210
    current_y = 200 # Starting Y

    # 1. Logo or Title
    clogo = download_logo_in_memory(item, plex._baseurl, plex._token)
    if clogo:
        clogo = resize_logo(clogo,1300,400).convert("RGBA")
        canvas.paste(clogo,(current_x, current_y),clogo)
        current_y += clogo.height + padding
    else:
        title_text = truncate_summary(item.title,30)
        title_bbox = draw.textbbox((0,0), title_text, font=ft_title)
        draw_text_with_shadow(draw,(current_x - 10, current_y),title_text,ft_title,main_color,shadow_color,(shadow_offset,)*2)
        current_y += (title_bbox[3] - title_bbox[1]) + padding

    # 2. Info Text
    if media_type == "movie":
        genres = [g.tag for g in item.genres][:3]
        dur    = item.duration and f"{item.duration//3600000}h {(item.duration//60000)%60}min"
        rating = item.audienceRating or item.rating or ""
        parts  = [str(item.year)] + genres + ([dur] if dur else []) + ([f"IMDb: {rating}"] if rating else [])
    else:
        genres = [g.tag for g in item.genres][:3]
        seasons= len(item.seasons())
        rating = item.audienceRating or item.rating or ""
        parts  = [str(item.year)] + genres + ([f"{seasons} Season" if seasons==1 else f"{seasons} Seasons"]) + ([f"IMDb: {rating}"] if rating else [])
    info_text = "  •  ".join(filter(None, parts))
    draw_text_with_shadow(draw, (current_x, current_y), info_text, ft_info, info_color, shadow_color, (shadow_offset,)*2)
    info_bbox = draw.textbbox((0,0), info_text, font=ft_info)
    current_y += (info_bbox[3] - info_bbox[1]) + padding

    # 3. Summary
    summary = truncate_summary(item.summary, max_summary_chars)
    lines = wrap_summary_with_line_limit(summary, ft_summary, max_summary_width, draw, max_lines=summary_max_lines)
    wrapped = "\n".join(lines)
    draw_text_with_shadow(draw, (current_x, current_y), wrapped, ft_summary, summary_color, shadow_color, (shadow_offset,)*2)
    summary_bbox = draw.textbbox((0,0), wrapped, font=ft_summary)
    current_y += (summary_bbox[3] - summary_bbox[1]) + padding * 2

    # 4. Label and Plex Logo
    if friend:
        lbl = f"{added_label} {friend}'s" if order_type == "added" else aired_label if order_type == "aired" else f"{random_label} {friend}'s" if order_type == "random" else f"{default_label} {friend}'s"
    else:
        lbl = {"added": added_label, "aired": aired_label, "random": random_label}.get(order_type, default_label)
    draw_text_with_shadow(draw,(current_x, current_y),lbl,ft_custom,metadata_color,shadow_color,(shadow_offset,)*2)
    w0 = draw.textbbox((0,0), lbl, font=ft_custom)[2]
    lx = current_x + w0 + 20 + plex_logo_horizontal_offset
    ly = current_y + plex_logo_vertical_offset + 15
    canvas.paste(plex_logo,(lx,ly),plex_logo)

    # Save
    canvas.convert("RGB").save(out_path,quality=95)
    print(f"Saved: {out_path}")

# === Media Fetching ===
def sort_movies(movies,k): return sorted([m for m in movies if getattr(m,k,None)], key=lambda x:getattr(x,k), reverse=True)
def sort_shows(shows,k):
    arr=[]
    for s in shows:
        eps=[e for e in s.episodes() if getattr(e,k,None)]
        if eps: arr.append((s,max(eps,key=lambda e:getattr(e,k))))
    return [s for s,_ in sorted(arr,key=lambda t:getattr(t[1],k),reverse=True)]

def download_latest_media(plex, order, lim, typ, plex_logo, friend):
    items = plex.library.search(libtype="movie" if typ=="movie" else "show")
    key   = "originallyAvailableAt" if order=="aired" else "addedAt"
    sorted_items = (sort_movies if typ=="movie" else sort_shows)(items,key)[:lim]

    for itm in sorted_items:
        generate_background_for_item(itm, typ, order, plex_logo, background_dir, friend, plex)
        time.sleep(plex_api_delay_seconds)

# === Main ===
def main_for_friend(plex, friend):
    download_font(env_font_url, env_font_name)
    logo_file = "plexlogo.png" if logo_variant=="white" else "plexlogo_color.png"
    plex_logo = Image.open(os.path.join(os.path.dirname(__file__),logo_file)).convert("RGBA")

    if download_movies:
        download_latest_media(plex, order_by, limit, "movie", plex_logo, friend)
    if download_series:
        download_latest_media(plex, order_by, limit, "show", plex_logo, friend)

if __name__=="__main__":
    os.makedirs(background_dir, exist_ok=True)
    servers = get_friend_servers(PLEX_TOKEN, TARGET_FRIEND)
    for friend, plex in servers.items():
        print(f"\n=== Processing {friend} ===")
        main_for_friend(plex, friend)
