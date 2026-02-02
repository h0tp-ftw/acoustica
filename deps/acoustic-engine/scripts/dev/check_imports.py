import importlib
import os
import sys


def check_imports():
    # Ensure src is in python path
    src_path = os.path.abspath("src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    print(f"Scanning for python modules in {src_path}...")

    modules_to_check = []

    # Walk the directory to find all modules
    for root, dirs, files in os.walk(src_path):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, src_path)

                # Convert path to module name
                module_name = rel_path.replace(os.path.sep, ".")[:-3]
                if module_name.endswith(".__init__"):
                    module_name = module_name[:-9]

                modules_to_check.append(module_name)

    # Sort for cleaner output
    modules_to_check.sort()

    print(f"Found {len(modules_to_check)} modules. Attempting to import them...\n")

    failed = []
    skipped = []

    for module_name in modules_to_check:
        if not module_name:  # Root package itself
            continue

        try:
            # Try to import
            importlib.import_module(module_name)
            # print(f"[OK] {module_name}")
        except Exception as e:
            print(f"[FAIL] {module_name}")
            print(f"  Error: {e}")
            # print(traceback.format_exc()) # Uncomment for full trace
            failed.append((module_name, str(e)))
        except SystemExit:
            print(f"[FAIL] {module_name} (Module called sys.exit())")
            failed.append((module_name, "Called sys.exit()"))

    print("\n" + "=" * 40)
    print("IMPORT CHECK SUMMARY")
    print("=" * 40)

    if not failed:
        print("All modules imported successfully!")
    else:
        print(f"Found {len(failed)} faulty imports:\n")
        for mod, err in failed:
            print(f"❌ {mod}")
            print(f"   └── {err}")


if __name__ == "__main__":
    check_imports()
