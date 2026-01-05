const status = document.getElementById('status');
const controls = document.getElementById('controls');
const resumeSelectContainer = document.getElementById('resumeSelectContainer');
const resumeSelect = document.getElementById('resumeSelect');
const chkResume = document.getElementById('chkResume');

let resumes = [];

function setStatus(text, type = '') {
  status.innerHTML = text;
  status.className = type;
}

function setButtons(disabled) {
  document.querySelectorAll('button').forEach(btn => btn.disabled = disabled);
}

// Fetch available resumes on load
async function loadResumes() {
  try {
    const response = await fetch('http://localhost:8000/api/list-resumes');
    const data = await response.json();
    if (data.success) {
      resumes = data.resumes;
      resumeSelect.innerHTML = '<option value="">Select a resume...</option>';
      resumes.forEach(r => {
        const option = document.createElement('option');
        option.value = r;
        option.textContent = r.replace('.tex', '');
        resumeSelect.appendChild(option);
      });
    }
  } catch (e) {
    console.error('Failed to load resumes:', e);
  }
}

// Show/hide resume dropdown based on checkbox
chkResume.addEventListener('change', () => {
  if (chkResume.checked && resumes.length > 0) {
    resumeSelectContainer.classList.remove('hidden');
  } else {
    resumeSelectContainer.classList.add('hidden');
  }
});

// Start Scrape & Run Pipeline
document.getElementById('scrapeBtn').addEventListener('click', async () => {
  const wantResume = chkResume.checked;
  
  // Validate resume selection
  let selectedResume = '';
  if (wantResume) {
    if (resumes.length === 0) {
      setStatus('✗ No resumes found in data folder', 'error');
      return;
    } else if (resumes.length === 1) {
      selectedResume = resumes[0];
    } else {
      selectedResume = resumeSelect.value;
      if (!selectedResume) {
        setStatus('✗ Please select a resume', 'error');
        return;
      }
    }
  }

  const options = {
    resume: wantResume,
    resumeFile: selectedResume,
    coverLetter: document.getElementById('chkCover').checked,
    linkedin: document.getElementById('chkLinkedin').checked
  };

  setButtons(true);
  setStatus('🔄 Step 1/4: Scraping page...', 'info');

  try {
    // Send scrape request
    const response = await chrome.runtime.sendMessage({ action: 'scrape', options });
    
    if (response.success) {
      const pdfName = response.pdf_path ? response.pdf_path.split('/').pop() : null;
      
      let statusHtml = '✓ Pipeline complete!<br>';
      if (pdfName) {
        statusHtml += `📄 <a href="http://localhost:8000/api/download-pdf/${pdfName}" target="_blank">Download PDF</a>`;
      }
      
      setStatus(statusHtml, 'success');
    } else {
      setStatus('✗ ' + (response.error || response.message), 'error');
    }
  } catch (e) {
    setStatus('✗ ' + e.message, 'error');
  }

  setButtons(false);
});

// Store Information
document.getElementById('storeBtn').addEventListener('click', async () => {
  setButtons(true);
  setStatus('Storing...', 'info');
  // TODO: Implement store to parquet
  setStatus('✓ Stored (not implemented)', 'success');
  setButtons(false);
});

// Clear All
document.getElementById('clearBtn').addEventListener('click', async () => {
  setButtons(true);
  setStatus('Clearing...', 'info');
  
  try {
    const response = await fetch('http://localhost:8000/api/clear', { method: 'DELETE' });
    const data = await response.json();
    if (data.success) {
      setStatus('✓ Cleared all files', 'success');
    } else {
      setStatus('✗ ' + data.error, 'error');
    }
  } catch (e) {
    setStatus('✗ ' + e.message, 'error');
  }
  
  setButtons(false);
});

// Load resumes on popup open
loadResumes();