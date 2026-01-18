// Video to Transcript - Word 2003 Edition
// Frontend Application Logic

const API_BASE = '';

// State
let currentData = {
    title: 'Untitled Document',
    transcript: '',
    chapters: [],
    takeaways: [],
    segments: [],
    highlights: []
};

let currentHighlightColor = '#ffff00';
let currentTextColor = '#000000';

// DOM Elements
const urlInput = document.getElementById('urlInput');
const transcribeBtn = document.getElementById('transcribeBtn');
const savePdfBtn = document.getElementById('savePdfBtn');
const saveDocxBtn = document.getElementById('saveDocxBtn');
const fontFamily = document.getElementById('fontFamily');
const fontSize = document.getElementById('fontSize');
const editor = document.getElementById('editor');
const titleEditor = document.getElementById('titleEditor');
const chaptersList = document.getElementById('chaptersList');
const takeawaysList = document.getElementById('takeawaysList');
const statusText = document.getElementById('statusText');
const wordCount = document.getElementById('wordCount');
const loadingOverlay = document.getElementById('loadingOverlay');
const loadingMessage = document.getElementById('loadingMessage');
const loadingProgressFill = document.getElementById('loadingProgressFill');
const progressSection = document.getElementById('progressSection');
const progressFill = document.getElementById('progressFill');
const progressText = document.getElementById('progressText');
const highlightBtn = document.getElementById('highlightBtn');
const highlightPalette = document.getElementById('highlightPalette');
const textColorBtn = document.getElementById('textColorBtn');
const textColorPalette = document.getElementById('textColorPalette');
const regenerateBtn = document.getElementById('regenerateBtn');
const thumbnailSection = document.getElementById('thumbnailSection');
const thumbnailPreview = document.getElementById('thumbnailPreview');
const thumbnailInfo = document.getElementById('thumbnailInfo');
const downloadThumbnailBtn = document.getElementById('downloadThumbnailBtn');

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    checkHealth();
    updateWordCount();
});

function initializeEventListeners() {
    // Transcribe button
    transcribeBtn.addEventListener('click', startTranscription);
    urlInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') startTranscription();
    });

    // Save buttons
    savePdfBtn.addEventListener('click', () => exportDocument('pdf'));
    saveDocxBtn.addEventListener('click', () => exportDocument('docx'));

    // Font controls
    fontFamily.addEventListener('change', applyFontFamily);
    fontSize.addEventListener('change', applyFontSize);

    // Format buttons (Bold, Italic, Underline)
    document.querySelectorAll('.format-btn').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            const command = btn.dataset.command;
            editor.focus();
            applyFormatCommand(command);
            btn.classList.toggle('active');
        });
    });

    // Highlight dropdown
    highlightBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        highlightPalette.classList.toggle('show');
        textColorPalette.classList.remove('show');
    });

    highlightPalette.querySelectorAll('.color-option').forEach(opt => {
        opt.addEventListener('click', (e) => {
            e.preventDefault();
            currentHighlightColor = opt.dataset.color;
            editor.focus();

            if (currentHighlightColor === 'transparent') {
                applyHighlight(null); // Remove highlight
            } else {
                applyHighlight(currentHighlightColor);
            }

            highlightPalette.classList.remove('show');
            highlightBtn.querySelector('.highlight-icon').style.background =
                currentHighlightColor === 'transparent' ? '#ffff00' : currentHighlightColor;
        });
    });

    // Text color dropdown
    textColorBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        textColorPalette.classList.toggle('show');
        highlightPalette.classList.remove('show');
    });

    textColorPalette.querySelectorAll('.color-option').forEach(opt => {
        opt.addEventListener('click', (e) => {
            e.preventDefault();
            currentTextColor = opt.dataset.color;
            editor.focus();
            applyFormatCommand('foreColor', currentTextColor);
            textColorPalette.classList.remove('show');
            textColorBtn.querySelector('.color-bar').style.background = currentTextColor;
        });
    });

    // Close dropdowns on outside click
    document.addEventListener('click', () => {
        highlightPalette.classList.remove('show');
        textColorPalette.classList.remove('show');
    });

    // Editor events
    editor.addEventListener('input', updateWordCount);
    titleEditor.addEventListener('input', () => {
        currentData.title = titleEditor.textContent || 'Untitled Document';
    });

    // Regenerate button
    regenerateBtn.addEventListener('click', regenerateChapters);

    // Download thumbnail button
    downloadThumbnailBtn.addEventListener('click', downloadThumbnail);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey || e.metaKey) {
            switch (e.key.toLowerCase()) {
                case 's':
                    e.preventDefault();
                    exportDocument('pdf');
                    break;
                case 'b':
                    e.preventDefault();
                    document.execCommand('bold', false, null);
                    break;
                case 'i':
                    e.preventDefault();
                    document.execCommand('italic', false, null);
                    break;
                case 'u':
                    e.preventDefault();
                    document.execCommand('underline', false, null);
                    break;
            }
        }
    });
}

async function checkHealth() {
    try {
        const response = await fetch(`${API_BASE}/api/health`);
        const data = await response.json();

        if (data.status === 'ok') {
            statusText.textContent = 'Ready';
        } else {
            statusText.textContent = data.message;
        }
    } catch (error) {
        statusText.textContent = 'Server not running - start with: python main.py';
    }
}

async function startTranscription() {
    const url = urlInput.value.trim();

    if (!url) {
        alert('Please enter a YouTube or podcast URL');
        return;
    }

    // Validate URL
    if (!isValidUrl(url)) {
        alert('Please enter a valid URL');
        return;
    }

    showLoading('Starting transcription...');
    transcribeBtn.disabled = true;

    try {
        // Start transcription job
        const response = await fetch(`${API_BASE}/api/transcribe`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });

        if (!response.ok) {
            throw new Error('Failed to start transcription');
        }

        const { job_id } = await response.json();

        // Poll for status
        await pollJobStatus(job_id);

    } catch (error) {
        hideLoading();
        alert('Error: ' + error.message);
    } finally {
        transcribeBtn.disabled = false;
    }
}

async function pollJobStatus(jobId) {
    const pollInterval = 2000; // 2 seconds

    while (true) {
        try {
            const response = await fetch(`${API_BASE}/api/job/${jobId}`);
            const job = await response.json();

            updateProgress(job.progress, job.message);

            if (job.status === 'complete') {
                hideLoading();
                displayResults(job.result);
                break;
            } else if (job.status === 'error') {
                hideLoading();
                alert('Error: ' + job.message);
                break;
            }

            await new Promise(resolve => setTimeout(resolve, pollInterval));
        } catch (error) {
            hideLoading();
            alert('Error polling job status: ' + error.message);
            break;
        }
    }
}

function displayResults(result) {
    // Clean title - remove ** markdown markers
    let cleanTitle = (result.title || 'Untitled Document').replace(/\*\*/g, '');

    currentData = {
        title: cleanTitle,
        transcript: result.transcript || result.raw_transcript,
        chapters: result.chapters || [],
        takeaways: result.takeaways || [],
        segments: result.segments || [],
        highlights: [],
        thumbnail_path: result.thumbnail_path || null,
        channel: result.channel || ""
    };

    // Update title
    titleEditor.textContent = currentData.title;

    // Update editor content
    editor.innerHTML = formatTranscriptForDisplay(currentData.transcript);

    // Update chapters
    displayChapters(currentData.chapters);

    // Update takeaways
    displayTakeaways(currentData.takeaways);

    // Display thumbnail if available
    displayThumbnail(currentData.thumbnail_path, currentData.channel);

    // Show regenerate button
    regenerateBtn.style.display = 'block';

    // Update word count
    updateWordCount();

    statusText.textContent = 'Transcription complete';
}

function displayThumbnail(thumbnailPath, channel) {
    if (thumbnailPath) {
        // Extract filename from path
        const filename = thumbnailPath.split('/').pop();

        // Show thumbnail section
        thumbnailSection.style.display = 'block';

        // Set thumbnail image source (serve from API)
        thumbnailPreview.src = `${API_BASE}/api/thumbnail/${filename}`;
        thumbnailPreview.onerror = () => {
            thumbnailSection.style.display = 'none';
        };

        // Show channel info
        if (channel) {
            thumbnailInfo.textContent = `Channel: ${channel}`;
        }
    } else {
        thumbnailSection.style.display = 'none';
    }
}

function downloadThumbnail() {
    if (!currentData.thumbnail_path) {
        statusText.textContent = 'No thumbnail available';
        return;
    }

    const filename = currentData.thumbnail_path.split('/').pop();
    const downloadName = `${currentData.title.replace(/[^a-zA-Z0-9]/g, '_')}_thumbnail.jpg`;

    // Create download link
    const a = document.createElement('a');
    a.href = `${API_BASE}/api/thumbnail/${filename}`;
    a.download = downloadName;
    document.body.appendChild(a);
    a.click();
    a.remove();

    statusText.textContent = 'Thumbnail downloaded';
}

function formatTranscriptForDisplay(text) {
    // Convert **bold** markdown to styled span (handles multi-line too)
    let html = text.replace(/\*\*(.+?)\*\*/gs, '<span class="section-heading-inline">$1</span>');

    // Remove any remaining stray ** that didn't match
    html = html.replace(/\*\*/g, '');

    // Split into paragraphs and wrap in <p> tags
    const paragraphs = html.split(/\n\n+/);
    return paragraphs
        .filter(p => p.trim())
        .map(p => {
            const trimmed = p.trim();
            // Check if paragraph starts with a section heading
            if (trimmed.startsWith('<span class="section-heading-inline">')) {
                // It's a section heading - make it a proper heading element
                return `<h3 class="section-heading">${trimmed.replace(/\n/g, '<br>')}</h3>`;
            }
            return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
        })
        .join('');
}

function displayChapters(chapters) {
    if (!chapters || chapters.length === 0) {
        chaptersList.innerHTML = '<p class="placeholder-text">No chapters generated</p>';
        return;
    }

    chaptersList.innerHTML = chapters.map((ch, i) => `
        <div class="chapter-item" data-index="${i}">
            <span class="chapter-time">${ch.timestamp || '00:00'}</span>
            <span class="chapter-title">${ch.title || 'Chapter ' + (i + 1)}</span>
        </div>
    `).join('');

    // Add click handlers to jump to timestamp
    chaptersList.querySelectorAll('.chapter-item').forEach(item => {
        item.addEventListener('click', () => {
            // Could implement scroll-to-timestamp if segments have timestamps
            item.classList.add('active');
            setTimeout(() => item.classList.remove('active'), 200);
        });
    });
}

function displayTakeaways(takeaways) {
    if (!takeaways || takeaways.length === 0) {
        takeawaysList.innerHTML = '<p class="placeholder-text">No takeaways generated</p>';
        return;
    }

    takeawaysList.innerHTML = takeaways.map((t, i) => `
        <div class="takeaway-item">${i + 1}. ${t}</div>
    `).join('');
}

async function regenerateChapters() {
    if (!currentData.transcript) {
        alert('No transcript to process');
        return;
    }

    showLoading('Regenerating chapters and takeaways...');

    try {
        const response = await fetch(`${API_BASE}/api/regenerate-chapters`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                transcript: currentData.transcript,
                segments: currentData.segments,
                title: currentData.title
            })
        });

        if (!response.ok) {
            throw new Error('Failed to regenerate');
        }

        const result = await response.json();
        currentData.chapters = result.chapters || [];
        currentData.takeaways = result.takeaways || [];

        displayChapters(currentData.chapters);
        displayTakeaways(currentData.takeaways);

        hideLoading();
        statusText.textContent = 'Chapters regenerated';

    } catch (error) {
        hideLoading();
        alert('Error: ' + error.message);
    }
}

async function exportDocument(format) {
    const transcript = editor.innerText || editor.textContent;

    if (!transcript || transcript.includes('Paste a YouTube')) {
        alert('No content to export. Please transcribe a video first.');
        return;
    }

    showLoading(`Exporting as ${format.toUpperCase()}...`);

    try {
        const response = await fetch(`${API_BASE}/api/export`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: titleEditor.textContent || 'Transcript',
                chapters: currentData.chapters,
                takeaways: currentData.takeaways,
                transcript: transcript,
                format: format,
                font_name: fontFamily.value,
                font_size: parseInt(fontSize.value),
                highlights: currentData.highlights,
                thumbnail_path: currentData.thumbnail_path,
                channel: currentData.channel
            })
        });

        if (!response.ok) {
            throw new Error('Export failed');
        }

        // Download the file
        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${(titleEditor.textContent || 'transcript').slice(0, 50)}.${format}`;
        document.body.appendChild(a);
        a.click();
        window.URL.revokeObjectURL(url);
        a.remove();

        hideLoading();
        statusText.textContent = `Exported as ${format.toUpperCase()}`;

    } catch (error) {
        hideLoading();
        alert('Export error: ' + error.message);
    }
}

function applyFontFamily() {
    document.execCommand('fontName', false, fontFamily.value);
    editor.style.fontFamily = fontFamily.value;
}

function applyFontSize() {
    // execCommand fontSize only supports 1-7, so we use CSS
    const selection = window.getSelection();
    if (selection.rangeCount > 0) {
        const range = selection.getRangeAt(0);
        if (!range.collapsed) {
            const span = document.createElement('span');
            span.style.fontSize = fontSize.value + 'pt';
            range.surroundContents(span);
        }
    }
    editor.style.fontSize = fontSize.value + 'pt';
}

function applyFormatCommand(command, value = null) {
    // Save selection
    const selection = window.getSelection();
    if (!selection.rangeCount) return;

    const range = selection.getRangeAt(0);

    // Make sure we're in the editor
    if (!editor.contains(range.commonAncestorContainer)) {
        return;
    }

    // Execute the command
    document.execCommand(command, false, value);
}

function applyHighlight(color) {
    const selection = window.getSelection();
    if (!selection.rangeCount) return;

    const range = selection.getRangeAt(0);

    // Make sure we're in the editor and have selected text
    if (!editor.contains(range.commonAncestorContainer)) {
        statusText.textContent = 'Click inside the text first, then select text to highlight';
        return;
    }

    if (range.collapsed) {
        statusText.textContent = 'Select some text first to apply highlight';
        return;
    }

    // Manual approach: wrap selection in a span with background color
    try {
        if (color === null) {
            // Remove highlight - try to unwrap or set transparent
            const selectedText = range.extractContents();
            const tempDiv = document.createElement('div');
            tempDiv.appendChild(selectedText);

            // Remove any highlight spans
            tempDiv.querySelectorAll('span[style*="background"]').forEach(span => {
                span.style.backgroundColor = '';
            });

            range.insertNode(tempDiv.firstChild || document.createTextNode(tempDiv.textContent));
        } else {
            // Create highlight span
            const span = document.createElement('span');
            span.style.backgroundColor = color;
            span.style.padding = '0 2px';

            // Wrap the selection
            range.surroundContents(span);
        }

        // Clear selection
        selection.removeAllRanges();
        statusText.textContent = color ? 'Highlight applied' : 'Highlight removed';

    } catch (e) {
        // Fallback: try execCommand
        if (color) {
            document.execCommand('backColor', false, color);
        } else {
            document.execCommand('removeFormat', false, null);
        }
    }
}

function updateWordCount() {
    const text = editor.innerText || editor.textContent || '';
    const words = text.trim().split(/\s+/).filter(w => w.length > 0);
    wordCount.textContent = `Words: ${words.length}`;
}

function showLoading(message) {
    loadingMessage.textContent = message;
    loadingProgressFill.style.width = '0%';
    loadingOverlay.classList.add('show');
    progressSection.style.display = 'flex';
    // Add percentage to loading dialog
    const percentSpan = document.getElementById('loadingPercent');
    if (percentSpan) percentSpan.textContent = '0%';
}

function hideLoading() {
    loadingOverlay.classList.remove('show');
    progressSection.style.display = 'none';
}

function updateProgress(percent, message) {
    // Update loading dialog message
    loadingMessage.textContent = message;
    loadingProgressFill.style.width = percent + '%';

    // Update large percentage display
    const loadingPercent = document.getElementById('loadingPercent');
    if (loadingPercent) {
        loadingPercent.textContent = percent + '%';
    }

    // Update status bar
    progressFill.style.width = percent + '%';
    progressText.textContent = percent + '%';
    statusText.textContent = `${message} - ${percent}%`;
}

function isValidUrl(string) {
    try {
        new URL(string);
        return true;
    } catch (_) {
        return false;
    }
}
