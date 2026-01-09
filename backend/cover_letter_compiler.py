"""
cover_letter_compiler.py - Cover Letter LaTeX Compiler
Merges personal_info from resume JSON + content from tailored_cover JSON

Location: backend/cover_letter_compiler.py
Usage: python backend/cover_letter_compiler.py [command]
"""

import shutil
import sys
from pathlib import Path

# Add backend folder to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# Import shared functions from latex_compiler (same folder)
from latex_compiler import (
    load_json_file,
    escape_json_data,
    create_jinja_environment,
    compile_to_pdf,
    TEMPLATES_DIR,
    DOWNLOADED_DIR,
    OUTPUT_DIR,
    BASE_DIR
)

# ============================================================
# CONFIGURATION
# ============================================================

SAMPLES_DIR = BASE_DIR / "samples"


# ============================================================
# TEMPLATE SETUP
# ============================================================

def ensure_cover_template_exists(template_name: str = "cover") -> bool:
    """
    Check if cover letter template exists in templates/.
    If not, copy from samples/ folder.
    
    Returns:
        True if template is available, False otherwise
    """
    template_path = TEMPLATES_DIR / f"{template_name}.tex"
    sample_path = SAMPLES_DIR / f"{template_name}.tex"
    
    if template_path.exists():
        print(f"✓ Template found: {template_path}")
        return True
    
    print(f"Template not found in templates/")
    
    if sample_path.exists():
        print(f"Copying from samples/...")
        shutil.copy(sample_path, template_path)
        print(f"✓ Copied: {sample_path} → {template_path}")
        return True
    else:
        print(f"✗ Template not found in samples/ either: {sample_path}")
        return False


# ============================================================
# COVER LETTER SPECIFIC FUNCTIONS
# ============================================================

def render_cover_letter(
    resume_json_name: str,
    cover_json_name: str = "tailored_cover",
    template_name: str = "cover",
    escape_latex: bool = True
) -> str:
    """
    Render cover letter by merging two JSON sources.
    
    Args:
        resume_json_name: Name of resume JSON in templates/ (without .json)
        cover_json_name: Name of cover JSON in downloaded/ (without .json)
        template_name: Name of .tex template in templates/ (without .tex)
        escape_latex: Whether to escape special LaTeX characters
    
    Returns:
        Rendered LaTeX string
    """
    # Ensure template exists (copy from samples if needed)
    if not ensure_cover_template_exists(template_name):
        raise FileNotFoundError(f"Template '{template_name}.tex' not found in templates/ or samples/")
    
    # Paths
    template_path = TEMPLATES_DIR / f"{template_name}.tex"
    resume_json_path = TEMPLATES_DIR / f"{resume_json_name}.json"
    cover_json_path = DOWNLOADED_DIR / f"{cover_json_name}.json"
    
    # Validate files exist
    if not resume_json_path.exists():
        raise FileNotFoundError(f"Resume JSON not found: {resume_json_path}")
    if not cover_json_path.exists():
        raise FileNotFoundError(f"Cover JSON not found: {cover_json_path}")
    
    print(f"Template: {template_path}")
    print(f"Resume JSON: {resume_json_path}")
    print(f"Cover JSON: {cover_json_path}")
    
    # Load data
    template_content = template_path.read_text(encoding="utf-8")
    resume_data = load_json_file(resume_json_path)
    cover_data = load_json_file(cover_json_path)
    
    # Merge: personal_info from resume + everything from cover
    merged_data = {
        "personal_info": resume_data.get("personal_info", {}),
        **cover_data
    }
    
    # Escape LaTeX special characters
    if escape_latex:
        merged_data = escape_json_data(merged_data)
    
    # Render template
    env = create_jinja_environment()
    template = env.from_string(template_content)
    rendered = template.render(**merged_data)
    
    return rendered


def compile_cover_letter(
    resume_json_name: str,
    cover_json_name: str = "tailored_cover",
    template_name: str = "Cover_Letter",
    output_name: str = None,
    escape_latex: bool = True
) -> Path:
    """
    Compile cover letter to PDF.
    
    Args:
        resume_json_name: Name of resume JSON in templates/
        cover_json_name: Name of cover JSON in downloaded/
        template_name: Name of .tex template
        output_name: Custom output filename (default: Cover_Letter)
        escape_latex: Whether to escape special LaTeX characters
    
    Returns:
        Path to generated PDF or None if failed
    """
    rendered = render_cover_letter(
        resume_json_name=resume_json_name,
        cover_json_name=cover_json_name,
        template_name=template_name,
        escape_latex=escape_latex
    )
    
    if output_name is None:
        output_name = template_name
    
    return compile_to_pdf(rendered, output_name)


def auto_compile():
    """
    Auto compile using metadata.json to determine resume JSON.
    Expects tailored_cover.json in downloaded/
    """
    print("=" * 50)
    print("COVER LETTER AUTO COMPILE")
    print("=" * 50)
    
    # Load metadata
    metadata = load_json_file(DOWNLOADED_DIR / "metadata.json")
    if not metadata:
        print("✗ metadata.json not found in downloaded/")
        return None
    
    # Get resume file name from metadata
    resume_file = metadata.get("options", {}).get("resumeFile", "")
    if not resume_file:
        print("✗ resumeFile not found in metadata.json")
        return None
    
    resume_json_name = Path(resume_file).stem
    print(f"Resume JSON: {resume_json_name}")
    
    # Check for tailored_cover.json
    cover_json_path = DOWNLOADED_DIR / "tailored_cover.json"
    if not cover_json_path.exists():
        print("✗ tailored_cover.json not found in downloaded/")
        return None
    
    print(f"Cover JSON: tailored_cover")
    
    return compile_cover_letter(
        resume_json_name=resume_json_name,
        cover_json_name="tailored_cover",
        template_name="cover",
        output_name="cover"
    )


def list_available():
    """List available templates and data files."""
    print("\nCover Letter Template:")
    template_path = TEMPLATES_DIR / "cover.tex"
    sample_path = SAMPLES_DIR / "cover.tex"
    
    if template_path.exists():
        print(f"  ✓ cover.tex (in templates/)")
    elif sample_path.exists():
        print(f"  ○ cover.tex (in samples/ - will be copied on compile)")
    else:
        print(f"  ✗ cover.tex (not found)")
    
    print("\nResume JSONs (in templates/):")
    for f in TEMPLATES_DIR.glob("*.json"):
        print(f"    {f.stem}")
    
    print("\nCover JSONs (in downloaded/):")
    cover_files = [f for f in DOWNLOADED_DIR.glob("*cover*.json")]
    if cover_files:
        for f in cover_files:
            print(f"    {f.stem}")
    else:
        print("    (none)")
    
    print("\nMetadata:")
    metadata_path = DOWNLOADED_DIR / "metadata.json"
    if metadata_path.exists():
        metadata = load_json_file(metadata_path)
        resume_file = metadata.get("options", {}).get("resumeFile", "N/A")
        print(f"    resumeFile: {resume_file}")
    else:
        print("    ✗ metadata.json not found")


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compile Cover Letter from LaTeX template + JSON data"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["compile", "auto", "list"],
        default="auto",
        help="Action to perform (default: auto)"
    )
    parser.add_argument(
        "--resume", "-r",
        help="Resume JSON name in templates/ (without .json)"
    )
    parser.add_argument(
        "--cover", "-c",
        default="tailored_cover",
        help="Cover JSON name in downloaded/ (default: tailored_cover)"
    )
    parser.add_argument(
        "--template", "-t",
        default="cover",
        help="Template name (default: cover)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Custom output filename"
    )
    parser.add_argument(
        "--no-escape",
        action="store_true",
        help="Disable LaTeX escaping"
    )
    
    args = parser.parse_args()
    
    if args.command == "list":
        print("=" * 50)
        print("COVER LETTER COMPILER")
        print("=" * 50)
        list_available()
    
    elif args.command == "auto":
        auto_compile()
    
    elif args.command == "compile":
        print("=" * 50)
        print("COVER LETTER COMPILER - Manual")
        print("=" * 50)
        
        if not args.resume:
            print("Error: --resume required for manual compile")
            print("Example: python cover_letter_compiler.py compile --resume Data_Engineer_Resume\n")
            list_available()
        else:
            compile_cover_letter(
                resume_json_name=args.resume,
                cover_json_name=args.cover,
                template_name=args.template,
                output_name=args.output,
                escape_latex=not args.no_escape
            )