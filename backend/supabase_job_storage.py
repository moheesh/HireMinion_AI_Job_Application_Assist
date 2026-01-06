import json
import socket
import hashlib
import os
from datetime import datetime
from pathlib import Path
from supabase import create_client, Client

# ============================================================
# CONFIGURATION - Safe to share (no password!)
# ============================================================
SUPABASE_URL = "https://mubcqeiwkrilzemzpndr.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im11YmNxZWl3a3JpbHplbXpwbmRyIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Njc2ODEyOTcsImV4cCI6MjA4MzI1NzI5N30.aF1FbMmElv6d8q6NI01dCcfiTOFbE63mbrmxgGxb0js"

# Resume archive folder
PROJECT_ROOT = Path(__file__).parent.parent
RESUME_ARCHIVE_DIR = PROJECT_ROOT / "resume_archive"
DOWNLOADED_DIR = PROJECT_ROOT / "downloaded"


class JobStorage:
    def __init__(self):
        self.client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
        self.machine_id = socket.gethostname()
        self.valid_columns = None
    
    def _get_valid_columns(self) -> set:
        """Fetch valid columns from Supabase table schema (cached)."""
        if self.valid_columns is not None:
            return self.valid_columns
        
        try:
            # Get one row to determine columns, or empty result shows columns
            response = self.client.table("jobs").select("*").limit(1).execute()
            if response.data:
                self.valid_columns = set(response.data[0].keys())
            else:
                # Fallback: try inserting empty and parse error, or use known columns
                self.valid_columns = {
                    "id", "company", "role", "location", "work_type", "job_number",
                    "min_salary", "max_salary", "required_skills", "nice_to_have",
                    "experience_years", "clearance", "url", "posted_date",
                    "short_description", "min_qualification", "scraped_at",
                    "ingested_at", "machine_id"
                }
        except:
            self.valid_columns = set()
        
        return self.valid_columns
    
    def load_json(self, json_path: str = "downloaded/job_details.json") -> list[dict]:
        """Load job details from JSON file."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # Handle both single dict and list of dicts
        if isinstance(data, dict):
            data = [data]
        
        return data
    
    def _prepare_for_supabase(self, jobs: list[dict]) -> list[dict]:
        """Filter jobs to only include valid columns for Supabase."""
        valid_cols = self._get_valid_columns()
        cleaned_data = []
        
        for job in jobs:
            # Filter only valid columns (skip 'id' as it's auto-generated)
            if valid_cols:
                cleaned_job = {k: v for k, v in job.items() if k in valid_cols and k != "id"}
            else:
                # If we couldn't get schema, just pass everything and let it fail gracefully
                cleaned_job = {k: v for k, v in job.items() if k != "id"}
            
            # Add metadata
            cleaned_job["machine_id"] = self.machine_id
            cleaned_job["ingested_at"] = datetime.now().isoformat()
            
            # Convert lists to JSON strings for JSONB columns
            for key in ["required_skills", "nice_to_have"]:
                if key in cleaned_job and isinstance(cleaned_job[key], list):
                    cleaned_job[key] = json.dumps(cleaned_job[key])
            
            cleaned_data.append(cleaned_job)
        
        return cleaned_data
    
    def store(self, json_path: str = "downloaded/job_details.json") -> dict:
        """Store jobs to Supabase with upsert (insert or update on conflict)."""
        try:
            raw_jobs = self.load_json(json_path)
            jobs = self._prepare_for_supabase(raw_jobs)
            
            # Upsert - inserts new rows, updates existing ones based on 'url'
            response = self.client.table("jobs").upsert(
                jobs, 
                on_conflict="url"
            ).execute()
            
            print(f"  ✓ Stored {len(jobs)} jobs to Supabase")
            return {"success": True, "count": len(jobs)}
        except Exception:
            print(f"  ✗ Failed to store to Supabase")
            return {"success": False}
    
    def get_all(self, limit: int = 100) -> list[dict]:
        """Retrieve all jobs."""
        response = self.client.table("jobs").select("*").order("ingested_at", desc=True).limit(limit).execute()
        return response.data
    
    def get_by_company(self, company: str) -> list[dict]:
        """Get jobs by company name."""
        response = self.client.table("jobs").select("*").ilike("company", f"%{company}%").execute()
        return response.data
    
    def get_by_role(self, role: str) -> list[dict]:
        """Get jobs by role/title."""
        response = self.client.table("jobs").select("*").ilike("role", f"%{role}%").execute()
        return response.data
    
    def get_recent(self, days: int = 7) -> list[dict]:
        """Get jobs posted in the last N days."""
        from datetime import timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        response = self.client.table("jobs").select("*").gte("posted_date", cutoff).execute()
        return response.data
    
    def count(self) -> int:
        """Get total job count."""
        response = self.client.table("jobs").select("id", count="exact").execute()
        return response.count
    
    def delete_by_url(self, url: str) -> dict:
        """Delete a job by URL."""
        response = self.client.table("jobs").delete().eq("url", url).execute()
        return response
    
    def archive_resume(
        self,
        job_details_path: str = None,
        tailored_resume_path: str = None
    ) -> dict:
        """
        Archive job details + tailored resume to single archive.json file.
        Only appends if URL doesn't already exist.
        
        Returns:
            dict with status info
        """
        try:
            # Default paths
            job_details_path = job_details_path or DOWNLOADED_DIR / "job_details.json"
            tailored_resume_path = tailored_resume_path or DOWNLOADED_DIR / "tailored_resume.json"
            
            # Ensure archive folder exists
            RESUME_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            archive_file = RESUME_ARCHIVE_DIR / "archive.json"
            
            # Load existing archive or create empty dict
            if archive_file.exists():
                with open(archive_file, "r", encoding="utf-8") as f:
                    archive = json.load(f)
            else:
                archive = {}
            
            # Load job details
            with open(job_details_path, "r", encoding="utf-8") as f:
                job_details = json.load(f)
            
            url = job_details.get("url")
            if not url:
                print("  ✗ No URL found, skipping local archive")
                return {"success": False}
            
            # Check if URL already exists
            if url in archive:
                print(f"  ✓ Already archived locally")
                return {"success": True, "already_exists": True, "url": url}
            
            # Load tailored resume
            tailored_resume = {}
            if Path(tailored_resume_path).exists():
                with open(tailored_resume_path, "r", encoding="utf-8") as f:
                    tailored_resume = json.load(f)
            
            # Add to archive (URL is the key)
            archive[url] = {
                "archived_at": datetime.now().isoformat(),
                "machine_id": self.machine_id,
                "job_details": job_details,
                "tailored_resume": tailored_resume
            }
            
            # Save archive
            with open(archive_file, "w", encoding="utf-8") as f:
                json.dump(archive, f, indent=2)
            
            print(f"  ✓ Archived locally: {job_details.get('company')} | {job_details.get('role')}")
            return {"success": True, "already_exists": False, "url": url}
        except Exception:
            print(f"  ✗ Failed to archive locally")
            return {"success": False}
    
    def list_archives(self) -> list[dict]:
        """List all archived resumes with summary info."""
        archive_file = RESUME_ARCHIVE_DIR / "archive.json"
        if not archive_file.exists():
            return []
        
        with open(archive_file, "r", encoding="utf-8") as f:
            archive = json.load(f)
        
        return [
            {
                "url": url,
                "company": data.get("job_details", {}).get("company"),
                "role": data.get("job_details", {}).get("role"),
                "archived_at": data.get("archived_at")
            }
            for url, data in archive.items()
        ]
    
    def archive_count(self) -> int:
        """Get count of archived resumes."""
        archive_file = RESUME_ARCHIVE_DIR / "archive.json"
        if not archive_file.exists():
            return 0
        with open(archive_file, "r", encoding="utf-8") as f:
            return len(json.load(f))


if __name__ == "__main__":
    storage = JobStorage()
    
    # Store jobs from JSON to Supabase
    storage.store("downloaded/job_details.json")
    
    # Archive resume locally (only if not already archived)
    storage.archive_resume(
        job_details_path="downloaded/job_details.json",
        tailored_resume_path="downloaded/tailored_resume.json"
    )
    
    # View counts
    print(f"\nTotal jobs in Supabase: {storage.count()}")
    print(f"Total archived resumes: {storage.archive_count()}")