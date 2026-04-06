"""Fix theme_manager imports - move them to top of file and remove duplicates."""
import re
from pathlib import Path

def fix_imports(filepath):
    """Fix import placement in a single file."""
    print(f"\nProcessing: {filepath.name}")
    
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    
    lines = content.split('\n')
    
    # Find all lines with the theme_manager import
    import_line = "from gui.theme_manager import get_theme_manager"
    import_indices = []
    
    for i, line in enumerate(lines):
        if import_line in line:
            import_indices.append(i)
    
    if not import_indices:
        print(f"  - No theme_manager import found")
        return False
    
    if len(import_indices) == 1:
        # Check if it's in the right place (top of file, in imports section)
        import_idx = import_indices[0]
        if import_idx < 30:  # Reasonable position for imports
            print(f"  - Import already in correct position (line {import_idx + 1})")
            return False
    
    print(f"  - Found {len(import_indices)} import(s) at lines: {[i+1 for i in import_indices]}")
    
    # Remove all existing imports
    for idx in reversed(import_indices):
        lines.pop(idx)
    
    # Find the correct position to insert (after last import)
    last_import_idx = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('import ') or stripped.startswith('from '):
            last_import_idx = i
    
    if last_import_idx >= 0:
        lines.insert(last_import_idx + 1, import_line)
        print(f"  - Moved import to line {last_import_idx + 2}")
    else:
        # No imports found, add at the beginning
        lines.insert(0, import_line)
        print(f"  - Added import at top of file")
    
    # Write back
    new_content = '\n'.join(lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(new_content)
    
    print(f"  [OK] File updated")
    return True

def main():
    base_dir = Path(r"C:\Users\nmikik\Desktop\VS REPOS\shopify-fulfillment-tool\gui")
    
    target_files = [
        "column_config_dialog.py",
        "reference_labels_widget.py",
        "rule_test_dialog.py",
        "tag_management_panel.py",
    ]
    
    print("=" * 60)
    print("Fix Theme Manager Imports")
    print("=" * 60)
    
    for filename in target_files:
        filepath = base_dir / filename
        if filepath.exists():
            fix_imports(filepath)
        else:
            print(f"\n[ERROR] File not found: {filepath}")
    
    print("\n" + "=" * 60)
    print("Done!")
    print("=" * 60)

if __name__ == "__main__":
    main()
