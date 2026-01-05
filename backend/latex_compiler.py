"""
latex_compiler.py - Phase 2: LaTeX Template + JSON → Final PDF
Merges templates with data using Jinja2 and compiles to PDF online
"""

import json
import requests
from pathlib import Path
from jinja2 import Environment, BaseLoader

# ============================================================
# CONFIGURATION
# ============================================================

# Directory structure (relative to project root)
BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
DOWNLOADED_DIR = BASE_DIR / "downloaded"
OUTPUT_DIR = BASE_DIR / "output"

# Create directories if they don't exist
TEMPLATES_DIR.mkdir(exist_ok=True)
DOWNLOADED_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json_file(path: Path) -> dict:
    """Load JSON file, return empty dict if not found."""
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


# ============================================================
# LATEX ESCAPING
# ============================================================

def latex_escape(text: str) -> str:
    """Escape special LaTeX characters (but NOT backslash, braces for commands)."""
    if not isinstance(text, str):
        return str(text) if text is not None else ""
    
    replacements = [
        ("&", r"\&"),
        ("%", r"\%"),
        ("$", r"\$"),
        ("#", r"\#"),
        ("_", r"\_"),
        ("~", r"\textasciitilde{}"),
        ("^", r"\textasciicircum{}"),
    ]
    
    for old, new in replacements:
        text = text.replace(old, new)
    
    return text


def escape_json_data(data) -> dict:
    """Recursively escape all string values in JSON data."""
    if isinstance(data, dict):
        return {k: escape_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [escape_json_data(item) for item in data]
    elif isinstance(data, str):
        return latex_escape(data)
    else:
        return data


# ============================================================
# JINJA2 ENVIRONMENT
# ============================================================

def create_jinja_environment() -> Environment:
    """Create Jinja2 environment with LaTeX-safe delimiters."""
    env = Environment(
        loader=BaseLoader(),
        block_start_string=r"\BLOCK{",
        block_end_string="}",
        variable_start_string=r"\VAR{",
        variable_end_string="}",
        comment_start_string=r"\#{",
        comment_end_string="}",
        autoescape=False
    )
    
    env.filters["latex_escape"] = latex_escape
    env.filters["join_skills"] = lambda x: ", ".join(x) if x else ""
    env.filters["join_list"] = lambda x, sep=", ": sep.join(x) if x else ""
    
    return env


# ============================================================
# COMPILER FUNCTIONS
# ============================================================

def render_template(
    template_name: str,
    data_filename: str = None,
    data_source: str = "downloads",
    escape_latex: bool = True
) -> str:
    """
    Merge a template with JSON data to create final LaTeX content.
    
    Returns:
        Rendered LaTeX content as string
    """
    if data_filename is None:
        data_filename = template_name
    
    # Locate template file
    template_path = TEMPLATES_DIR / f"{template_name}.tex"
    
    # Locate data file
    if data_source == "downloaded":
        data_path = DOWNLOADED_DIR / f"{data_filename}.json"
    else:
        data_path = TEMPLATES_DIR / f"{data_filename}.json"
    
    # Validate files exist
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    print(f"Template: {template_path}")
    print(f"Data: {data_path}")
    
    # Load template and data
    template_content = template_path.read_text(encoding="utf-8")
    raw_data = json.loads(data_path.read_text(encoding="utf-8"))
    
    # Escape LaTeX special characters
    if escape_latex:
        data = escape_json_data(raw_data)
    else:
        data = raw_data
    
    # Initialize Jinja2 and render
    env = create_jinja_environment()
    template = env.from_string(template_content)
    rendered = template.render(**data)
    
    return rendered


def compile_to_pdf(latex_content: str, output_name: str) -> Path:
    """
    Compile LaTeX content to PDF using online API.
    
    Returns:
        Path to generated PDF, or None if failed
    """
    api_url = "https://latexonline.cc/compile"
    
    params = {
        "text": latex_content,
        "command": "pdflatex",
        "download": f"{output_name}.pdf"
    }
    
    print("Compiling LaTeX online...")
    
    try:
        response = requests.get(api_url, params=params, timeout=120)
        
        if response.status_code == 200 and response.content[:4] == b'%PDF':
            output_path = OUTPUT_DIR / f"{output_name}.pdf"
            with open(output_path, "wb") as f:
                f.write(response.content)
            print(f"✓ PDF saved to: {output_path}")
            return output_path
        else:
            print(f"Compilation failed. Status: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return None
            
    except Exception as e:
        print(f"Error: {e}")
        return None


def compile_resume(
    template_name: str,
    data_filename: str = None,
    data_source: str = "downloads",
    output_name: str = None,
    escape_latex: bool = True
) -> Path:
    """
    Full pipeline: Template + JSON → PDF
    
    Args:
        template_name: Name of template file (without .tex extension)
        data_filename: Name of JSON file (without .json extension)
        data_source: "downloads" or "templates" - where to find JSON
        output_name: Custom name for output PDF (optional)
        escape_latex: Whether to escape LaTeX special characters
    
    Returns:
        Path to generated PDF
    """
    # Render the template
    rendered = render_template(
        template_name=template_name,
        data_filename=data_filename,
        data_source=data_source,
        escape_latex=escape_latex
    )
    
    # Determine output filename
    if output_name is None:
        output_name = template_name
    
    # Compile to PDF
    return compile_to_pdf(rendered, output_name)


def list_available():
    """List all available templates and data files."""
    print("Templates (in templates/):")
    templates = list(TEMPLATES_DIR.glob("*.tex"))
    if templates:
        for t in templates:
            json_exists = (TEMPLATES_DIR / f"{t.stem}.json").exists()
            status = "✓" if json_exists else "✗"
            print(f"  {status} {t.stem}")
    else:
        print("  (none)")
    
    print("\nData files:")
    print("  In templates/ (extracted):")
    for f in TEMPLATES_DIR.glob("*.json"):
        print(f"    {f.stem}")
    
    print("  In downloaded/ (tailored):")
    downloaded = list(DOWNLOADED_DIR.glob("*.json"))
    if downloaded:
        for f in downloaded:
            print(f"    {f.stem}")
    else:
        print("    (none)")


def auto_compile():
    """
    Automatically compile using metadata.json and tailored_resume.json
    Reads template name from metadata, uses tailored_resume.json as data
    """
    print("="*50)
    print("AUTO COMPILE - Using metadata.json")
    print("="*50)
    
    # Load metadata
    metadata = load_json_file(DOWNLOADED_DIR / "metadata.json")
    if not metadata:
        print("✗ metadata.json not found in downloaded/")
        return None
    
    # Get template name from metadata
    resume_file = metadata.get("options", {}).get("resumeFile", "")
    if not resume_file:
        print("✗ resumeFile not found in metadata.json")
        return None
    
    template_name = Path(resume_file).stem
    print(f"Template: {template_name}")
    
    # Check if tailored_resume.json exists
    tailored_path = DOWNLOADED_DIR / "tailored_resume.json"
    if not tailored_path.exists():
        print("✗ tailored_resume.json not found in downloaded/")
        return None
    
    print(f"Data: tailored_resume.json")
    
    # Compile
    return compile_resume(
        template_name=template_name,
        data_filename="tailored_resume",
        data_source="downloaded",
        output_name=template_name
    )


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Compile LaTeX templates with JSON data into PDF"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["compile", "auto", "list"],
        default="auto",
        help="Action to perform (default: auto)"
    )
    parser.add_argument(
        "--template", "-t",
        help="Template name (without .tex extension)"
    )
    parser.add_argument(
        "--data", "-d",
        help="Data filename (without .json extension, defaults to template name)"
    )
    parser.add_argument(
        "--source", "-s",
        choices=["downloaded", "templates"],
        default="downloaded",
        help="Where to find JSON data (default: downloaded)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Custom output filename (without extension)"
    )
    parser.add_argument(
        "--no-escape",
        action="store_true",
        help="Don't escape LaTeX special characters in data"
    )
    
    args = parser.parse_args()
    
    if args.command == "list":
        print("="*50)
        print("LATEX COMPILER")
        print("="*50)
        list_available()
    
    elif args.command == "auto":
        auto_compile()
    
    elif args.command == "compile":
        print("="*50)
        print("LATEX COMPILER - Manual")
        print("="*50)
        if not args.template:
            print("Error: --template required for manual compile\n")
            list_available()
        else:
            compile_resume(
                template_name=args.template,
                data_filename=args.data,
                data_source=args.source,
                output_name=args.output,
                escape_latex=not args.no_escape
            )