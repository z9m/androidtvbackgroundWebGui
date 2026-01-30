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
    logBatch("Stopping batch process...");
    document.getElementById('btn-start-batch').style.display = 'block';
    document.getElementById('btn-stop-batch').style.display = 'none';
    if (typeof setUIInteraction === 'function') setUIInteraction(true);
}

async function startBatchProcess() {
    if (isBatchRunning) return;
    isBatchRunning = true;
    
    const layoutName = document.getElementById('batchLayoutSelect').value;
    const mode = document.getElementById('batchMode').value;
    const filterMode = document.getElementById('batchFilterMode').value;
    const count = parseInt(document.getElementById('batchCount').value);
    const delay = 1500; // Fixed generous delay for stability
    const overwrite = document.getElementById('batchOverwrite').checked;
    const sortGenre = document.getElementById('batchSortGenre').checked;
    const dryRun = document.getElementById('batchDryRun').checked;
    
    document.getElementById('btn-start-batch').style.display = 'none';
    document.getElementById('btn-stop-batch').style.display = 'block';
    document.getElementById('batchLog').innerText = "";
    
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
        
        await fetchMediaData(item ? item.id : null); 
        await saveToGalleryInternal(layoutName, overwrite ? null : null, 'gallery', sortGenre);
        
        // Update preview image in batch tab
        document.getElementById('batchPreviewImg').src = canvas.toDataURL({ format: 'jpeg', quality: 0.5 });

        if (delay > 0) await new Promise(r => setTimeout(r, delay));
    }

    document.getElementById('batchProgressBar').style.width = `100%`;
    document.getElementById('batchProgressBar').innerText = `100%`;
    logBatch("Batch processing finished!");
    stopBatchProcess();
    loadGallery();
}
