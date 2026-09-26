// Workspace - tab switching, shared URL box and shared video-info fetch
// used by the Thumbnail Studio and Video Analytics tabs.

const VIEW_TITLES = {
    transcriber: 'TLDR.video - Transcriber',
    thumbnail: 'TLDR.video - Thumbnail Studio',
    analytics: 'TLDR.video - Video Analytics'
};

// Last fetched /api/video-info result, shared by both tabs
let videoInfoCache = { url: '', data: null };

document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.workspace-tab').forEach(tab => {
        tab.addEventListener('click', () => switchView(tab.dataset.view));
    });

    // Keep the URL box the same on every tab
    const urlInputs = document.querySelectorAll('.shared-url');
    urlInputs.forEach(input => {
        input.addEventListener('input', () => {
            urlInputs.forEach(other => {
                if (other !== input) other.value = input.value;
            });
        });
    });

    try {
        const saved = localStorage.getItem('tldr.activeView');
        if (saved && VIEW_TITLES[saved]) switchView(saved);
    } catch (e) { /* storage unavailable */ }
});

function switchView(view) {
    document.querySelectorAll('.workspace-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.view === view);
    });
    document.querySelectorAll('.view').forEach(el => {
        el.classList.toggle('active', el.id === `view-${view}`);
    });
    document.querySelectorAll('.transcriber-only').forEach(el => {
        el.style.display = view === 'transcriber' ? '' : 'none';
    });
    document.getElementById('windowTitle').textContent = VIEW_TITLES[view];
    try { localStorage.setItem('tldr.activeView', view); } catch (e) { /* ignore */ }

    if (view === 'thumbnail' && typeof drawThumbnail === 'function') drawThumbnail();
}

function getSharedUrl() {
    const active = document.querySelector('.view.active .shared-url');
    return (active ? active.value : document.getElementById('urlInput').value).trim();
}

/**
 * Fetch thumbnail + analytics for a URL (cached, so switching tabs doesn't refetch).
 * Returns the data or null on failure (after telling the user).
 */
async function fetchVideoInfo(url, { force = false } = {}) {
    if (!url) {
        alert('Please enter a YouTube URL');
        return null;
    }
    if (!isValidUrl(url)) {
        alert('Please enter a valid URL');
        return null;
    }
    if (!force && videoInfoCache.url === url && videoInfoCache.data) {
        return videoInfoCache.data;
    }

    const header = document.querySelector('.loading-header');
    const previousHeader = header.textContent;
    header.textContent = 'Fetching Video Info...';
    showLoading('Reading video details from YouTube...');
    updateProgress(40, 'Reading video details');

    try {
        const response = await fetch(`${API_BASE}/api/video-info`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        if (!response.ok) {
            let detail = 'Failed to fetch video info';
            try { detail = (await response.json()).detail || detail; } catch (e) { /* not JSON */ }
            throw new Error(detail);
        }
        const data = await response.json();
        videoInfoCache = { url, data };

        // Populate both tabs from one fetch
        if (data.thumbnail_filename && typeof loadStudioThumbnail === 'function') {
            loadStudioThumbnail(data.thumbnail_filename, {
                title: data.video.title,
                channel: data.video.channel
            });
        }
        if (typeof renderAnalytics === 'function') renderAnalytics(data);

        statusText.textContent = `Loaded: ${data.video.title}`;
        return data;
    } catch (error) {
        statusText.textContent = 'Error: ' + error.message;
        alert('Error: ' + error.message);
        return null;
    } finally {
        hideLoading();
        header.textContent = previousHeader;
    }
}

// Shared helpers
function escapeHtml(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
}

function slugify(text) {
    return (text || 'thumbnail').replace(/[^a-zA-Z0-9]+/g, '_').replace(/^_|_$/g, '').slice(0, 60) || 'thumbnail';
}
