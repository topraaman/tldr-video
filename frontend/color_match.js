// Color matching for Thumbnail Studio.
// - extractPalette(): dominant colors of the original thumbnail (k-means)
// - colorStats() + gradeImage(): tone-aware color transfer in Oklab space
//   (lightness histogram match + per shadow/midtone/highlight color shift),
//   so a user's photo takes on the original thumbnail's colors and grade.

// sRGB <-> linear lookup tables for speed
const SRGB_TO_LINEAR = new Float32Array(256);
for (let i = 0; i < 256; i++) {
    const c = i / 255;
    SRGB_TO_LINEAR[i] = c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
}
const LINEAR_TO_SRGB_STEPS = 4096;
const LINEAR_TO_SRGB = new Uint8ClampedArray(LINEAR_TO_SRGB_STEPS + 1);
for (let i = 0; i <= LINEAR_TO_SRGB_STEPS; i++) {
    const c = i / LINEAR_TO_SRGB_STEPS;
    LINEAR_TO_SRGB[i] = Math.round(255 * (c <= 0.0031308 ? c * 12.92 : 1.055 * Math.pow(c, 1 / 2.4) - 0.055));
}

function linearToSrgb8(c) {
    if (c <= 0) return 0;
    if (c >= 1) return 255;
    return LINEAR_TO_SRGB[(c * LINEAR_TO_SRGB_STEPS) | 0];
}

// Draw an image into a canvas, scaled so its long side is at most maxSide
function imageToCanvas(img, maxSide) {
    const w0 = img.naturalWidth || img.width;
    const h0 = img.naturalHeight || img.height;
    const scale = Math.min(1, maxSide / Math.max(w0, h0));
    const canvas = document.createElement('canvas');
    canvas.width = Math.max(1, Math.round(w0 * scale));
    canvas.height = Math.max(1, Math.round(h0 * scale));
    canvas.getContext('2d').drawImage(img, 0, 0, canvas.width, canvas.height);
    return canvas;
}

const L_BINS = 256;

// Soft shadow / midtone / highlight weights for a tonal rank t in 0..1
function bandWeights(t) {
    return [(1 - t) * (1 - t), 2 * t * (1 - t), t * t];
}

/**
 * Tonal color statistics of an image in Oklab (sampled at low resolution):
 * the lightness distribution (CDF and its inverse) plus the average color
 * (a, b) of its shadows, midtones and highlights.
 */
function colorStats(img) {
    const canvas = imageToCanvas(img, 256);
    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const labs = [];
    const hist = new Float64Array(L_BINS);
    const lab = [0, 0, 0];
    for (let i = 0; i < data.length; i += 4) {
        if (data[i + 3] < 128) continue;
        rgbToOklab(data[i], data[i + 1], data[i + 2], lab);
        labs.push(lab[0], lab[1], lab[2]);
        hist[lightnessBin(lab[0])]++;
    }
    const n = Math.max(labs.length / 3, 1);

    // Smooth the histogram so flat areas don't turn into steps (banding)
    const smooth = new Float64Array(L_BINS);
    const radius = 6;
    for (let i = 0; i < L_BINS; i++) {
        let sum = 0;
        for (let j = -radius; j <= radius; j++) {
            sum += hist[Math.min(L_BINS - 1, Math.max(0, i + j))];
        }
        smooth[i] = sum / (radius * 2 + 1) + n * 1e-4;
    }
    const total = smooth.reduce((a, b) => a + b, 0);

    // CDF: lightness bin -> tonal rank; inverse: rank -> lightness
    const cdf = new Float64Array(L_BINS);
    let acc = 0;
    for (let i = 0; i < L_BINS; i++) {
        acc += smooth[i];
        cdf[i] = acc / total;
    }
    const inverse = new Float64Array(L_BINS);
    let bin = 0;
    for (let r = 0; r < L_BINS; r++) {
        const rank = (r + 0.5) / L_BINS;
        while (bin < L_BINS - 1 && cdf[bin] < rank) bin++;
        // Interpolate inside the bin for a smooth curve
        const prev = bin > 0 ? cdf[bin - 1] : 0;
        const frac = cdf[bin] > prev ? (rank - prev) / (cdf[bin] - prev) : 0.5;
        inverse[r] = (bin + Math.min(1, Math.max(0, frac))) / L_BINS;
    }

    // Average color per tonal band, then spread around it
    const wSum = [0, 0, 0], aSum = [0, 0, 0], bSum = [0, 0, 0];
    for (let i = 0; i < labs.length; i += 3) {
        const w = bandWeights(cdf[lightnessBin(labs[i])]);
        for (let k = 0; k < 3; k++) {
            wSum[k] += w[k];
            aSum[k] += w[k] * labs[i + 1];
            bSum[k] += w[k] * labs[i + 2];
        }
    }
    const bandA = aSum.map((v, k) => v / Math.max(wSum[k], 1e-6));
    const bandB = bSum.map((v, k) => v / Math.max(wSum[k], 1e-6));
    let varA = 0, varB = 0;
    for (let i = 0; i < labs.length; i += 3) {
        const w = bandWeights(cdf[lightnessBin(labs[i])]);
        varA += (labs[i + 1] - dot(w, bandA)) ** 2;
        varB += (labs[i + 2] - dot(w, bandB)) ** 2;
    }
    return {
        cdf, inverse, bandA, bandB,
        stdA: Math.sqrt(varA / n) + 1e-4,
        stdB: Math.sqrt(varB / n) + 1e-4
    };
}

function lightnessBin(L) {
    return Math.min(L_BINS - 1, Math.max(0, (L * L_BINS) | 0));
}

// Linear interpolation into a table at fractional index x
function lookup(table, x) {
    if (x <= 0) return table[0];
    const last = table.length - 1;
    if (x >= last) return table[last];
    const i = x | 0;
    return table[i] + (table[i + 1] - table[i]) * (x - i);
}

function dot(w, v) {
    return w[0] * v[0] + w[1] * v[1] + w[2] * v[2];
}

function rgbToOklab(r8, g8, b8, out) {
    const r = SRGB_TO_LINEAR[r8], g = SRGB_TO_LINEAR[g8], b = SRGB_TO_LINEAR[b8];
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    out[0] = 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s;
    out[1] = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s;
    out[2] = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s;
}

function oklabToRgb8(L, A, B, out, o) {
    const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
    const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
    const s = Math.pow(L - 0.0894841775 * A - 1.2914855480 * B, 3);
    out[o] = linearToSrgb8(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
    out[o + 1] = linearToSrgb8(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
    out[o + 2] = linearToSrgb8(-0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s);
}

/**
 * Return a canvas with `img` recolored to look like `target` (colorStats of the
 * original thumbnail): its brightness/contrast curve is matched, and shadows,
 * midtones and highlights take on the target's colors for the same tones.
 * strength 0..1 blends with the untouched photo.
 */
function gradeImage(img, target, strength) {
    const canvas = imageToCanvas(img, 1600);
    const ctx = canvas.getContext('2d');
    if (!target || strength <= 0) return canvas;

    const source = colorStats(img);
    const ratioA = Math.min(1.8, Math.max(0.5, target.stdA / source.stdA));
    const ratioB = Math.min(1.8, Math.max(0.5, target.stdB / source.stdB));

    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = imageData.data;
    const lab = [0, 0, 0];
    for (let i = 0; i < data.length; i += 4) {
        rgbToOklab(data[i], data[i + 1], data[i + 2], lab);
        const rank = lookup(source.cdf, lab[0] * L_BINS - 0.5);
        const w = bandWeights(rank);
        const L = lookup(target.inverse, rank * L_BINS - 0.5);
        const A = (lab[1] - dot(w, source.bandA)) * ratioA + dot(w, target.bandA);
        const B = (lab[2] - dot(w, source.bandB)) * ratioB + dot(w, target.bandB);
        oklabToRgb8(
            lab[0] + (L - lab[0]) * strength,
            lab[1] + (A - lab[1]) * strength,
            lab[2] + (B - lab[2]) * strength,
            data, i
        );
    }
    ctx.putImageData(imageData, 0, 0);
    return canvas;
}

/** Dominant colors of an image, most common first, as hex strings. */
function extractPalette(img, k = 6) {
    const canvas = imageToCanvas(img, 96);
    const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
    const pixels = [];
    for (let i = 0; i < data.length; i += 4) pixels.push([data[i], data[i + 1], data[i + 2]]);
    if (!pixels.length) return [];

    const dist = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

    // Deterministic farthest-point initialisation
    const centers = [pixels[Math.floor(pixels.length / 2)].slice()];
    while (centers.length < k) {
        let best = null, bestD = -1;
        for (const p of pixels) {
            const d = Math.min(...centers.map(c => dist(p, c)));
            if (d > bestD) { bestD = d; best = p; }
        }
        if (bestD <= 0) break;
        centers.push(best.slice());
    }

    let counts = [];
    for (let iter = 0; iter < 10; iter++) {
        const sums = centers.map(() => [0, 0, 0]);
        counts = centers.map(() => 0);
        for (const p of pixels) {
            let bi = 0, bd = Infinity;
            centers.forEach((c, ci) => {
                const d = dist(p, c);
                if (d < bd) { bd = d; bi = ci; }
            });
            sums[bi][0] += p[0]; sums[bi][1] += p[1]; sums[bi][2] += p[2];
            counts[bi]++;
        }
        centers.forEach((c, ci) => {
            if (counts[ci]) for (let j = 0; j < 3; j++) c[j] = sums[ci][j] / counts[ci];
        });
    }

    const toHex = c => '#' + c.map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
    return centers
        .map((c, i) => ({ hex: toHex(c), rgb: c, count: counts[i] }))
        .filter(c => c.count > 0)
        .sort((a, b) => b.count - a.count);
}

function colorLuminance([r, g, b]) {
    return 0.2126 * SRGB_TO_LINEAR[Math.round(r)] + 0.7152 * SRGB_TO_LINEAR[Math.round(g)] +
        0.0722 * SRGB_TO_LINEAR[Math.round(b)];
}

function colorSaturation([r, g, b]) {
    const max = Math.max(r, g, b), min = Math.min(r, g, b);
    return max === 0 ? 0 : (max - min) / max;
}

/** Pick headline fill (bright & vivid) and outline (darkest) colors from a palette. */
function textColorsFromPalette(palette) {
    if (!palette.length) return null;
    const fill = palette.reduce((best, c) =>
        colorSaturation(c.rgb) * 0.6 + colorLuminance(c.rgb) * 0.8 >
        colorSaturation(best.rgb) * 0.6 + colorLuminance(best.rgb) * 0.8 ? c : best);
    const outline = palette.reduce((best, c) => colorLuminance(c.rgb) < colorLuminance(best.rgb) ? c : best);
    const l1 = colorLuminance(fill.rgb), l2 = colorLuminance(outline.rgb);
    const contrast = (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
    // Fall back to classic thumbnail text if the palette has too little contrast
    return contrast >= 3
        ? { fill: fill.hex, outline: outline.hex }
        : { fill: l1 > 0.4 ? fill.hex : '#ffffff', outline: '#000000' };
}
