import os
import textwrap
import unicodedata
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
import numpy as np
from PIL import ImageFilter

class ImageGenerator:
    def __init__(self, font_path='Roboto-Light.ttf', background_path='bckg.png', overlay_path='overlay.png'):
        self.base_path = os.path.dirname(os.path.abspath(__file__))
        self.font_path = os.path.join(self.base_path, font_path)
        self.background_path = os.path.join(self.base_path, background_path)
        self.overlay_path = os.path.join(self.base_path, overlay_path)
        
        self.fonts = {}
        self._load_resources()
        
        # Layout State
        self.padding = 25
        self.shadow_offset = 2
        self.current_x = 210
        self.current_y = 200
        self.last_element_width = 0
        self.draw = None
        self.canvas = None

    def _load_resources(self):
        # Load Fonts
        try:
            self.fonts['title'] = ImageFont.truetype(self.font_path, size=190)
            self.fonts['info'] = ImageFont.truetype(self.font_path, size=55)
            self.fonts['summary'] = ImageFont.truetype(self.font_path, size=50)
            self.fonts['custom'] = ImageFont.truetype(self.font_path, size=60)
            self.fonts['metadata'] = ImageFont.truetype(self.font_path, size=50)
        except Exception as e:
            print(f"Error loading fonts: {e}")

        # Load Base Images
        try:
            self.base_bg = Image.open(self.background_path).convert('RGBA')
            self.overlay = Image.open(self.overlay_path).convert('RGBA')
        except Exception as e:
            print(f"Error loading base images: {e}")

    def reset_layout(self):
        """Resets the Y-cursor to the top position for a new image."""
        self.current_y = 200
        self.last_element_width = 0

    def create_canvas(self, artwork_image):
        """Creates the base canvas with artwork and overlay."""
        self.reset_layout()
        self.canvas = self.base_bg.copy()
        
        # Resize artwork to height 1500 maintaining aspect ratio
        ratio = 1500 / artwork_image.height
        width = int(artwork_image.width * ratio)
        resized_art = artwork_image.resize((width, 1500))
        
        # Paste artwork and overlay
        self.canvas.paste(resized_art, (1175, 0))
        self.canvas.paste(self.overlay, (1175, 0), self.overlay)
        
        self.draw = ImageDraw.Draw(self.canvas)
        return self.canvas

    def create_color_canvas(self, artwork_image, target_width=3000):
        """Creates a dynamic, blurred color canvas from the artwork."""
        self.reset_layout()

        # Step 1: Create blurry/dark canvas
        canvas_rgb, _ = self._create_blurry_background(artwork_image, size=(3840, 2160), blur_radius=800)
        canvas_array = (np.array(canvas_rgb).astype(np.float32) * 0.4).clip(0, 255).astype(np.uint8)
        canvas_rgb = Image.fromarray(canvas_array)

        self.canvas = Image.new("RGBA", canvas_rgb.size, (0, 0, 0, 255))
        self.canvas.paste(canvas_rgb, (0, 0))

        # Step 2: Resize input to target width and apply vignette
        w_percent = target_width / artwork_image.width
        new_size = (target_width, int(artwork_image.height * w_percent))
        img_resized = artwork_image.resize(new_size, Image.LANCZOS).convert("RGBA")
        mask = self._vignette_side(img_resized.height, img_resized.width, fade_ratio=0.3, fade_power=2.5, position="bottom-left")
        img_resized.putalpha(mask)

        # Step 3: Paste artwork and set up for drawing
        self.canvas.paste(img_resized, (3840 - img_resized.width, 0), img_resized)
        self.draw = ImageDraw.Draw(self.canvas)

    def ensure_high_contrast(self, image, threshold=100):
        """
        Analyzes the brightness of non-transparent pixels.
        If the average brightness is below the threshold, recolors the image to white
        while preserving the alpha channel.
        """
        if not image:
            return None
            
        img = image.convert("RGBA")
        data = np.array(img)
        
        if data.size == 0: return img
            
        r, g, b, a = data[:,:,0], data[:,:,1], data[:,:,2], data[:,:,3]
        mask = a > 0 # Requirement 2: ONLY for pixels that are not transparent (Alpha > 0)
        
        if not np.any(mask): return img
            
        # Calculate luminance: 0.299*R + 0.587*G + 0.114*B
        luminance = 0.299 * r[mask] + 0.587 * g[mask] + 0.114 * b[mask]
        avg_lum = np.mean(luminance)
        
        print(f"[DEBUG] Logo Luminance: {avg_lum:.2f} (Threshold: {threshold})")

        # Requirement 3: If below threshold, recolor to pure White (255, 255, 255)
        if avg_lum < threshold:
            print("[DEBUG] -> Recoloring logo to WHITE")
            white_img = Image.new("RGBA", img.size, (255, 255, 255, 0))
            white_img.paste((255, 255, 255, 255), (0, 0), mask=img)
            return white_img
            
        print("[DEBUG] -> Keeping original logo color")
        # Requirement 4: Return original if bright enough
        return img

    def _smart_resize_logo(self, logo_image, max_w=1200, max_h=450):
        """
        Smart resizes the logo:
        1. Auto-crops transparent borders.
        2. Scales to fit within max_w x max_h while maintaining aspect ratio.
        3. Reduces max_h for vertical/square logos to prevent them from overpowering the layout.
        """
        if not logo_image: return None
        
        # Step A: Auto-Crop
        bbox = logo_image.getbbox()
        if bbox:
            logo_image = logo_image.crop(bbox)
        
        # Step B: Aspect Ratio Logic
        src_w, src_h = logo_image.size
        ratio = src_w / src_h
        
        effective_max_h = max_h
        if ratio < 0.8:      # Tall / Vertical
            effective_max_h = max_h * 0.6
        elif ratio < 1.2:    # Square / Compact
            effective_max_h = max_h * 0.75
        
        # Step C: Scaling
        scale = min(max_w / src_w, effective_max_h / src_h)
        
        new_w = int(src_w * scale)
        new_h = int(src_h * scale)
        
        return logo_image.resize((new_w, new_h), Image.LANCZOS)

    def draw_logo_or_title(self, logo_image=None, title_text=None):
        """Draws the logo if available, otherwise draws the title text."""
        if logo_image:
            logo_image = self.ensure_high_contrast(logo_image)
            
            # Use Smart Resize
            logo_resized = self._smart_resize_logo(logo_image, max_w=1200, max_h=450)
            
            self.canvas.paste(logo_resized, (self.current_x, self.current_y), logo_resized)
            self.current_y += logo_resized.height + self.padding
            self.last_element_width = logo_resized.width
        elif title_text:
            # Fallback to text title
            self._draw_text_with_shadow((self.current_x - 10, self.current_y), title_text, self.fonts['title'])
            bbox = self.draw.textbbox((0,0), title_text, font=self.fonts['title'])
            self.current_y += (bbox[3] - bbox[1]) + self.padding
            self.last_element_width = bbox[2] - bbox[0]

    def draw_info_text(self, text):
        """Draws the metadata info line (Year, Genre, Duration, etc.)."""
        self._draw_text_with_shadow((self.current_x, self.current_y), text, self.fonts['info'], fill="white", shadow="black")
        bbox = self.draw.textbbox((0,0), text, font=self.fonts['info'])
        self.current_y += (bbox[3] - bbox[1]) + self.padding

    def draw_horizontal_tags(self, tags, font_key='info', separator="  •  ", color="white"):
        """
        Draws a list of tags horizontally, moving the X-cursor to the right.
        This ensures correct spacing regardless of the text length of previous tags.
        """
        if not tags: return

        font = self.fonts.get(font_key, self.fonts['info'])
        
        valid_tags = [str(t) for t in tags if t]
        sep_width = self.draw.textlength(separator, font=font) if separator else 0
        
        # Calculate total width of all tags + separators
        total_width = 0
        for i, tag in enumerate(valid_tags):
            total_width += self.draw.textlength(tag, font=font)
            if i > 0:
                total_width += sep_width
        
        cursor_x = self.current_x
        
        # Center tags if they are shorter than the logo/title above them
        if self.last_element_width > 0 and total_width < self.last_element_width:
            cursor_x += (self.last_element_width - total_width) / 2
            
        max_height = 0
        
        for i, tag in enumerate(valid_tags):
            # Draw separator if not first item
            if i > 0 and separator:
                self._draw_text_with_shadow((cursor_x, self.current_y), separator, font, fill=color, shadow="black")
                cursor_x += sep_width
            
            # Draw tag
            self._draw_text_with_shadow((cursor_x, self.current_y), tag, font, fill=color, shadow="black")
            cursor_x += self.draw.textlength(tag, font=font)
            
            # Calculate max height for Y update
            bbox = self.draw.textbbox((0, 0), tag, font=font)
            height = bbox[3] - bbox[1]
            if height > max_height:
                max_height = height
                
        if max_height > 0:
            self.current_y += max_height + self.padding

    def measure_tags_width(self, tags, font_key='info', separator="  •  "):
        """Calculates the exact visual width of the tags line using a temporary canvas (Auto-Crop logic)."""
        if not tags: return 0
        valid_tags = [str(t) for t in tags if t]
        if not valid_tags: return 0

        font = self.fonts.get(font_key, self.fonts['info'])
        
        # 1. Estimate size for temp image (make it large enough)
        sep_width = self.draw.textlength(separator, font=font) if separator else 0
        est_width = 0
        for i, tag in enumerate(valid_tags):
            est_width += self.draw.textlength(tag, font=font)
            if i > 0: est_width += sep_width
            
        temp_w = int(est_width * 1.2) + 200
        temp_h = int(getattr(font, 'size', 50) * 3) + 100
        
        # 2. Create temp image
        temp_img = Image.new('RGBA', (temp_w, temp_h), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        
        # 3. Draw tags exactly as they would be drawn on canvas (including shadow)
        cursor_x = 100 # Start with padding to capture left bearing
        cursor_y = temp_h // 3
        
        for i, tag in enumerate(valid_tags):
            if i > 0 and separator:
                self._draw_text_with_shadow((cursor_x, cursor_y), separator, font, fill="white", shadow="black", draw_obj=temp_draw)
                cursor_x += temp_draw.textlength(separator, font=font)
            
            self._draw_text_with_shadow((cursor_x, cursor_y), tag, font, fill="white", shadow="black", draw_obj=temp_draw)
            cursor_x += temp_draw.textlength(tag, font=font)
            
        # 4. Get bounding box of visible pixels
        bbox = temp_img.getbbox()
        if bbox:
            return bbox[2] - bbox[0]
            
        return 0

    def _measure_visual_bbox(self, text, font):
        """Measures the exact visual bounding box of text using a temporary canvas."""
        if not text: return 0, 0
        
        # Estimate size (generous padding)
        dummy_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        est_bbox = dummy_draw.textbbox((0, 0), text, font=font)
        temp_w = (est_bbox[2] - est_bbox[0]) + 100
        temp_h = (est_bbox[3] - est_bbox[1]) + 100
        
        temp_img = Image.new('RGBA', (temp_w, temp_h), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_img)
        
        self._draw_text_with_shadow((50, 50), text, font, draw_obj=temp_draw)
        
        bbox = temp_img.getbbox()
        if bbox:
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        return 0, 0

    def draw_media_block(self, logo_image, title_text, tags, align='left', margin_x=50):
        """
        Draws Logo and Tags as a unified block to ensure consistent alignment.
        """
        # Step A: Measure
        w_logo = 0
        
        if logo_image:
            # Use Smart Resize logic for measurement
            logo_image = self.ensure_high_contrast(logo_image)
            logo_image = self._smart_resize_logo(logo_image, max_w=1200, max_h=450)
            w_logo = logo_image.width
        elif title_text:
            bbox = self.draw.textbbox((0,0), title_text, font=self.fonts['title'])
            w_logo = bbox[2] - bbox[0]

        w_tags = self.measure_tags_width(tags)

        # Step B: Container
        block_width = max(w_logo, w_tags)

        # Step C: Position Block
        canvas_width = self.canvas.width
        if align == 'center':
            start_x = (canvas_width - block_width) // 2
        elif align == 'right':
            start_x = canvas_width - margin_x - block_width
        else: # left
            start_x = margin_x

        # Step D: Draw
        # 1. Draw Logo/Title (Centered in Block)
        logo_x = start_x + (block_width - w_logo) // 2
        self.current_x = logo_x
        self.draw_logo_or_title(logo_image, title_text)
        
        # 2. Draw Tags (Centered in Block)
        tags_x = start_x + (block_width - w_tags) // 2
        self.current_x = tags_x
        
        # Disable internal centering logic of draw_horizontal_tags since we handled it explicitly
        self.last_element_width = 0 
        self.draw_horizontal_tags(tags)

    def draw_summary(self, text):
        """Draws the summary text, truncated and wrapped."""
        shortened = textwrap.shorten(text or "", width=175, placeholder="...")
        wrapped = "\n".join(textwrap.wrap(shortened, width=95))
        
        self._draw_text_with_shadow((self.current_x, self.current_y), wrapped, self.fonts['summary'])
        _, visual_height = self._measure_visual_bbox(wrapped, self.fonts['summary'])
        self.current_y += visual_height + self.padding * 2

    def draw_custom_text_and_provider_logo(self, text, provider_logo_path):
        """Draws the custom footer text and the provider logo (e.g. Jellyfin/Plex logo)."""
        self._draw_text_with_shadow((self.current_x, self.current_y), text, self.fonts['custom'])
        
        # Calculate logo position relative to text
        text_width, _ = self._measure_visual_bbox(text, self.fonts['custom'])
        
        full_logo_path = os.path.join(self.base_path, provider_logo_path)
        if os.path.exists(full_logo_path):
            p_logo = Image.open(full_logo_path).convert('RGBA')
            p_logo = self.ensure_high_contrast(p_logo)
            # Center vertically relative to text
            metrics = self.fonts['custom'].getmetrics()
            text_height = metrics[0] + metrics[1]
            logo_y = self.current_y + (text_height - p_logo.height) // 2
            logo_x = self.current_x + text_width + 15
            
            self.canvas.paste(p_logo, (logo_x, logo_y), p_logo)

    def _draw_text_with_shadow(self, pos, text, font, fill="white", shadow="black", draw_obj=None):
        d = draw_obj if draw_obj else self.draw
        x, y = pos
        d.text((x + self.shadow_offset, y + self.shadow_offset), text, font=font, fill=shadow)
        d.text((x, y), text, font=font, fill=fill)

    def save(self, path):
        """Saves the current canvas to a file."""
        self.canvas.convert('RGB').save(path)

    def get_bytes(self):
        """Returns the image as a BytesIO object (for web serving)."""
        img_io = BytesIO()
        self.canvas.convert('RGB').save(img_io, 'JPEG', quality=95)
        img_io.seek(0)
        return img_io

    def _vignette_side(self, h, w, fade_ratio=5, fade_power=5.0, position="bottom-left"):
        y, x = np.ogrid[0:h, 0:w]
        rx, ry = w * fade_ratio, h * fade_ratio

        dist_x, dist_y = np.ones_like(x, dtype=np.float32), np.ones_like(y, dtype=np.float32)

        if "left" in position: dist_x = np.clip(x / rx, 0, 1)
        elif "right" in position: dist_x = np.clip((w - x) / rx, 0, 1)
        if "top" in position: dist_y = np.clip(y / ry, 0, 1)
        elif "bottom" in position: dist_y = np.clip((h - y) / ry, 0, 1)

        alpha = np.minimum(dist_x, dist_y) if ("left" in position or "right" in position) and ("top" in position or "bottom" in position) else dist_x * dist_y
        alpha = (alpha ** fade_power * 255).astype(np.uint8)
        mask = Image.fromarray(alpha)
        return mask.filter(ImageFilter.GaussianBlur(radius=50))

    def _create_blurry_background(self, image, size=(3840, 2160), blur_radius=800, dither_strength=16):
        bg = image.resize(size, Image.LANCZOS).filter(ImageFilter.GaussianBlur(radius=blur_radius))
        bg_array = np.array(bg).astype(np.float32)
        noise = np.random.uniform(-dither_strength, dither_strength, bg_array.shape)
        bg_array = np.clip(bg_array + noise, 0, 255).astype(np.uint8)
        bg_img = Image.fromarray(bg_array)
        
        # Detect uniformity
        gray = np.array(bg_img.convert("L"))
        is_uniform = gray.std() < 15
        
        return bg_img, is_uniform

    @staticmethod
    def clean_filename(filename):
        return "".join(c if c.isalnum() or c in "._-" else "_" for c in filename)
