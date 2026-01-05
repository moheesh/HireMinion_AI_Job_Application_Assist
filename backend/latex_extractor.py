"""
latex_extractor.py - Phase 1: LaTeX → Template + JSON
Processes .tex files in data/ folder using Gemini API
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

# Directory structure (relative to project root)
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
TEMPLATES_DIR = BASE_DIR / "templates"

# Create directories if they don't exist
DATA_DIR.mkdir(exist_ok=True)
TEMPLATES_DIR.mkdir(exist_ok=True)

# ============================================================
# SYSTEM PROMPT
# ============================================================

SYSTEM_PROMPT = """
Convert this LaTeX resume into:
1. A LaTeX TEMPLATE with Jinja2 placeholders (replacing hardcoded content)
2. A JSON file with the extracted content

## Output Format
===TEMPLATE_START===
[LaTeX template code with Jinja2 placeholders]
===TEMPLATE_END===

===DATA_START===
[JSON with extracted content]
===DATA_END===

## Jinja2 Placeholders
- Variables: \\VAR{key}
- Loops: \\BLOCK{for item in list} ... \\BLOCK{endfor}

## Rules
- Keep the EXACT same LaTeX structure, formatting, packages, and styling
- Only replace the CONTENT with Jinja2 placeholders
- Do NOT change margins, spacing, fonts, or any formatting
- Every \\VAR{} must have a matching JSON key
- JSON must be valid syntax

## CRITICAL: Hyperlinks
- Keep \\href{} commands in the TEMPLATE, not in JSON
- Store only the display text and URL separately in JSON if needed
- Example template: \\href{\\VAR{linkedin_url}}{LinkedIn}
- Example JSON: "linkedin_url": "https://linkedin.com/in/username"

## For Skills Section
Store each category as a SINGLE STRING (comma-separated):
```json
"skills": {
  "data_warehousing": "Snowflake, Azure Synapse, Microsoft Fabric",
  "data_processing": "PySpark, Apache Airflow, Azure Data Factory"
}
```
Use in template: \\VAR{skills.data_warehousing}

## For Experience/Projects with Bullets
Store bullets as arrays, use loops:
```json
"experience": [
  {
    "title": "Job Title",
    "company": "Company Name",
    "location": "City, State",
    "start_date": "Jan 2021",
    "end_date": "Dec 2024",
    "bullets": ["First achievement", "Second achievement"]
  }
]
```
Template:
\\BLOCK{for job in experience}
\\textbf{\\VAR{job.title}} \\hfill \\VAR{job.start_date} -- \\VAR{job.end_date}\\\\
\\textit{\\VAR{job.company}} \\hfill \\textit{\\VAR{job.location}}
\\begin{itemize}
\\BLOCK{for bullet in job.bullets}
\\item \\VAR{bullet}
\\BLOCK{endfor}
\\end{itemize}
\\BLOCK{endfor}
"""


# ============================================================
# EXTRACTION FUNCTIONS
# ============================================================

def extract_template_and_data(tex_path: Path) -> tuple[str, dict]:
    """
    Send LaTeX file to Gemini and extract template + JSON data.
    Returns: (latex_template, json_data)
    """
    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=SYSTEM_PROMPT
    )
    
    # Read the LaTeX file
    print(f"  Reading {tex_path.name}...")
    tex_content = tex_path.read_text(encoding="utf-8")
    
    # Generate response
    print(f"  Generating template and extracting data...")
    response = model.generate_content([
        f"""Here is the LaTeX resume to convert:

---LATEX START---
{tex_content}
---LATEX END---

Convert this to a Jinja2 template and JSON data file. Keep ALL formatting exactly the same."""
    ])
    
    text = response.text
    
    # Extract template
    template_match = re.search(
        r"===TEMPLATE_START===\s*(.*?)\s*===TEMPLATE_END===",
        text,
        re.DOTALL
    )
    
    # Extract data
    data_match = re.search(
        r"===DATA_START===\s*(.*?)\s*===DATA_END===",
        text,
        re.DOTALL
    )
    
    if not template_match:
        raise ValueError("Failed to extract template from Gemini response")
    if not data_match:
        raise ValueError("Failed to extract JSON data from Gemini response")
    
    latex_template = template_match.group(1).strip()
    
    # Clean JSON (remove markdown code blocks if present)
    json_str = data_match.group(1).strip()
    json_str = re.sub(r"^```json\s*", "", json_str)
    json_str = re.sub(r"\s*```$", "", json_str)
    
    try:
        json_data = json.loads(json_str)
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in Gemini response: {e}")
    
    return latex_template, json_data


def process_single_tex(tex_path: Path) -> bool:
    """Process a single .tex file. Returns True on success."""
    print(f"\nProcessing: {tex_path.name}")
    
    try:
        # Extract template and data
        template, data = extract_template_and_data(tex_path)
        
        # Generate output filenames
        base_name = tex_path.stem
        
        # Save template
        template_path = TEMPLATES_DIR / f"{base_name}.tex"
        template_path.write_text(template, encoding="utf-8")
        print(f"  ✓ Saved template: {template_path.name}")
        
        # Save JSON data
        json_path = TEMPLATES_DIR / f"{base_name}.json"
        json_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        print(f"  ✓ Saved data: {json_path.name}")
        
        return True
        
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def process_all_tex():
    """Process all .tex files in the data/ folder."""
    tex_files = list(DATA_DIR.glob("*.tex"))
    
    if not tex_files:
        print(f"No .tex files found in {DATA_DIR}")
        return
    
    print(f"Found {len(tex_files)} .tex file(s) to process")
    print(f"Templates directory: {TEMPLATES_DIR}")
    
    success_count = 0
    for tex_path in tex_files:
        if process_single_tex(tex_path):
            success_count += 1
    
    print(f"\n{'='*50}")
    print(f"Completed: {success_count}/{len(tex_files)} files processed successfully")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract Jinja2 templates and JSON data from LaTeX resumes"
    )
    parser.add_argument(
        "--file", "-f",
        help="Process a specific .tex file (default: process all in data/)"
    )
    
    args = parser.parse_args()
    
    print("="*50)
    print("LATEX EXTRACTOR - Phase 1")
    print("="*50)
    
    if args.file:
        tex_path = Path(args.file)
        if not tex_path.exists():
            tex_path = DATA_DIR / args.file
        if not tex_path.exists():
            print(f"Error: File not found: {args.file}")
        else:
            process_single_tex(tex_path)
    else:
        process_all_tex()