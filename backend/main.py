"""
main.py - FastAPI backend for Resume Tailor
Handles scraping, cleaning, tailoring, and PDF generation
"""

import os
import json
from datetime import datetime
from urllib.parse import urlparse
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Import pipeline modules
from cleaning import clean_file
from gemini_client import tailor_resume
from latex_compiler import auto_compile
from supabase_job_storage import JobStorage

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOWNLOADED_DIR = os.path.join(PROJECT_ROOT, "downloaded")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
DATA_DIR = os.path.join(PROJECT_ROOT, "data")

os.makedirs(DOWNLOADED_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(DATA_DIR, exist_ok=True)

# Initialize Supabase storage
job_storage = JobStorage()


class ScrapeRequest(BaseModel):
    html: str
    url: str = ""
    options: dict = {}


def run_pipeline():
    """Run the full pipeline: clean → tailor → store → compile"""
    try:
        print("\n" + "="*50)
        print("RUNNING FULL PIPELINE")
        print("="*50)
        
        # Step 1: Clean HTML
        print("\n[1/4] Cleaning HTML...")
        clean_result = clean_file()
        print(f"  ✓ Cleaned: {clean_result['text_path']}")
        
        # Step 2: Tailor resume with Gemini
        print("\n[2/4] Tailoring with Gemini...")
        tailor_resume()
        
        # Step 3: Store job details to Supabase + local archive
        print("\n[3/4] Storing job...")
        job_details_path = os.path.join(DOWNLOADED_DIR, "job_details.json")
        tailored_resume_path = os.path.join(DOWNLOADED_DIR, "tailored_resume.json")
        
        if os.path.exists(job_details_path):
            # Online: Supabase
            job_storage.store(job_details_path)
            print("  ✓ Stored to Supabase")
            
            # Local: archive.json
            job_storage.archive_resume(job_details_path, tailored_resume_path)
        else:
            print("  ⚠ No job_details.json found, skipping storage")
        
        # Step 4: Compile to PDF
        print("\n[4/4] Compiling PDF...")
        pdf_path = auto_compile()
        
        if pdf_path:
            print(f"\n✓ Pipeline complete! Output: {pdf_path}")
            return {"success": True, "pdf_path": str(pdf_path)}
        else:
            print("\n✗ PDF compilation failed")
            return {"success": False, "error": "PDF compilation failed"}
            
    except Exception as e:
        print(f"\n✗ Pipeline error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/save-html")
async def save_html(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Save HTML and run full pipeline"""
    try:
        html_path = os.path.join(DOWNLOADED_DIR, "html_snapshot.html")
        meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
        
        parsed_url = urlparse(req.url)
        
        metadata = {
            "url": req.url,
            "domain": parsed_url.netloc,
            "scraped_at": datetime.now().isoformat(),
            "options": req.options
        }
        
        # Save HTML
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(req.html)
        
        # Save metadata
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
        
        print(f"✓ Saved HTML to {html_path}")
        print(f"✓ Saved metadata: {metadata}")
        
        # Run pipeline
        result = run_pipeline()
        
        return {
            "success": result["success"],
            "message": "Pipeline complete" if result["success"] else result.get("error", "Unknown error"),
            "metadata": metadata,
            "pdf_path": result.get("pdf_path")
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/run-pipeline")
async def run_pipeline_endpoint():
    """Manually trigger the pipeline"""
    result = run_pipeline()
    return result


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/list-resumes")
async def list_resumes():
    """List available resume .tex files in data folder"""
    try:
        resumes = [f for f in os.listdir(DATA_DIR) if f.endswith('.tex')]
        return {"success": True, "resumes": resumes}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/download-pdf/{filename}")
async def download_pdf(filename: str):
    """Download generated PDF"""
    pdf_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(pdf_path):
        return FileResponse(pdf_path, media_type="application/pdf", filename=filename)
    return {"success": False, "error": "PDF not found"}


@app.get("/api/status")
async def get_status():
    """Get current pipeline status"""
    meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
    tailored_path = os.path.join(DOWNLOADED_DIR, "tailored_resume.json")
    job_details_path = os.path.join(DOWNLOADED_DIR, "job_details.json")
    
    status = {
        "has_metadata": os.path.exists(meta_path),
        "has_tailored_resume": os.path.exists(tailored_path),
        "has_job_details": os.path.exists(job_details_path),
        "output_pdfs": [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.pdf')] if os.path.exists(OUTPUT_DIR) else []
    }
    
    if status["has_metadata"]:
        with open(meta_path, "r") as f:
            status["metadata"] = json.load(f)
    
    if status["has_job_details"]:
        with open(job_details_path, "r") as f:
            status["job_details"] = json.load(f)
    
    return status


@app.get("/api/jobs")
async def get_jobs(limit: int = 100):
    """Get all stored jobs from Supabase"""
    try:
        jobs = job_storage.get_all(limit=limit)
        return {"success": True, "count": len(jobs), "jobs": jobs}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/jobs/count")
async def get_job_count():
    """Get total job count"""
    try:
        count = job_storage.count()
        return {"success": True, "count": count}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/archives")
async def get_archives():
    """Get all locally archived resumes"""
    try:
        archives = job_storage.list_archives()
        return {"success": True, "count": len(archives), "archives": archives}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.delete("/api/clear")
async def clear_downloaded():
    """Clear all files in downloaded folder"""
    try:
        for f in os.listdir(DOWNLOADED_DIR):
            if f != ".keep":
                os.remove(os.path.join(DOWNLOADED_DIR, f))
        return {"success": True, "message": "Cleared downloaded folder"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print(f"🚀 Backend running on port 8000")
    print(f"📁 Project root: {PROJECT_ROOT}")
    uvicorn.run(app, host="0.0.0.0", port=8000)