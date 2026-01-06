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

BASE_DIR = Path(__file__).parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
DOWNLOADED_DIR = BASE_DIR / "downloaded"
OUTPUT_DIR = BASE_DIR / "output"

TEMPLATES_DIR.mkdir(exist_ok=True)
DOWNLOADED_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)


# ============================================================
# HELPER FUNCTIONS
# ============================================================

def load_json_file(path: Path) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {}


def format_skill_key(key: str) -> str:
    """Convert skill key to display name: data_warehousing -> Data Warehousing"""
    return key.replace('_', ' ').title()


def preprocess_data(data: dict) -> dict:
    """Preprocess JSON data before rendering."""
    # Convert skills dict to list of tuples for easier iteration
    if 'skills' in data and isinstance(data['skills'], dict):
        data['skills_list'] = [
            (format_skill_key(k), v) 
            for k, v in data['skills'].items()
        ]
    return data


# ============================================================
# LATEX ESCAPING
# ============================================================

def latex_escape(text: str) -> str:
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
    if isinstance(data, dict):
        return {k: escape_json_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [escape_json_data(item) for item in data]
    elif isinstance(data, tuple):
        return tuple(escape_json_data(item) for item in data)
    elif isinstance(data, str):
        return latex_escape(data)
    else:
        return data


# ============================================================
# JINJA2 ENVIRONMENT
# ============================================================

def create_jinja_environment() -> Environment:
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
    if data_filename is None:
        data_filename = template_name
    
    template_path = TEMPLATES_DIR / f"{template_name}.tex"
    
    if data_source == "downloaded":
        data_path = DOWNLOADED_DIR / f"{data_filename}.json"
    else:
        data_path = TEMPLATES_DIR / f"{data_filename}.json"
    
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")
    
    print(f"Template: {template_path}")
    print(f"Data: {data_path}")
    
    template_content = template_path.read_text(encoding="utf-8")
    raw_data = json.loads(data_path.read_text(encoding="utf-8"))
    
    # Preprocess data (convert skills dict to list)
    raw_data = preprocess_data(raw_data)
    
    if escape_latex:
        data = escape_json_data(raw_data)
    else:
        data = raw_data
    
    env = create_jinja_environment()
    template = env.from_string(template_content)
    rendered = template.render(**data)
    
    return rendered


def compile_to_pdf(latex_content: str, output_name: str) -> Path:
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
    rendered = render_template(
        template_name=template_name,
        data_filename=data_filename,
        data_source=data_source,
        escape_latex=escape_latex
    )
    
    if output_name is None:
        output_name = template_name
    
    return compile_to_pdf(rendered, output_name)


def list_available():
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
    print("="*50)
    print("AUTO COMPILE - Using metadata.json")
    print("="*50)
    
    metadata = load_json_file(DOWNLOADED_DIR / "metadata.json")
    if not metadata:
        print("✗ metadata.json not found in downloaded/")
        return None
    
    resume_file = metadata.get("options", {}).get("resumeFile", "")
    if not resume_file:
        print("✗ resumeFile not found in metadata.json")
        return None
    
    template_name = Path(resume_file).stem
    print(f"Template: {template_name}")
    
    tailored_path = DOWNLOADED_DIR / "tailored_resume.json"
    if not tailored_path.exists():
        print("✗ tailored_resume.json not found in downloaded/")
        return None
    
    print(f"Data: tailored_resume.json")
    
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
    parser.add_argument("--template", "-t", help="Template name (without .tex)")
    parser.add_argument("--data", "-d", help="Data filename (without .json)")
    parser.add_argument("--source", "-s", choices=["downloaded", "templates"], default="downloaded")
    parser.add_argument("--output", "-o", help="Custom output filename")
    parser.add_argument("--no-escape", action="store_true")
    
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