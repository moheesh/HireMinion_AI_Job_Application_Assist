"""
resume_extractor.py - Extract resume data from PDF using Gemini (Two-Step Approach)
Step 1: Extract JSON data from PDF
Step 2: Generate LaTeX template that visually matches PDF with correct placeholders
"""

import os
import json
import re
from pathlib import Path
from dotenv import load_dotenv
import google.generativeai as genai
import fitz  # PyMuPDF

# Import compiler functions
from latex_compiler import compile_to_pdf, escape_json_data, create_jinja_environment, preprocess_data

# ============================================================
# CONFIGURATION
# ============================================================

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
SAMPLES_DIR = BASE_DIR / "samples"
TEMPLATES_DIR = BASE_DIR / "templates"
OUTPUT_DIR = BASE_DIR / "output"

TEMPLATES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in environment variables")

genai.configure(api_key=GEMINI_API_KEY)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def get_available_pdfs() -> list[Path]:
    """Get all PDF files from data folder."""
    return list(DATA_DIR.glob("*.pdf"))


def get_pdf_by_name(name: str) -> Path:
    """Get specific PDF file from data folder by name."""
    if not name.lower().endswith(".pdf"):
        name = f"{name}.pdf"
    
    pdf_path = DATA_DIR / name
    
    if not pdf_path.exists():
        available = get_available_pdfs()
        available_names = [p.name for p in available]
        raise FileNotFoundError(
            f"PDF '{name}' not found in {DATA_DIR}\n"
            f"Available PDFs: {available_names if available_names else 'None'}"
        )
    
    return pdf_path


def load_sample_json() -> dict:
    """Load sample JSON schema."""
    sample_json_path = SAMPLES_DIR / "resume.json"
    if not sample_json_path.exists():
        raise FileNotFoundError(f"Sample JSON not found: {sample_json_path}")
    return json.loads(sample_json_path.read_text(encoding="utf-8"))


def load_sample_tex() -> str:
    """Load sample LaTeX template."""
    sample_tex_path = SAMPLES_DIR / "resume.tex"
    if not sample_tex_path.exists():
        raise FileNotFoundError(f"Sample LaTeX not found: {sample_tex_path}")
    return sample_tex_path.read_text(encoding="utf-8")


def get_json_keys_flat(data: dict, prefix: str = "") -> set[str]:
    """Recursively get all keys from JSON structure."""
    keys = set()
    if isinstance(data, dict):
        for k, v in data.items():
            full_key = f"{prefix}.{k}" if prefix else k
            keys.add(full_key)
            keys.update(get_json_keys_flat(v, full_key))
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        keys.update(get_json_keys_flat(data[0], prefix))
    return keys


def get_json_structure(data: dict, indent: int = 0) -> str:
    """Get JSON structure as a readable string showing keys and types."""
    lines = []
    spacing = "  " * indent
    
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{spacing}{k}: (object)")
                lines.append(get_json_structure(v, indent + 1))
            elif isinstance(v, list):
                if v and isinstance(v[0], dict):
                    lines.append(f"{spacing}{k}: (array of objects)")
                    lines.append(get_json_structure(v[0], indent + 1))
                else:
                    lines.append(f"{spacing}{k}: (array of strings)")
            else:
                lines.append(f"{spacing}{k}: (string)")
    
    return "\n".join(lines)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text and hyperlinks from PDF using PyMuPDF."""
    try:
        doc = fitz.open(pdf_path)
        text_parts = []
        all_links = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            
            # Extract text
            text = page.get_text("text")
            text_parts.append(f"--- Page {page_num + 1} ---\n{text}")
            
            # Extract hyperlinks
            links = page.get_links()
            for link in links:
                if link.get("uri"):
                    uri = link["uri"]
                    # Get the text associated with this link area
                    rect = link.get("from")
                    if rect:
                        link_text = page.get_text("text", clip=rect).strip()
                        if link_text:
                            all_links.append(f"{link_text}: {uri}")
                        else:
                            all_links.append(uri)
                    else:
                        all_links.append(uri)
        
        doc.close()
        
        # Combine text and links
        result = "\n\n".join(text_parts)
        
        if all_links:
            result += "\n\n--- HYPERLINKS FOUND IN PDF ---\n"
            result += "\n".join(all_links)
        
        return result
    except Exception as e:
        print(f"  WARNING: Could not extract text from PDF: {e}")
        return ""


# ============================================================
# VALIDATION FUNCTIONS
# ============================================================

def validate_json_keys(extracted: dict, sample: dict) -> dict:
    """Ensure extracted JSON only uses keys from sample. Remove invalid keys."""
    
    def filter_keys(ext_data, sample_data):
        if not isinstance(sample_data, dict):
            return ext_data
        
        filtered = {}
        for key in sample_data:
            if key in ext_data:
                if isinstance(sample_data[key], dict) and isinstance(ext_data[key], dict):
                    filtered[key] = filter_keys(ext_data[key], sample_data[key])
                elif isinstance(sample_data[key], list) and isinstance(ext_data[key], list):
                    if ext_data[key] and isinstance(ext_data[key][0], dict) and sample_data[key] and isinstance(sample_data[key][0], dict):
                        filtered[key] = [filter_keys(item, sample_data[key][0]) for item in ext_data[key]]
                    else:
                        filtered[key] = ext_data[key]
                else:
                    filtered[key] = ext_data[key]
        return filtered
    
    return filter_keys(extracted, sample)


def validate_latex_completeness(latex: str) -> None:
    """Ensure LaTeX is complete and valid."""
    if "\\documentclass" not in latex:
        raise ValueError("LaTeX is missing \\documentclass")
    if "\\begin{document}" not in latex:
        raise ValueError("LaTeX is missing \\begin{document}")
    if "\\end{document}" not in latex:
        raise ValueError("LaTeX is missing \\end{document}")


def validate_latex_placeholders(latex: str, json_data: dict) -> list[str]:
    """Ensure LaTeX uses correct placeholder syntax."""
    
    warnings = []
    
    # Check for correct loop variables
    required_patterns = [
        (r'\\BLOCK\{for job in experience\}', 'experience loop must use "job" variable'),
        (r'\\BLOCK\{for project in projects\}', 'projects loop must use "project" variable'),
        (r'\\BLOCK\{for edu in education\}', 'education loop must use "edu" variable'),
        (r'\\BLOCK\{for cert in certifications\}', 'certifications loop must use "cert" variable'),
        (r'\\BLOCK\{for category, skill_list in skills_list\}', 'skills must use "skills_list" with category, skill_list'),
    ]
    
    for pattern, msg in required_patterns:
        if not re.search(pattern, latex):
            warnings.append(f"Missing or incorrect: {msg}")
    
    # Check for hardcoded URLs (bad)
    if re.search(r'https?://(?:www\.)?linkedin\.com(?!/)', latex):
        if '\\VAR{personal_info.linkedin_url}' not in latex:
            warnings.append("LinkedIn URL is hardcoded - should use \\VAR{personal_info.linkedin_url}")
    
    if re.search(r'https?://(?:www\.)?github\.com(?!/)', latex):
        if '\\VAR{personal_info.github_url}' not in latex:
            warnings.append("GitHub URL is hardcoded - should use \\VAR{personal_info.github_url}")
    
    # Check for wrong skills format
    if re.search(r'\\VAR\{skills\.\w+\}', latex):
        warnings.append("Using skills.xxx format - should use skills_list loop instead")
    
    return warnings


# ============================================================
# STEP 1: EXTRACT JSON FROM PDF
# ============================================================

def step1_extract_json(pdf_path: Path, sample_json: dict) -> dict:
    """Extract resume data from PDF into JSON format."""
    
    print("\n" + "=" * 60)
    print("STEP 1: EXTRACT JSON FROM PDF")
    print("=" * 60)
    
    # Extract text from PDF using PyMuPDF
    print("  Extracting text from PDF...")
    extracted_text = extract_text_from_pdf(pdf_path)
    
    if extracted_text:
        print(f"  ✓ Extracted {len(extracted_text)} characters from PDF")
    else:
        print("  ⚠ No text extracted, relying on PDF visual only")
    
    json_structure = get_json_structure(sample_json)
    
    prompt = f"""You are a precise resume data extractor. 

TASK: Extract ALL resume information into JSON format.

You have TWO sources of information:
1. The attached PDF file (for visual layout and verification)
2. The extracted text below (for accurate text content and hyperlinks)

USE BOTH SOURCES: The extracted text provides accurate content, while the PDF shows the structure and layout.

==============================================================================
EXTRACTED TEXT FROM PDF:
==============================================================================
{extracted_text}

==============================================================================
HYPERLINK MAPPING (CRITICAL):
==============================================================================
- The "HYPERLINKS FOUND IN PDF" section above contains all clickable links
- Map "LinkedIn: <url>" to personal_info.linkedin_url
- Map "GitHub: <url>" to personal_info.github_url
- Map certification links (e.g., "DP-700: <url>") to certifications[].url
- Use the EXACT URLs from the hyperlinks section - do not guess or modify them

==============================================================================
STRICT RULES:
==============================================================================
1. Use ONLY the keys shown in the schema below - NO NEW KEYS ALLOWED
2. You MAY omit keys if that data is not present in the PDF
3. Maintain exact data types (strings, arrays, objects)
4. Extract ALL information - do not skip any content from the PDF
5. For arrays, include ALL items found in the PDF
6. For skills, categorize them exactly as shown in schema structure
7. Use the extracted text for accurate spelling of names, emails, URLs, etc.
8. For ALL URL fields, use the exact hyperlinks from the "HYPERLINKS FOUND IN PDF" section

REQUIRED JSON SCHEMA (use these keys ONLY):
{json_structure}

SAMPLE JSON FOR REFERENCE:
```json
{json.dumps(sample_json, indent=2)}
```

INSTRUCTIONS:
1. Read the extracted text AND verify with the PDF
2. Map every piece of information to the correct key
3. Map ALL hyperlinks to their corresponding URL fields
4. Return ONLY valid JSON - no explanations, no markdown, no code blocks
5. Start with {{ and end with }}

OUTPUT FORMAT:
Return raw JSON only. No ```json blocks. No explanations before or after."""

    model = genai.GenerativeModel(GEMINI_MODEL)
    pdf_file = genai.upload_file(pdf_path, mime_type="application/pdf")
    
    print("  Calling Gemini API...")
    response = model.generate_content([pdf_file, prompt])
    
    response_text = response.text.strip()
    
    # Clean response - remove markdown code blocks if present
    if response_text.startswith("```"):
        response_text = re.sub(r'^```json?\s*', '', response_text)
        response_text = re.sub(r'\s*```$', '', response_text)
    
    try:
        extracted_json = json.loads(response_text)
    except json.JSONDecodeError as e:
        print(f"  ERROR: Invalid JSON response")
        print(f"  Response preview: {response_text[:500]}")
        raise ValueError(f"Gemini returned invalid JSON: {e}")
    
    # Validate keys
    validated_json = validate_json_keys(extracted_json, sample_json)
    
    print("  ✓ JSON extracted and validated")
    
    return validated_json


# ============================================================
# STEP 2: GENERATE LATEX FROM PDF + JSON
# ============================================================

def step2_generate_latex(pdf_path: Path, json_data: dict, sample_tex: str) -> str:
    """Generate LaTeX template that matches PDF visually with correct placeholders."""
    
    print("\n" + "=" * 60)
    print("STEP 2: GENERATE LATEX TEMPLATE")
    print("=" * 60)
    
    prompt = f"""You are an expert LaTeX developer creating a resume template.

TASK: Create a LaTeX template that EXACTLY replicates the visual layout of the attached PDF resume, using the EXACT placeholder syntax from the sample template.

==============================================================================
CRITICAL: COPY THESE SECTIONS EXACTLY - DO NOT MODIFY
==============================================================================

1. HEADER (copy exactly - only change layout to match PDF):
\\begin{{center}}
{{\\Large\\bfseries \\VAR{{personal_info.name}}}}\\\\[2pt]
\\VAR{{personal_info.location}} \\, | \\, \\VAR{{personal_info.email}} \\, | \\, \\VAR{{personal_info.phone}} \\, | \\, \\href{{\\VAR{{personal_info.linkedin_url}}}}{{LinkedIn}} \\, | \\, \\href{{\\VAR{{personal_info.github_url}}}}{{GitHub}}
\\end{{center}}

2. SKILLS SECTION (copy EXACTLY - no extra line breaks):
\\section{{Skills}}
\\BLOCK{{for category, skill_list in skills_list}}\\textbf{{\\VAR{{category}}:}} \\VAR{{skill_list}}\\\\[1pt]
\\BLOCK{{endfor}}\\textbf{{Certification:}} \\BLOCK{{for cert in certifications}}\\VAR{{cert.name}} (\\href{{\\VAR{{cert.url}}}}{{\\VAR{{cert.code}}}})\\BLOCK{{if not loop.last}}, \\BLOCK{{endif}}\\BLOCK{{endfor}}

3. EXPERIENCE SECTION (copy exactly):
\\section{{Experience}}

\\BLOCK{{for job in experience}}
\\textbf{{\\VAR{{job.title}}}} \\hfill \\VAR{{job.start_date}} -- \\VAR{{job.end_date}}\\\\
\\textit{{\\VAR{{job.company}}}} \\hfill \\textit{{\\VAR{{job.location}}}}
\\begin{{itemize}}
\\BLOCK{{for bullet in job.bullets}}
\\item \\VAR{{bullet}}
\\BLOCK{{endfor}}
\\end{{itemize}}
\\BLOCK{{if job.recognition}}
\\textit{{Recognition: \\VAR{{job.recognition}}}}
\\BLOCK{{endif}}
\\BLOCK{{if not loop.last}}\\vspace{{2pt}}\\BLOCK{{endif}}
\\BLOCK{{endfor}}

4. PROJECTS SECTION (copy exactly):
\\section{{Projects}}

\\BLOCK{{for project in projects}}
\\textbf{{\\VAR{{project.name}}}} \\, | \\, \\VAR{{project.tech_stack}}\\\\
\\VAR{{project.description}}
\\BLOCK{{if not loop.last}}\\vspace{{2pt}}\\BLOCK{{endif}}
\\BLOCK{{endfor}}

5. EDUCATION SECTION (copy exactly):
\\section{{Education}}

\\BLOCK{{for edu in education}}
\\textbf{{\\VAR{{edu.degree}}}} \\, | \\, GPA: \\VAR{{edu.gpa}} \\, | \\, \\VAR{{edu.university}}, \\VAR{{edu.location}} \\hfill \\VAR{{edu.start_year}} -- \\VAR{{edu.end_year}}\\BLOCK{{if not loop.last}}\\\\[2pt]\\BLOCK{{endif}}
\\BLOCK{{endfor}}

==============================================================================
SAMPLE TEMPLATE (REFERENCE FOR PACKAGES AND DOCUMENT STRUCTURE):
==============================================================================
```latex
{sample_tex}
```

==============================================================================
VISUAL MATCHING REQUIREMENTS:
==============================================================================
- Match the PDF's exact: fonts, font sizes, section order, section header styles, horizontal lines/rules
- Match: separator characters (use | or --- based on PDF)
- The BLOCK and VAR syntax MUST be copied exactly as shown above

SPACING ADJUSTMENTS (MANDATORY):
- MARGINS: Reduce by 0.1in from what you see in PDF (e.g., if PDF looks like 0.5in, use 0.4in)
- LINE SPACING: Reduce spacing between lines slightly (use tighter \\vspace values)
- Keep content compact but readable

==============================================================================
JSON DATA FOR REFERENCE:
==============================================================================
```json
{json.dumps(json_data, indent=2)}
```

==============================================================================
STRICT RULES:
==============================================================================
1. Copy the placeholder sections EXACTLY as shown above
2. DO NOT add extra newlines inside BLOCK loops
3. DO NOT modify the skills_list loop format
4. DO NOT change href syntax for links
5. Only adjust: margins, font sizes, separators (| vs ---) to match PDF visual

OUTPUT: Return ONLY raw LaTeX code. No ```latex blocks. No explanations."""

    model = genai.GenerativeModel(GEMINI_MODEL)
    pdf_file = genai.upload_file(pdf_path, mime_type="application/pdf")
    
    print("  Calling Gemini API...")
    response = model.generate_content([pdf_file, prompt])
    
    latex_content = response.text.strip()
    
    # Clean response
    if latex_content.startswith("```"):
        latex_content = re.sub(r'^```(?:latex|tex)?\s*', '', latex_content)
        latex_content = re.sub(r'\s*```$', '', latex_content)
    
    # Validate completeness
    validate_latex_completeness(latex_content)
    print("  ✓ LaTeX structure validated")
    
    # Validate placeholders
    missing_keys = validate_latex_placeholders(latex_content, json_data)
    if missing_keys:
        print(f"  ⚠ WARNING: Missing placeholders for keys: {missing_keys}")
    else:
        print("  ✓ All placeholders present")
    
    return latex_content


# ============================================================
# STEP 3: COMPILE PDF
# ============================================================

def step3_compile_pdf(json_data: dict, latex_template: str, output_name: str) -> Path:
    """Compile LaTeX template with JSON data to PDF."""
    
    print("\n" + "=" * 60)
    print("STEP 3: COMPILE PDF")
    print("=" * 60)
    
    # Preprocess and escape data
    processed_data = preprocess_data(json_data.copy())
    escaped_data = escape_json_data(processed_data)
    
    # Render template
    env = create_jinja_environment()
    template = env.from_string(latex_template)
    
    try:
        rendered_latex = template.render(**escaped_data)
    except Exception as e:
        print(f"  ERROR: Template rendering failed: {e}")
        debug_path = OUTPUT_DIR / "debug_template.tex"
        debug_path.write_text(latex_template, encoding="utf-8")
        print(f"  Debug template saved to: {debug_path}")
        raise
    
    # Compile - saves directly to output folder
    pdf_output = compile_to_pdf(rendered_latex, output_name)
    
    if pdf_output and pdf_output.exists():
        print(f"  ✓ PDF saved to: {pdf_output}")
        return pdf_output
    else:
        print("  ✗ PDF compilation failed")
        debug_path = OUTPUT_DIR / "debug_rendered.tex"
        debug_path.write_text(rendered_latex, encoding="utf-8")
        print(f"  Debug rendered LaTeX saved to: {debug_path}")
        return None


# ============================================================
# MAIN EXTRACTION FUNCTION
# ============================================================

def extract_resume_from_pdf(resume_name: str):
    """Main function: Two-step extraction process."""
    
    print("=" * 60)
    print("RESUME EXTRACTOR - Two-Step Gemini Processing")
    print("=" * 60)
    
    # Load inputs
    print("\nLoading inputs...")
    pdf_path = get_pdf_by_name(resume_name)
    print(f"  PDF: {pdf_path.name}")
    
    # Get base filename without extension
    base_filename = pdf_path.stem
    
    sample_json = load_sample_json()
    print(f"  Sample JSON: loaded")
    
    sample_tex = load_sample_tex()
    print(f"  Sample LaTeX: loaded")
    
    # Step 1: Extract JSON
    json_data = step1_extract_json(pdf_path, sample_json)
    
    # Save JSON to templates folder with original filename
    json_output_path = TEMPLATES_DIR / f"{base_filename}.json"
    if json_output_path.exists():
        json_output_path.unlink()
    json_output_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
    print(f"  Saved: {json_output_path}")
    
    # Step 2: Generate LaTeX
    latex_template = step2_generate_latex(pdf_path, json_data, sample_tex)
    
    # Save LaTeX to templates folder with original filename
    tex_output_path = TEMPLATES_DIR / f"{base_filename}.tex"
    if tex_output_path.exists():
        tex_output_path.unlink()
    tex_output_path.write_text(latex_template, encoding="utf-8")
    print(f"  Saved: {tex_output_path}")
    
    # Save copy of LaTeX to data folder
    tex_data_copy_path = DATA_DIR / f"{base_filename}.tex"
    if tex_data_copy_path.exists():
        tex_data_copy_path.unlink()
    tex_data_copy_path.write_text(latex_template, encoding="utf-8")
    print(f"  Saved copy: {tex_data_copy_path}")
    
    # Step 3: Compile PDF
    output_name = f"{base_filename}_check"
    step3_compile_pdf(json_data, latex_template, output_name)
    
    print("\n" + "=" * 60)
    print("EXTRACTION COMPLETE")
    print("=" * 60)
    
    return json_data, latex_template


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Extract resume data from PDF using Gemini and generate LaTeX template"
    )
    parser.add_argument(
        "--resume", "-r",
        type=str,
        help="Name of the PDF file in data/ folder (with or without .pdf extension)"
    )
    
    args = parser.parse_args()
    
    if not args.resume:
        available = get_available_pdfs()
        print("=" * 60)
        print("RESUME EXTRACTOR")
        print("=" * 60)
        print("\nUsage: python backend/resume_extractor.py --resume <filename>")
        print("   or: python backend/resume_extractor.py -r <filename>")
        print("\nAvailable PDFs in data/ folder:")
        if available:
            for pdf in available:
                print(f"  - {pdf.name}")
        else:
            print("  (none found)")
        print("\nExample:")
        print("  python backend/resume_extractor.py -r john_doe.pdf")
        print("  python backend/resume_extractor.py --resume john_doe")
    else:
        extract_resume_from_pdf(args.resume)