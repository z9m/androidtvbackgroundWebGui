console.log("DEBUG: Script starts...");

try {
    const fs = require('fs');
    const path = require('path');
    console.log("DEBUG: Modules loaded (fs, path)");

    // Try to load 'canvas' to register fonts (Fabric uses node-canvas under the hood)
    let registerFont = null;
    try {
        const canvasModule = require('canvas');
        registerFont = canvasModule.registerFont;
        console.log("DEBUG: 'canvas' module found for font registration.");
    } catch (e) {
        console.warn("WARNING: 'canvas' module not found directly. Custom fonts might not load correctly.", e);
    }

    const { fabric } = require('fabric');
    console.log("DEBUG: Fabric loaded");

    // --- NEW: FUNCTION TO REGISTER LOCAL FONTS ---
    function registerLocalFonts() {
        if (!registerFont) return;

        const fontsDir = path.join(__dirname, 'fonts');
        if (!fs.existsSync(fontsDir)) {
            console.log("DEBUG: No 'fonts' directory found. Skipping font registration.");
            return;
        }

        const files = fs.readdirSync(fontsDir);
        let count = 0;

        files.forEach(file => {
            const ext = path.extname(file).toLowerCase();
            if (['.ttf', '.otf', '.woff', '.woff2'].includes(ext)) {
                try {
                    const filePath = path.join(fontsDir, file);
                    const nameWithoutExt = path.basename(file, ext);
                    
                    // 1. Detect Style/Weight from filename (Simple logic to match Python backend)
                    let weight = 'normal';
                    let style = 'normal';
                    
                    if (nameWithoutExt.match(/bold/i)) weight = 'bold';
                    if (nameWithoutExt.match(/italic|oblique/i)) style = 'italic';
                    
                    // 2. Clean up Family Name (remove 'Regular', 'Bold', etc.)
                    // This logic ensures "BungeeSpice-Regular" becomes Family "BungeeSpice"
                    let family = nameWithoutExt;
                    const keywords = ['Regular', 'Bold', 'Italic', 'Light', 'Medium', 'Black', 'Thin', 'ExtraBold', 'SemiBold', 'Heavy'];
                    keywords.forEach(kw => {
                        const reg = new RegExp(`[-_]?${kw}`, 'gi');
                        family = family.replace(reg, '');
                    });
                    
                    // Clean up separators
                    family = family.replace(/[-_]/g, ' ').trim();
                    
                    // If everything was stripped (e.g. filename was just "Bold.ttf"), fallback to original
                    if (!family) family = nameWithoutExt;

                    // 3. Register the font with node-canvas
                    registerFont(filePath, { family: family, weight: weight, style: style });
                    count++;
                } catch (err) {
                    console.warn(`WARNING: Failed to register font ${file}:`, err.message);
                }
            }
        });
        console.log(`DEBUG: Registered ${count} custom fonts from /fonts directory.`);
    }

    // --- MAIN EXECUTION ---
    
    // 1. Register Fonts immediately
    registerLocalFonts();

    // 2. Parse Arguments
    console.log("DEBUG: Arguments:", process.argv);
    const layoutPath = process.argv[2];
    const metadataPath = process.argv[3];
    const outputPath = process.argv[4];

    if (!layoutPath || !metadataPath || !outputPath) {
        console.error("ERROR: Missing arguments! Usage: node render_task.js <layout> <metadata> <output>");
        process.exit(1);
    }

    // 3. Check Files
    if (!fs.existsSync(layoutPath)) {
        console.error(`ERROR: Layout file not found: ${layoutPath}`);
        process.exit(1);
    }
    if (!fs.existsSync(metadataPath)) {
        console.error(`ERROR: Meta file not found: ${metadataPath}`);
        process.exit(1);
    }

    console.log("DEBUG: Files exist. Loading JSON...");
    
    // 4. Load Layout JSON
    const rawLayout = fs.readFileSync(layoutPath, 'utf8');
    // Sanity check for empty file
    if (rawLayout.trim().length === 0) {
        throw new Error("Layout file is empty (0 bytes)!");
    }
    const layoutJson = JSON.parse(rawLayout);

    // 5. Load Metadata JSON
    const rawMeta = fs.readFileSync(metadataPath, 'utf8');
    if (rawMeta.trim().length === 0) {
        throw new Error("Meta file is empty (0 bytes)!");
    }
    const metadata = JSON.parse(rawMeta);

    console.log("DEBUG: JSON parsed successfully.");

    // 6. Setup Canvas (HD or 4K based on layout width)
    // We assume 1920x1080 as base if not specified
    const width = 1920; 
    const height = 1080; 
    
    const canvas = new fabric.StaticCanvas(null, { width: width, height: height });
    console.log("DEBUG: Canvas created.");

    // 7. Load Data into Canvas
    console.log("DEBUG: Loading Layout into Canvas...");
    
    // Helper to apply metadata to objects
    function applyMetadata() {
        const objects = canvas.getObjects();
        
        // A. Handle Background (Backdrop URL)
        const bgObj = objects.find(o => o.dataTag === 'background');
        if (bgObj && metadata.backdrop_url) {
            // NOTE: In a real batch scenario, 'backdrop_url' might be a remote URL.
            // Fabric (Node) can load URLs, but it might be faster if Python downloaded it locally first.
            // For now, we assume metadata.backdrop_url is accessible.
            // However, loading remote images in Node-Fabric is async.
            // The JSON loading above handles the structure, but we might need to swap the src.
            
            // Note: Since 'loadFromJSON' is async for images, we handle logic inside the callback below.
        }

        // B. Handle Texts
        objects.forEach(obj => {
            if (!obj.dataTag) return;
            
            // Map metadata to tags
            if (obj.dataTag === 'title' && (obj.type === 'i-text' || obj.type === 'text' || obj.type === 'textbox')) {
                obj.set('text', metadata.title || "Unknown Title");
            }
            if (obj.dataTag === 'year') {
                obj.set('text', String(metadata.year || ""));
            }
            if (obj.dataTag === 'rating' || obj.dataTag === 'rating_val') {
                obj.set('text', String(metadata.rating || ""));
            }
            if (obj.dataTag === 'genres') {
                obj.set('text', String(metadata.genres || ""));
            }
            if (obj.dataTag === 'runtime') {
                obj.set('text', String(metadata.runtime || ""));
            }
            if (obj.dataTag === 'overview' && (obj.type === 'textbox' || obj.type === 'i-text')) {
                obj.set('text', metadata.overview || "");
            }
            if (obj.dataTag === 'certification') {
                // Image handling would be complex here without local files, 
                // assuming Python pre-processed the paths or we skip dynamic image swapping for simplicity in this step.
            }
        });
    }

    // 8. Execute Loading
    (async () => {
        try {
            // Wrap loadFromJSON in a promise
            await new Promise((resolve, reject) => {
                canvas.loadFromJSON(layoutJson, () => {
                    resolve();
                }, (o, object) => {
                    // Reviver: Restore gradients if needed (simplified from Frontend logic)
                    if (object.fill && object.fill.type === 'linear' && object.fill.colorStops) {
                        object.fill.colorStops = object.fill.colorStops.map(stop => ({
                            offset: stop.offset, color: stop.color
                        }));
                    }
                });
            });

            console.log("DEBUG: Layout loaded. Applying metadata...");
            applyMetadata();

            // Handle Background Image Logic (if provided in metadata)
            if (metadata.backdrop_url) {
                // Check if background object exists
                let bgObj = canvas.getObjects().find(o => o.dataTag === 'background');
                
                if (bgObj && bgObj.type === 'image') {
                    // Load the new image
                    try {
                        // Fabric node requires 'canvas' to load images usually.
                        // We use fabric.Image.fromURL logic adapted for node.
                        await new Promise((resolveImg) => {
                            fabric.Image.fromURL(metadata.backdrop_url, (img) => {
                                if (!img) {
                                    console.warn("DEBUG: Failed to load backdrop URL");
                                    resolveImg();
                                    return;
                                }
                                // Retain properties
                                img.set({
                                    left: bgObj.left,
                                    top: bgObj.top,
                                    scaleX: bgObj.scaleX, // You might need 'cover' logic here roughly
                                    scaleY: bgObj.scaleY,
                                    width: bgObj.width,
                                    height: bgObj.height,
                                    opacity: bgObj.opacity,
                                    dataTag: 'background'
                                });
                                // Replace in canvas
                                canvas.remove(bgObj);
                                canvas.add(img);
                                canvas.sendToBack(img);
                                resolveImg();
                            });
                        });
                    } catch (e) {
                        console.error("DEBUG: Error loading backdrop:", e);
                    }
                }
            }
            
            // Adjust Textbox Layouts (Simple auto-fit logic)
            canvas.getObjects().forEach(obj => {
                if (obj.type === 'textbox' && obj.dataTag === 'overview') {
                    // Simple logic: if text is too long, shrink font size slightly?
                    // For now, we just rely on the layout settings.
                }
            });

            console.log("DEBUG: Rendering...");
            canvas.renderAll();

            console.log(`DEBUG: Saving to ${outputPath}...`);
            const out = fs.createWriteStream(outputPath);
            const stream = canvas.createJPEGStream({ quality: 0.9 });
            
            stream.on('error', (err) => console.error("DEBUG: Stream Error:", err));
            out.on('error', (err) => console.error("DEBUG: File Write Error:", err));
            
            stream.pipe(out);
            
            out.on('finish', () => {
                console.log("SUCCESS");
            });

        } catch (innerErr) {
            console.error("DEBUG: Inner Error:", innerErr);
        }
    })();

} catch (e) {
    console.error("DEBUG: Critical Top-Level Error:", e);
    process.exit(1);
}