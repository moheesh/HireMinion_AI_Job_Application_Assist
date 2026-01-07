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
        self._url_index = None  # Cached index for O(1) lookups
    
    def _get_valid_columns(self) -> set:
        """Fetch valid columns from Supabase table schema (cached)."""
        if self.valid_columns is not None:
            return self.valid_columns
        
        try:
            response = self.client.table("jobs").select("*").limit(1).execute()
            if response.data:
                self.valid_columns = set(response.data[0].keys())
            else:
                self.valid_columns = {
                    "id", "company", "role", "location", "work_type", "job_number",
                    "min_salary", "max_salary", "required_skills", "nice_to_have",
                    "experience_years", "clearance", "url", "posted_date",
                    "short_description", "min_qualification", "scraped_at",
                    "ingested_at", "machine_id", "raw_content"
                }
        except:
            self.valid_columns = set()
        
        return self.valid_columns
    
    def _get_archive_path(self) -> Path:
        """Get path to JSONL archive file."""
        return RESUME_ARCHIVE_DIR / "archive.jsonl"
    
    def _build_url_index(self) -> set:
        """Build index of all URLs in archive for O(1) lookup."""
        if self._url_index is not None:
            return self._url_index
        
        self._url_index = set()
        archive_file = self._get_archive_path()
        
        if not archive_file.exists():
            return self._url_index
        
        with open(archive_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        record = json.loads(line)
                        if "url" in record:
                            self._url_index.add(record["url"])
                    except json.JSONDecodeError:
                        continue
        
        return self._url_index
    
    def _invalidate_index(self):
        """Invalidate the URL index (call after writes)."""
        self._url_index = None
    
    def _load_raw_content(self) -> str:
        """Load raw content from cleaned.txt file."""
        cleaned_path = DOWNLOADED_DIR / "cleaned.txt"
        if cleaned_path.exists():
            return cleaned_path.read_text(encoding="utf-8")
        return ""
    
    def load_json(self, json_path: str = "downloaded/job_details.json") -> list[dict]:
        """Load job details from JSON file."""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        if isinstance(data, dict):
            data = [data]
        
        return data
    
    def _prepare_for_supabase(self, jobs: list[dict]) -> list[dict]:
        """Filter jobs to only include valid columns for Supabase."""
        valid_cols = self._get_valid_columns()
        cleaned_data = []
        raw_content = self._load_raw_content()
        
        for job in jobs:
            if valid_cols:
                cleaned_job = {k: v for k, v in job.items() if k in valid_cols and k != "id"}
            else:
                cleaned_job = {k: v for k, v in job.items() if k != "id"}
            
            cleaned_job["machine_id"] = self.machine_id
            cleaned_job["ingested_at"] = datetime.now().isoformat()
            cleaned_job["raw_content"] = raw_content
            
            for key in ["required_skills", "nice_to_have"]:
                if key in cleaned_job and isinstance(cleaned_job[key], list):
                    cleaned_job[key] = json.dumps(cleaned_job[key])
            
            cleaned_data.append(cleaned_job)
        
        return cleaned_data
    
    def store(self, json_path: str = "downloaded/job_details.json") -> dict:
        """Store jobs to Supabase with upsert."""
        try:
            raw_jobs = self.load_json(json_path)
            jobs = self._prepare_for_supabase(raw_jobs)
            
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
    
    def mark_applied(self, url: str) -> dict:
        """
        Mark a job as applied. Rewrites the JSONL file (O(n) operation).
        For frequent updates, consider using SQLite instead.
        """
        try:
            archive_file = self._get_archive_path()
            
            if not archive_file.exists():
                return {"success": False, "not_found": True, "error": "No archive exists"}
            
            # Read all records
            records = []
            found = False
            company = "Unknown"
            role = "Unknown"
            
            with open(archive_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        if record.get("url") == url:
                            record["applied"] = True
                            record["applied_at"] = datetime.now().isoformat()
                            found = True
                            company = record.get("job_details", {}).get("company", "Unknown")
                            role = record.get("job_details", {}).get("role", "Unknown")
                        records.append(record)
                    except json.JSONDecodeError:
                        continue
            
            if not found:
                return {"success": False, "not_found": True, "error": "URL not in archive"}
            
            # Rewrite file
            with open(archive_file, "w", encoding="utf-8") as f:
                for record in records:
                    f.write(json.dumps(record) + "\n")
            
            print(f"  ✓ Marked as applied: {company} | {role}")
            return {"success": True, "company": company, "role": role}
            
        except Exception as e:
            print(f"  ✗ Failed to mark as applied: {e}")
            return {"success": False, "error": str(e)}
    
    def archive_resume(
        self,
        job_details_path: str = None,
        tailored_resume_path: str = None
    ) -> dict:
        """
        Archive job details + tailored resume to JSONL file.
        O(1) append operation - only writes one line.
        """
        try:
            job_details_path = Path(job_details_path) if job_details_path else DOWNLOADED_DIR / "job_details.json"
            tailored_resume_path = Path(tailored_resume_path) if tailored_resume_path else DOWNLOADED_DIR / "tailored_resume.json"
            
            RESUME_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
            archive_file = self._get_archive_path()
            
            with open(job_details_path, "r", encoding="utf-8") as f:
                job_details = json.load(f)
            
            url = job_details.get("url")
            if not url:
                print("  ✗ No URL found, skipping local archive")
                return {"success": False, "error": "No URL in job details"}
            
            # O(1) lookup using cached index
            url_index = self._build_url_index()
            if url in url_index:
                print(f"  ✓ Already archived locally")
                return {"success": True, "already_exists": True, "url": url}
            
            tailored_resume = {}
            if tailored_resume_path.exists():
                with open(tailored_resume_path, "r", encoding="utf-8") as f:
                    tailored_resume = json.load(f)
            
            raw_content = self._load_raw_content()
            
            record = {
                "url": url,
                "archived_at": datetime.now().isoformat(),
                "machine_id": self.machine_id,
                "job_details": job_details,
                "tailored_resume": tailored_resume,
                "raw_content": raw_content,
                "applied": False
            }
            
            # O(1) append - just write one line
            with open(archive_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
            
            # Update index
            url_index.add(url)
            
            print(f"  ✓ Archived locally: {job_details.get('company')} | {job_details.get('role')}")
            return {"success": True, "already_exists": False, "url": url}
        except Exception as e:
            print(f"  ✗ Failed to archive locally: {e}")
            return {"success": False, "error": str(e)}
    
    def list_archives(self) -> list[dict]:
        """List all archived resumes with summary info."""
        archive_file = self._get_archive_path()
        if not archive_file.exists():
            return []
        
        results = []
        with open(archive_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    results.append({
                        "url": record.get("url"),
                        "company": record.get("job_details", {}).get("company"),
                        "role": record.get("job_details", {}).get("role"),
                        "archived_at": record.get("archived_at"),
                        "applied": record.get("applied", False),
                        "applied_at": record.get("applied_at")
                    })
                except json.JSONDecodeError:
                    continue
        
        return results
    
    def archive_count(self) -> int:
        """Get count of archived resumes."""
        archive_file = self._get_archive_path()
        if not archive_file.exists():
            return 0
        
        count = 0
        with open(archive_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    count += 1
        return count
    
    def applied_count(self) -> int:
        """Get count of applied jobs."""
        archive_file = self._get_archive_path()
        if not archive_file.exists():
            return 0
        
        count = 0
        with open(archive_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if record.get("applied", False):
                        count += 1
                except json.JSONDecodeError:
                    continue
        return count


if __name__ == "__main__":
    storage = JobStorage()
    
    storage.store("downloaded/job_details.json")
    
    storage.archive_resume(
        job_details_path="downloaded/job_details.json",
        tailored_resume_path="downloaded/tailored_resume.json"
    )
    
    print(f"\nTotal jobs in Supabase: {storage.count()}")
    print(f"Total archived resumes: {storage.archive_count()}")
    print(f"Total applied: {storage.applied_count()}")