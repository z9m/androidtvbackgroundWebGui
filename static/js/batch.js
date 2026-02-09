let batchTimer = null;

function toggleBatchInputs() {
    const mode = document.getElementById('batchMode').value;
    const filterMode = document.getElementById('batchFilterMode').value;
    
    document.getElementById('batchRandomSettings').style.display = (mode === 'random') ? 'block' : 'none';
    document.getElementById('batchFilterSettings').style.display = (mode === 'library') ? 'block' : 'none';
    
    // Filter Inputs
    document.getElementById('filterInputYear').style.display = (mode === 'library' && filterMode === 'year') ? 'block' : 'none';
    document.getElementById('filterInputGenre').style.display = (mode === 'library' && filterMode === 'genre') ? 'block' : 'none';
    document.getElementById('filterInputRating').style.display = (mode === 'library' && (filterMode === 'rating' || filterMode === 'imdb')) ? 'block' : 'none';
    document.getElementById('filterInputOfficialRating').style.display = (mode === 'library' && filterMode === 'official_rating') ? 'block' : 'none';
    document.getElementById('filterInputCustom').style.display = (mode === 'library' && filterMode === 'custom') ? 'block' : 'none';
    
    // Update label for count based on context
    const countLabel = document.querySelector('label[for="batchCount"]');
    if (mode === 'library') countLabel.innerText = "Limit (Max Images)";
    else countLabel.innerText = "Number of Images";

    // Auto-Run Visibility
    document.getElementById('autoRunSettings').style.display = document.getElementById('batchAutoRun').checked ? 'block' : 'none';
}

async function loadBatchLayouts() {
    const select = document.getElementById('batchLayoutSelect');
    const resp = await fetch('/api/layouts/list');
    const layouts = await resp.json();
    select.innerHTML = '';
    layouts.forEach(l => {
        const opt = document.createElement('option');
        opt.value = l;
        opt.innerText = l;
        select.appendChild(opt);
    });
    // Select current layout if possible
    const current = document.getElementById('layoutName').value;
    if (layouts.includes(current)) select.value = current;
}

function logBatch(msg) {
    const log = document.getElementById('batchLog');
    const time = new Date().toLocaleTimeString();
    log.innerText += `[${time}] ${msg}\n`;
    log.scrollTop = log.scrollHeight;
}

function stopBatchProcess() {
    isBatchRunning = false;
    if (batchTimer) clearTimeout(batchTimer);
    logBatch("Stopping batch process...");
    document.getElementById('btn-start-batch').style.display = 'block';
    document.getElementById('btn-stop-batch').style.display = 'none';
    if (typeof setUIInteraction === 'function') setUIInteraction(true);
}

async function startBatchProcess() {
    if (isBatchRunning) return;
    if (batchTimer) clearTimeout(batchTimer);
    isBatchRunning = true;
    
    const layoutName = document.getElementById('batchLayoutSelect').value;
    const mode = document.getElementById('batchMode').value;
    const filterMode = document.getElementById('batchFilterMode').value;
    const count = parseInt(document.getElementById('batchCount').value);
    const delay = 1500; // Fixed generous delay for stability
    const overwrite = document.getElementById('batchOverwrite').checked;
    const sortGenre = false;
    const dryRun = document.getElementById('batchDryRun').checked;
    
    document.getElementById('btn-start-batch').style.display = 'none';
    document.getElementById('btn-stop-batch').style.display = 'block';
    
    const logDiv = document.getElementById('batchLog');
    if (logDiv) {
        logDiv.innerText = "";
        logDiv.style.maxHeight = '300px';
        logDiv.style.overflowY = 'auto';
    }
    
    if (typeof setUIInteraction === 'function') {
        setUIInteraction(false);
        document.getElementById('btn-stop-batch').disabled = false;
    }
    
    logBatch(`Starting batch for layout: "${layoutName}"`);
    
    if (dryRun) {
        logBatch(`[DRY RUN] Mode active. No images will be generated.`);
    }

    let itemsToProcess = [];
    if (mode === 'library') {
        let qs = `?mode=${filterMode}`;
        if (filterMode === 'year') qs += `&val=${encodeURIComponent(document.getElementById('batchFilterYear').value)}`;
        if (filterMode === 'genre') qs += `&val=${encodeURIComponent(document.getElementById('batchFilterGenre').value)}`;
        if (filterMode === 'rating') qs += `&val=${encodeURIComponent(document.getElementById('batchFilterRating').value)}`;
        if (filterMode === 'official_rating') qs += `&val=${encodeURIComponent(document.getElementById('batchFilterOfficialRating').value)}`;
        if (filterMode === 'custom') {
            qs += `&min_year=${encodeURIComponent(document.getElementById('batchFilterMinYear').value)}`;
            qs += `&max_year=${encodeURIComponent(document.getElementById('batchFilterMaxYear').value)}`;
            qs += `&min_rating=${encodeURIComponent(document.getElementById('batchFilterMinRating').value)}`;
            qs += `&genre=${encodeURIComponent(document.getElementById('batchFilterCustomGenre').value)}`;
        }

        logBatch(`Fetching library list (Filter: ${filterMode})...`);
        const resp = await fetch('/api/media/list' + qs);
        const list = await resp.json();
        if (list.error) { logBatch("Error: " + list.error); stopBatchProcess(); return; }
        
        itemsToProcess = list.map(i => ({id: i.Id, name: i.Name}));
        logBatch(`Found ${itemsToProcess.length} matching items.`);
        
        if (itemsToProcess.length === 0) {
            logBatch("No items found. Stopping.");
            stopBatchProcess();
            return;
        }
    } else {
        logBatch(`Target: ${count} random images`);
        itemsToProcess = Array(count).fill(null);
    }

    // 1. Load the selected layout first
    if (!dryRun) {
        await loadLayout(layoutName, true); // This loads it onto the main canvas (Silent Mode)
    }
    logBatch("Layout loaded successfully.");

    // --- FIX: Capture initial layout state ---
    let initialState = null;
    if (!dryRun && typeof canvas !== 'undefined') {
        initialState = canvas.toJSON(['dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 'autoBackgroundColor', 'textureId', 'textureScale', 'textureRotation', 'textureOpacity', 'snapToObjects', 'logoAutoFix']);
    }

    const total = itemsToProcess.length;
    for (let i = 0; i < total; i++) {
        if (!isBatchRunning) break;
        
        const progress = Math.round(((i) / total) * 100);
        document.getElementById('batchProgressBar').style.width = `${progress}%`;
        document.getElementById('batchProgressBar').innerText = `${progress}%`;

        const item = itemsToProcess[i];
        const label = item ? item.name : `Random #${i+1}`;
        
        if (dryRun) {
             logBatch(`[Dry Run] Would process: ${label}`);
             await new Promise(r => setTimeout(r, 50)); // Tiny delay for visual effect
             continue;
        }

        logBatch(`Processing (${i+1}/${total}): ${label}`);
        
        // --- FIX: Restore initial layout state ---
        // Resets object positions (e.g. Overview) to prevent layout shifts from persisting
        if (!dryRun && initialState) {
            await new Promise(resolve => {
                canvas.loadFromJSON(initialState, () => {
                    mainBg = canvas.getObjects().find(o => o.dataTag === 'background');
                    resolve();
                });
            });
        }
        
        // 1. Load data and update canvas text
        // (fetchMediaData comes from editor.js and handles the data fetching)
        await fetchMediaData(item ? item.id : null); 
        
        // --- FIX: Correct Layout (Fixes overflow issues) ---
        // Since the text content has changed, widths have changed.
        // We must manually trigger a layout recalculation before saving.
        if (typeof canvas !== 'undefined') {
            
            // A. Recalculate Textboxes (e.g. Overview) to fit container
            canvas.getObjects().forEach(obj => {
                if (obj.dataTag === 'overview' && obj.type === 'textbox') {
                    if (typeof fitTextToContainer === 'function') {
                        fitTextToContainer(obj);
                    }
                }
                // Invalidate cache to prevent artifacts
                obj.setCoords(); 
                obj.dirty = true;
            });

            // B. CRITICAL: Re-align right-aligned tags
            // This pulls tags back to the left if they grew wider.
            if (typeof updateVerticalLayout === 'function') {
                updateVerticalLayout();
            }
            
            // C. Force a clean redraw
            canvas.renderAll();
        }
        // --- FIX END ---

        // 2. Hide overlay for screenshot
        const overlay = canvas.getObjects().find(o => o.dataTag === 'guide_overlay');
        const wasVisible = overlay ? overlay.visible : false;
        if (overlay) overlay.visible = false;

        const dataURL = canvas.toDataURL({ format: 'jpeg', quality: 0.95 });
        if (overlay) overlay.visible = wasVisible;

        const json = canvas.toJSON(['dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 'autoBackgroundColor', 'textureId', 'textureScale', 'textureRotation', 'textureOpacity']);
        
        // Inject custom_effects so the saved JSON contains overlay info & blocked areas
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
            },
            logoAutoFix: document.getElementById('batchLogoAutoFix') ? document.getElementById('batchLogoAutoFix').checked : true
        };

        if (json.custom_effects.overlayId && typeof overlayProfiles !== 'undefined') {
            const profile = overlayProfiles.find(p => p.id === json.custom_effects.overlayId);
            if (profile && profile.blocked_areas) {
                json.custom_effects.blocked_areas = profile.blocked_areas;
            }
        }
        
        let metadata = {};
        if (typeof extractMetadata === 'function' && lastFetchedData) {
            metadata = extractMetadata(lastFetchedData);
        }

        const payload = { 
            image: dataURL, 
            layout_name: layoutName, 
            canvas_json: json, 
            overwrite_filename: null, 
            target_type: 'gallery',
            organize_by_genre: sortGenre,
            metadata: metadata
        };

        await fetch('/api/save_image', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        
        // Update preview image in batch tab
        document.getElementById('batchPreviewImg').src = canvas.toDataURL({ format: 'jpeg', quality: 0.5 });

        if (delay > 0) await new Promise(r => setTimeout(r, delay));
    }

    document.getElementById('batchProgressBar').style.width = `100%`;
    document.getElementById('batchProgressBar').innerText = `100%`;
    logBatch("Batch processing finished!");
    
    loadGallery();

    // Auto-Run Logic
    if (document.getElementById('batchAutoRun').checked) {
        const interval = parseInt(document.getElementById('batchInterval').value) || 60;
        logBatch(`Auto-Run enabled. Waiting ${interval} minutes for next run...`);
        // Do NOT call stopBatchProcess() here to keep the "Stop" button active
        batchTimer = setTimeout(startBatchProcess, interval * 60 * 1000);
    } else {
        stopBatchProcess();
    }
}
