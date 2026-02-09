let lightboxImages = [], currentLightboxIndex = 0, loadedGalleryData = {}, currentGalleryTab = null, currentEditingFile = null;
let galleryCacheBuster = Date.now();

function openLightbox(layoutKey, index) {
    if (!loadedGalleryData || !loadedGalleryData[layoutKey]) return;
    
    lightboxImages = loadedGalleryData[layoutKey];
    currentLightboxIndex = index;
    
    document.getElementById('lightbox').style.display = 'flex';
    document.addEventListener('keydown', handleLightboxKeys);
    
    showLightboxImage(currentLightboxIndex);
}

function closeLightbox() {
    document.getElementById('lightbox').style.display = 'none';
    document.removeEventListener('keydown', handleLightboxKeys);
}

function showLightboxImage(index) {
    if (index < 0) index = lightboxImages.length - 1;
    if (index >= lightboxImages.length) index = 0;
    currentLightboxIndex = index;
    
    const layoutKey = Object.keys(loadedGalleryData).find(k => loadedGalleryData[k] === lightboxImages);
    const imgSrc = `/api/gallery/image/${encodeURIComponent(layoutKey)}/${encodeURIComponent(lightboxImages[index])}?t=${galleryCacheBuster}`;
    document.getElementById('lightbox-img').src = imgSrc;
    
    const editBtn = document.getElementById('lightbox-edit-btn');
    if (layoutKey && layoutKey.startsWith("LayoutPreview: ")) {
        editBtn.style.display = 'none';
    } else {
        editBtn.style.display = 'block';
        editBtn.onclick = () => editGalleryImage(layoutKey, lightboxImages[index]);
    }
}

function changeLightboxImage(direction) {
    showLightboxImage(currentLightboxIndex + direction);
}

function handleLightboxKeys(e) {
    if (e.key === 'ArrowRight') {
        changeLightboxImage(1);
    } else if (e.key === 'ArrowLeft') {
        changeLightboxImage(-1);
    } else if (e.key === 'Escape') {
        closeLightbox();
    }
}

function renderGalleryUI() {
    const container = document.getElementById('gallery-content');
    const folders = Object.keys(loadedGalleryData).filter(f => !f.startsWith("LayoutPreview: ")).sort();
    const images = loadedGalleryData[currentGalleryTab] || [];
    
    let tabsHtml = '<div class="sub-nav-tabs" style="overflow: hidden; justify-content: space-between; align-items: center;">';
    tabsHtml += '<div style="display: flex; gap: 10px; overflow-x: auto; scrollbar-width: thin; padding-bottom: 5px; flex: 1; margin-right: 10px;">';
    folders.forEach(folder => {
        const activeClass = folder === currentGalleryTab ? 'active' : '';
        const displayName = folder.replace('Layout: ', '');
        tabsHtml += `<div class="sub-tab-link ${activeClass}" onclick="switchGalleryTab('${folder}')">${displayName}</div>`;
    });
    tabsHtml += '</div>';
    
    if (images.length > 0) {
        tabsHtml += `<button onclick="deleteAllGalleryImages('${currentGalleryTab}')" style="background: #c62828; width: auto; padding: 6px 12px; font-size: 12px; border: 1px solid #ff5252; white-space: nowrap; flex-shrink: 0;">🗑️ Delete All</button>`;
    }
    tabsHtml += '</div>';

    let imagesHtml = '<div class="gallery-grid">';
    
    if (images.length === 0) {
            imagesHtml += '<p style="grid-column: 1/-1; text-align:center; color:#666; margin-top: 20px;">No images in this folder.</p>';
    } else {
        images.forEach((img, index) => {
            const src = `/api/gallery/image/${encodeURIComponent(currentGalleryTab)}/${encodeURIComponent(img)}?t=${galleryCacheBuster}`;
            imagesHtml += `
                <div class="gallery-item">
                    <img src="${src}" loading="lazy" onclick="openLightbox('${currentGalleryTab}', ${index})">
                    <div class="caption">${img}</div>
                    <button onclick="editGalleryImage('${currentGalleryTab}', '${img}')" style="position:absolute; top:5px; right:5px; width:auto; padding:4px 8px; font-size:12px; background:rgba(0,0,0,0.7); border:1px solid #fff; cursor:pointer; color:white;">✏️</button>
                    <button onclick="deleteGalleryImage('${currentGalleryTab}', '${img}')" style="position:absolute; top:5px; left:5px; width:auto; padding:4px 8px; font-size:12px; background:rgba(198, 40, 40, 0.7); border:1px solid #fff; cursor:pointer; color:white;">🗑️</button>
                </div>`;
        });
    }
    imagesHtml += '</div>';
    
    container.innerHTML = tabsHtml + imagesHtml;
}

function switchGalleryTab(folder) {
    currentGalleryTab = folder;
    renderGalleryUI();
}

async function loadGallery() {
    const container = document.getElementById('gallery-content');
    
    try {
        const resp = await fetch('/api/gallery/list');
        const data = await resp.json();
        loadedGalleryData = data;
        const visibleFolders = Object.keys(data).filter(f => !f.startsWith("LayoutPreview: "));
        
        if (visibleFolders.length === 0) {
            container.innerHTML = '<p style="color:#888; text-align:center; margin-top:50px;">No generated images found.</p>';
            return;
        }

        // Default tab selection
        if (!currentGalleryTab || !data[currentGalleryTab] || currentGalleryTab.startsWith("LayoutPreview: ")) {
            const folders = visibleFolders.sort();
            if (data["Editor (Unsorted)"]) currentGalleryTab = "Editor (Unsorted)";
            else currentGalleryTab = folders[0];
        }

        renderGalleryUI();
    } catch (e) {
        console.error(e);
        container.innerHTML = '<p style="color:red; text-align:center;">Error loading gallery.</p>';
    }
}

function saveImage() { 
    const l = document.createElement('a'); 
    
    const overlay = canvas.getObjects().find(o => o.dataTag === 'guide_overlay');
    const wasVisible = overlay ? overlay.visible : false;
    if (overlay) overlay.visible = false;

    l.href = canvas.toDataURL({ format: 'jpeg', quality: 0.95 }); 
    
    if (overlay) overlay.visible = wasVisible;

    let fname = 'tv-background.jpg';
    if (lastFetchedData && lastFetchedData.title) {
        const safeTitle = lastFetchedData.title.replace(/[^a-z0-9\s\.\-_]/gi, '').trim();
        const parts = [safeTitle];
        if(lastFetchedData.year && lastFetchedData.year !== 'N/A') parts.push(lastFetchedData.year);
        if(lastFetchedData.imdb_id) parts.push(lastFetchedData.imdb_id);
        fname = parts.join(' - ') + '.jpg';
    }
    l.download = fname; 
    l.click(); 
}

async function saveToGallery() {
    // Clear editing state if saving as new
    currentEditingFile = null;
    document.getElementById('btn-save-changes').style.display = 'none';
    await saveToGalleryInternal(document.getElementById('layoutName').value || "Default");
    galleryCacheBuster = Date.now();
    alert("Image saved to Gallery!");
    loadGallery();
}

async function saveToGalleryInternal(layoutName, overwriteFilename = null, targetType = 'gallery', organizeByGenre = false, useSharedMetadata = false) {
    const overlay = canvas.getObjects().find(o => o.dataTag === 'guide_overlay');
    const wasVisible = overlay ? overlay.visible : false;
    if (overlay) overlay.visible = false;

    const dataURL = canvas.toDataURL({ format: 'jpeg', quality: 0.95 });
    
    if (overlay) overlay.visible = wasVisible;

    const json = canvas.toJSON(['dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 'autoBackgroundColor', 'textureId', 'textureScale', 'textureRotation', 'textureOpacity']);
    
    // Save custom effects settings to ensure exact restoration
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
        textContentAlignment: document.getElementById('textContentAlignSelect').value,
        genreLimit: document.getElementById('genreLimitSlider').value,
        overlayId: document.getElementById('overlaySelect').value,
        margins: {
            top: document.getElementById('marginTopInput').value,
            bottom: document.getElementById('marginBottomInput').value,
            left: document.getElementById('marginLeftInput').value,
            right: document.getElementById('marginRightInput').value
        }
    };
    // Filter out fade effects so they aren't saved as static objects (we regenerate them)
    json.objects = json.objects.filter(o => o.dataTag !== 'fade_effect' && o.dataTag !== 'grid_line' && o.dataTag !== 'guide_overlay');

    const payload = { 
        image: dataURL, 
        layout_name: layoutName, 
        canvas_json: json, 
        overwrite_filename: overwriteFilename, 
        target_type: targetType,
        organize_by_genre: organizeByGenre
    };
    
    if (lastFetchedData) {
        if (typeof extractMetadata === 'function') {
            payload.metadata = extractMetadata(lastFetchedData);
        } else {
            // Fallback if extractMetadata is not available (e.g. standalone gallery page)
            payload.metadata = { 
                ...lastFetchedData,
                action_url: (lastFetchedData.source === 'Jellyfin' && lastFetchedData.id) ? "jellyfin://items/" + lastFetchedData.id : null,
            };
        }
    }
    const resp = await fetch('/api/save_image', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(payload)
    });
    return await resp.json();
}

async function editGalleryImage(folder, filename) {
    const resp = await fetch(`/api/gallery/data/${encodeURIComponent(folder)}/${encodeURIComponent(filename)}`);
    const data = await resp.json();
    
    if (data.status === 'error') {
        alert("Cannot edit this image (no layout data found). Only images generated with the new editor version can be edited.");
        return;
    }
    
    if (data.metadata) {
        lastFetchedData = data.metadata;
    }

    canvas.loadFromJSON(data, () => {
        canvas.getObjects().forEach(o => { if(o.dataTag === 'overview') o.set('objectCaching', false); });
        canvas.requestRenderAll();
        
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
        
        // Attempt to recover background color from legacy images (missing custom_effects)
        if (!data.custom_effects) {
            const fadeObj = canvas.getObjects().find(o => o.dataTag === 'fade_effect');
            if (fadeObj && fadeObj.fill && fadeObj.fill.colorStops && fadeObj.fill.colorStops.length > 0) {
                let col = fadeObj.fill.colorStops[0].color;
                if (col) {
                    if (col.startsWith('rgb')) {
                        const rgb = col.match(/\d+/g);
                        if (rgb && rgb.length >= 3) {
                            col = "#" + ((1 << 24) + (parseInt(rgb[0]) << 16) + (parseInt(rgb[1]) << 8) + parseInt(rgb[2])).toString(16).slice(1);
                        }
                    }
                    data.custom_effects = { bgColor: col };
                }
            }
        }

        // Remove ghost effects
        const ghosts = canvas.getObjects().filter(o => o.dataTag === 'fade_effect' || o.dataTag === 'grid_line');
        ghosts.forEach(g => canvas.remove(g));

        // Restore UI settings from saved data
        if (data.custom_effects) {
            const eff = data.custom_effects;
            
            // Helper to finalize UI updates after BG is ready
            const finalizeEffects = () => {
                if (typeof updateFadeControls === 'function') updateFadeControls();
            };

            if(eff.bgColor) { 
                document.getElementById('bgColor').value = eff.bgColor; 
                canvas.setBackgroundColor(eff.bgColor, () => { finalizeEffects(); }); 
            }
            if(eff.bgBrightness) document.getElementById('bgBrightness').value = eff.bgBrightness;
            if(eff.fadeEffect) document.getElementById('fadeEffect').value = eff.fadeEffect;
            if(eff.fadeRadius) document.getElementById('fadeRadius').value = eff.fadeRadius;
            if(eff.fadeLeft) document.getElementById('fadeLeft').value = eff.fadeLeft;
            if(eff.fadeRight) document.getElementById('fadeRight').value = eff.fadeRight;
            if(eff.fadeTop) document.getElementById('fadeTop').value = eff.fadeTop;
            if(eff.fadeBottom) document.getElementById('fadeBottom').value = eff.fadeBottom;
            if(eff.tagAlignment) document.getElementById('tagAlignSelect').value = eff.tagAlignment;
            else if(eff.centerTags !== undefined) document.getElementById('tagAlignSelect').value = eff.centerTags ? 'center' : 'left';
            if(eff.textContentAlignment) document.getElementById('textContentAlignSelect').value = eff.textContentAlignment;
            if(eff.limitGenres !== undefined) {
                const val = eff.limitGenres ? 2 : 6;
                document.getElementById('genreLimitSlider').value = val;
                document.getElementById('genreLimitVal').innerText = (val == 6) ? "Max" : val;
            }
            if(eff.genreLimit !== undefined) {
                document.getElementById('genreLimitSlider').value = eff.genreLimit;
                document.getElementById('genreLimitVal').innerText = (eff.genreLimit == 6) ? "Max" : eff.genreLimit;
            }
            
            // If no bgColor was set, we must call finalize manually here, otherwise it happens in callback
            if (!eff.bgColor) finalizeEffects();
        } else {
            if (typeof updateFades === 'function') updateFades();
        }

        closeLightbox();
        openTab({currentTarget: document.querySelector('.tab-link')}, 'editor-tab');
        
        currentEditingFile = { folder: folder, filename: filename };
        
        // Toggle UI for Editing Mode
        document.getElementById('btn-save-changes').style.display = 'block';
        document.getElementById('btn-save-layout').style.display = 'none';
        document.getElementById('layoutNameContainer').style.display = 'none';

        // Lock UI
        document.querySelectorAll('.tab-link').forEach(el => { el.style.pointerEvents = 'none'; el.style.opacity = '0.5'; });
        ['btn-shuffle', 'btn-save-gallery', 'btn-save-layout', 'btn-load-layout', 'btn-start-batch'].forEach(id => {
            const btn = document.getElementById(id);
            if(btn) btn.disabled = true;
        });
        
        if (folder.startsWith("Layout: ")) {
            document.getElementById('layoutName').value = folder.replace("Layout: ", "");
        }
    });
}

async function saveEditedImage() {
    if (!currentEditingFile) return;
    
    const saveBtn = document.getElementById('btn-save-changes');
    const originalText = saveBtn.innerText;
    saveBtn.disabled = true;
    saveBtn.innerText = "Saving...";

    const layoutName = document.getElementById('layoutName').value || "Default";
    let overwrite = currentEditingFile.filename;
    
    await saveToGalleryInternal(layoutName, overwrite);
    galleryCacheBuster = Date.now();
    
    if (currentEditingFile.folder) {
        currentGalleryTab = currentEditingFile.folder;
    }
    await loadGallery();

    // Unlock UI
    document.querySelectorAll('.tab-link').forEach(el => { el.style.pointerEvents = 'auto'; el.style.opacity = '1'; });
    ['btn-shuffle', 'btn-save-gallery', 'btn-save-layout', 'btn-load-layout', 'btn-start-batch'].forEach(id => {
        const btn = document.getElementById(id);
        if(btn) btn.disabled = false;
    });
    
    const galleryTabBtn = document.querySelector(".tab-link[onclick*='gallery-tab']");
    if (galleryTabBtn && typeof openTab === 'function') {
        openTab({currentTarget: galleryTabBtn}, 'gallery-tab');
    }
    
    currentEditingFile = null;
    saveBtn.style.display = 'none';
    document.getElementById('btn-save-layout').style.display = 'block';
    document.getElementById('layoutNameContainer').style.display = 'block';
    saveBtn.disabled = false;
    saveBtn.innerText = originalText;
}

async function deleteAllGalleryImages(folder) {
    if (!confirm(`⚠️ DANGER ⚠️\n\nAre you sure you want to delete ALL images in "${folder}"?\n\nThis action cannot be undone!`)) {
        return;
    }
    
    const resp = await fetch('/api/gallery/delete_all', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ folder: folder })
    });
    
    if (resp.ok) {
        loadGallery();
    } else {
        const err = await resp.json();
        alert("Error: " + (err.message || "Unknown error"));
    }
}

async function deleteGalleryImage(folder, filename) {
    if (!confirm(`Delete image "${filename}"?`)) return;
    
    const resp = await fetch('/api/gallery/delete', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ folder: folder, filename: filename })
    });
    
    if (resp.ok) {
        loadGallery();
    } else {
        const err = await resp.json();
        alert("Error: " + (err.message || "Unknown error"));
    }
}

async function loadLayoutsList() {
    const container = document.getElementById('layouts-content');
    const resp = await fetch('/api/layouts/list');
    const layouts = await resp.json();
    
    const galResp = await fetch('/api/gallery/list');
    loadedGalleryData = await galResp.json();

    let html = '';
    layouts.forEach(l => {
        const key = `LayoutPreview: ${l}`;
        let previews = '';
        
        // Layout Thumbnail URL (with timestamp to force refresh)
        const thumbSrc = `/api/layouts/preview/${encodeURIComponent(l)}?t=${new Date().getTime()}`;

        if (loadedGalleryData[key]) {
            loadedGalleryData[key].slice(0, 10).forEach((img, index) => {
                const src = `/api/gallery/image/${encodeURIComponent(key)}/${encodeURIComponent(img)}?t=${galleryCacheBuster}`;
                previews += `<img src="${src}" onclick="openLightbox('${key}', ${index})">`;
            });
        } else { previews = '<span style="font-size:11px; color:#666;">No generated images yet.</span>'; }

        html += `<div class="layout-card">
            <div class="layout-header">
                <div style="display:flex; align-items:center; gap:10px;">
                    <img src="${thumbSrc}" style="height:40px; width:71px; object-fit:cover; border-radius:4px; border:1px solid #555;" onerror="this.style.display='none'">
                    <h3 style="margin:0; color:#fff; font-size:16px;">${l}</h3>
                </div>
                <div>
                    <button onclick="loadLayout('${l}')" style="width:auto; padding:5px 15px; font-size:12px;">📂 Load</button>
                    <button onclick="deleteLayout('${l}')" style="width:auto; padding:5px 15px; font-size:12px; background-color: #c62828; margin-left: 5px;">🗑️ Delete</button>
                </div>
            </div>
            <div class="layout-previews">${previews}</div>
        </div>`;
    });
    container.innerHTML = html || '<p style="text-align:center; color:#666;">No saved layouts.</p>';
}

async function deleteLayout(name) {
    if (!confirm(`Are you sure you want to delete the layout "${name}"? Generated images in the gallery will be kept.`)) {
        return;
    }
    const resp = await fetch(`/api/layouts/delete/${name}`, { method: 'POST' });
    if (resp.ok) {
        loadLayoutsList();
        loadGallery();
    } else {
        alert("Error deleting layout.");
    }
}
