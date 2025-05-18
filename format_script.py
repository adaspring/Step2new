import ast
import astor
import sys
import os

def fix_indentation(input_file, output_file=None):
    try:
        with open(input_file, "r", encoding="utf-8") as f:
            source = f.read()

        # Parse and regenerate code
        tree = ast.parse(source, filename=input_file)
        fixed_code = astor.to_source(tree)

        # Default to in-place formatting
        output_file = output_file or input_file
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(fixed_code)

        print(f"Formatted: {input_file}")

    except SyntaxError as e:
        print(f"Syntax error in {input_file}: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error processing {input_file}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python format_script.py <input_file.py> [output_file.py]")
        sys.exit(1)
    fix_indentation(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
