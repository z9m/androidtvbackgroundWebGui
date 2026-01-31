// --- GLOBAL FIXES ---
(function() {
    const originalSetter = Object.getOwnPropertyDescriptor(CanvasRenderingContext2D.prototype, 'textBaseline').set;
    Object.defineProperty(CanvasRenderingContext2D.prototype, 'textBaseline', {
        set: function(value) {
            if (value === 'alphabetical') value = 'alphabetic';
            return originalSetter.call(this, value);
        },
        configurable: true
    });

    // Patch Textbox to render background covering padding
    fabric.Textbox.prototype._renderBackground = function(ctx) {
        if (!this.backgroundColor) return;
        var dim = this._getNonTransformedDimensions();
        ctx.fillStyle = this.backgroundColor;
        const pad = this.padding || 0;
        ctx.fillRect(
            -dim.x / 2 - pad - 10,
            -dim.y / 2 - pad,
            dim.x + pad * 2 + 20,
            dim.y + pad * 2
        );
        this._removeShadow(ctx);
    };

    // Patch IText to render background with same buffer
    fabric.IText.prototype._renderBackground = function(ctx) {
        if (!this.backgroundColor) return;
        var dim = this._getNonTransformedDimensions();
        ctx.fillStyle = this.backgroundColor;
        const pad = this.padding || 0;
        ctx.fillRect(
            -dim.x / 2 - pad - 10,
            -dim.y / 2 - pad,
            dim.x + pad * 2 + 20,
            dim.y + pad * 2
        );
        this._removeShadow(ctx);
    };
})();

let canvas, mainBg = null;
let fades = { left: null, right: null, top: null, bottom: null, corner: null };
let scalingTimeout = null, lastFetchedData = null;
let gridEnabled = false, movingObjects = [], snapLines = { v: [], h: [] }, guideLines = [], isBatchRunning = false;
const gridSize = 50;
const screenMargin = 50;

function updateSelectionUI(e) {
    const activeObj = canvas.getActiveObject();
    const textPanel = document.getElementById('text-properties');
    const iconPanel = document.getElementById('icon-properties');
    const alignControl = document.getElementById('textAlignControl');
    const bgControl = document.getElementById('textBackgroundControl');
    
    // Hide all initially
    textPanel.style.display = 'none';
    if (iconPanel) iconPanel.style.display = 'none';

    if (!activeObj) return;

    if (activeObj.type === 'image' && (activeObj.dataTag === 'icon' || activeObj.dataTag === 'certification')) {
        if (iconPanel) {
            iconPanel.style.display = 'block';
            document.getElementById('iconSizeInput').value = Math.round(activeObj.getScaledHeight());
            const isMatchHeight = activeObj.matchHeight || false;
            document.getElementById('matchHeightToggle').checked = isMatchHeight;
            document.getElementById('iconSizeInput').disabled = isMatchHeight;
        }
    } else if (activeObj.type === 'i-text' || activeObj.type === 'textbox' || (activeObj.type === 'group' && (activeObj.dataTag === 'rating_star' || activeObj.dataTag === 'rating'))) {
        textPanel.style.display = 'block';
        
        let textObj = activeObj;
        if (activeObj.type === 'group') textObj = activeObj.getObjects().find(o => o.type === 'i-text');
        
        if (textObj) {
            document.getElementById('fontSizeInput').value = textObj.fontSize;
            document.getElementById('fontFamilySelect').value = textObj.fontFamily;
            const color = new fabric.Color(textObj.fill);
            document.getElementById('fontColorInput').value = "#" + color.toHex();
        }
        
        if (activeObj.type === 'textbox') {
            alignControl.style.display = 'block';
            if (bgControl) {
                bgControl.style.display = 'block';
                const hasBg = !!activeObj.backgroundColor;
                document.getElementById('textBgEnable').checked = hasBg;
                document.getElementById('textBgSettings').style.display = hasBg ? 'block' : 'none';
                
                if (hasBg) {
                    const c = new fabric.Color(activeObj.backgroundColor);
                    const source = c.getSource();
                    const isAuto = activeObj.autoBackgroundColor || false;
                    document.getElementById('textBgAuto').checked = isAuto;
                    document.getElementById('textBgColor').disabled = isAuto;
                    
                    if (source) {
                        const hex = "#" + ((1 << 24) + (source[0] << 16) + (source[1] << 8) + source[2]).toString(16).slice(1);
                        document.getElementById('textBgColor').value = hex;
                        const opacity = Math.round(source[3] * 100);
                        document.getElementById('textBgOpacity').value = opacity;
                        document.getElementById('textBgOpacityVal').innerText = opacity + "%";
                    }
                }
            }
        } else {
            alignControl.style.display = 'none';
            if (bgControl) bgControl.style.display = 'none';
        }
    }
}

function updateSelectedFontSize() {
    const activeObj = canvas.getActiveObject();
    if (activeObj) { 
        const newSize = parseInt(document.getElementById('fontSizeInput').value);
        let textObj = (activeObj.type === 'group') ? activeObj.getObjects().find(o => o.type === 'i-text') : activeObj;
        if (textObj) { 
            textObj.set("fontSize", newSize); 
            if(activeObj.type==='group') {
                if (activeObj.dataTag === 'rating_star' || activeObj.dataTag === 'rating') {
                    const imgObj = activeObj.getObjects().find(o => o.type === 'image');
                    if (imgObj) {
                        imgObj.scaleToHeight(newSize);
                        textObj.set('left', imgObj.left + imgObj.getScaledWidth() + 10);
                        textObj.set('top', imgObj.top + (imgObj.getScaledHeight() - textObj.getScaledHeight()) / 2);
                    }
                }
                activeObj.addWithUpdate(); 
            }
            else activeObj.setCoords();
            updateVerticalLayout();
            canvas.requestRenderAll();
            saveToLocalStorage();
        }
    }
}

function updateIconSize() {
    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.type === 'image') {
        const newSize = parseInt(document.getElementById('iconSizeInput').value);
        activeObj.scaleToHeight(newSize);
        activeObj.setCoords();
        updateVerticalLayout();
        canvas.requestRenderAll();
        saveToLocalStorage();
    }
}

function updateSelectedFontFamily() {
    const activeObj = canvas.getActiveObject();
    if (activeObj) { 
        let textObj = (activeObj.type === 'group') ? activeObj.getObjects().find(o => o.type === 'i-text') : activeObj; 
        if(textObj) { 
            const fontName = document.getElementById('fontFamilySelect').value;
            document.fonts.load(`10px "${fontName}"`).then(() => {
                textObj.set("fontFamily", fontName); 
                if (textObj.type === 'i-text') textObj.set("text", textObj.text);
                if(activeObj.type==='group') {
                    if (activeObj.dataTag === 'rating_star' || activeObj.dataTag === 'rating') {
                        canvas.renderAll(); // Force dimension update for text
                        const imgObj = activeObj.getObjects().find(o => o.type === 'image');
                        if (imgObj && textObj) {
                            textObj.set('top', imgObj.top + (imgObj.getScaledHeight() - textObj.getScaledHeight()) / 2);
                        }
                    }
                    activeObj.addWithUpdate(); 
                }
                else activeObj.setCoords();
                canvas.renderAll(); // Force dimension update before layout
                updateVerticalLayout();
                canvas.requestRenderAll();
                saveToLocalStorage();
            });
        } 
    }
}

function applyFontToAll() {
    const fontName = document.getElementById('fontFamilySelect').value;
    const fontColor = document.getElementById('fontColorInput').value;
    if (!canvas) return;
    document.fonts.load(`10px "${fontName}"`).then(() => {
        canvas.getObjects().forEach(obj => {
            if (obj.dataTag === 'overview') return;
            if (obj.type === 'i-text' || obj.type === 'textbox') {
                obj.set("fontFamily", fontName);
                obj.set("fill", fontColor);
                if (obj.type === 'i-text') obj.set("text", obj.text);
                obj.setCoords();
            } else if (obj.type === 'group') {
                const textObj = obj.getObjects().find(o => o.type === 'i-text');
                if (textObj) {
                    textObj.set("fontFamily", fontName);
                    textObj.set("fill", fontColor);
                    obj.addWithUpdate();
                }
            }
        });
        canvas.renderAll(); // Force dimension update before layout
        updateVerticalLayout();
        canvas.requestRenderAll();
        saveToLocalStorage();
    });
}

function setTextAlignment(align) {
    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.type === 'textbox') {
        activeObj.set('textAlign', align);
        canvas.requestRenderAll();
        saveToLocalStorage();
    }
}

function toggleMatchHeight() {
    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.type === 'image') {
        activeObj.matchHeight = document.getElementById('matchHeightToggle').checked;
        document.getElementById('iconSizeInput').disabled = activeObj.matchHeight;
        updateVerticalLayout();
        canvas.requestRenderAll();
        saveToLocalStorage();
    }
}

function toggleTextBackground() {
    const activeObj = canvas.getActiveObject();
    if (activeObj && activeObj.type === 'textbox') {
        const enabled = document.getElementById('textBgEnable').checked;
        document.getElementById('textBgSettings').style.display = enabled ? 'block' : 'none';
        if (enabled) {
            activeObj.set('padding', 20);
            activeObj.setCoords();
            if (!activeObj.backgroundColor) {
                document.getElementById('textBgAuto').checked = true;
                document.getElementById('textBgOpacity').value = 50;
            }
            updateTextBackgroundSettings();
        } else {
            activeObj.set('backgroundColor', '');
            activeObj.set('padding', 0);
            activeObj.setCoords();
            activeObj.autoBackgroundColor = false;
            canvas.requestRenderAll();
            saveToLocalStorage();
        }
    }
}

function updateTextBackgroundSettings() {
    const activeObj = canvas.getActiveObject();
    if (!activeObj || activeObj.type !== 'textbox') return;
    
    const isAuto = document.getElementById('textBgAuto').checked;
    const opacity = parseInt(document.getElementById('textBgOpacity').value) / 100;
    document.getElementById('textBgOpacityVal').innerText = Math.round(opacity * 100) + "%";
    document.getElementById('textBgColor').disabled = isAuto;
    activeObj.autoBackgroundColor = isAuto;
    
    let r, g, b;
    if (isAuto) {
        const rgb = new fabric.Color(document.getElementById('bgColor').value).getSource();
        r = rgb[0]; g = rgb[1]; b = rgb[2];
        document.getElementById('textBgColor').value = "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    } else {
        const hex = document.getElementById('textBgColor').value;
        r = parseInt(hex.slice(1, 3), 16); g = parseInt(hex.slice(3, 5), 16); b = parseInt(hex.slice(5, 7), 16);
    }
    activeObj.set('backgroundColor', `rgba(${r}, ${g}, ${b}, ${opacity})`);
    canvas.requestRenderAll();
    saveToLocalStorage();
}

function updateSelectedColor() {
    const activeObj = canvas.getActiveObject();
    if (activeObj) { 
        let textObj = (activeObj.type === 'group') ? activeObj.getObjects().find(o => o.type === 'i-text') : activeObj; 
        if(textObj) { 
            textObj.set("fill", document.getElementById('fontColorInput').value); 
            if(activeObj.type==='group') activeObj.addWithUpdate(); 
            canvas.renderAll(); 
        } 
    }
}

function applyTruncation(textbox, textToDisplay) {
    if (!canvas) return;
    const textSource = textToDisplay || textbox.fullMediaText || "";
    const oldState = canvas.renderOnAddRemove;
    canvas.renderOnAddRemove = false;
    textbox.set('text', textSource);
    textbox.initDimensions();
    const limit = textbox.fixedHeight || textbox.height;
    if (textbox.height > limit) {
        let words = textSource.split(' ');
        while (textbox.height > limit && words.length > 10) { words.splice(-10); textbox.set('text', words.join(' ') + '...'); textbox.initDimensions(); }
        while (textbox.height > limit && words.length > 0) { words.pop(); textbox.set('text', words.join(' ') + '...'); textbox.initDimensions(); }
    }
    canvas.renderOnAddRemove = oldState;
    canvas.requestRenderAll();
}

async function searchMedia() {
    const query = document.getElementById('mediaSearchInput').value;
    if (!query) return;
    
    const btn = document.querySelector('button[onclick="searchMedia()"]');
    const originalText = btn.innerText;
    btn.innerText = "⏳";
    btn.disabled = true;
    
    try {
        const resp = await fetch(`/api/media/search?q=${encodeURIComponent(query)}`);
        const items = await resp.json();
        
        if (items.length === 0) {
            alert("No results found.");
        } else if (items.length === 1) {
            fetchMediaData(items[0].Id);
        } else {
            let msg = "Found multiple items:\n";
            items.forEach((item, index) => {
                msg += `${index + 1}. ${item.Name} (${item.ProductionYear || '?'})\n`;
            });
            msg += "\nEnter number to select:";
            const choice = prompt(msg, "1");
            if (choice) {
                const idx = parseInt(choice) - 1;
                if (items[idx]) fetchMediaData(items[idx].Id);
            }
        }
    } catch (e) {
        console.error(e);
        alert("Search failed");
    } finally {
        btn.innerText = originalText;
        btn.disabled = false;
    }
}

async function fetchRandomPreview() {
    await fetchMediaData(null);
}

async function fetchMediaData(itemId = null) {
    const btn = document.getElementById('btn-shuffle');
    const indicator = document.getElementById('source-indicator');
    
    btn.disabled = true;
    const originalText = btn.innerText;
    if (!isBatchRunning) btn.innerText = "⏳ Loading...";
    if (!isBatchRunning) indicator.innerText = "Fetching...";
    
    try {
        const url = itemId ? `/api/media/item/${itemId}` : '/api/media/random';
        const response = await fetch(url);
        const data = await response.json();
        lastFetchedData = data;
        
        // 1. Assets vorladen (Preload) - noch nichts am Canvas ändern!
        const assetPromises = [];
        let newBgImg = null;
        let newLogoImg = null;

        if (data.backdrop_url) {
            assetPromises.push(new Promise(resolve => {
                const proxiedUrl = `/api/proxy/image?url=${encodeURIComponent(data.backdrop_url)}`;
                fabric.Image.fromURL(proxiedUrl, (img) => { newBgImg = img; resolve(); }, { crossOrigin: 'anonymous' });
            }));
        }
        if (data.logo_url) {
            assetPromises.push(new Promise(resolve => {
                const proxiedLogo = `/api/proxy/image?url=${encodeURIComponent(data.logo_url)}`;
                fabric.Image.fromURL(proxiedLogo, (img) => { newLogoImg = img; resolve(); }, { crossOrigin: 'anonymous' });
            }));
        }
        await Promise.all(assetPromises);

        // 2. Jetzt alles auf einmal anwenden (synchron)
        if (mainBg) canvas.remove(mainBg);
        mainBg = newBgImg;
        
        if (mainBg) {
            mainBg.set({ left: 0, top: 0, selectable: true, dataTag: 'background' });
            const targetWidth = canvas.width * 0.70;
            mainBg.scaleToWidth(targetWidth);
            mainBg.set({ left: canvas.width - targetWidth, top: 0 });
            canvas.add(mainBg); canvas.sendToBack(mainBg); 
            updateFades(true);
        } else {
            // Ensure fades are updated (removed) if no background
            updateFades(true);
        }

        await autoDetectBgColor(true, true);
        await previewTemplate(data, true, newLogoImg);
        saveToLocalStorage();
        canvas.renderAll(); // Force synchronous render to ensure image is ready
        
        const btnSaveGallery = document.getElementById('btn-save-gallery');
        if(btnSaveGallery) btnSaveGallery.disabled = false;

        if (!isBatchRunning) indicator.innerText = "Source: " + data.source;
    } catch (err) { console.error(err); indicator.innerText = "Error loading preview"; }
    finally {
        btn.disabled = false;
        btn.innerText = originalText;
    }
}

function previewTemplate(mediaData, skipRender = false, preloadedLogo = null) {
    return new Promise((resolve) => {
        if (!canvas || !mediaData) { resolve(); return; }
        
        // Helper to calculate smart positioning for the new logo
        const getNewLogoLeft = (oldObj, newWidth, newScale) => {
            const align = document.getElementById('tagAlignSelect').value;
            const cW = canvas.width;
            const oldW = oldObj.getScaledWidth();
            
            let boundsL = oldObj.left;
            let boundsR = oldObj.left + oldW;

            // If centered, the "visual block" includes the tags
            if (align === 'center') {
                const tags = canvas.getObjects().filter(o => ['year', 'genres', 'runtime', 'rating_val', 'rating_star', 'certification'].includes(o.dataTag) && o.visible);
                tags.forEach(t => {
                    if (t.left < boundsL) boundsL = t.left;
                    const r = t.left + t.getScaledWidth();
                    if (r > boundsR) boundsR = r;
                });
            }

            const isStickyLeft = Math.abs(boundsL - screenMargin) < 20;
            const isStickyRight = Math.abs(boundsR - (cW - screenMargin)) < 20;

            if (isStickyLeft) return screenMargin;
            if (isStickyRight) return (cW - screenMargin) - (newWidth * newScale);

            // Not sticky: preserve alignment anchor based on mode
            if (align === 'center') {
                const center = (boundsL + boundsR) / 2;
                return center - (newWidth * newScale) / 2;
            } else if (align === 'right') {
                return (oldObj.left + oldW) - (newWidth * newScale);
            } else {
                return oldObj.left;
            }
        };

        let promises = [];
        
        [...canvas.getObjects()].forEach(obj => {
            if (obj.dataTag) {
                let val = "";
                switch(obj.dataTag) {
                    case 'title':
                        if (mediaData.logo_url && preloadedLogo) {
                            // Benutze das vorgeladene Logo sofort (synchron)
                            const maxW = canvas.width * 0.55; 
                            const maxH = canvas.height * 0.35; 
                            const scale = Math.min(maxW / preloadedLogo.width, maxH / preloadedLogo.height) * 0.8;
                            
                            const newLeft = getNewLogoLeft(obj, preloadedLogo.width, scale);

                            preloadedLogo.set({ left: newLeft, top: obj.top, dataTag: 'title' });
                            preloadedLogo.scale(scale);
                            canvas.remove(obj); canvas.add(preloadedLogo);
                        } else if (mediaData.logo_url) {
                            const p = new Promise(r => {
                                const proxiedLogo = `/api/proxy/image?url=${encodeURIComponent(mediaData.logo_url)}`;
                                fabric.Image.fromURL(proxiedLogo, function(img, isError) {
                                    if (isError || !img) { canvas.remove(obj); r(); return; }
                                    const maxW = canvas.width * 0.55; 
                                    const maxH = canvas.height * 0.35; 
                                    const scale = Math.min(maxW / img.width, maxH / img.height) * 0.8;
                                    
                                    const newLeft = getNewLogoLeft(obj, img.width, scale);

                                    img.set({ left: newLeft, top: obj.top, dataTag: 'title' });
                                    img.scale(scale);
                                    canvas.remove(obj); canvas.add(img); 
                                    r();
                                }, { crossOrigin: 'anonymous' });
                            });
                            promises.push(p);
                            return; 
                        } else { 
                            val = mediaData.title || mediaData.Name;
                            // Fix: If switching from Logo (Image) to Text, replace the object
                            if (obj.type === 'image') {
                                const is4K = document.getElementById('resSelect').value === '2160';
                                const titleSize = is4K ? 120 : 80;
                                const newText = new fabric.IText(val, { 
                                    left: obj.left, top: obj.top, 
                                    fontFamily: 'Oswald', fontSize: titleSize, 
                                    fill: 'white', shadow: '2px 2px 10px rgba(0,0,0,0.8)', 
                                    dataTag: 'title', editable: false 
                                });
                                canvas.remove(obj); canvas.add(newText);
                            }
                        }
                        break;
                    case 'year': val = mediaData.year || mediaData.ProductionYear; break;
                    case 'rating': 
                        let r = mediaData.rating || mediaData.CommunityRating; 
                        if (r && r !== 'N/A' && !isNaN(parseFloat(r))) r = parseFloat(r).toFixed(1);
                        if (obj.type === 'group') {
                            const t = obj.getObjects().find(o => o.type === 'i-text');
                            if(t) { t.set({ text: (r && r !== 'N/A') ? `${r}` : '' }); obj.addWithUpdate(); }
                            val = undefined;
                        } else {
                            val = (r && r !== 'N/A') ? `IMDb: ${r}` : ''; 
                        }
                        break;
                    case 'rating_val': 
                        let rv = mediaData.rating || mediaData.CommunityRating; 
                        if (rv && rv !== 'N/A' && !isNaN(parseFloat(rv))) rv = parseFloat(rv).toFixed(1);
                        val = (rv && rv !== 'N/A') ? `${rv}` : ''; 
                        break;
                    case 'rating_star': 
                        let rs = mediaData.rating || mediaData.CommunityRating; 
                        if (rs && rs !== 'N/A' && !isNaN(parseFloat(rs))) rs = parseFloat(rs).toFixed(1);
                        val = (rs && rs !== 'N/A') ? `${rs}` : '';
                        if (obj.type === 'group') {
                            const t = obj.getObjects().find(o => o.type === 'i-text');
                            if(t) { t.set({ text: val }); obj.addWithUpdate(); }
                            val = undefined; 
                        }
                        break;
                    case 'overview': 
                        let ov = mediaData.overview || mediaData.Overview || "";
                        if (obj.type === 'textbox') { obj.fullMediaText = ov; applyTruncation(obj, ov); } else { val = ov; }
                        break;
                    case 'genres': 
                        val = mediaData.genres || ""; 
                        const gLimit = parseInt(document.getElementById('genreLimitSlider').value);
                        if (gLimit < 6) {
                            val = val.split(',').slice(0, gLimit).join(',');
                        }
                        break;
                    case 'runtime': 
                        val = mediaData.runtime || ""; 
                        const rtCheck = String(val).toLowerCase().replace(/\s/g, '');
                        if (rtCheck === '0min' || rtCheck === '0') {
                            obj.set('visible', false);
                        } else {
                            obj.set('visible', true);
                        }
                        break;
                    case 'provider_source':
                        const src = (mediaData.source || "").toLowerCase();
                        if (src === 'radarr' || src === 'sonarr') {
                            val = "Available soon...";
                        } else if (src) {
                            const pName = src === 'tmdb' ? 'TMDB' : src.charAt(0).toUpperCase() + src.slice(1);
                            val = `Now available on ${pName}`;
                        }
                        break;
                    case 'certification':
                        let cert = mediaData.officialRating || mediaData.certification || mediaData.OfficialRating;
                        let certUrl = null;
                        
                        // 1. Try Official Rating string
                        if (cert) {
                            certUrl = getCertificationImageUrl(cert);
                        }
                        
                        // 2. Fallback: If no URL found (or no official rating), try Inherited Value (Numeric)
                        if (!certUrl && mediaData.inheritedParentalRatingValue !== undefined) {
                            certUrl = getCertificationImageUrl(String(mediaData.inheritedParentalRatingValue));
                        }
                        
                        if (certUrl) {
                            const p = new Promise(r => {
                                const urlToLoad = certUrl.startsWith('http') ? `/api/proxy/image?url=${encodeURIComponent(certUrl)}` : certUrl;
                                fabric.Image.fromURL(urlToLoad, function(img, isError) {
                                    if (isError || !img) { obj.set('visible', false); r(); return; }
                                    const targetHeight = obj.getScaledHeight(); 
                                    img.scaleToHeight(targetHeight);
                                    img.set({ left: obj.left, top: obj.top, dataTag: 'certification' });
                                    if (obj.matchHeight) img.matchHeight = true;
                                    canvas.remove(obj);
                                    canvas.add(img);
                                    r();
                                }, { crossOrigin: 'anonymous', dataTag: 'certification' });
                            });
                            promises.push(p);
                            return;
                        } else {
                            obj.set('visible', false);
                        }
                        break;
                }
                if (val !== undefined && obj.dataTag !== 'overview') obj.set({ text: String(val) });
            }
        });
        
        Promise.all(promises).then(() => {
            canvas.renderAll(); // Force dimension update before layout
            updateVerticalLayout(skipRender);
            resolve();
        });
    });
}

let detectedBaseColor = null;

function autoDetectBgColor(forceRecalc, skipRender = false) {
    if (!mainBg) return Promise.resolve();
    
    if (forceRecalc || !detectedBaseColor) {
        const img = mainBg.getElement();
        const cvs = document.createElement('canvas');
        cvs.width = img.naturalWidth || img.width;
        cvs.height = img.naturalHeight || img.height;
        const ctx = cvs.getContext('2d');
        ctx.drawImage(img, 0, 0);
        
        const frame = 50; 
        const w = cvs.width, h = cvs.height;
        let r=0, g=0, b=0, count=0;
        
        try {
            const data = ctx.getImageData(0, 0, w, h).data;
            const step = 20; 
            for (let y=0; y<h; y+=step) {
                for (let x=0; x<w; x+=step) {
                    if (x < frame || x > w-frame || y < frame || y > h-frame) {
                        const i = (y*w + x)*4;
                        r += data[i]; g += data[i+1]; b += data[i+2];
                        count++;
                    }
                }
            }
        } catch(e) { console.error("Pixel access error", e); return; }
        
        if (count > 0) {
            detectedBaseColor = { r: Math.floor(r/count), g: Math.floor(g/count), b: Math.floor(b/count) };
        }
    }
    return applyBrightness(skipRender);
}

function adjustAutoBrightness() {
    document.getElementById('brightVal').innerText = document.getElementById('bgBrightness').value + '%';
    if (detectedBaseColor) {
        applyBrightness();
    } else if (mainBg) {
        autoDetectBgColor(true);
    }
}

function applyBrightness(skipRender = false) {
    if (!detectedBaseColor) return Promise.resolve();
    const factor = parseInt(document.getElementById('bgBrightness').value) / 100;
    let r = Math.floor(detectedBaseColor.r * factor);
    let g = Math.floor(detectedBaseColor.g * factor);
    let b = Math.floor(detectedBaseColor.b * factor);
    const hex = "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
    document.getElementById('bgColor').value = hex;
    return updateBgColor(skipRender);
}

function addMetadataTag(type, placeholder) {
    let textObj;
    const count = canvas.getObjects().filter(o => o.dataTag).length;
    
    const is4K = document.getElementById('resSelect').value === '2160';
    const baseSize = is4K ? 54 : 35;
    const titleSize = is4K ? 120 : 80;
    const step = is4K ? 150 : 100;
    const props = { left: 100 + (count * 30), top: 100 + (count * step), fontFamily: 'Oswald', fontSize: type === 'title' ? titleSize : baseSize, fill: 'white', shadow: '2px 2px 10px rgba(0,0,0,0.8)', dataTag: type };
    
    if (type === 'rating_star') {
        const starUrl = 'https://upload.wikimedia.org/wikipedia/commons/thumb/2/29/Gold_Star.svg/1024px-Gold_Star.svg.png';
        const proxiedUrl = `/api/proxy/image?url=${encodeURIComponent(starUrl)}`;
        fabric.Image.fromURL(proxiedUrl, function(img) {
            if(!img) return;
            img.scaleToHeight(props.fontSize).set({dataTag: 'rating_star_img'});
            const text = new fabric.IText(placeholder, { ...props, left: img.getScaledWidth() + 10, top: 0, shadow: undefined, editable: false });
            const group = new fabric.Group([img, text], { left: props.left, top: props.top, dataTag: type });
            canvas.add(group);
            canvas.setActiveObject(group);
            if (lastFetchedData) previewTemplate(lastFetchedData);
            else canvas.requestRenderAll();
        }, { crossOrigin: 'anonymous' });
        return;
    }

    if (type === 'certification') {
        const defaultUrl = '/api/certification/FSK_16.svg';
        const urlToLoad = defaultUrl.startsWith('http') ? `/api/proxy/image?url=${encodeURIComponent(defaultUrl)}` : defaultUrl;
        fabric.Image.fromURL(urlToLoad, function(img, isError) {
            if(isError || !img) { console.error("Failed to load certification image"); return; }
            img.scaleToHeight(props.fontSize * 1.5);
            img.set({ left: props.left, top: props.top, dataTag: type });
            canvas.add(img);
            canvas.setActiveObject(img);
            if (lastFetchedData) previewTemplate(lastFetchedData);
            else canvas.requestRenderAll();
        }, { crossOrigin: 'anonymous', dataTag: type });
        return;
    }
    
    if (type === 'rating') {
        const logoUrl = 'https://upload.wikimedia.org/wikipedia/commons/thumb/6/69/IMDB_Logo_2016.svg/1200px-IMDB_Logo_2016.svg.png';
        const proxiedUrl = `/api/proxy/image?url=${encodeURIComponent(logoUrl)}`;
        fabric.Image.fromURL(proxiedUrl, function(img) {
            if(!img) return;
            img.scaleToHeight(props.fontSize).set({dataTag: 'rating_logo_img'});
            const textVal = placeholder.replace('IMDb: ', '');
            const text = new fabric.IText(textVal, { ...props, left: img.getScaledWidth() + 10, top: 0, shadow: undefined, editable: false });
            text.set('top', (img.getScaledHeight() - text.getScaledHeight()) / 2);
            const group = new fabric.Group([img, text], { left: props.left, top: props.top, dataTag: type });
            canvas.add(group);
            canvas.setActiveObject(group);
            if (lastFetchedData) previewTemplate(lastFetchedData);
            else canvas.requestRenderAll();
        }, { crossOrigin: 'anonymous' });
        return;
    }

    if (type === 'overview') {
        textObj = new fabric.Textbox(placeholder, { ...props, width: 600, height: 300, fixedHeight: 300, splitByGrapheme: false, lockScalingY: false, fullMediaText: placeholder, editable: false });
    } else {
        textObj = new fabric.IText(placeholder, { ...props, editable: false });
    }
    canvas.add(textObj);
    canvas.setActiveObject(textObj);
    if (lastFetchedData) previewTemplate(lastFetchedData);
    else canvas.requestRenderAll();
}

function addLogo(url) {
    const proxiedUrl = `/api/proxy/image?url=${encodeURIComponent(url)}`;
    fabric.Image.fromURL(proxiedUrl, function(img) {
        if(!img) return;
        img.scaleToWidth(100);
        const count = canvas.getObjects().length;
        const offset = count * 20;
        img.set({ left: 100 + offset, top: 100 + offset });
        canvas.add(img);
        canvas.setActiveObject(img);
        canvas.requestRenderAll();
        updateVerticalLayout();
        saveToLocalStorage();
    }, { crossOrigin: 'anonymous', dataTag: 'icon' });
}

function getCertificationImageUrl(rating) {
    if (!rating) return null;
    let r = String(rating).toUpperCase();
    let clean = r.replace(/[\s-]/g, ''); // Remove spaces and dashes: "DE-12" -> "DE12"

    // FSK (German)
    if (clean === 'FSK0' || clean === '0' || clean === 'DE0') return '/api/certification/FSK_0.svg';
    if (clean === 'FSK6' || clean === '6' || clean === 'DE6') return '/api/certification/FSK_6.svg';
    if (clean === 'FSK12' || clean === '12' || clean === 'DE12') return '/api/certification/FSK_12.svg';
    if (clean === 'FSK16' || clean === '16' || clean === 'DE16') return '/api/certification/FSK_16.svg';
    if (clean === 'FSK18' || clean === '18' || clean === 'DE18') return '/api/certification/FSK_18.svg';

    // Common German variations (e.g. "ab 6")
    if (clean === 'AB0' || clean === 'AB0JAHREN') return '/api/certification/FSK_0.svg';
    if (clean === 'AB6' || clean === 'AB6JAHREN') return '/api/certification/FSK_6.svg';
    if (clean === 'AB12' || clean === 'AB12JAHREN') return '/api/certification/FSK_12.svg';
    if (clean === 'AB16' || clean === 'AB16JAHREN') return '/api/certification/FSK_16.svg';
    if (clean === 'AB18' || clean === 'AB18JAHREN') return '/api/certification/FSK_18.svg';

    // MPAA (US)
    if (clean === 'G' || clean === 'USG') return 'https://upload.wikimedia.org/wikipedia/commons/0/05/RATED_G.svg';
    if (clean === 'PG' || clean === 'USPG') return 'https://upload.wikimedia.org/wikipedia/commons/b/bc/RATED_PG.svg';
    if (clean === 'PG13' || clean === 'USPG13') return 'https://upload.wikimedia.org/wikipedia/commons/c/c0/RATED_PG-13.svg';
    if (clean === 'R' || clean === 'USR') return 'https://upload.wikimedia.org/wikipedia/commons/7/7e/RATED_R.svg';
    if (clean === 'NC17' || clean === 'USNC17') return 'https://upload.wikimedia.org/wikipedia/commons/5/50/RATED_NC-17.svg';
    
    // TV Ratings (US)
    if (clean === 'TVY' || clean === 'USTVY') return 'https://upload.wikimedia.org/wikipedia/commons/2/25/TV-Y_icon.svg';
    if (clean === 'TVY7' || clean === 'USTVY7') return 'https://upload.wikimedia.org/wikipedia/commons/5/5a/TV-Y7_icon.svg';
    if (clean === 'TVG' || clean === 'USTVG') return 'https://upload.wikimedia.org/wikipedia/commons/5/5e/TV-G_icon.svg';
    if (clean === 'TVPG' || clean === 'USTVPG') return 'https://upload.wikimedia.org/wikipedia/commons/9/9a/TV-PG_icon.svg';
    if (clean === 'TV14' || clean === 'USTV14') return 'https://upload.wikimedia.org/wikipedia/commons/c/c3/TV-14_icon.svg';
    if (clean === 'TVMA' || clean === 'USTVMA') return 'https://upload.wikimedia.org/wikipedia/commons/3/34/TV-MA_icon.svg';
    return null;
}

function updateGenreLimit() {
    const val = document.getElementById('genreLimitSlider').value;
    document.getElementById('genreLimitVal').innerText = (val == 6) ? "Max" : val;
    if (lastFetchedData) previewTemplate(lastFetchedData);
}

function groupElementsByRow(elements, threshold = 30) {
    if (!elements.length) return [];
    
    elements.sort((a, b) => a.top - b.top);
    
    const rows = [];
    let currentRow = [elements[0]];
    
    for (let i = 1; i < elements.length; i++) {
        if (Math.abs(elements[i].top - currentRow[0].top) < threshold) {
            currentRow.push(elements[i]);
        } else {
            rows.push(currentRow);
            currentRow = [elements[i]];
        }
    }
    rows.push(currentRow);
    return rows;
}

function updateVerticalLayout(skipRender = false) {
    const padding = 20; // This is the minimum vertical distance
    const hPadding = 20; // Horizontal spacing between tags
    const rowThreshold = 30; // How close elements must be to be considered in the same row
    
    canvas.renderAll(); // Ensure all dimensions (especially i-text) are calculated correctly
    
    const anchor = canvas.getObjects().find(o => o.dataTag === 'title');
    if (!anchor) { canvas.requestRenderAll(); return; }

    // Auto-switch alignment based on position (Left vs Right)
    const alignSelect = document.getElementById('tagAlignSelect');
    if (alignSelect.value !== 'center') {
        const centerX = anchor.left + (anchor.getScaledWidth() / 2);
        alignSelect.value = (centerX > canvas.width / 2) ? 'right' : 'left';
    }
    const alignment = alignSelect.value;

    // Sync text alignment for overview and provider_source based on layout alignment
    canvas.getObjects().forEach(o => {
        if ((o.dataTag === 'overview' || o.dataTag === 'provider_source') && (o.type === 'textbox' || o.type === 'i-text')) {
            o.set('textAlign', alignment);
            o.set('dirty', true);
        }
    });

    // Ensure anchor (Logo/Title) respects screen margin
    if (anchor.left < screenMargin) anchor.set('left', screenMargin);
    if (anchor.left + anchor.getScaledWidth() > canvas.width - screenMargin) {
        anchor.set('left', Math.max(screenMargin, canvas.width - screenMargin - anchor.getScaledWidth()));
    }
    
    // Vertical constraint for anchor (Top & Bottom)
    if (anchor.top < screenMargin) anchor.set('top', screenMargin);
    if (anchor.top + anchor.getScaledHeight() > canvas.height - screenMargin) {
        anchor.set('top', Math.max(screenMargin, canvas.height - screenMargin - anchor.getScaledHeight()));
    }
    anchor.setCoords();

    let current_y = anchor.top + anchor.getScaledHeight() + padding;
    
    const elements = canvas.getObjects().filter(o => {
        if (o === mainBg) return false; // Explicitly exclude mainBg
        if (o.dataTag === 'background') return false;
        if (o.dataTag === 'title') return false;
        if (o.dataTag === 'guide') return false;
        if (o.dataTag === 'fade_effect') return false;
        if (o.dataTag === 'grid_line') return false;
        if (!o.dataTag) return false;
        // if (!o.visible) return false; // Keep invisible objects to preserve order
        return true;
    });
    const rows = groupElementsByRow(elements, rowThreshold);

    if (rows.length > 0) {
        let maxRowWidth = 0;
        rows.forEach(row => {
            let w = 0;
            const visibleEls = row.filter(e => e.visible);
            visibleEls.forEach((el, i) => {
                const pad = el.padding || 0;
                w += el.getScaledWidth() + (pad * 2);
                if (i < visibleEls.length - 1) w += hPadding;
            });
            if (w > maxRowWidth) maxRowWidth = w;
        });

        const anchorW = anchor.getScaledWidth();
        let shift = 0;

        if (alignment === 'center') {
            const idealStart = anchor.left + (anchorW - maxRowWidth) / 2;
            if (idealStart < screenMargin) shift = screenMargin - idealStart;
            else if (idealStart + maxRowWidth > canvas.width - screenMargin) shift = (canvas.width - screenMargin - maxRowWidth) - idealStart;
        } else if (alignment === 'right') {
            const idealStart = (anchor.left + anchorW) - maxRowWidth;
            if (idealStart < screenMargin) shift = screenMargin - idealStart;
        } else { // left
            const idealStart = anchor.left;
            if (idealStart + maxRowWidth > canvas.width - screenMargin) shift = (canvas.width - screenMargin - maxRowWidth) - idealStart;
        }

        if (shift !== 0) { anchor.set('left', anchor.left + shift); anchor.setCoords(); }
    }

    const anchorLeft = anchor.left;
    const anchorWidth = anchor.getScaledWidth();

    rows.forEach(row => {
        // Auto-resize icons if enabled (Match Height)
        const resizableIcons = row.filter(el => el.type === 'image' && el.matchHeight && el.visible);
        if (resizableIcons.length > 0) {
            const ref = row.find(el => (el.type === 'i-text' || el.type === 'textbox' || el.type === 'group') && !el.matchHeight && el.visible);
            if (ref) {
                const targetH = ref.getScaledHeight();
                resizableIcons.forEach(icon => {
                    if (Math.abs(icon.getScaledHeight() - targetH) > 0.5) {
                        icon.scaleToHeight(targetH);
                        icon.setCoords();
                    }
                });
            }
        }

        // Sort elements in this row by their X position (left to right)
        row.sort((a, b) => a.left - b.left);
        
        // Calculate total width of this row
        let totalRowWidth = 0;
        const visibleEls = row.filter(e => e.visible);
        visibleEls.forEach((el, index) => {
            el.setCoords(); // Ensure coords are fresh for width calc
            const pad = el.padding || 0;
            totalRowWidth += el.getScaledWidth() + (pad * 2);
            if (index < visibleEls.length - 1) totalRowWidth += hPadding;
        });

        // Determine starting X: Center relative to logo (even if wider), else align left
        let current_x;
        if (alignment === 'center') {
            current_x = anchorLeft + (anchorWidth - totalRowWidth) / 2;
        } else if (alignment === 'right') {
            current_x = (anchorLeft + anchorWidth) - totalRowWidth;
            // FIX: Shift right to align CONTENT edge to anchor (ignore padding of last element)
            const lastEl = visibleEls[visibleEls.length - 1];
            if (lastEl) current_x += (lastEl.padding || 0);
        } else {
            current_x = anchorLeft;
            // FIX: Shift left to align CONTENT edge to anchor (ignore padding of first element)
            const firstEl = visibleEls[0];
            if (firstEl) current_x -= (firstEl.padding || 0);
        }

        // Ensure tags don't go off-screen (apply margins)
        if (current_x < screenMargin) current_x = screenMargin;
        if (current_x + totalRowWidth > canvas.width - screenMargin) {
            current_x = Math.max(screenMargin, canvas.width - screenMargin - totalRowWidth);
        }

        const maxRowHeight = Math.max(...row.map(el => el.visible ? el.getScaledHeight() + ((el.padding||0)*2) : 0));
        
        // Stack elements horizontally starting from the calculated current_x
        row.forEach(el => {
            const pad = el.padding || 0;
            el.set({ top: current_y + pad, left: current_x + pad });
            el.setCoords(); // Update coordinates for accurate width calculation
            if (el.visible) {
                current_x += el.getScaledWidth() + (pad * 2) + hPadding;
            } else {
                // Increment tiny amount to preserve order for next sort without visual gap
                current_x += 0.1;
            }
        });
        
        if (maxRowHeight > 0) {
            current_y += maxRowHeight + padding;
        }
    });

    // Check for bottom overflow and shift up if necessary
    const contentBottom = current_y - padding;
    const maxBottom = canvas.height - screenMargin;
    
    if (contentBottom > maxBottom) {
        const shift = contentBottom - maxBottom;
        const maxShift = anchor.top - screenMargin;
        const actualShift = Math.min(shift, maxShift);
        
        if (actualShift > 0) {
            anchor.set('top', anchor.top - actualShift);
            rows.forEach(row => row.forEach(el => el.set('top', el.top - actualShift)));
        }
    }

    canvas.getObjects().forEach(o => o.setCoords());
    if (!skipRender) canvas.requestRenderAll();
}

function toggleGrid() {
    gridEnabled = !gridEnabled;
    if (gridEnabled) drawGrid();
    else removeGrid();
    canvas.requestRenderAll();
}

function drawGrid() {
    removeGrid();
    const w = canvas.width, h = canvas.height;
    const opts = { stroke: '#555', strokeDashArray: [5, 5], selectable: false, evented: false, dataTag: 'grid_line' };
    for (let i = 1; i < (w / gridSize); i++) canvas.add(new fabric.Line([ i * gridSize, 0, i * gridSize, h], opts));
    for (let i = 1; i < (h / gridSize); i++) canvas.add(new fabric.Line([ 0, i * gridSize, w, i * gridSize], opts));
    
    const gridLines = canvas.getObjects().filter(o => o.dataTag === 'grid_line');
    const fadeObjs = canvas.getObjects().filter(o => o.dataTag === 'fade_effect');
    
    gridLines.forEach(o => canvas.sendToBack(o));
    fadeObjs.forEach(o => canvas.sendToBack(o));
    if (mainBg) canvas.sendToBack(mainBg);
}

function drawGuide(x1, y1, x2, y2) {
    const l = new fabric.Line([x1, y1, x2, y2], { stroke: 'cyan', strokeWidth: 1, strokeDashArray: [4, 4], selectable: false, evented: false, dataTag: 'guide' });
    canvas.add(l); guideLines.push(l);
}
function clearGuides() { guideLines.forEach(l => canvas.remove(l)); guideLines = []; }

function removeGrid() {
    const gridLines = canvas.getObjects().filter(o => o.dataTag === 'grid_line');
    gridLines.forEach(o => canvas.remove(o));
}

function init() {
    canvas = new fabric.Canvas('mainCanvas', { width: 1920, height: 1080, backgroundColor: '#000000', preserveObjectStacking: true });
    canvas.renderOnAddRemove = false;
    fabric.Object.prototype.objectCaching = true;

    canvas.on('object:scaling', (e) => {
        const t = e.target;
        if (t instanceof fabric.Textbox) {
            t.set({ width: t.width * t.scaleX, fixedHeight: t.height * t.scaleY, scaleX: 1, scaleY: 1 });
            if (t.dataTag === 'overview') { clearTimeout(scalingTimeout); scalingTimeout = setTimeout(() => applyTruncation(t, t.fullMediaText), 50); }
        }
        if (t === mainBg) updateFades();
        canvas.requestRenderAll();
        saveToLocalStorage();
    });

    canvas.on('mouse:down', (e) => {
        const active = e.target;
        if (!active || !active.selectable || active === mainBg) return;
        snapLines = { v: [], h: [] };
        if (!gridEnabled) {
            canvas.getObjects().forEach(obj => {
                if (obj === active || !obj.selectable || !obj.visible || obj.dataTag === 'guide') return;
                const b = obj.getBoundingRect();
                snapLines.h.push(b.top, b.top + b.height, b.top + b.height / 2);
                snapLines.v.push(b.left, b.left + b.width, b.left + b.width / 2);
            });
        }
    });
    
    canvas.on('object:moving', (e) => { 
        const active = e.target;
        if (active === mainBg) { updateFades(); return; }

        if (gridEnabled) {
            active.set({
                left: Math.round(active.left / gridSize) * gridSize,
                top: Math.round(active.top / gridSize) * gridSize
            });
        } else { 
            const threshold = 10;
            const b = active.getBoundingRect();
            const pts = { x: [b.left, b.left + b.width, b.left + b.width/2], y: [b.top, b.top + b.height, b.top + b.height/2] };
            
            clearGuides();

            for (const line of snapLines.v) {
                for (const pt of pts.x) {
                    if (Math.abs(pt - line) < threshold) {
                        active.set({ left: active.left + (line - pt) });
                        drawGuide(line, 0, line, canvas.height);
                        canvas.requestRenderAll();
                        return;
                    }
                }
            }
            for (const line of snapLines.h) {
                for (const pt of pts.y) {
                    if (Math.abs(pt - line) < threshold) {
                        active.set({ top: active.top + (line - pt) });
                        drawGuide(0, line, canvas.width, line);
                        canvas.requestRenderAll();
                        return;
                    }
                }
            }
        }
    });
    
    canvas.on('mouse:up', (e) => {
        try {
            clearGuides();
            if (e.target && e.target.dataTag) {
                setTimeout(() => {
                    updateVerticalLayout();
                    saveToLocalStorage();
                }, 0);
            }
        } catch (err) { console.error("Error in mouse:up", err); }
    });

    canvas.on('selection:created', updateSelectionUI);
    canvas.on('selection:updated', updateSelectionUI);
    canvas.on('selection:cleared', updateSelectionUI);
    
    canvas.on('object:modified', saveToLocalStorage);
    canvas.on('object:added', saveToLocalStorage);
    canvas.on('object:removed', saveToLocalStorage);
    canvas.on('text:changed', saveToLocalStorage);
    
    window.addEventListener('keydown', (e) => {
        const active = canvas.getActiveObject();
        if (active && (active.type === 'i-text' || active.type === 'textbox') && active.isEditing) return;

        if (e.key === "Delete" || e.key === "Backspace") {
            canvas.getActiveObjects().forEach(obj => { if (obj === mainBg) mainBg = null; canvas.remove(obj); });
            canvas.discardActiveObject().requestRenderAll();
        }
    });

    if (!loadFromLocalStorage()) {
        if (window.initialBackdropUrl) loadBackground(window.initialBackdropUrl);
    }
    updateFadeControls();
}

function loadBackground(url, skipRender = false) {
    return new Promise((resolve) => {
        const proxiedUrl = url.startsWith('http') ? `/api/proxy/image?url=${encodeURIComponent(url)}` : url;
        fabric.Image.fromURL(proxiedUrl, function(img, isError) {
            if (isError || !img) { resolve(); return; }
            if (mainBg) canvas.remove(mainBg);
            mainBg = img;
            img.set({ left: 0, top: 0, selectable: true, dataTag: 'background' });
        
            const targetWidth = canvas.width * 0.70;
            img.scaleToWidth(targetWidth);
            img.set({ left: canvas.width - targetWidth, top: 0 });
        
            canvas.add(img); canvas.sendToBack(img); updateFades(skipRender);
            resolve();
            saveToLocalStorage();
        }, { crossOrigin: 'anonymous' });
    });
}

function updateFadeControls() {
    const type = document.getElementById('fadeEffect').value;
    const show = (id) => document.getElementById(id).style.display = 'block';
    const hide = (id) => document.getElementById(id).style.display = 'none';
    const radiusLabel = document.querySelector('label[for="fadeRadius"]');

    ['ctrl-fade-radius', 'ctrl-fade-left', 'ctrl-fade-right', 'ctrl-fade-top', 'ctrl-fade-bottom'].forEach(show);

    if (type === 'custom') {
        hide('ctrl-fade-radius');
    } else if (type === 'bottom-left') {
        hide('ctrl-fade-top');
        hide('ctrl-fade-right');
        radiusLabel.innerText = "Corner Radius";
    } else if (type === 'bottom-right') {
        hide('ctrl-fade-top');
        hide('ctrl-fade-left');
        radiusLabel.innerText = "Corner Radius";
    } else if (type === 'top-left') {
        hide('ctrl-fade-bottom');
        hide('ctrl-fade-right');
        radiusLabel.innerText = "Corner Radius";
    } else if (type === 'top-right') {
        hide('ctrl-fade-bottom');
        hide('ctrl-fade-left');
        radiusLabel.innerText = "Corner Radius";
    } else if (type === 'vignette') {
        hide('ctrl-fade-left');
        hide('ctrl-fade-right');
        show('ctrl-fade-top');
        show('ctrl-fade-bottom');
        radiusLabel.innerText = "Vignette Radius";
    }
    updateFades();
}

function updateFades(skipRender = false) {
    if (!mainBg) return;
    const type = document.getElementById('fadeEffect').value;

    // Remove ALL existing fade effects from canvas to prevent stacking
    canvas.getObjects().filter(o => o.dataTag === 'fade_effect').forEach(o => canvas.remove(o));
    fades = {}; // Reset tracker

    const addLinear = (side) => {
        const el = document.getElementById('fade' + side.charAt(0).toUpperCase() + side.slice(1));
        if (el && el.value > 0) {
            fades[side] = createFadeRect(side, el.value);
            canvas.add(fades[side]);
            fades[side].moveTo(canvas.getObjects().indexOf(mainBg) + 1);
        }
    };

    if (type === 'custom') {
        ['left', 'right', 'top', 'bottom'].forEach(addLinear);
    } else if (type === 'bottom-left') {
        addCornerFade('bottom-left');
        addLinear('left');
        addLinear('bottom');
    } else if (type === 'bottom-right') {
        addCornerFade('bottom-right');
        addLinear('right');
        addLinear('bottom');
    } else if (type === 'top-left') {
        addCornerFade('top-left');
        addLinear('left');
        addLinear('top');
    } else if (type === 'top-right') {
        addCornerFade('top-right');
        addLinear('right');
        addLinear('top');
    } else if (type === 'vignette') {
        addVignette();
        addLinear('top');
        addLinear('bottom');
    }
    if (!skipRender) canvas.requestRenderAll();
}

function addCornerFade(pos) {
    const r = parseInt(document.getElementById('fadeRadius').value);
    if (r <= 0) return;
    const bgColor = document.getElementById('bgColor').value;
    const w = mainBg.getScaledWidth(), h = mainBg.getScaledHeight();
    let rectLeft, rectTop, gradCx, gradCy;

    if (pos === 'bottom-left') {
        rectLeft = mainBg.left; rectTop = mainBg.top + h - r;
        gradCx = 0; gradCy = r;
    } else if (pos === 'bottom-right') {
        rectLeft = mainBg.left + w - r; rectTop = mainBg.top + h - r;
        gradCx = r; gradCy = r;
    } else if (pos === 'top-left') {
        rectLeft = mainBg.left; rectTop = mainBg.top;
        gradCx = 0; gradCy = 0;
    } else if (pos === 'top-right') {
        rectLeft = mainBg.left + w - r; rectTop = mainBg.top;
        gradCx = r; gradCy = 0;
    }

    const grad = new fabric.Gradient({
        type: 'radial',
        coords: { r1: 0, r2: r, x1: gradCx, y1: gradCy, x2: gradCx, y2: gradCy },
        colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }]
    });

    fades.corner = new fabric.Rect({ left: rectLeft, top: rectTop, width: r, height: r, fill: grad, selectable: false, evented: false, dataTag: 'fade_effect' });
    canvas.add(fades.corner);
    fades.corner.moveTo(canvas.getObjects().indexOf(mainBg) + 1);
}

function addVignette() {
    const r = parseInt(document.getElementById('fadeRadius').value);
    if (r <= 0) return;
    const bgColor = document.getElementById('bgColor').value;
    const padding = 10;
    const w = Math.ceil(mainBg.getScaledWidth()) + padding, h = Math.ceil(mainBg.getScaledHeight()) + padding;
    
    const grad = new fabric.Gradient({
        type: 'radial',
        coords: { r1: 0, r2: r, x1: w/2, y1: h/2, x2: w/2, y2: h/2 },
        colorStops: [{ offset: 0, color: hexToRgba(bgColor, 0) }, { offset: 1, color: bgColor }]
    });

    fades.corner = new fabric.Rect({ left: mainBg.left - (padding/2), top: mainBg.top - (padding/2), width: w, height: h, fill: grad, selectable: false, evented: false, dataTag: 'fade_effect' });
    canvas.add(fades.corner);
    fades.corner.moveTo(canvas.getObjects().indexOf(mainBg) + 1);
}

function createFadeRect(type, size) {
    const bgColor = document.getElementById('bgColor').value;
    const b = 2, wImg = mainBg.getScaledWidth(), hImg = mainBg.getScaledHeight();
    let w, h, x, y, c;
    if (type === 'left') { w = parseInt(size) + b; h = hImg + b*2; x = mainBg.left - b; y = mainBg.top - b; c = { x1: 0, y1: 0, x2: 1, y2: 0 }; }
    else if (type === 'right') { w = parseInt(size) + b; h = hImg + b*2; x = mainBg.left + wImg - size; y = mainBg.top - b; c = { x1: 1, y1: 0, x2: 0, y2: 0 }; }
    else if (type === 'top') { w = wImg + b*2; h = parseInt(size) + b; x = mainBg.left - b; y = mainBg.top - b; c = { x1: 0, y1: 0, x2: 0, y2: 1 }; }
    else if (type === 'bottom') { w = wImg + b*2; h = parseInt(size) + b; x = mainBg.left - b; y = mainBg.top + hImg - size; c = { x1: 0, y1: 1, x2: 0, y2: 0 }; }
    return new fabric.Rect({
        left: x, top: y, width: w, height: h, selectable: false, evented: false,
        fill: new fabric.Gradient({ type: 'linear', gradientUnits: 'percentage', coords: c, colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }] }),
        dataTag: 'fade_effect'
    });
}

function hexToRgba(hex, a) {
    let r = parseInt(hex.slice(1, 3), 16), g = parseInt(hex.slice(3, 5), 16), b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${a === 0 ? 0.005 : a})`;
}

function updateBgColor(skipRender = false) { 
    if(!canvas) return Promise.resolve(); 
    
    const bgColorHex = document.getElementById('bgColor').value;
    canvas.getObjects().forEach(obj => {
        if (obj.type === 'textbox' && obj.autoBackgroundColor && obj.backgroundColor) {
            const c = new fabric.Color(obj.backgroundColor);
            const currentOpacity = c.getSource()[3];
            const rgb = new fabric.Color(bgColorHex).getSource();
            obj.set('backgroundColor', `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${currentOpacity})`);
        }
    });

    return new Promise(resolve => {
        canvas.setBackgroundColor(bgColorHex, () => { 
            updateFades(true); 
            if (!skipRender) canvas.requestRenderAll(); 
            resolve();
        });
    });
}

function setUIInteraction(enabled) {
    const elements = document.querySelectorAll('button, input, select, textarea, .tab-link');
    elements.forEach(el => {
        if (el.classList.contains('tab-link')) {
            el.style.pointerEvents = enabled ? 'auto' : 'none';
            el.style.opacity = enabled ? '1' : '0.5';
        } else {
            el.disabled = !enabled;
        }
    });
    
    // Disable canvas interaction
    const canvasWrapper = document.getElementById('canvas-wrapper');
    if (canvasWrapper) {
        canvasWrapper.style.pointerEvents = enabled ? 'auto' : 'none';
        canvasWrapper.style.opacity = enabled ? '1' : '0.8';
    }
    
    if (enabled) updateSelectionUI();
}

function openTab(evt, tabId) { document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active')); document.querySelectorAll('.tab-link').forEach(l => l.classList.remove('active')); document.getElementById(tabId).classList.add('active'); evt.currentTarget.classList.add('active'); }
async function saveSettings() {
    const config = {
        general: {
            overwrite_existing: document.getElementById('batchOverwrite').checked
        },
        jellyfin: {
            url: document.getElementById('set-jf-url').value,
            api_key: document.getElementById('set-jf-key').value,
            user_id: document.getElementById('set-jf-user').value,
            excluded_libraries: document.getElementById('set-jf-exclude').value
        },
        plex: {
            url: document.getElementById('set-plex-url').value,
            token: document.getElementById('set-plex-token').value
        },
        tmdb: {
            api_key: document.getElementById('set-tmdb-key').value,
            language: document.getElementById('set-tmdb-lang').value
        },
        radarr: {
            url: document.getElementById('set-radarr-url').value,
            api_key: document.getElementById('set-radarr-key').value
        },
        sonarr: {
            url: document.getElementById('set-sonarr-url').value,
            api_key: document.getElementById('set-sonarr-key').value
        },
        jellyseerr: {
            url: document.getElementById('set-jellyseerr-url').value,
            api_key: document.getElementById('set-jellyseerr-key').value
        },
        trakt: {
            api_key: document.getElementById('set-trakt-key').value,
            username: document.getElementById('set-trakt-user').value,
            listname: document.getElementById('set-trakt-list').value
        },
        editor: {
            resolution: document.getElementById('resSelect').value
        }
    };
    const resp = await fetch('/api/settings', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(config) });
    if(resp.ok) alert("Settings saved!");
}
function changeResolution() {
    if (gridEnabled) removeGrid();
    const res = document.getElementById('resSelect').value;
    const targetW = (res === '2160') ? 3840 : 1920;
    const scale = targetW / canvas.width;
    canvas.setDimensions({ width: targetW, height: (res === '2160' ? 2160 : 1080) });
    canvas.getObjects().forEach(obj => { obj.scaleX *= scale; obj.scaleY *= scale; obj.left *= scale; obj.top *= scale; obj.setCoords(); });
    if (gridEnabled) drawGrid();
    updateFades();
}

async function saveLayout() {
    const name = document.getElementById('layoutName').value;
    if (!name) return alert("Please enter a layout name");
    
    const btn = document.querySelector('button[onclick="saveLayout()"]');
    const originalText = btn.innerText;
    btn.disabled = true;
    btn.innerText = "Saving Layout...";
    setUIInteraction(false);

    const layout = canvas.toJSON(['dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 'autoBackgroundColor']);
    
    // Filter out fade effects and grid lines BEFORE saving
    layout.objects = layout.objects.filter(o => o.dataTag !== 'fade_effect' && o.dataTag !== 'grid_line');

    layout.custom_effects = {
        bgColor: document.getElementById('bgColor').value,
        bgBrightness: document.getElementById('bgBrightness').value,
        fadeEffect: document.getElementById('fadeEffect').value,
        fadeRadius: document.getElementById('fadeRadius').value,
        fadeLeft: document.getElementById('fadeLeft').value,
        fadeRight: document.getElementById('fadeRight').value,
        fadeTop: document.getElementById('fadeTop').value,
        fadeBottom: document.getElementById('fadeBottom').value,
        tagAlignment: document.getElementById('tagAlignSelect').value,
        genreLimit: document.getElementById('genreLimitSlider').value
    };

    // Generate Preview Thumbnail (smaller size)
    const previewData = canvas.toDataURL({ format: 'jpeg', quality: 0.8, multiplier: 0.5 });

    const resp = await fetch('/api/layouts/save', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({name, layout, preview_image: previewData}) });
    if(!resp.ok) {
        alert("Error saving layout");
        btn.innerText = originalText;
        btn.disabled = false;
        setUIInteraction(true);
        return;
    }

    // Generate 10 Previews
    const generatedImages = [];
    isBatchRunning = true; // Suppress UI updates in fetchRandomPreview
    try {
        for(let i=0; i<10; i++) {
            btn.innerText = `Generating ${i+1}/10...`;
            await fetchRandomPreview();
            const res = await saveToGalleryInternal(name, null, 'layout_preview');
            if(res && res.status === 'success') generatedImages.push(res.filename);
        }
    } catch(e) { console.error(e); }
    finally {
        isBatchRunning = false;
        btn.innerText = originalText;
        btn.disabled = false;
        setUIInteraction(true);
    }

    loadLayoutsList();
    await loadGallery(); // Refresh gallery data so lightbox works
    showPreviewPopup(name, generatedImages);
}

function showPreviewPopup(layoutName, images) {
    const grid = document.getElementById('preview-grid');
    grid.innerHTML = '';
    const layoutKey = `LayoutPreview: ${layoutName}`;
    
    images.forEach(img => {
        const src = `/api/gallery/image/${encodeURIComponent(layoutKey)}/${encodeURIComponent(img)}`;
        grid.innerHTML += `
            <div class="gallery-item">
                <img src="${src}" onclick="closePreviewPopup(); openLightbox('${layoutKey}', ${loadedGalleryData[layoutKey].indexOf(img)})">
                <div class="caption">${img}</div>
                <button onclick="closePreviewPopup(); editGalleryImage('${layoutKey}', '${img}')" style="position:absolute; top:5px; right:5px; width:auto; padding:4px 8px; font-size:12px; background:rgba(0,0,0,0.7); border:1px solid #fff; cursor:pointer; color:white;">✏️</button>
            </div>`;
    });
    document.getElementById('preview-popup').style.display = 'flex';
}

function closePreviewPopup() {
    document.getElementById('preview-popup').style.display = 'none';
}

async function loadLayout(name, silent = false) {
    const resp = await fetch(`/api/layouts/load/${name}`);
    if(!resp.ok) {
        if(!silent) alert("Error loading layout");
        return;
    }
    const data = await resp.json();
    
    return new Promise((resolve) => {
    canvas.loadFromJSON(data, () => {
        canvas.renderAll();
        
        // Restore mainBg reference
        mainBg = canvas.getObjects().find(o => o.dataTag === 'background');
        // Fallback if not tagged
        if (!mainBg && canvas.getObjects().length > 0) {
            const firstObj = canvas.item(0);
            if (firstObj && firstObj.type === 'image' && firstObj.width > 500) {
                mainBg = firstObj;
                mainBg.set('dataTag', 'background');
            }
        }
        // Remove ghost effects
        const ghosts = canvas.getObjects().filter(o => o.dataTag === 'fade_effect' || o.dataTag === 'grid_line');
        ghosts.forEach(g => canvas.remove(g));

        document.getElementById('layoutName').value = name;
        
        if (data.custom_effects) {
            const eff = data.custom_effects;
            if(eff.bgColor) { document.getElementById('bgColor').value = eff.bgColor; canvas.setBackgroundColor(eff.bgColor); }
            if(eff.bgBrightness) document.getElementById('bgBrightness').value = eff.bgBrightness;
            if(eff.fadeEffect) document.getElementById('fadeEffect').value = eff.fadeEffect;
            if(eff.fadeRadius) document.getElementById('fadeRadius').value = eff.fadeRadius;
            if(eff.fadeLeft) document.getElementById('fadeLeft').value = eff.fadeLeft;
            if(eff.fadeRight) document.getElementById('fadeRight').value = eff.fadeRight;
            if(eff.fadeTop) document.getElementById('fadeTop').value = eff.fadeTop;
            if(eff.fadeBottom) document.getElementById('fadeBottom').value = eff.fadeBottom;
            if(eff.tagAlignment) document.getElementById('tagAlignSelect').value = eff.tagAlignment;
            else if(eff.centerTags !== undefined) document.getElementById('tagAlignSelect').value = eff.centerTags ? 'center' : 'left';
            if(eff.limitGenres !== undefined) {
                const val = eff.limitGenres ? 2 : 6;
                document.getElementById('genreLimitSlider').value = val;
                document.getElementById('genreLimitVal').innerText = (val == 6) ? "Max" : val;
            }
            if(eff.genreLimit !== undefined) {
                document.getElementById('genreLimitSlider').value = eff.genreLimit;
                document.getElementById('genreLimitVal').innerText = (eff.genreLimit == 6) ? "Max" : eff.genreLimit;
            }
            
            updateFadeControls();
            updateBgColor();
        } else {
            updateFades();
        }

        const btnSaveGallery = document.getElementById('btn-save-gallery');
        if(btnSaveGallery) btnSaveGallery.disabled = true;
        
        const btnShuffle = document.getElementById('btn-shuffle');
        if(btnShuffle) btnShuffle.disabled = false;
        
        if (!silent) {
            openTab({currentTarget: document.querySelector('.tab-link')}, 'editor-tab');
            alert(`Layout "${name}" loaded!`);
        }
        resolve();
    });
    });
}

function mirrorBackground() {
    if (!mainBg) return;
    mainBg.set('flipX', !mainBg.flipX);
    canvas.requestRenderAll();
}

function saveToLocalStorage() {
    if (!canvas) return;
    const json = canvas.toJSON(['dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 'autoBackgroundColor']);
    // Filter out fade effects so they aren't saved as static objects
    json.objects = json.objects.filter(o => o.dataTag !== 'fade_effect' && o.dataTag !== 'grid_line');
    
    json.custom_effects = {
        bgColor: document.getElementById('bgColor').value,
        bgBrightness: document.getElementById('bgBrightness').value,
        fadeEffect: document.getElementById('fadeEffect').value,
        fadeRadius: document.getElementById('fadeRadius').value,
        fadeLeft: document.getElementById('fadeLeft').value,
        fadeRight: document.getElementById('fadeRight').value,
        fadeTop: document.getElementById('fadeTop').value,
        fadeBottom: document.getElementById('fadeBottom').value,
        tagAlignment: document.getElementById('tagAlignSelect').value,
        genreLimit: document.getElementById('genreLimitSlider').value
    };
    json.lastFetchedData = lastFetchedData;
    localStorage.setItem('autosave_layout', JSON.stringify(json));
}

function loadFromLocalStorage() {
    const saved = localStorage.getItem('autosave_layout');
    if (saved) {
        try {
            const data = JSON.parse(saved);
            lastFetchedData = data.lastFetchedData || null;
            canvas.loadFromJSON(data, () => {
                canvas.renderAll();
                mainBg = canvas.getObjects().find(o => o.dataTag === 'background');
                
                // Cleanup: Remove any existing fade effects (tagged or untagged ghosts)
                const ghosts = canvas.getObjects().filter(o => 
                    o.dataTag === 'fade_effect' || 
                    o.dataTag === 'grid_line' || 
                    (o.type === 'rect' && !o.selectable && !o.evented) ||
                    (o.type === 'line' && o.stroke === '#555' && !o.selectable) // Legacy grid cleanup
                );
                ghosts.forEach(g => canvas.remove(g));
                
                
                // Fallback: If no background tag found, assume the first large image is the background
                if (!mainBg && canvas.getObjects().length > 0) {
                    const firstObj = canvas.item(0);
                    if (firstObj && firstObj.type === 'image' && firstObj.width > 500) {
                        mainBg = firstObj;
                        mainBg.set('dataTag', 'background');
                    }
                }
                
                if (data.custom_effects) {
                    const eff = data.custom_effects;
                    if(eff.bgColor) { document.getElementById('bgColor').value = eff.bgColor; canvas.setBackgroundColor(eff.bgColor, () => {}); }
                    if(eff.bgBrightness) document.getElementById('bgBrightness').value = eff.bgBrightness;
                    if(eff.fadeEffect) document.getElementById('fadeEffect').value = eff.fadeEffect;
                    if(eff.fadeRadius) document.getElementById('fadeRadius').value = eff.fadeRadius;
                    if(eff.fadeLeft) document.getElementById('fadeLeft').value = eff.fadeLeft;
                    if(eff.fadeRight) document.getElementById('fadeRight').value = eff.fadeRight;
                    if(eff.fadeTop) document.getElementById('fadeTop').value = eff.fadeTop;
                    if(eff.fadeBottom) document.getElementById('fadeBottom').value = eff.fadeBottom;
                    if(eff.tagAlignment) document.getElementById('tagAlignSelect').value = eff.tagAlignment;
                    else if(eff.centerTags !== undefined) document.getElementById('tagAlignSelect').value = eff.centerTags ? 'center' : 'left';
                    if(eff.limitGenres !== undefined) {
                        const val = eff.limitGenres ? 2 : 6;
                        document.getElementById('genreLimitSlider').value = val;
                        document.getElementById('genreLimitVal').innerText = (val == 6) ? "Max" : val;
                    }
                    if(eff.genreLimit !== undefined) {
                        document.getElementById('genreLimitSlider').value = eff.genreLimit;
                        document.getElementById('genreLimitVal').innerText = (eff.genreLimit == 6) ? "Max" : eff.genreLimit;
                    }
                    updateFadeControls();
                }
                updateFades();
            });
            return true;
        } catch(e) { console.error("Autosave load error", e); }
    }
    return false;
}
window.onload = init;