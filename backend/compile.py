import os
import shutil
import sys
from setuptools import setup
from setuptools.extension import Extension
from Cython.Build import cythonize

# Walk through backend/app to find all .py files (excluding __init__.py and wrappers)
backend_dir = os.path.dirname(os.path.abspath(__file__))
app_dir = os.path.join(backend_dir, "app")
py_files = []

# Exclude entry point scripts or specific files we don't want to compile
exclude_files = ["record_complete.py", "__init__.py"]

for root, dirs, files in os.walk(app_dir):
    # Exclude __pycache__
    if "__pycache__" in dirs:
        dirs.remove("__pycache__")
    for file in files:
        if file.endswith(".py") and file not in exclude_files:
            full_path = os.path.join(root, file)
            py_files.append(full_path)

# Prepare extensions
extensions = []
for py_file in py_files:
    # Compute module name relative to the backend directory
    rel_path = os.path.relpath(py_file, backend_dir)
    # Convert path to python module format (e.g., app.models)
    module_name = rel_path[:-3].replace(os.path.sep, ".")
    extensions.append(Extension(module_name, [py_file]))

print(f"Found {len(extensions)} files to compile...")

try:
    # Run setup compilation
    setup(
        name="VMS Backend",
        ext_modules=cythonize(
            extensions,
            compiler_directives={"language_level": "3"},
            quiet=True
        ),
        script_args=["build_ext", "--inplace"]
    )
    print("Compilation succeeded!")

    # Cleanup .c and original .py source files
    print("Cleaning up C and original Python source files...")
    for py_file in py_files:
        # Remove original .py file
        try:
            os.remove(py_file)
        except Exception as e:
            print(f"Error removing source {py_file}: {e}")

        # Remove temporary .c file
        c_file = py_file[:-3] + ".c"
        if os.path.exists(c_file):
            try:
                os.remove(c_file)
            except Exception as e:
                print(f"Error removing temp C file {c_file}: {e}")

    # Remove setuptools temporary build folder
    build_dir = os.path.join(backend_dir, "build")
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
        except Exception as e:
            print(f"Error removing build directory: {e}")

    print("Cleanup complete!")
except Exception as err:
    import traceback
    traceback.print_exc()
    print(f"Compilation/cleanup failed: {err}")
    sys.exit(1)
