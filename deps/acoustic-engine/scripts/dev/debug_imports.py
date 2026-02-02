import ast
import importlib.util
import os
import sys


def check_managed_imports():
    start_path = os.path.abspath(".")
    src_path = os.path.join(start_path, "src")

    if os.path.exists(src_path) and src_path not in sys.path:
        sys.path.insert(0, src_path)

    print(f"Starting Static Import Analysis on {start_path}...")
    print(
        "This tool checks all 'import' statements (including inside functions) to see if the module exists."
    )

    errors = []

    # Cache for checked modules to speed up (module_name -> exists)
    checked_modules = {}

    ignore_dirs = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
        ".ruff_cache",
        ".pytest_cache",
        "site-packages",
    }

    for root, dirs, files in os.walk(start_path):
        # Modify dirs in-place to skip ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]

        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                rel_file_path = os.path.relpath(file_path, start_path)

                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        source = f.read()

                    tree = ast.parse(source, filename=file_path)

                    # Determine current package context based on file path relative to src
                    # e.g. src/package/module.py -> package
                    # src/package/sub/module.py -> package
                    current_package = None
                    if file_path.startswith(src_path + os.path.sep):
                        path_within_src = os.path.relpath(file_path, src_path)
                        parts_within_src = path_within_src.split(os.path.sep)
                        if len(parts_within_src) > 1:
                            current_package = parts_within_src[0]
                        elif len(parts_within_src) == 1 and parts_within_src[0] == "__init__.py":
                            # If it's src/__init__.py, then src itself is the package.
                            # But we treat src as the root for imports, so no specific package name here.
                            current_package = (
                                None  # Or could be "" if we want to signify the root of src
                            )
                        elif len(parts_within_src) == 1 and parts_within_src[0].endswith(".py"):
                            # File directly in src, e.g., src/main.py. No enclosing package within src.
                            current_package = None

                    for node in ast.walk(tree):
                        if isinstance(node, ast.Import):
                            for alias in node.names:
                                validate_import(
                                    alias.name,
                                    file_path,
                                    node.lineno,
                                    errors,
                                    checked_modules,
                                    current_package,
                                )
                        elif isinstance(node, ast.ImportFrom):
                            if node.level == 0:
                                # Absolute import
                                if node.module:
                                    validate_import(
                                        node.module,
                                        file_path,
                                        node.lineno,
                                        errors,
                                        checked_modules,
                                        current_package,
                                    )
                            else:
                                # Relative import
                                validate_relative_import(
                                    node.module, node.level, root, file_path, node.lineno, errors
                                )

                except SyntaxError as e:
                    print(f"❌ Syntax Error in {rel_file_path}: {e}")
                    errors.append((f"{rel_file_path}:0", f"Syntax Error: {e}"))
                except Exception as e:
                    print(f"❌ Error reading {rel_file_path}: {e}")

    print("\n" + "=" * 50)
    print("ANALYSIS SUMMARY")
    print("=" * 50)

    if not errors:
        print("✅ No missing modules found based on static analysis.")
    else:
        print(f"Found {len(errors)} potential import issues:")
        for loc, msg in errors:
            print(f" • {loc} -> {msg}")


def validate_import(module_name, file_path, lineno, errors, checked_modules, current_package=None):
    # Check for self-package absolute imports
    if current_package and module_name.startswith(current_package + "."):
        rel_path = os.path.relpath(file_path, os.getcwd())
        print(
            f"⚠️  Suspicious absolute import '{module_name}' inside package '{current_package}' (in {rel_path}:{lineno})"
        )
        errors.append(
            (
                f"{rel_path}:{lineno}",
                f"Suspicious absolute import of own package '{module_name}' (use relative import)",
            )
        )

    if module_name in checked_modules:
        if not checked_modules[module_name]:
            rel_path = os.path.relpath(file_path, os.getcwd())
            print(f"❌ '{module_name}' not found (cached result) (in {rel_path}:{lineno})")
            errors.append((f"{rel_path}:{lineno}", f"Module '{module_name}' not found"))
        return

    try:
        # find_spec
        spec = importlib.util.find_spec(module_name)
        if spec is None:
            checked_modules[module_name] = False
            rel_path = os.path.relpath(file_path, os.getcwd())
            print(f"❌ '{module_name}' not found (in {rel_path}:{lineno})")
            errors.append((f"{rel_path}:{lineno}", f"Module '{module_name}' not found"))
        else:
            checked_modules[module_name] = True
    except ModuleNotFoundError:
        checked_modules[module_name] = False
        rel_path = os.path.relpath(file_path, os.getcwd())
        print(f"❌ '{module_name}' not found (ModuleNotFoundError) (in {rel_path}:{lineno})")
        errors.append((f"{rel_path}:{lineno}", f"Module '{module_name}' not found"))
    except Exception as e:
        checked_modules[module_name] = False
        rel_path = os.path.relpath(file_path, os.getcwd())
        print(f"❌ Error checking '{module_name}': {e} (in {rel_path}:{lineno})")
        errors.append((f"{rel_path}:{lineno}", f"Error checking '{module_name}': {e}"))


def validate_relative_import(module, level, current_dir, file_path, lineno, errors):
    target_dir = current_dir
    for i in range(level - 1):
        target_dir = os.path.dirname(target_dir)

    if module:
        parts = module.split(".")
        path_check = os.path.join(target_dir, *parts)
        if not (
            os.path.exists(path_check + ".py")
            or os.path.exists(os.path.join(path_check, "__init__.py"))
        ):
            print(
                f"❌ Relative import '{'.' * level}{module}' target not found at {path_check} (in {os.path.basename(file_path)}:{lineno})"
            )
            errors.append(
                (
                    f"{os.path.basename(file_path)}:{lineno}",
                    f"Relative import target '{module}' not found",
                )
            )


if __name__ == "__main__":
    check_managed_imports()
