"""
gemini_client.py - Tailor resume, cover letter, LinkedIn message based on job description
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

genai.configure(api_key=GEMINI_API_KEY)

# Directory structure
BASE_DIR = Path(__file__).parent.parent
DOWNLOADED_DIR = BASE_DIR / "downloaded"
TEMPLATES_DIR = BASE_DIR / "templates"
PROMPTS_DIR = Path(__file__).parent / "prompts"

# ============================================================
# LOAD PROMPT
# ============================================================

def load_prompt(name: str) -> str:
    """Load prompt from prompts folder."""
    prompt_path = PROMPTS_DIR / f"{name}.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt not found: {prompt_path}")


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json_file(path: Path) -> dict:
    """Load JSON file, return empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def save_json_file(path: Path, data: dict):
    """Save dict as JSON file."""
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  ✓ Saved: {path.name}")


def extract_json_block(text: str, start_marker: str, end_marker: str) -> dict:
    """Extract JSON from between markers."""
    pattern = rf"{re.escape(start_marker)}\s*(.*?)\s*{re.escape(end_marker)}"
    match = re.search(pattern, text, re.DOTALL)
    
    if not match:
        return {}
    
    json_str = match.group(1).strip()
    json_str = re.sub(r"^```json\s*", "", json_str)
    json_str = re.sub(r"\s*```$", "", json_str)
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return {}


def get_option(metadata: dict, key: str) -> bool:
    """Safely get option flag from metadata."""
    options = metadata.get("options", {})
    return options.get(key, False)


# ============================================================
# MAIN FUNCTION
# ============================================================

def tailor_resume():
    """Main function to tailor resume based on job description."""
    
    print("="*50)
    print("GEMINI CLIENT - Resume Tailor")
    print("="*50)
    
    # Load input files
    print("\nLoading input files...")
    
    metadata = load_json_file(DOWNLOADED_DIR / "metadata.json")
    if not metadata:
        print("  ✗ metadata.json not found")
        return
    print("  ✓ metadata.json")
    
    job_description = (DOWNLOADED_DIR / "cleaned.txt").read_text(encoding="utf-8")
    print("  ✓ cleaned.txt")
    
    # Get template filename from metadata
    resume_file = metadata.get("options", {}).get("resumeFile", "")
    template_name = Path(resume_file).stem if resume_file else ""
    template_resume = {}
    
    if template_name:
        template_resume = load_json_file(TEMPLATES_DIR / f"{template_name}.json")
        print(f"  {'✓' if template_resume else '✗'} {template_name}.json (template)")
    
    # Determine what to generate
    generate_resume = get_option(metadata, "resume")
    generate_cover = get_option(metadata, "coverLetter")
    generate_linkedin = get_option(metadata, "linkedin")
    
    print(f"\nGeneration flags:")
    print(f"  Resume: {generate_resume}")
    print(f"  Cover Letter: {generate_cover}")
    print(f"  LinkedIn: {generate_linkedin}")
    print(f"  Job Details: Always")
    
    # Build prompt
    prompt = f"""
## JOB DESCRIPTION
{job_description}

## JOB URL
{metadata.get("url", "Not provided")}

## SCRAPED AT
{metadata.get("scraped_at", "Not provided")}

## TEMPLATE RESUME (Match this structure exactly)
{json.dumps(template_resume, indent=2) if template_resume else "Not provided"}

## GENERATION FLAGS
- Generate tailored resume: {generate_resume}
- Generate cover letter: {generate_cover}
- Generate LinkedIn message: {generate_linkedin}
- Generate job details: True

## INSTRUCTIONS
1. Always extract job details
2. If a generation flag is False, output empty JSON {{}} for that section
3. If a generation flag is True, generate the full content
4. For tailored resume: maintain EXACT same structure as template, only modify allowed sections
5. Respect word limits - do not exceed original word count for any field

Generate all four outputs now.
"""
    
    # Call Gemini
    print("\nCalling Gemini API...")
    
    system_prompt = load_prompt("tailor_resume")
    
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=system_prompt
    )
    
    response = model.generate_content(prompt)
    text = response.text
    
    # Extract outputs
    print("\nExtracting outputs...")
    
    job_details = extract_json_block(text, "===JOB_DETAILS_START===", "===JOB_DETAILS_END===")
    tailored_resume = extract_json_block(text, "===TAILORED_RESUME_START===", "===TAILORED_RESUME_END===")
    tailored_cover = extract_json_block(text, "===TAILORED_COVER_START===", "===TAILORED_COVER_END===")
    linkedin_message = extract_json_block(text, "===LINKEDIN_MESSAGE_START===", "===LINKEDIN_MESSAGE_END===")
    
    # Save outputs
    print("\nSaving outputs...")
    
    save_json_file(DOWNLOADED_DIR / "job_details.json", job_details)
    save_json_file(DOWNLOADED_DIR / "tailored_resume.json", tailored_resume)
    save_json_file(DOWNLOADED_DIR / "tailored_cover.json", tailored_cover)
    save_json_file(DOWNLOADED_DIR / "linkedin_message.json", linkedin_message)
    
    print("\n" + "="*50)
    print("Complete!")
    print("="*50)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    tailor_resume()