chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'scrape') {
    handleScrape(request.options, sendResponse);
    return true;
  }
});

async function handleScrape(options, sendResponse) {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    const url = tab.url;

    const results = await chrome.scripting.executeScript({
      target: { tabId: tab.id },
      func: () => {
        const clone = document.documentElement.cloneNode(true);
        clone.querySelectorAll('script, noscript, style').forEach(el => el.remove());
        return clone.outerHTML;
      }
    });

    const html = results[0].result;

    const response = await fetch('http://localhost:8000/api/save-html', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ html, url, options })
    });

    const data = await response.json();
    sendResponse(data);

  } catch (e) {
    console.error('Scrape error:', e);
    sendResponse({ success: false, error: e.message });
  }
}