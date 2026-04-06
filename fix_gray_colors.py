import re
import os
from pathlib import Path

# Define the replacements
COLOR_REPLACEMENTS = {
    r'#666666\b': '{theme.text_secondary}',
    r'#666\b': '{theme.text_secondary}',
    r'#999999\b': '{theme.text_secondary}',
    r'#999\b': '{theme.text_secondary}',
    r'#444\b': '{theme.text_secondary}',
    r'#cccccc\b': '{theme.border}',
    r'#ccc\b': '{theme.border}',
    r'#9E9E9E\b': '{theme.border}',
    r'\bcolor:\s*gray\b': 'color: {theme.text_secondary}',
}

THEME_IMPORT = "from gui.theme_manager import get_theme_manager"
THEME_VAR = "theme = get_theme_manager().get_current_theme()"

def has_import(content, import_line):
    """Check if import already exists in file"""
    return import_line in content

def add_import_if_needed(content):
    """Add theme import at the top of the file if not present"""
    if has_import(content, THEME_IMPORT):
        return content, False
    
    # Find the last import statement
    lines = content.split('\n')
    last_import_idx = -1
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            last_import_idx = i
    
    if last_import_idx >= 0:
        # Insert after the last import
        lines.insert(last_import_idx + 1, THEME_IMPORT)
        return '\n'.join(lines), True
    else:
        # No imports found, add at the beginning after any shebangs/encoding
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('#'):
                insert_idx = i + 1
            else:
                break
        lines.insert(insert_idx, THEME_IMPORT)
        return '\n'.join(lines), True

def replace_colors_in_stylesheet(content):
    """Replace gray color codes with theme variables"""
    modified = content
    replacements_made = []
    
    for pattern, replacement in COLOR_REPLACEMENTS.items():
        if re.search(pattern, modified, re.IGNORECASE):
            modified = re.sub(pattern, replacement, modified, flags=re.IGNORECASE)
            replacements_made.append(pattern)
    
    return modified, bool(replacements_made)

def convert_setstylesheet_to_fstring(content):
    """Convert setStyleSheet calls to use f-strings with theme"""
    lines = content.split('\n')
    modified_lines = []
    i = 0
    changes_made = False
    
    while i < len(lines):
        line = lines[i]
        
        # Look for setStyleSheet calls
        if 'setStyleSheet' in line and '{theme.' in line:
            # Check if this line has a regular string (not f-string)
            if re.search(r'\.setStyleSheet\s*\(\s*["\']', line) and not re.search(r'\.setStyleSheet\s*\(\s*f["\']', line):
                # Convert to f-string
                line = re.sub(r'\.setStyleSheet\s*\(\s*(["\'])', r'.setStyleSheet(f\1', line)
                changes_made = True
                
                # Check if we need to add theme variable before this line
                # Look backwards to see if theme var exists in current scope
                needs_theme_var = True
                for j in range(max(0, i - 20), i):  # Look back up to 20 lines
                    if THEME_VAR in modified_lines[j]:
                        needs_theme_var = False
                        break
                
                if needs_theme_var:
                    # Get the indentation of the current line
                    indent = len(line) - len(line.lstrip())
                    theme_line = ' ' * indent + THEME_VAR
                    modified_lines.append(theme_line)
                    changes_made = True
        
        modified_lines.append(line)
        i += 1
    
    return '\n'.join(modified_lines), changes_made

def process_file(filepath):
    """Process a single file"""
    print(f"\nProcessing: {filepath}")
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        total_changes = False
        
        # Step 1: Replace color codes
        content, colors_changed = replace_colors_in_stylesheet(content)
        if colors_changed:
            print(f"  - Replaced gray color codes")
            total_changes = True
        
        # Step 2: Convert setStyleSheet to f-strings
        content, fstring_changed = convert_setstylesheet_to_fstring(content)
        if fstring_changed:
            print(f"  - Converted to f-strings and added theme variables")
            total_changes = True
        
        # Step 3: Add import if needed
        content, import_added = add_import_if_needed(content)
        if import_added:
            print(f"  - Added theme import")
            total_changes = True
        
        # Write back if changes were made
        if total_changes:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  [OK] File updated successfully")
        else:
            print(f"  - No changes needed")
            
        return total_changes
        
    except Exception as e:
        print(f"  [ERROR] Error processing file: {e}")
        return False

def main():
    # Base directory
    base_dir = Path(r"C:\Users\nmikik\Desktop\VS REPOS\shopify-fulfillment-tool\gui")
    
    # Target files
    target_files = [
        "barcode_generator_widget.py",
        "client_settings_dialog.py",
        "column_config_dialog.py",
        "column_mapping_widget.py",
        "reference_labels_widget.py",
        "rule_test_dialog.py",
        "tag_categories_dialog.py",
        "tag_management_panel.py",
        "session_browser_widget.py",
        "report_selection_dialog.py",
    ]
    
    print("=" * 60)
    print("Gray Color Code Replacement Script")
    print("=" * 60)
    
    files_processed = 0
    files_modified = 0
    
    for filename in target_files:
        filepath = base_dir / filename
        if filepath.exists():
            files_processed += 1
            if process_file(filepath):
                files_modified += 1
        else:
            print(f"\n[ERROR] File not found: {filepath}")
    
    print("\n" + "=" * 60)
    print(f"Summary:")
    print(f"  Files processed: {files_processed}/{len(target_files)}")
    print(f"  Files modified: {files_modified}")
    print("=" * 60)

if __name__ == "__main__":
    main()
