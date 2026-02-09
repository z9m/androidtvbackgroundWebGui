const fs = require('fs');
const path = require('path');
const { fabric } = require('fabric');
const canvasModule = require('canvas');

// Explicitly link fabric to node-canvas
fabric.nodeCanvas = canvasModule;

// --- ARGS ---
const payloadPath = process.argv[2];
const outputPath = process.argv[3];

if (!payloadPath || !outputPath) process.exit(1);

// --- ERROR HANDLERS ---
process.on('unhandledRejection', (reason, p) => {
    console.error('FATAL: Unhandled Rejection at:', p, 'reason:', reason);
    process.exit(1);
});
process.on('uncaughtException', (err) => {
    console.error('FATAL: Uncaught Exception:', err);
    process.exit(1);
});

// --- FONTS ---
const fontsDir = path.join(__dirname, 'fonts');

if (fs.existsSync(fontsDir)) {
    const files = fs.readdirSync(fontsDir);
    // Silent font registration
    files.forEach(file => {
        const ext = path.extname(file).toLowerCase();
        if (ext === '.ttf' || ext === '.otf') {
            const fullPath = path.join(fontsDir, file).replace(/\\/g, '/');
            try {
                let familyName = path.basename(file, ext).split('-')[0].replace(/[^a-zA-Z0-9]/g, '');
                if (!familyName) familyName = "CustomFont";
                canvasModule.registerFont(fullPath, { family: familyName });
            } catch (fontErr) {
                // Silent catch
            }
        }
    });
}

// --- HELPERS ---

function getCertificationFilename(rating) {
    if (!rating) return null;
    let r = String(rating).toUpperCase().replace(/[\s-]/g, ''); // Remove spaces/dashes

    // FSK (German)
    if (r === 'FSK0' || r === '0' || r === 'DE0' || r === 'AB0' || r === 'AB0JAHREN') return 'FSK_0.svg';
    if (r === 'FSK6' || r === '6' || r === 'DE6' || r === 'AB6' || r === 'AB6JAHREN') return 'FSK_6.svg';
    if (r === 'FSK12' || r === '12' || r === 'DE12' || r === 'AB12' || r === 'AB12JAHREN') return 'FSK_12.svg';
    if (r === 'FSK16' || r === '16' || r === 'DE16' || r === 'AB16' || r === 'AB16JAHREN') return 'FSK_16.svg';
    if (r === 'FSK18' || r === '18' || r === 'DE18' || r === 'AB18' || r === 'AB18JAHREN') return 'FSK_18.svg';

    // MPAA (US) - Assuming these files exist in certification folder, otherwise fallback or ignore
    // Note: You might need to add these SVGs to your /app/certification/ folder if they are missing
    // For now, we map what we know exists or return null if file logic handles check
    /*
    if (r === 'G' || r === 'USG') return 'RATED_G.svg';
    if (r === 'PG' || r === 'USPG') return 'RATED_PG.svg';
    if (r === 'PG13' || r === 'USPG13') return 'RATED_PG-13.svg';
    if (r === 'R' || r === 'USR') return 'RATED_R.svg';
    if (r === 'NC17' || r === 'USNC17') return 'RATED_NC-17.svg';
    */
    
    return null;
}

function fitTextToContainer(canvas, textbox) {
    if (!canvas || !textbox) return;
    const textSource = textbox.fullMediaText || textbox.text || "";
    
    textbox.set('text', textSource);
    
    // Helper to check height
    const getHeight = () => {
        if (typeof textbox.initDimensions === 'function') {
            textbox.initDimensions();
        } else if (typeof textbox._initDimensions === 'function') {
            textbox._initDimensions();
        }
        return textbox.height * textbox.scaleY;
    };

    const limit = (textbox.fixedHeight || textbox.height) - 5;

    if (getHeight() > limit) {
        let words = textSource.split(' ');
        
        if (getHeight() > limit * 1.5) {
            const ratio = limit / getHeight();
            words = words.slice(0, Math.floor(words.length * ratio));
            textbox.set('text', words.join(' ') + '...');
        }

        while (getHeight() > limit && words.length > 0) { 
            words.pop(); 
            textbox.set('text', words.join(' ') + '...'); 
        }
    }
}

function hexToRgba(hex, a) {
    let r = 0, g = 0, b = 0;
    if (!hex) return `rgba(0,0,0,${a === 0 ? 0.005 : a})`;
    if (hex.length === 4) {
        r = parseInt(hex[1] + hex[1], 16);
        g = parseInt(hex[2] + hex[2], 16);
        b = parseInt(hex[3] + hex[3], 16);
    } else if (hex.length === 7) {
        r = parseInt(hex.slice(1, 3), 16);
        g = parseInt(hex.slice(3, 5), 16);
        b = parseInt(hex.slice(5, 7), 16);
    }
    return `rgba(${r}, ${g}, ${b}, ${a === 0 ? 0.005 : a})`;
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

function checkCollision(obj, blockedAreas, scaleFactor = 1) {
    if (!blockedAreas || blockedAreas.length === 0) return false;
    const b = obj.getBoundingRect();
    return blockedAreas.some(area => {
        const aLeft = area.left * scaleFactor;
        const aTop = area.top * scaleFactor;
        const aWidth = area.width * scaleFactor;
        const aHeight = area.height * scaleFactor;

        return (b.left < aLeft + aWidth &&
                b.left + b.width > aLeft &&
                b.top < aTop + aHeight &&
                b.top + b.height > aTop);
    });
}

function createFadeRect(mainBg, type, size, bgColor) {
    const b = 2;
    const wImg = mainBg.width * mainBg.scaleX;
    const hImg = mainBg.height * mainBg.scaleY;
    
    let bgLeft = mainBg.left;
    let bgTop = mainBg.top;
    if (mainBg.originX === 'center') bgLeft -= wImg / 2;
    if (mainBg.originY === 'center') bgTop -= hImg / 2;

    let w, h, x, y, c;
    if (type === 'left') { w = parseInt(size) + b; h = hImg + b*2; x = bgLeft - b; y = bgTop - b; }
    else if (type === 'right') { w = parseInt(size) + b; h = hImg + b*2; x = bgLeft + wImg - size; y = bgTop - b; }
    else if (type === 'top') { w = wImg + b*2; h = parseInt(size) + b; x = bgLeft - b; y = bgTop - b; }
    else if (type === 'bottom') { w = wImg + b*2; h = parseInt(size) + b; x = bgLeft - b; y = bgTop + hImg - size; }

    if (type === 'left') c = { x1: 0, y1: 0, x2: 1, y2: 0 };
    else if (type === 'right') c = { x1: 1, y1: 0, x2: 0, y2: 0 };
    else if (type === 'top') c = { x1: 0, y1: 0, x2: 0, y2: 1 };
    else if (type === 'bottom') c = { x1: 0, y1: 1, x2: 0, y2: 0 };
    
    return new fabric.Rect({
        left: x, top: y, width: w, height: h, selectable: false, evented: false,
        fill: new fabric.Gradient({ 
            type: 'linear', 
            gradientUnits: 'percentage', 
            coords: c, 
            colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }] 
        }),
        dataTag: 'fade_effect'
    });
}

function addCornerFade(canvas, mainBg, pos, radius, bgColor) {
    const r = parseInt(radius);
    if (r <= 0) return;
    
    const w = mainBg.width * mainBg.scaleX;
    const h = mainBg.height * mainBg.scaleY;
    let bgLeft = mainBg.left;
    let bgTop = mainBg.top;
    if (mainBg.originX === 'center') bgLeft -= w / 2;
    if (mainBg.originY === 'center') bgTop -= h / 2;

    let rectLeft, rectTop, gradCx, gradCy;

    if (pos === 'bottom-left') {
        rectLeft = bgLeft; rectTop = bgTop + h - r;
        gradCx = 0; gradCy = r;
    } else if (pos === 'bottom-right') {
        rectLeft = bgLeft + w - r; rectTop = bgTop + h - r;
        gradCx = r; gradCy = r;
    } else if (pos === 'top-left') {
        rectLeft = bgLeft; rectTop = bgTop;
        gradCx = 0; gradCy = 0;
    } else if (pos === 'top-right') {
        rectLeft = bgLeft + w - r; rectTop = bgTop;
        gradCx = r; gradCy = 0;
    }

    const grad = new fabric.Gradient({
        type: 'radial',
        coords: { r1: 0, r2: r, x1: gradCx, y1: gradCy, x2: gradCx, y2: gradCy },
        colorStops: [{ offset: 0, color: bgColor }, { offset: 1, color: hexToRgba(bgColor, 0) }]
    });

    const rect = new fabric.Rect({ left: rectLeft, top: rectTop, width: r, height: r, fill: grad, selectable: false, evented: false, dataTag: 'fade_effect' });
    canvas.add(rect);
    rect.moveTo(canvas.getObjects().indexOf(mainBg) + 1);
}

function addVignette(canvas, mainBg, radius, bgColor) {
    const r = parseInt(radius);
    if (r <= 0) return;
    const padding = 10;
    const w = Math.ceil(mainBg.width * mainBg.scaleX) + padding;
    const h = Math.ceil(mainBg.height * mainBg.scaleY) + padding;
    
    let bgLeft = mainBg.left;
    let bgTop = mainBg.top;
    if (mainBg.originX === 'center') bgLeft -= (mainBg.width * mainBg.scaleX) / 2;
    if (mainBg.originY === 'center') bgTop -= (mainBg.height * mainBg.scaleY) / 2;
    
    const grad = new fabric.Gradient({
        type: 'radial',
        coords: { r1: 0, r2: r, x1: w/2, y1: h/2, x2: w/2, y2: h/2 },
        colorStops: [{ offset: 0, color: hexToRgba(bgColor, 0) }, { offset: 1, color: bgColor }]
    });

    const rect = new fabric.Rect({ left: bgLeft - (padding/2), top: bgTop - (padding/2), width: w, height: h, fill: grad, selectable: false, evented: false, dataTag: 'fade_effect' });
    canvas.add(rect);
    rect.moveTo(canvas.getObjects().indexOf(mainBg) + 1);
}

// Helper to reset logo to original state (prevents wandering/shrinking persistence)
function resetAnchorState(anchor, originalState) {
    if (!anchor || !originalState) return;
    anchor.scaleX = originalState.scaleX;
    anchor.scaleY = originalState.scaleY;
    anchor.left = originalState.left;
    anchor.top = originalState.top;
    anchor.setCoords();
}

function updateVerticalLayout(canvas, settings, activeBlockedAreas = []) {
    if (!canvas) return;
    
    const padding = 20;
    const hPadding = 20;
    const rowThreshold = 30;
    
    const marginTop = parseInt(settings.margins?.top || 50);
    const marginBottom = parseInt(settings.margins?.bottom || 50);
    const marginLeft = parseInt(settings.margins?.left || 50);
    const marginRight = parseInt(settings.margins?.right || 50);
    
    const scaleFactor = (canvas.width > 2000) ? 2 : 1;

    const anchor = canvas.getObjects().find(o => o.dataTag === 'title');
    if (!anchor) return;

    // Reset anchor to original layout state if available (prevents wandering)
    if (anchor._originalState) {
        resetAnchorState(anchor, anchor._originalState);
    }

    const alignment = settings.tagAlignment || 'left';

    // Ensure anchor (Logo/Title) respects screen margin
    if (anchor.left < marginLeft) anchor.set('left', marginLeft);
    if (anchor.left + (anchor.width * anchor.scaleX) > canvas.width - marginRight) {
        anchor.set('left', Math.max(marginLeft, canvas.width - marginRight - (anchor.width * anchor.scaleX)));
    }
    
    // Vertical constraint for anchor (Top & Bottom)
    if (anchor.top < marginTop) anchor.set('top', marginTop);
    if (anchor.top + (anchor.height * anchor.scaleY) > canvas.height - marginBottom) {
        anchor.set('top', Math.max(marginTop, canvas.height - marginBottom - (anchor.height * anchor.scaleY)));
    }
    anchor.setCoords();

    // 2.5. Auto-Scale Anchor to fit in vertical gaps between blocked areas
    if (activeBlockedAreas.length > 0) {
        const anchorH = anchor.height * anchor.scaleY;
        const anchorCenterY = anchor.top + (anchorH / 2);
        const anchorLeft = anchor.left;
        const anchorRight = anchor.left + (anchor.width * anchor.scaleX);
        
        const obstacles = [];
        obstacles.push({ top: -Infinity, bottom: marginTop });
        obstacles.push({ top: canvas.height - marginBottom, bottom: Infinity });
        
        activeBlockedAreas.forEach(area => {
            const aLeft = area.left * scaleFactor;
            const aWidth = area.width * scaleFactor;
            const aRight = aLeft + aWidth;
            
            if (aLeft < anchorRight && aRight > anchorLeft) {
                const aTop = area.top * scaleFactor;
                const aHeight = area.height * scaleFactor;
                obstacles.push({ top: aTop, bottom: aTop + aHeight });
            }
        });
        
        obstacles.sort((a, b) => a.top - b.top);
        const merged = [];
        if (obstacles.length > 0) {
            let curr = obstacles[0];
            for (let i = 1; i < obstacles.length; i++) {
                if (obstacles[i].top < curr.bottom) {
                    curr.bottom = Math.max(curr.bottom, obstacles[i].bottom);
                } else {
                    merged.push(curr);
                    curr = obstacles[i];
                }
            }
            merged.push(curr);
        }
        
        const gaps = [];
        for (let i = 0; i < merged.length - 1; i++) {
            const top = merged[i].bottom;
            const bottom = merged[i+1].top;
            if (bottom > top) {
                gaps.push({ top, bottom, height: bottom - top });
            }
        }
        
        let bestGap = gaps.find(g => anchorCenterY >= g.top && anchorCenterY <= g.bottom);
        
        if (!bestGap && gaps.length > 0) {
            bestGap = gaps.reduce((prev, curr) => {
                const prevDist = Math.min(Math.abs(anchorCenterY - prev.top), Math.abs(anchorCenterY - prev.bottom));
                const currDist = Math.min(Math.abs(anchorCenterY - curr.top), Math.abs(anchorCenterY - curr.bottom));
                return (currDist < prevDist) ? curr : prev;
            });
        }
        
        if (bestGap) {
            const currentH = anchor.height * anchor.scaleY;
            const maxH = Math.max(20, bestGap.height - 10);
            
            let targetH = currentH;
            // In render task, we assume current size is preferred size as it comes from saved layout
            
            const finalH = Math.min(targetH, maxH);
            
            if (Math.abs(finalH - currentH) > 1) {
                const oldLeft = anchor.left;
                const oldWidth = anchor.width * anchor.scaleX;
                const oldRight = oldLeft + oldWidth;
                const oldCenterX = oldLeft + (oldWidth / 2);

                anchor.scaleToHeight(finalH);
                const newWidth = anchor.width * anchor.scaleX;
                
                if (alignment === 'right') {
                    anchor.set('left', oldRight - newWidth);
                } else if (alignment === 'left') {
                    anchor.set('left', oldLeft);
                } else {
                    anchor.set('left', oldCenterX - (newWidth / 2));
                }

                anchor.set('top', bestGap.top + (bestGap.height - finalH) / 2);
                anchor.setCoords();
            }
        }
    }

    // Anchor Blocked Area Constraints (Push out of blocked areas)
    let safety = 0;
    while (checkCollision(anchor, activeBlockedAreas, scaleFactor) && safety < 10) {
        const b = anchor.getBoundingRect();
        const area = activeBlockedAreas.find(a => {
            const aLeft = a.left * scaleFactor;
            const aTop = a.top * scaleFactor;
            const aWidth = a.width * scaleFactor;
            const aHeight = a.height * scaleFactor;
            return (b.left < aLeft + aWidth && b.left + b.width > aLeft &&
                    b.top < aTop + aHeight && b.top + b.height > aTop);
        });

        if (area) {
            const aLeft = area.left * scaleFactor;
            const aTop = area.top * scaleFactor;
            const aWidth = area.width * scaleFactor;
            const aHeight = area.height * scaleFactor;

            const overL = (b.left + b.width) - aLeft;
            const overR = (aLeft + aWidth) - b.left;
            const overT = (b.top + b.height) - aTop;
            const overB = (aTop + aHeight) - b.top;
            
            const min = Math.min(overL, overR, overT, overB);
            
            if (min === overL) anchor.left -= overL;
            else if (min === overR) anchor.left += overR;
            else if (min === overT) anchor.top -= overT;
            else if (min === overB) anchor.top += overB;
            
            anchor.setCoords();
        }
        safety++;
    }
    anchor.setCoords();

    let current_y = anchor.top + (anchor.height * anchor.scaleY) + padding;
    
    const elements = canvas.getObjects().filter(o => {
        if (o.dataTag === 'background') return false;
        if (o.dataTag === 'title') return false;
        if (o.dataTag === 'guide') return false;
        if (o.dataTag === 'fade_effect') return false;
        if (o.dataTag === 'grid_line') return false;
        if (o.dataTag === 'guide_overlay') return false;
        if (!o.dataTag) return false;
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
                w += (el.width * el.scaleX) + (pad * 2);
                if (i < visibleEls.length - 1) w += hPadding;
            });
            if (w > maxRowWidth) maxRowWidth = w;
        });

        const anchorW = anchor.width * anchor.scaleX;
        let shift = 0;

        if (alignment === 'center') {
            const idealStart = anchor.left + (anchorW - maxRowWidth) / 2;
            if (idealStart < marginLeft) shift = marginLeft - idealStart;
            else if (idealStart + maxRowWidth > canvas.width - marginRight) shift = (canvas.width - marginRight - maxRowWidth) - idealStart;
        } else if (alignment === 'right') {
            const idealStart = (anchor.left + anchorW) - maxRowWidth;
            if (idealStart < marginLeft) shift = marginLeft - idealStart;
        } else { // left
            const idealStart = anchor.left;
            if (idealStart + maxRowWidth > canvas.width - marginRight) shift = (canvas.width - marginRight - maxRowWidth) - idealStart;
        }

        if (shift !== 0) { anchor.set('left', anchor.left + shift); anchor.setCoords(); }
    }

    const anchorLeft = anchor.left;
    const anchorWidth = anchor.width * anchor.scaleX;

    rows.forEach(row => {
        row.sort((a, b) => a.left - b.left);
        
        let totalRowWidth = 0;
        const visibleEls = row.filter(e => e.visible);
        visibleEls.forEach((el, index) => {
            el.setCoords();
            const pad = el.padding || 0;
            totalRowWidth += (el.width * el.scaleX) + (pad * 2);
            if (index < visibleEls.length - 1) totalRowWidth += hPadding;
        });

        let current_x;
        if (alignment === 'center') {
            current_x = anchorLeft + (anchorWidth - totalRowWidth) / 2;
        } else if (alignment === 'right') {
            current_x = (anchorLeft + anchorWidth) - totalRowWidth;
            const lastEl = visibleEls[visibleEls.length - 1];
            if (lastEl) current_x += (lastEl.padding || 0);
        } else {
            current_x = anchorLeft;
            const firstEl = visibleEls[0];
            if (firstEl) current_x -= (firstEl.padding || 0);
        }

        if (current_x < marginLeft) current_x = marginLeft;
        if (current_x + totalRowWidth > canvas.width - marginRight) {
            current_x = Math.max(marginLeft, canvas.width - marginRight - totalRowWidth);
        }

        const maxRowHeight = Math.max(...row.map(el => el.visible ? (el.height * el.scaleY) + ((el.padding||0)*2) : 0));
        
        row.forEach(el => {
            const pad = el.padding || 0;
            el.set({ top: current_y + pad, left: current_x + pad });
            el.setCoords();
            
            const startX = current_x;
            let isColliding = checkCollision(el, activeBlockedAreas, scaleFactor);
            
            while (isColliding && current_x < canvas.width - marginRight) {
                current_x += 10;
                el.set({ left: current_x + pad });
                el.setCoords();
                isColliding = checkCollision(el, activeBlockedAreas, scaleFactor);
            }
            if (isColliding) {
                current_x = startX;
                el.set({ left: current_x + pad });
                el.setCoords();
            }

            if (el.visible) {
                current_x += (el.width * el.scaleX) + (pad * 2) + hPadding;
            } else {
                current_x += 0.1;
            }
        });

        const lastEl = row[row.length - 1];
        if (lastEl && lastEl.visible) {
            const rightEdge = lastEl.left + (lastEl.width * lastEl.scaleX);
            const maxRight = canvas.width - marginRight;
            if (rightEdge > maxRight) {
                const overflow = rightEdge - maxRight;
                row.forEach(el => {
                    el.left -= overflow;
                    el.setCoords();
                });
            }
        }
        
        if (maxRowHeight > 0) {
            current_y += maxRowHeight + padding;
        }
    });

    // Check for bottom overflow and shift up if necessary
    const contentBottom = current_y - padding;
    const maxBottom = canvas.height - marginBottom;

    // Check collision with blocked areas for all placed elements to trigger vertical shift
    let maxBlockedShift = 0;
    const allElements = [anchor];
    rows.forEach(row => row.forEach(el => { if(el.visible) allElements.push(el); }));

    // Ensure coords are fresh for collision detection
    allElements.forEach(el => {
        el.setCoords();
        const b = el.getBoundingRect();
        activeBlockedAreas.forEach(area => {
            const aLeft = area.left * scaleFactor;
            const aTop = area.top * scaleFactor;
            const aWidth = area.width * scaleFactor;
            const aHeight = area.height * scaleFactor;
            
            if (b.left < aLeft + aWidth && b.left + b.width > aLeft &&
                b.top < aTop + aHeight && b.top + b.height > aTop) {
                const overlap = (b.top + b.height) - aTop;
                if (overlap > 0 && overlap > maxBlockedShift) maxBlockedShift = overlap;
            }
        });
    });

    const marginShift = Math.max(0, contentBottom - maxBottom);
    const totalShift = Math.max(marginShift, maxBlockedShift);
    
    if (totalShift > 0) {
        // Calculate available space above considering margins AND blocked areas
        let limitTop = marginTop;
        
        const anchorLeft = anchor.left;
        const anchorRight = anchor.left + (anchor.width * anchor.scaleX);

        activeBlockedAreas.forEach(area => {
            const aLeft = area.left * scaleFactor;
            const aWidth = area.width * scaleFactor;
            const aRight = aLeft + aWidth;
            const aTop = area.top * scaleFactor;
            const aHeight = area.height * scaleFactor;
            const aBottom = aTop + aHeight;

            // Check horizontal intersection with anchor
            if (aLeft < anchorRight && aRight > anchorLeft) {
                if (aBottom <= anchor.top + 5) { 
                    if (aBottom > limitTop) limitTop = aBottom;
                }
            }
        });

        const maxSafeShiftUp = Math.max(0, anchor.top - limitTop);
        
        if (totalShift > maxSafeShiftUp) {
            // Need to shrink because we can't shift up enough
            const deficit = totalShift - maxSafeShiftUp;
            const currentHeight = anchor.height * anchor.scaleY;
            const newHeight = Math.max(20, currentHeight - deficit);

            const oldLeft = anchor.left;
            const oldWidth = anchor.width * anchor.scaleX;
            const oldRight = oldLeft + oldWidth;
            const oldCenterX = oldLeft + (oldWidth / 2);
            
            anchor.scaleToHeight(newHeight);
            const newWidth = anchor.width * anchor.scaleX;

            if (alignment === 'right') {
                anchor.set('left', oldRight - newWidth);
            } else if (alignment === 'center') {
                anchor.set('left', oldCenterX - (newWidth / 2));
            }

            anchor.set('top', limitTop);
            rows.forEach(row => row.forEach(el => el.set('top', el.top - totalShift)));
        } else {
            anchor.set('top', anchor.top - totalShift);
            rows.forEach(row => row.forEach(el => el.set('top', el.top - totalShift)));
        }
    }
}

function applyCustomEffects(canvas, settings, mainBg) {
    if (!settings || !mainBg) return;
    
    const bgColor = settings.bgColor || "#000000";
    canvas.backgroundColor = bgColor;

    const type = settings.fadeEffect || 'none';
    const hasFadeSettings = (type !== 'none' && type !== 'custom') || 
                            (type === 'custom' && (settings.fadeLeft || settings.fadeRight || settings.fadeTop || settings.fadeBottom));

    if (!hasFadeSettings) return;

    canvas.getObjects().filter(o => o.dataTag === 'fade_effect').forEach(o => canvas.remove(o));

    const addLinear = (side) => {
        let val = 0;
        if (side === 'left') val = settings.fadeLeft;
        else if (side === 'right') val = settings.fadeRight;
        else if (side === 'top') val = settings.fadeTop;
        else if (side === 'bottom') val = settings.fadeBottom;
        
        if (val && parseInt(val) > 0) {
            const rect = createFadeRect(mainBg, side, val, bgColor);
            canvas.add(rect);
            const bgIdx = canvas.getObjects().indexOf(mainBg);
            if (bgIdx >= 0) rect.moveTo(bgIdx + 1);
        }
    };

    if (type === 'custom') {
        ['left', 'right', 'top', 'bottom'].forEach(addLinear);
    } else if (type === 'bottom-left') {
        addCornerFade(canvas, mainBg, 'bottom-left', settings.fadeRadius, bgColor);
        addLinear('left');
        addLinear('bottom');
    } else if (type === 'bottom-right') {
        addCornerFade(canvas, mainBg, 'bottom-right', settings.fadeRadius, bgColor);
        addLinear('right');
        addLinear('bottom');
    } else if (type === 'top-left') {
        addCornerFade(canvas, mainBg, 'top-left', settings.fadeRadius, bgColor);
        addLinear('left');
        addLinear('top');
    } else if (type === 'top-right') {
        addCornerFade(canvas, mainBg, 'top-right', settings.fadeRadius, bgColor);
        addLinear('right');
        addLinear('top');
    } else if (type === 'vignette') {
        addVignette(canvas, mainBg, settings.fadeRadius, bgColor);
        addLinear('top');
        addLinear('bottom');
    }
}

// --- MAIN ---
(async () => {
    try {
        const payload = JSON.parse(fs.readFileSync(payloadPath, 'utf8'));
        const layoutJson = JSON.parse(fs.readFileSync(payload.layout_file, 'utf8'));
        const meta = payload.metadata;
        const assets = payload.assets;

        // FIX: Pre-process Layout to handle relative URLs (Node.js doesn't support them)
        const API_BASE = "http://127.0.0.1:5000"; 
        
        const fixUrl = (obj) => {
            if (obj.src && obj.src.startsWith('/')) {
                obj.src = API_BASE + obj.src;
            }
        };

        if (layoutJson.objects) {
            layoutJson.objects.forEach(obj => {
                fixUrl(obj);
                if (obj.type === 'group' && obj.objects) {
                    obj.objects.forEach(sub => fixUrl(sub));
                }
            });
        }

        let baseWidth = 1920;
        let baseHeight = 1080;
        
        // Detect resolution from JSON or Heuristic (Check if objects are positioned for 4K)
        if ((layoutJson.width && layoutJson.width > 3000) || (layoutJson.objects && layoutJson.objects.some(o => o.left > 2500))) {
            baseWidth = 3840;
            baseHeight = 2160;
        }
        const canvas = new fabric.StaticCanvas(null, { width: baseWidth, height: baseHeight });

        // Load JSON with a timeout to prevent hanging
        await new Promise((resolve, reject) => {
            const timeout = setTimeout(() => {
                console.warn("WARNING: canvas.loadFromJSON timed out, proceeding anyway.");
                resolve();
            }, 10000); // 10 second timeout
            
            // Pass reviver to handle custom properties or errors if needed
            canvas.loadFromJSON(layoutJson, () => { clearTimeout(timeout); resolve(); }, (o, object) => {
                 // Ensure dataTag and other properties are preserved
            });
        });

        // FIX: Immediately enforce base resolution after loading JSON
        // This ensures that subsequent operations (like bg scaling) use the correct 1920/4K width
        // instead of whatever width was saved in the JSON (e.g. 1280 from a buggy save).
        if (canvas.getWidth() !== baseWidth || canvas.getHeight() !== baseHeight) {
             canvas.setDimensions({ width: baseWidth, height: baseHeight });
        }

        const settings = layoutJson.custom_effects || layoutJson.metadata?.custom_effects || {};

        const imagePromises = [];
        const certDir = path.join(__dirname, 'certification');

        canvas.getObjects().forEach(obj => {
            if (!obj.dataTag) return;
            let val = undefined;

            switch (obj.dataTag) {
                case 'title':
                    if (obj.type !== 'image') val = meta.title;
                    break;
                case 'year':
                    val = meta.year;
                    break;
                case 'rating':
                case 'rating_star':
                    let r = meta.rating;
                    if (r && r !== 'N/A' && !isNaN(parseFloat(r))) r = parseFloat(r).toFixed(1);
                    else r = null;

                    if (obj.type === 'group') {
                        const t = obj.getObjects().find(o => o.type === 'i-text');
                        if (t) {
                            t.set('text', r ? String(r) : '');
                            obj.addWithUpdate();
                        }
                        obj.set('visible', !!r);
                        val = undefined; // Handled here
                    } else {
                        val = r ? (obj.dataTag === 'rating' ? `IMDb: ${r}` : r) : null;
                    }
                    break;
                case 'rating_val':
                    let rv = meta.rating;
                    if (rv && rv !== 'N/A' && !isNaN(parseFloat(rv))) rv = parseFloat(rv).toFixed(1);
                    else rv = null;
                    val = rv;
                    break;
                case 'overview':
                    val = meta.overview;
                    if (obj.type === 'textbox') {
                        obj.fullMediaText = val || "";
                    }
                    break;
                case 'genres':
                val = meta.genres;
                if (val && settings.genreLimit) {
                    const limit = parseInt(settings.genreLimit);
                    if (!isNaN(limit) && limit > 0) {
                        val = val.split(',').slice(0, limit).join(',');
                    }
                }
                    break;
                case 'runtime':
                    val = meta.runtime;
                    const rtCheck = String(val || "").toLowerCase().replace(/\s/g, '');
                    if (rtCheck === '0min' || rtCheck === '0') val = null;
                    break;
                case 'officialRating':
                    val = meta.officialRating;
                    break;
                case 'provider_source':
                const src = (meta.source || "").toLowerCase();
                if (src === 'radarr' || src === 'sonarr') {
                    val = "Available soon...";
                } else if (src) {
                    const pName = src === 'tmdb' ? 'TMDB' : src.charAt(0).toUpperCase() + src.slice(1);
                    val = `Now available on ${pName}`;
                } else {
                    val = "Now available on Jellyfin";
                }
                    break;
                case 'certification':
                    const fname = getCertificationFilename(meta.officialRating);
                    if (fname) {
                        const p = new Promise(resolve => {
                            const fpath = path.join(certDir, fname);
                            if (fs.existsSync(fpath)) {
                                const imgData = fs.readFileSync(fpath);
                                const ext = path.extname(fname).slice(1);
                                const src = `data:image/${ext};base64,${imgData.toString('base64')}`;
                                fabric.Image.fromURL(src, (img) => {
                                    if (img) {
                                        img.set({
                                            left: obj.left, top: obj.top,
                                            originX: obj.originX, originY: obj.originY,
                                            dataTag: 'certification'
                                        });
                                        const targetH = obj.height * obj.scaleY;
                                        img.scaleToHeight(targetH);
                                        canvas.remove(obj);
                                        canvas.add(img);
                                    }
                                    resolve();
                                });
                            } else {
                                obj.set('visible', false);
                                resolve();
                            }
                        });
                        imagePromises.push(p);
                        val = undefined; // Handled async
                    } else {
                        val = null; // Hide if no mapping found
                    }
                    break;
            }

            if (val !== undefined && obj.dataTag !== 'overview' && obj.dataTag !== 'background' && obj.dataTag !== 'fade_effect' && obj.dataTag !== 'guide_overlay') {
                if (val === null || val === "" || val === "N/A") {
                    obj.set('visible', false);
                } else {
                    obj.set({ text: String(val), visible: true });
                }
            }

            if (obj.dataTag === 'overview' && obj.type === 'textbox') {
                if (!obj.fullMediaText && val) obj.fullMediaText = String(val);
                fitTextToContainer(canvas, obj);
            }
            
            // Save original state of title for reset in updateVerticalLayout
            if (obj.dataTag === 'title') {
                obj._originalState = {
                    scaleX: obj.scaleX,
                    scaleY: obj.scaleY,
                    left: obj.left,
                    top: obj.top
                };
            }
        });

        if (imagePromises.length > 0) {
            await Promise.all(imagePromises);
        }

        let mainBg = canvas.getObjects().find(o => o.dataTag === 'background');
        
        if (assets.backdrop_url) {
            let left = canvas.width / 2;
            let top = canvas.height / 2;
            let flipX = false;
            let flipY = false;
            let oldWidth = 0;
            const oldBg = mainBg;
            
            if (oldBg) {
                const center = oldBg.getCenterPoint();
                left = center.x;
                top = center.y;
                flipX = oldBg.flipX;
                flipY = oldBg.flipY;
                oldWidth = oldBg.width * oldBg.scaleX;
                
                canvas.remove(oldBg);
            }

            await new Promise(resolve => {
                fabric.Image.fromURL(assets.backdrop_url, (img) => {
                    if (!img) { 
                        console.warn(`DEBUG: Failed to fetch background from ${assets.backdrop_url}`);
                        resolve(); return; 
                    }
                    
                    let scale = Math.max(canvas.width / img.width, canvas.height / img.height);
                    
                    if (oldBg && oldWidth > 0 && img.width > 0) {
                        scale = oldWidth / img.width;
                    }

                    img.set({
                        left: left,
                        top: top,
                        originX: 'center', 
                        originY: 'center',
                        scaleX: scale, 
                        scaleY: scale,
                        flipX: flipX,
                        flipY: flipY,
                        dataTag: 'background'
                    });
                    
                    // FIX: Enforce Fixed Canvas Resolution (Prevents wandering tags if bg size differs)
                    if (canvas.getWidth() !== baseWidth || canvas.getHeight() !== baseHeight) {
                        canvas.setDimensions({ width: baseWidth, height: baseHeight });
                    }
                    
                    canvas.add(img);
                    canvas.sendToBack(img);
                    mainBg = img;
                    resolve();
                });
            });
        }
        
        if (!mainBg) {
             mainBg = canvas.getObjects().find(o => o.dataTag === 'background');
        }

        // --- AUTO COLOR DETECTION ---
        // Refactored Ambilight Logic to match editor.js behavior
        // 1. Timing: Executed after backdrop load but before layout updates
        if (mainBg && assets.backdrop_url) {
            try {
                // Load image specifically for node-canvas sampling
                // (JSDOM image element from fabric might not work with node-canvas drawImage)
                const imageForSampling = await canvasModule.loadImage(assets.backdrop_url);
                if (imageForSampling) {
                    // 2. Sampling Logic: Use temp canvas (min 200px)
                    const sampleSize = 200;
                    const tempCanvas = canvasModule.createCanvas(sampleSize, sampleSize);
                    const ctx = tempCanvas.getContext('2d');
                    ctx.drawImage(imageForSampling, 0, 0, sampleSize, sampleSize);
                    const imageData = ctx.getImageData(0, 0, sampleSize, sampleSize).data;
                    
                    let r = 0, g = 0, b = 0, count = 0;
                    const border = 10; // 5% of 200px = 10px (Samples edges like editor.js)

                    for (let y = 0; y < sampleSize; y++) {
                        for (let x = 0; x < sampleSize; x++) {
                            if (x < border || x > sampleSize - border || y < border || y > sampleSize - border) {
                                const i = (y * sampleSize + x) * 4;
                                r += imageData[i]; g += imageData[i + 1]; b += imageData[i + 2];
                                count++;
                            }
                        }
                    }
                    
                    if (count > 0) { 
                        // Calculate Average RGB
                        r = Math.floor(r/count); g = Math.floor(g/count); b = Math.floor(b/count); 

                        // 3. Brightness Correction: Apply factor from settings (default 20)
                        let bVal = parseInt(settings.bgBrightness);
                        if (isNaN(bVal)) bVal = 20;
                        const factor = bVal / 100;
                        r = Math.floor(r * factor);
                        g = Math.floor(g * factor);
                        b = Math.floor(b * factor);

                        const toHex = (c) => {
                            const hex = Math.max(0, Math.min(255, c)).toString(16);
                            return hex.length === 1 ? "0" + hex : hex;
                        };
                        const detectedHex = "#" + toHex(r) + toHex(g) + toHex(b);
                        
                        // 4. State Sync: Update settings.bgColor AND canvas.backgroundColor
                        // This ensures fade gradients use the correct darkened color
                        settings.bgColor = detectedHex;
                        if (typeof canvas.setBackgroundColor === 'function') canvas.setBackgroundColor(detectedHex, () => {});
                        canvas.backgroundColor = detectedHex;
                        
                        console.log(`Auto-Color Applied: ${detectedHex} (Brightness: ${bVal}%)`);

                        // Sync Textbox backgrounds
                        canvas.getObjects().forEach(obj => {
                            if (obj.type === 'textbox' && (obj.autoBackgroundColor === true || obj.autoBackgroundColor === "true") && obj.backgroundColor) {
                                const c = new fabric.Color(obj.backgroundColor);
                                const currentOpacity = c.getSource()[3];
                                obj.set('backgroundColor', `rgba(${r}, ${g}, ${b}, ${currentOpacity})`);
                            }
                        });
                    }
                }
            } catch (e) {
                console.warn("Auto color detection error:", e.message);
            }
        }

        if (assets.logo_url) {
            const titleObj = canvas.getObjects().find(o => o.dataTag === 'title');
            if (titleObj) {
                const targetW = titleObj.width * titleObj.scaleX;
                const targetL = titleObj.left;
                const targetT = titleObj.top;
                const originX = titleObj.originX || 'left';
                const originY = titleObj.originY || 'top';
                const oldWidth = titleObj.width * titleObj.scaleX;
                
                // Capture properties to persist
                const savedFilters = titleObj.filters;
                const savedLogoAutoFix = titleObj.logoAutoFix;

                canvas.remove(titleObj); 

                await new Promise(resolve => {
                    fabric.Image.fromURL(assets.logo_url, (img) => {
                        if (img) {
                            // --- SMART RESIZE LOGIC (Match editor.js) ---
                            const baseMaxW = canvas.width * 0.55;
                            const baseMaxH = canvas.height * 0.35;
                            const ratio = img.width / img.height;
                            let allowedHeight = baseMaxH;

                            if (ratio < 0.65) allowedHeight = baseMaxH * 0.50;      // Tall logos
                            else if (ratio < 1.2) allowedHeight = baseMaxH * 0.75;  // Square logos
                            
                            // Calculate scale based on canvas limits, ignoring placeholder size for better consistency
                            let scale = Math.min(baseMaxW / img.width, allowedHeight / img.height) * 0.9;

                            // --- ALIGNMENT CORRECTION ---
                            // Adjust 'left' to keep the anchor point stable based on alignment
                            let newLeft = targetL;
                            const align = settings.tagAlignment || 'left';
                            const newWidth = img.width * scale;

                            // Sticky Logic (Match editor.js)
                            const marginLeft = parseInt(settings.margins?.left || 50);
                            const marginRight = parseInt(settings.margins?.right || 50);
                            const cW = canvas.width;
                            const boundsL = targetL;
                            const boundsR = targetL + oldWidth;
                            
                            const isStickyLeft = Math.abs(boundsL - marginLeft) < 20;
                            const isStickyRight = Math.abs(boundsR - (cW - marginRight)) < 20;

                            if (isStickyLeft) {
                                newLeft = marginLeft;
                            } else if (isStickyRight) {
                                newLeft = (cW - marginRight) - newWidth;
                            } else if (align === 'right') {
                                newLeft = (targetL + oldWidth) - newWidth;
                            } else if (align === 'center') {
                                newLeft = (targetL + (oldWidth / 2)) - (newWidth / 2);
                            }
                            // If 'left', targetL stays the same

                            img.set({ 
                                left: newLeft, top: targetT, 
                                originX: originX, originY: originY,
                                scaleX: scale, scaleY: scale, 
                                dataTag: 'title',
                                crossOrigin: 'anonymous',
                                logoAutoFix: savedLogoAutoFix
                            });
                            
                            // Restore filters if present
                            if (savedFilters && savedFilters.length > 0) {
                                img.filters = savedFilters;
                                img.applyFilters();
                            }

                            canvas.add(img);
                            canvas.bringToFront(img);
                        }
                        resolve();
                    }, { crossOrigin: 'anonymous' });
                });
            }
        } else {
            // Fallback: If no logo (e.g. BoxSet item), ensure Title is Text
            // If the layout uses an Image for title (placeholder), replace it with Text
            const titleObj = canvas.getObjects().find(o => o.dataTag === 'title');
            if (titleObj && titleObj.type === 'image') {
                const is4K = canvas.width > 2000;
                const fontSize = is4K ? 120 : 80;
                const newText = new fabric.IText(meta.title || "Title", { 
                    left: titleObj.left, top: titleObj.top, 
                    fontFamily: 'Roboto', fontSize: fontSize, 
                    fill: 'white', shadow: new fabric.Shadow({ color: 'rgba(0,0,0,0.8)', blur: 10, offsetX: 2, offsetY: 2 }), 
                    dataTag: 'title', editable: false 
                });

                // --- FIX: Apply Alignment/Sticky Logic for Text Replacement ---
                // Prevents short text from shifting left when replacing a wide logo in right-aligned layouts
                const oldWidth = titleObj.width * titleObj.scaleX;
                const targetL = titleObj.left;
                const align = settings.tagAlignment || 'left';
                const newWidth = newText.width * newText.scaleX;

                const marginLeft = parseInt(settings.margins?.left || 50);
                const marginRight = parseInt(settings.margins?.right || 50);
                const cW = canvas.width;
                const boundsL = targetL;
                const boundsR = targetL + oldWidth;
                
                const isStickyLeft = Math.abs(boundsL - marginLeft) < 20;
                const isStickyRight = Math.abs(boundsR - (cW - marginRight)) < 20;

                let newLeft = targetL;

                if (isStickyLeft) {
                    newLeft = marginLeft;
                } else if (isStickyRight) {
                    newLeft = (cW - marginRight) - newWidth;
                } else if (align === 'right') {
                    newLeft = (targetL + oldWidth) - newWidth;
                } else if (align === 'center') {
                    newLeft = (targetL + (oldWidth / 2)) - (newWidth / 2);
                }
                
                newText.set('left', newLeft);
                // -------------------------------------------------------------

                canvas.remove(titleObj);
                canvas.add(newText);
            }
        }

        let activeBlockedAreas = [];
        let overlayImageFile = null;
        let overlayFound = false;

        try {
            const overlaysPath = path.join(__dirname, 'overlays.json');
            if (fs.existsSync(overlaysPath)) {
                const overlays = JSON.parse(fs.readFileSync(overlaysPath, 'utf8'));
                const activeOverlay = Array.isArray(overlays) ? overlays.find(o => o.id === settings.overlayId) : null;
                if (activeOverlay) {
                    overlayFound = true;
                    if (activeOverlay.blocked_areas) {
                        activeBlockedAreas = activeOverlay.blocked_areas;
                        console.log(`[Overlay] Loaded ${activeBlockedAreas.length} blocked areas from server profile: ${activeOverlay.name}`);
                    }
                    
                    // Determine correct overlay image file (4K vs 1080p)
                    const is4K = canvas.width > 2000;
                    overlayImageFile = is4K ? activeOverlay.file_4k : activeOverlay.file_1080;
                    if (!overlayImageFile) overlayImageFile = is4K ? activeOverlay.file_1080 : activeOverlay.file_4k;
                }
            }
        } catch (e) {
            console.warn("Could not load blocked areas from overlays.json", e.message);
        }

        // Fallback to settings from JSON only if overlay profile was not found on server
        if (!overlayFound && settings.blocked_areas && Array.isArray(settings.blocked_areas)) {
            activeBlockedAreas = settings.blocked_areas;
        }
        
        // FIX: Enforce Fixed Canvas Resolution (Final Check before Layout)
        if (canvas.getWidth() !== baseWidth || canvas.getHeight() !== baseHeight) {
             canvas.setDimensions({ width: baseWidth, height: baseHeight });
        }
        
        // FIX: Refresh textboxes and layout (Match batch.js behavior)
        // Ensure text metrics are calculated before layout update
        canvas.getObjects().forEach(obj => {
            if (obj.dataTag === 'overview' && obj.type === 'textbox') {
                fitTextToContainer(canvas, obj);
            }
            obj.setCoords();
            obj.dirty = true;
        });
        canvas.renderAll(); // Force calc of text widths

        updateVerticalLayout(canvas, settings, activeBlockedAreas);
        
        if (mainBg) {
            applyCustomEffects(canvas, settings, mainBg);
        } else {
            console.warn("No main background found, skipping effects.");
        }

        canvas.renderAll();
        
        if (canvas.width === 0 || canvas.height === 0) {
            console.error("FATAL: Canvas dimensions are 0x0. Rendering aborted.");
            process.exit(1);
        }

        await new Promise((resolve, reject) => {
            const outStream = fs.createWriteStream(outputPath);
            const canvasStream = canvas.createJPEGStream({ quality: 0.95 });
            canvasStream.pipe(outStream);
            outStream.on('finish', resolve);
            outStream.on('error', reject);
        });

        const toProxy = (url) => {
            if (!url) return null;
            return `/api/proxy/image?url=${encodeURIComponent(url)}`;
        };

        const bgObjFinal = canvas.getObjects().find(o => o.dataTag === 'background');
        if (bgObjFinal && assets.backdrop_url) {
            bgObjFinal.set('src', toProxy(assets.backdrop_url));
            bgObjFinal.set('crossOrigin', 'anonymous');
        }
        
        const titleObjFinal = canvas.getObjects().find(o => o.dataTag === 'title' && o.type === 'image');
        if (titleObjFinal && assets.logo_url) {
            titleObjFinal.set('src', toProxy(assets.logo_url));
            titleObjFinal.set('crossOrigin', 'anonymous');
        }

        const jsonOutPath = outputPath + ".json";
        const jsonOutput = canvas.toJSON([
            'dataTag', 'fullMediaText', 'selectable', 'evented', 'lockScalingY', 
            'splitByGrapheme', 'fixedHeight', 'editable', 'matchHeight', 
            'autoBackgroundColor', 'textureId', 'textureScale', 'textureRotation', 
            'textureOpacity', 'snapToObjects', 'logoAutoFix', 'src', 'crossOrigin'
        ]);
        
        jsonOutput.metadata = meta;
        // FIX: Add action_url to root to match batch.js output
        if (meta && meta.action_url) {
            jsonOutput.action_url = meta.action_url;
        }
        jsonOutput.custom_effects = settings;

        // FIX: Post-process JSON to ensure Certification URL is correct (Fixes Editor Preview)
        // We replace the embedded Base64 data with the API URL so the Editor can load it.
        if (jsonOutput.objects) {
            const certObj = jsonOutput.objects.find(o => o.dataTag === 'certification' && o.type === 'image');
            if (certObj && meta && meta.officialRating) {
                const certFilename = getCertificationFilename(meta.officialRating);
                if (certFilename) {
                    certObj.src = `/api/certification/${certFilename}`;
                    certObj.crossOrigin = 'anonymous';
                }
            }
        }

        fs.writeFileSync(jsonOutPath, JSON.stringify(jsonOutput));

        console.log("SUCCESS");

    } catch (err) {
        console.error("FATAL:", err);
        process.exit(1);
    }
})();
