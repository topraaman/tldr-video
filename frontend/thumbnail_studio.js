// Thumbnail Studio - extract a video's thumbnail, add your own image and
// headline text, and export a 1280x720 custom thumbnail. All editing happens
// in the browser on a <canvas>.

const THUMB_W = 1280;
const THUMB_H = 720;

const studio = {
    thumbnailFilename: null,
    videoTitle: '',
    bgThumbImg: null,
    bgUploadImg: null,
    bgUploadFile: null,     // original photo file, sent to the AI person swap
    swapBgImg: null,        // original thumbnail with its person removed (AI)
    userImg: null,
    userImgPreGraded: false, // AI cut-out is already color matched on the server
    user: { x: 960, y: 380 },
    text: { x: 640, y: 590 },
    bg: { x: 0, y: 0 },  // pan offset for "My photo" background
    // Style of the original thumbnail, used to recreate it with the user's photo
    targetStats: null,
    palette: [],
    gradedCache: new Map(),
    // Hit boxes from the last draw, used for dragging
    bounds: { user: null, text: null, bg: null },
    drag: null
};

const thumbCanvas = document.getElementById('thumbCanvas');
const thumbCtx = thumbCanvas.getContext('2d');

const studioEls = {
    urlInput: document.getElementById('thumbUrlInput'),
    extractBtn: document.getElementById('extractThumbBtn'),
    downloadOriginalBtn: document.getElementById('downloadOriginalThumbBtn'),
    savePngBtn: document.getElementById('saveThumbPngBtn'),
    saveJpgBtn: document.getElementById('saveThumbJpgBtn'),
    resetBtn: document.getElementById('resetThumbBtn'),
    original: document.getElementById('studioOriginal'),
    originalEmpty: document.getElementById('studioOriginalEmpty'),
    info: document.getElementById('studioInfo'),
    bgSource: document.getElementById('bgSource'),
    bgUpload: document.getElementById('bgUpload'),
    bgColor: document.getElementById('bgColor'),
    bgDarken: document.getElementById('bgDarken'),
    bgBlur: document.getElementById('bgBlur'),
    userUpload: document.getElementById('userImageUpload'),
    userSize: document.getElementById('userImageSize'),
    userShape: document.getElementById('userImageShape'),
    userOutline: document.getElementById('userImageOutline'),
    userOutlineColor: document.getElementById('userImageOutlineColor'),
    removeUserBtn: document.getElementById('removeUserImageBtn'),
    text: document.getElementById('thumbText'),
    font: document.getElementById('thumbFont'),
    textSize: document.getElementById('thumbTextSize'),
    textColor: document.getElementById('thumbTextColor'),
    textStroke: document.getElementById('thumbTextStroke'),
    textUpper: document.getElementById('thumbTextUpper'),
    textShadow: document.getElementById('thumbTextShadow'),
    matchColors: document.getElementById('matchColors'),
    matchStrength: document.getElementById('matchStrength'),
    paletteSwatches: document.getElementById('paletteSwatches'),
    applyPaletteBtn: document.getElementById('applyPaletteBtn'),
    swapPersonBtn: document.getElementById('swapPersonBtn')
};

document.addEventListener('DOMContentLoaded', () => {
    studioEls.extractBtn.addEventListener('click', () => fetchVideoInfo(getSharedUrl(), { force: true }));
    studioEls.urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') fetchVideoInfo(getSharedUrl(), { force: true });
    });
    studioEls.downloadOriginalBtn.addEventListener('click', downloadOriginalThumbnail);
    studioEls.savePngBtn.addEventListener('click', () => saveCustomThumbnail('png'));
    studioEls.saveJpgBtn.addEventListener('click', () => saveCustomThumbnail('jpg'));
    studioEls.resetBtn.addEventListener('click', resetStudio);

    studioEls.bgUpload.addEventListener('change', async () => {
        const img = await loadImageFile(studioEls.bgUpload.files[0]);
        if (!img) return;
        studio.bgUploadImg = img;
        studio.bgUploadFile = studioEls.bgUpload.files[0];
        updateSwapButton();
        studio.bg = { x: 0, y: 0 };
        studioEls.bgSource.value = 'upload';
        // Recreate the original's look: its palette for the text, its title as headline
        if (studio.palette.length) applyPaletteToText();
        if (!studioEls.text.value && studio.videoTitle) {
            studioEls.text.value = studio.videoTitle.split(/\s+/).slice(0, 4).join(' ');
        }
        drawThumbnail();
        statusText.textContent = studio.targetStats
            ? 'Photo added - colors matched to the original thumbnail'
            : 'Photo added - extract a thumbnail to match its colors';
    });
    studioEls.userUpload.addEventListener('change', async () => {
        const img = await loadImageFile(studioEls.userUpload.files[0]);
        if (!img) return;
        studio.userImg = img;
        studio.userImgPreGraded = false;
        studioEls.removeUserBtn.disabled = false;
        drawThumbnail();
    });
    studioEls.removeUserBtn.addEventListener('click', () => {
        studio.userImg = null;
        studio.userImgPreGraded = false;
        studioEls.userUpload.value = '';
        studioEls.removeUserBtn.disabled = true;
        drawThumbnail();
    });

    studioEls.swapPersonBtn.addEventListener('click', swapPersonWithAI);

    studioEls.applyPaletteBtn.addEventListener('click', () => {
        applyPaletteToText();
        drawThumbnail();
    });

    // Any control change redraws
    [studioEls.matchColors, studioEls.matchStrength, studioEls.bgSource, studioEls.bgColor, studioEls.bgDarken, studioEls.bgBlur,
     studioEls.userSize, studioEls.userShape, studioEls.userOutline, studioEls.userOutlineColor,
     studioEls.text, studioEls.font, studioEls.textSize, studioEls.textColor,
     studioEls.textStroke, studioEls.textUpper, studioEls.textShadow
    ].forEach(el => el.addEventListener('input', drawThumbnail));

    thumbCanvas.addEventListener('pointerdown', onCanvasPointerDown);
    thumbCanvas.addEventListener('pointermove', onCanvasPointerMove);
    thumbCanvas.addEventListener('pointerup', onCanvasPointerUp);
    thumbCanvas.addEventListener('pointercancel', onCanvasPointerUp);

    drawThumbnail();
});

// Called by the Transcriber and by fetchVideoInfo when a thumbnail is available
function loadStudioThumbnail(filename, { title = '', channel = '' } = {}) {
    const src = `${API_BASE}/api/thumbnail/${encodeURIComponent(filename)}`;
    const img = new Image();
    img.onload = () => {
        studio.thumbnailFilename = filename;
        studio.videoTitle = title;
        studio.bgThumbImg = img;
        studio.swapBgImg = null;
        studio.targetStats = colorStats(img);
        studio.palette = extractPalette(img);
        studio.gradedCache.clear();
        renderPalette();
        updateSwapButton();
        // Keep the user's photo as the background if they already added one
        studioEls.bgSource.value = studio.bgUploadImg ? 'upload' : 'thumbnail';
        studioEls.original.src = src;
        studioEls.original.style.display = 'block';
        studioEls.originalEmpty.style.display = 'none';
        studioEls.info.textContent = [title, channel && `Channel: ${channel}`,
            `${img.naturalWidth} × ${img.naturalHeight}px`].filter(Boolean).join(' · ');
        studioEls.downloadOriginalBtn.disabled = false;
        if (!studioEls.text.value && title) {
            studioEls.text.value = title.split(/\s+/).slice(0, 4).join(' ');
        }
        drawThumbnail();
    };
    img.onerror = () => {
        statusText.textContent = 'Could not load the thumbnail image';
    };
    img.src = src;
}

function loadImageFile(file) {
    return new Promise(resolve => {
        if (!file) return resolve(null);
        if (!file.type.startsWith('image/')) {
            alert('Please choose an image file');
            return resolve(null);
        }
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => {
            alert('Could not read that image');
            resolve(null);
        };
        img.src = URL.createObjectURL(file);
    });
}

// ---------- Drawing ----------

function drawThumbnail() {
    const ctx = thumbCtx;
    ctx.save();
    ctx.clearRect(0, 0, THUMB_W, THUMB_H);

    drawBackground(ctx);

    const darken = Number(studioEls.bgDarken.value) / 100;
    if (darken > 0) {
        ctx.fillStyle = `rgba(0, 0, 0, ${darken})`;
        ctx.fillRect(0, 0, THUMB_W, THUMB_H);
    }

    studio.bounds.user = studio.userImg ? drawUserImage(ctx) : null;
    studio.bounds.text = drawHeadline(ctx);

    if (studio.drag && studio.drag.layer !== 'bg') {
        const b = studio.bounds[studio.drag.layer];
        if (b) {
            ctx.setLineDash([12, 8]);
            ctx.lineWidth = 3;
            ctx.strokeStyle = '#316ac5';
            ctx.strokeRect(b.x - 6, b.y - 6, b.w + 12, b.h + 12);
        }
    }
    ctx.restore();
}

// The user's image, color-graded to match the original thumbnail when enabled
function styledImage(img) {
    if (!img || !studio.targetStats || !studioEls.matchColors.checked) return img;
    const strength = Number(studioEls.matchStrength.value) / 100;
    const cached = studio.gradedCache.get(img);
    if (cached && cached.strength === strength) return cached.canvas;
    const canvas = gradeImage(img, studio.targetStats, strength);
    studio.gradedCache.set(img, { strength, canvas });
    return canvas;
}

function imageSize(img) {
    return { w: img.naturalWidth || img.width, h: img.naturalHeight || img.height };
}

function drawBackground(ctx) {
    const source = studioEls.bgSource.value;
    const img = source === 'thumbnail' ? studio.bgThumbImg
        : source === 'upload' ? styledImage(studio.bgUploadImg)
        : source === 'swap' ? studio.swapBgImg : null;
    studio.bounds.bg = null;

    if (!img) {
        ctx.fillStyle = studioEls.bgColor.value;
        ctx.fillRect(0, 0, THUMB_W, THUMB_H);
        if (source !== 'color') {
            ctx.fillStyle = 'rgba(255, 255, 255, 0.55)';
            ctx.font = '28px Tahoma, sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText({
                thumbnail: 'Extract a thumbnail from a video URL to use it here',
                upload: 'Choose your photo in the "Use My Photo" panel',
                swap: 'Click "AI: Swap person into original" to create this background'
            }[source], THUMB_W / 2, 60);
        }
        return;
    }

    const blur = Number(studioEls.bgBlur.value);
    // Cover-fit, slightly oversized when blurred so edges stay filled
    const pad = blur * 2;
    const size = imageSize(img);
    const scale = Math.max((THUMB_W + pad * 2) / size.w, (THUMB_H + pad * 2) / size.h);
    const w = size.w * scale;
    const h = size.h * scale;
    let x = (THUMB_W - w) / 2;
    let y = (THUMB_H - h) / 2;
    if (source === 'upload') {
        // Photo can be dragged to reframe the 16:9 crop; keep the frame covered
        const maxX = (w - THUMB_W) / 2;
        const maxY = (h - THUMB_H) / 2;
        studio.bg.x = Math.min(maxX, Math.max(-maxX, studio.bg.x));
        studio.bg.y = Math.min(maxY, Math.max(-maxY, studio.bg.y));
        x += studio.bg.x;
        y += studio.bg.y;
        studio.bounds.bg = { x: 0, y: 0, w: THUMB_W, h: THUMB_H };
    }
    ctx.save();
    if (blur > 0) ctx.filter = `blur(${blur}px)`;
    ctx.drawImage(img, x, y, w, h);
    ctx.restore();
}

function drawUserImage(ctx) {
    const img = studio.userImgPreGraded ? studio.userImg : styledImage(studio.userImg);
    const size = imageSize(img);
    const shape = studioEls.userShape.value;
    const h = THUMB_H * Number(studioEls.userSize.value) / 100;
    let w = h * size.w / size.h;
    if (shape === 'circle') w = h;
    const x = studio.user.x - w / 2;
    const y = studio.user.y - h / 2;

    ctx.save();
    ctx.beginPath();
    if (shape === 'circle') {
        ctx.arc(studio.user.x, studio.user.y, h / 2, 0, Math.PI * 2);
    } else if (shape === 'rounded') {
        roundedRectPath(ctx, x, y, w, h, Math.min(w, h) * 0.08);
    } else {
        ctx.rect(x, y, w, h);
    }
    ctx.save();
    ctx.clip();
    if (shape === 'circle') {
        // Cover-crop the image into the circle
        const s = Math.max(w / size.w, h / size.h);
        const iw = size.w * s;
        const ih = size.h * s;
        ctx.drawImage(img, studio.user.x - iw / 2, studio.user.y - ih / 2, iw, ih);
    } else {
        ctx.drawImage(img, x, y, w, h);
    }
    ctx.restore();
    if (studioEls.userOutline.checked) {
        ctx.lineWidth = 10;
        ctx.strokeStyle = studioEls.userOutlineColor.value;
        ctx.stroke();
    }
    ctx.restore();
    return { x, y, w, h };
}

function drawHeadline(ctx) {
    let value = studioEls.text.value.trim();
    if (!value) return null;
    if (studioEls.textUpper.checked) value = value.toUpperCase();

    const lines = value.split('\n');
    ctx.save();
    const setFont = px => { ctx.font = `bold ${px}px "${studioEls.font.value}", Impact, sans-serif`; };
    let size = Number(studioEls.textSize.value);
    setFont(size);
    // Shrink to fit so long headlines never run off the canvas
    const widest = Math.max(...lines.map(line => ctx.measureText(line).width));
    const maxW = THUMB_W * 0.94;
    if (widest > maxW) {
        size = Math.floor(size * maxW / widest);
        setFont(size);
    }
    const lineHeight = size * 1.05;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';

    const widths = lines.map(line => ctx.measureText(line).width);
    const blockW = Math.max(...widths);
    const blockH = lineHeight * lines.length;
    const top = studio.text.y - blockH / 2;

    lines.forEach((line, i) => {
        const ly = top + lineHeight * (i + 0.5);
        if (studioEls.textShadow.checked) {
            ctx.shadowColor = 'rgba(0, 0, 0, 0.6)';
            ctx.shadowBlur = 14;
            ctx.shadowOffsetX = 6;
            ctx.shadowOffsetY = 6;
        }
        ctx.lineWidth = Math.max(4, size * 0.14);
        ctx.strokeStyle = studioEls.textStroke.value;
        ctx.strokeText(line, studio.text.x, ly);
        ctx.shadowColor = 'transparent';
        ctx.fillStyle = studioEls.textColor.value;
        ctx.fillText(line, studio.text.x, ly);
    });
    ctx.restore();
    return { x: studio.text.x - blockW / 2, y: top, w: blockW, h: blockH };
}

function roundedRectPath(ctx, x, y, w, h, r) {
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
}

// ---------- Dragging ----------

function canvasPoint(e) {
    const rect = thumbCanvas.getBoundingClientRect();
    return {
        x: (e.clientX - rect.left) * THUMB_W / rect.width,
        y: (e.clientY - rect.top) * THUMB_H / rect.height
    };
}

function hitLayer(p) {
    // Text is drawn on top, so it wins
    for (const layer of ['text', 'user', 'bg']) {
        const b = studio.bounds[layer];
        if (b && p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) return layer;
    }
    return null;
}

function onCanvasPointerDown(e) {
    const p = canvasPoint(e);
    const layer = hitLayer(p);
    if (!layer) return;
    studio.drag = { layer, dx: studio[layer].x - p.x, dy: studio[layer].y - p.y };
    thumbCanvas.setPointerCapture(e.pointerId);
    thumbCanvas.style.cursor = 'grabbing';
    drawThumbnail();
}

function onCanvasPointerMove(e) {
    const p = canvasPoint(e);
    if (!studio.drag) {
        thumbCanvas.style.cursor = hitLayer(p) ? 'grab' : 'default';
        return;
    }
    const pos = studio[studio.drag.layer];
    pos.x = p.x + studio.drag.dx;
    pos.y = p.y + studio.drag.dy;
    if (studio.drag.layer !== 'bg') {  // background clamps itself while drawing
        pos.x = Math.min(THUMB_W, Math.max(0, pos.x));
        pos.y = Math.min(THUMB_H, Math.max(0, pos.y));
    }
    drawThumbnail();
}

function onCanvasPointerUp() {
    if (!studio.drag) return;
    studio.drag = null;
    thumbCanvas.style.cursor = 'grab';
    drawThumbnail();
}

// ---------- Saving ----------

function triggerDownload(blob, filename) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
}

function saveCustomThumbnail(format) {
    drawThumbnail();
    const type = format === 'jpg' ? 'image/jpeg' : 'image/png';
    thumbCanvas.toBlob(blob => {
        if (!blob) {
            statusText.textContent = 'Could not export the thumbnail';
            return;
        }
        const name = `${slugify(studio.videoTitle || studioEls.text.value)}_custom_thumbnail.${format}`;
        triggerDownload(blob, name);
        const sizeKb = Math.round(blob.size / 1024);
        statusText.textContent = `Saved ${name} (${sizeKb} KB)` +
            (blob.size > 2 * 1024 * 1024 ? ' - over YouTube\'s 2 MB limit, try JPG' : '');
    }, type, 0.92);
}

async function downloadOriginalThumbnail() {
    if (!studio.thumbnailFilename) return;
    try {
        const response = await fetch(`${API_BASE}/api/thumbnail/${encodeURIComponent(studio.thumbnailFilename)}`);
        if (!response.ok) throw new Error('Failed to download thumbnail');
        triggerDownload(await response.blob(), `${slugify(studio.videoTitle)}_thumbnail.jpg`);
        statusText.textContent = 'Original thumbnail downloaded';
    } catch (error) {
        statusText.textContent = 'Failed to download thumbnail: ' + error.message;
    }
}

function resetStudio() {
    studio.bgUploadImg = null;
    studio.bgUploadFile = null;
    studio.swapBgImg = null;
    studio.userImg = null;
    studio.userImgPreGraded = false;
    studio.user = { x: 960, y: 380 };
    studio.text = { x: 640, y: 590 };
    studio.bg = { x: 0, y: 0 };
    studio.gradedCache.clear();
    studioEls.bgUpload.value = '';
    studioEls.userUpload.value = '';
    studioEls.removeUserBtn.disabled = true;
    studioEls.bgSource.value = studio.bgThumbImg ? 'thumbnail' : 'color';
    updateSwapButton();
    studioEls.bgDarken.value = 0;
    studioEls.bgBlur.value = 0;
    studioEls.userSize.value = 80;
    studioEls.textSize.value = 110;
    studioEls.matchColors.checked = true;
    studioEls.matchStrength.value = 80;
    drawThumbnail();
    statusText.textContent = 'Thumbnail reset';
}

// ---------- Original thumbnail palette ----------

function renderPalette() {
    const box = studioEls.paletteSwatches;
    box.innerHTML = '';
    studio.palette.forEach(c => {
        const swatch = document.createElement('button');
        swatch.className = 'palette-swatch';
        swatch.style.background = c.hex;
        swatch.title = `${c.hex} - click: text color, Shift+click: outline color`;
        swatch.addEventListener('click', (e) => {
            (e.shiftKey ? studioEls.textStroke : studioEls.textColor).value = c.hex;
            drawThumbnail();
        });
        box.appendChild(swatch);
    });
    studioEls.applyPaletteBtn.disabled = !studio.palette.length;
}

function applyPaletteToText() {
    const colors = textColorsFromPalette(studio.palette);
    if (!colors) return;
    studioEls.textColor.value = colors.fill;
    studioEls.textStroke.value = colors.outline;
}

// ---------- AI person swap ----------

function updateSwapButton() {
    const ready = Boolean(studio.thumbnailFilename && studio.bgUploadFile);
    studioEls.swapPersonBtn.disabled = !ready;
    studioEls.swapPersonBtn.title = ready
        ? 'Replace the person in the original thumbnail with the person in your photo'
        : 'Extract a thumbnail and choose a photo first';
}

function loadImageUrl(src) {
    return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error('Could not load the AI result'));
        img.src = src;
    });
}

async function swapPersonWithAI() {
    if (!studio.thumbnailFilename || !studio.bgUploadFile) return;

    const form = new FormData();
    form.append('thumbnail_filename', studio.thumbnailFilename);
    form.append('photo', studio.bgUploadFile);

    const header = document.querySelector('.loading-header');
    const previousHeader = header.textContent;
    header.textContent = 'AI Person Swap...';
    showLoading('Finding people and rebuilding the background...');
    updateProgress(30, 'AI is swapping the person (first run downloads the models)');
    studioEls.swapPersonBtn.disabled = true;

    try {
        const response = await fetch(`${API_BASE}/api/thumbnail/swap-person`, { method: 'POST', body: form });
        if (!response.ok) {
            let detail = 'Person swap failed';
            try { detail = (await response.json()).detail || detail; } catch (e) { /* not JSON */ }
            throw new Error(detail);
        }
        const result = await response.json();
        const [background, person] = await Promise.all([
            loadImageUrl(result.background), loadImageUrl(result.person)
        ]);

        studio.swapBgImg = background;
        studioEls.bgSource.value = 'swap';

        // The cut-out becomes the editable "Your Image" layer, placed where the original person was
        studio.userImg = person;
        studio.userImgPreGraded = true;
        const box = result.box;
        studio.user = { x: box.x + box.w / 2, y: box.y + box.h / 2 };
        studioEls.userSize.value = Math.round(Math.min(200, Math.max(10, box.h / THUMB_H * 100)));
        studioEls.userShape.value = 'original';
        studioEls.userOutline.checked = false;
        studioEls.removeUserBtn.disabled = false;
        if (studio.palette.length) applyPaletteToText();

        drawThumbnail();
        statusText.textContent = result.inpaint_method === 'lama'
            ? 'Person swapped - drag or resize your cut-out to fine-tune'
            : 'Person swapped with basic background fill (LaMa model unavailable) - drag or resize to fine-tune';
    } catch (error) {
        statusText.textContent = 'AI swap failed: ' + error.message;
        alert('AI swap: ' + error.message);
    } finally {
        hideLoading();
        header.textContent = previousHeader;
        updateSwapButton();
    }
}
