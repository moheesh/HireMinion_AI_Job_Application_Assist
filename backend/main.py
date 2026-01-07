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


def validate_job_details(job_details: dict) -> tuple[bool, str]:
    """Validate that job details have required fields."""
    company = job_details.get("company")
    role = job_details.get("role")
    description = job_details.get("short_description")
    
    missing = []
    if not company:
        missing.append("company")
    if not role:
        missing.append("role")
    if not description:
        missing.append("description")
    
    if missing:
        return False, f"This page is not scrapable. Missing: {', '.join(missing)}"
    
    return True, ""


def run_pipeline(options: dict):
    """Run the pipeline based on options."""
    try:
        print("\n" + "="*50)
        print("RUNNING PIPELINE")
        print("="*50)
        
        generate_resume = options.get("resume", False)
        generate_cover = options.get("coverLetter", False)
        
        # Step 1: Clean HTML
        print("\n[1/4] Cleaning HTML...")
        clean_result = clean_file()
        print(f"  ✔ Cleaned: {clean_result['text_path']}")
        
        # Step 2: Tailor with Gemini
        print("\n[2/4] Processing with Gemini...")
        tailor_result = tailor_resume()
        custom_output = tailor_result.get("custom_output")
        
        # Step 3: Validate job details before storing
        print("\n[3/4] Validating job details...")
        job_details_path = os.path.join(DOWNLOADED_DIR, "job_details.json")
        
        if os.path.exists(job_details_path):
            with open(job_details_path, "r", encoding="utf-8") as f:
                job_details = json.load(f)
            
            is_valid, error_msg = validate_job_details(job_details)
            if not is_valid:
                print(f"  ✗ {error_msg}")
                return {
                    "success": False, 
                    "error": error_msg,
                    "custom_output": custom_output
                }
            print("  ✔ Job details validated")
            
            # Store to Supabase + local archive
            job_storage.store(job_details_path)
            print("  ✔ Stored to Supabase")
            
            tailored_resume_path = os.path.join(DOWNLOADED_DIR, "tailored_resume.json")
            if os.path.exists(tailored_resume_path):
                job_storage.archive_resume(job_details_path, tailored_resume_path)
        else:
            print("  ⚠ No job_details.json found")
            return {
                "success": False,
                "error": "This page is not scrapable. No job details extracted.",
                "custom_output": custom_output
            }
        
        # Step 4: Compile to PDF only if resume is checked
        pdf_path = None
        if generate_resume:
            print("\n[4/4] Compiling PDF...")
            pdf_path = auto_compile()
            
            if pdf_path:
                print(f"  ✔ PDF generated: {pdf_path}")
            else:
                print("  ✗ PDF compilation failed")
                return {
                    "success": False, 
                    "error": "PDF compilation failed",
                    "custom_output": custom_output
                }
        else:
            print("\n[4/4] Skipping PDF compilation (resume not selected)")
        
        print("\n" + "="*50)
        print("Pipeline complete!")
        print("="*50)
        
        return {
            "success": True, 
            "pdf_path": str(pdf_path) if pdf_path else None,
            "custom_output": custom_output
        }
            
    except Exception as e:
        print(f"\n✗ Pipeline error: {e}")
        return {"success": False, "error": str(e)}


@app.post("/api/save-html")
async def save_html(req: ScrapeRequest, background_tasks: BackgroundTasks):
    """Save HTML and run pipeline"""
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
        
        print(f"✔ Saved HTML to {html_path}")
        print(f"✔ Saved metadata: {metadata}")
        
        # Run pipeline with options
        result = run_pipeline(req.options)
        
        return {
            "success": result["success"],
            "message": "Pipeline complete" if result["success"] else result.get("error", "Unknown error"),
            "error": result.get("error") if not result["success"] else None,
            "metadata": metadata,
            "pdf_path": result.get("pdf_path"),
            "custom_output": result.get("custom_output")
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/run-pipeline")
async def run_pipeline_endpoint():
    """Manually trigger the pipeline"""
    # Load options from metadata
    meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
    options = {}
    if os.path.exists(meta_path):
        with open(meta_path, "r") as f:
            metadata = json.load(f)
            options = metadata.get("options", {})
    
    result = run_pipeline(options)
    return result


@app.post("/api/mark-applied")
async def mark_applied():
    """Mark current job as applied in local archive."""
    try:
        meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
        
        # Get current URL from metadata
        if not os.path.exists(meta_path):
            return {"success": False, "no_metadata": True, "error": "No metadata found. Scrape a page first."}
        
        with open(meta_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
        
        url = metadata.get("url")
        if not url:
            return {"success": False, "no_metadata": True, "error": "No URL in metadata"}
        
        # Try to mark as applied in archive
        result = job_storage.mark_applied(url)
        
        return result
        
    except Exception as e:
        return {"success": False, "error": str(e)}


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


@app.get("/api/custom-output")
async def get_custom_output():
    """Get the custom prompt output"""
    try:
        custom_path = os.path.join(DOWNLOADED_DIR, "custom_output.json")
        if os.path.exists(custom_path):
            with open(custom_path, "r", encoding="utf-8") as f:
                return {"success": True, "data": json.load(f)}
        return {"success": False, "error": "No custom output found"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/status")
async def get_status():
    """Get current pipeline status"""
    meta_path = os.path.join(DOWNLOADED_DIR, "metadata.json")
    tailored_path = os.path.join(DOWNLOADED_DIR, "tailored_resume.json")
    job_details_path = os.path.join(DOWNLOADED_DIR, "job_details.json")
    custom_output_path = os.path.join(DOWNLOADED_DIR, "custom_output.json")
    
    status = {
        "has_metadata": os.path.exists(meta_path),
        "has_tailored_resume": os.path.exists(tailored_path),
        "has_job_details": os.path.exists(job_details_path),
        "has_custom_output": os.path.exists(custom_output_path),
        "output_pdfs": [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.pdf')] if os.path.exists(OUTPUT_DIR) else []
    }
    
    if status["has_metadata"]:
        with open(meta_path, "r") as f:
            status["metadata"] = json.load(f)
    
    if status["has_job_details"]:
        with open(job_details_path, "r") as f:
            status["job_details"] = json.load(f)
    
    if status["has_custom_output"]:
        with open(custom_output_path, "r", encoding="utf-8") as f:
            status["custom_output"] = json.load(f)
    
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