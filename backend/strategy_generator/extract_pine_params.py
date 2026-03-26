"""
Extracts all input parameters from Pine Script templates in docs/pine_templates/
and generates a JSON config for each version for use in Backtrader.
"""
import os
import re
import json

BASE = os.path.abspath(os.path.join(os.path.dirname(__file__), '../..'))
TEMPLATE_DIR = os.path.join(BASE, 'docs', 'pine_templates')
OUTPUT_DIR = os.path.join(BASE, 'backend', 'strategy_generator', 'configs')

os.makedirs(OUTPUT_DIR, exist_ok=True)

input_pattern = re.compile(r'^(\s*)([a-zA-Z0-9_]+)\s*=\s*input\.([a-zA-Z_]+)\((.*)', re.MULTILINE)

for fname in os.listdir(TEMPLATE_DIR):
    if not fname.endswith('.pine'):
        continue
    version = fname.replace('apm_', '').replace('_template.pine', '')
    path = os.path.join(TEMPLATE_DIR, fname)
    with open(path, 'r', encoding='utf-8') as f:
        code = f.read()
    params = {}
    for match in input_pattern.finditer(code):
        var, typ, args = match.group(2), match.group(3), match.group(4)
        # Try to extract default value and label
        arg_parts = [a.strip() for a in args.split(',')]
        default = arg_parts[0] if arg_parts else None
        label = arg_parts[1].strip('"') if len(arg_parts) > 1 else var
        params[var] = {'type': typ, 'default': default, 'label': label}
    # Write config
    out_path = os.path.join(OUTPUT_DIR, f'{version}.json')
    with open(out_path, 'w', encoding='utf-8') as outf:
        json.dump(params, outf, indent=2)
print(f"Configs generated in {OUTPUT_DIR}")
