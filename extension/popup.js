const outputBox = document.getElementById('outputBox');
const resumeSelect = document.getElementById('resumeSelect');
const chkCustomPrompt = document.getElementById('chkCustomPrompt');
const customPromptBox = document.getElementById('customPromptBox');
const progressContainer = document.getElementById('progressContainer');
const progressText = document.getElementById('progressText');
const spinner = document.getElementById('spinner');

let resumes = [];

// === PERSISTENCE ===
function saveState() {
  chrome.storage.local.set({
    ui: {
      output: outputBox.value,
      selectedResume: resumeSelect.value,
      customPromptText: customPromptBox.value
    }
  });
}

async function loadState() {
  const { ui } = await chrome.storage.local.get('ui');
  if (!ui) return;
  
  outputBox.value = ui.output || '';
  customPromptBox.value = ui.customPromptText || '';
  
  if (ui.selectedResume) {
    resumeSelect.value = ui.selectedResume;
  }
}
// === END PERSISTENCE ===

function setOutput(text) {
  outputBox.value = text;
  saveState();
}

function clearOutput() {
  outputBox.value = '';
  saveState();
}

function showProgress(message = 'Processing...') {
  progressContainer.style.display = 'block';
  progressContainer.className = '';
  spinner.style.display = 'block';
  progressText.textContent = message;
}

function showError(message) {
  progressContainer.style.display = 'block';
  progressContainer.className = 'error';
  spinner.style.display = 'none';
  progressText.textContent = message;
}

function showSuccess(message = 'Complete!') {
  progressContainer.style.display = 'block';
  progressContainer.className = 'success';
  spinner.style.display = 'none';
  progressText.textContent = message;
}

function hideProgress() {
  progressContainer.style.display = 'none';
}

function setButtons(disabled) {
  document.querySelectorAll('button').forEach(btn => btn.disabled = disabled);
}

// Toggle custom prompt textarea
chkCustomPrompt.addEventListener('change', () => {
  customPromptBox.style.display = chkCustomPrompt.checked ? 'block' : 'none';
});

// Save on changes
resumeSelect.addEventListener('change', saveState);
customPromptBox.addEventListener('input', saveState);

// Fetch available resumes on load
async function loadResumes() {
  try {
    const response = await fetch('http://localhost:8000/api/list-resumes');
    const data = await response.json();
    if (data.success && data.resumes.length > 0) {
      resumes = data.resumes;
      resumeSelect.innerHTML = '<option value="">Select a resume...</option>';
      resumes.forEach(r => {
        const option = document.createElement('option');
        option.value = r;
        option.textContent = r.replace('.tex', '');
        resumeSelect.appendChild(option);
      });
    } else {
      resumeSelect.innerHTML = '<option value="">No resumes found</option>';
    }
  } catch (e) {
    console.error('Failed to load resumes:', e);
    resumeSelect.innerHTML = '<option value="">Failed to load resumes</option>';
  }
}

// Start Scrape & Run Pipeline
document.getElementById('scrapeBtn').addEventListener('click', async () => {
  // Validate resume selection (required)
  const selectedResume = resumeSelect.value;
  if (!selectedResume) {
    showError('Please select a resume');
    return;
  }

  const options = {
    resume: document.getElementById('chkResume').checked,
    resumeFile: selectedResume,
    coverLetter: document.getElementById('chkCover').checked,
    customPrompt: chkCustomPrompt.checked ? customPromptBox.value : null
  };

  setButtons(true);
  clearOutput();
  showProgress('Processing...');

  try {
    const response = await chrome.runtime.sendMessage({ action: 'scrape', options });
    
    if (response.success) {
      showSuccess('Complete!');
      
      let output = '';
      
      if (response.pdf_path) {
        const pdfName = response.pdf_path.split('/').pop();
        output += `📄 PDF: http://localhost:8000/api/download-pdf/${pdfName}\n\n`;
      }
      
      if (response.custom_output) {
        output += '--- Custom Output ---\n';
        output += response.custom_output;
      }
      
      if (output) {
        setOutput(output);
      }
    } else {
      showError(response.error || response.message || 'Unknown error');
      if (response.error_details) {
        setOutput(response.error_details);
      }
    }
  } catch (e) {
    showError('Connection failed');
    setOutput(e.message);
  }

  setButtons(false);
});

// Store Information - Mark as applied
document.getElementById('storeBtn').addEventListener('click', async () => {
  const selectedResume = resumeSelect.value;
  if (!selectedResume) {
    showError('Please select a resume');
    return;
  }

  setButtons(true);
  clearOutput();
  showProgress('Marking as applied...');

  try {
    // First try to mark as applied directly
    const response = await fetch('http://localhost:8000/api/mark-applied', {
      method: 'POST'
    });
    const data = await response.json();

    if (data.success) {
      showSuccess('Marked as applied!');
      setOutput(`${data.company} | ${data.role}`);
    } else if (data.not_found || data.no_metadata) {
      // URL not in archive or no metadata, need to scrape first
      showProgress('Scraping page first...');
      
      // Run scrape with all checkboxes off (just job details)
      const scrapeResponse = await chrome.runtime.sendMessage({
        action: 'scrape',
        options: {
          resume: false,
          resumeFile: selectedResume,
          coverLetter: false,
          customPrompt: null
        }
      });

      if (scrapeResponse.success) {
        // Now mark as applied
        const retryResponse = await fetch('http://localhost:8000/api/mark-applied', {
          method: 'POST'
        });
        const retryData = await retryResponse.json();

        if (retryData.success) {
          showSuccess('Scraped & marked as applied!');
          setOutput(`${retryData.company} | ${retryData.role}`);
        } else {
          showError(retryData.error || 'Failed to mark as applied');
        }
      } else {
        showError(scrapeResponse.error || 'Failed to scrape page');
      }
    } else {
      showError(data.error || 'Failed to mark as applied');
    }
  } catch (e) {
    showError('Connection failed');
    setOutput(e.message);
  }

  setButtons(false);
});

// Clear All
document.getElementById('clearBtn').addEventListener('click', async () => {
  setButtons(true);
  showProgress('Clearing...');
  
  try {
    const response = await fetch('http://localhost:8000/api/clear', { method: 'DELETE' });
    const data = await response.json();
    if (data.success) {
      showSuccess('Cleared all files');
      clearOutput();
      resumeSelect.value = '';
      customPromptBox.value = '';
      chrome.storage.local.remove('ui');
    } else {
      showError(data.error);
    }
  } catch (e) {
    showError(e.message);
  }
  
  setButtons(false);
});

// Load resumes on popup open, then restore state
loadResumes().then(() => loadState());