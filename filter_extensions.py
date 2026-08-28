import argparse
import os
import shutil
from pathlib import Path


def extract_extensions(file_paths):
    """Extract all unique extensions from a list of paths."""
    extensions = set()
    for path_obj in file_paths:
        ext = path_obj.suffix
        if ext:
            extensions.add(ext.lower())
    return sorted(list(extensions))


def copy_preserving_structure(src_path, dest_root, base_dir=None):
    """Copy a file to dest_root while maintaining its directory structure.

    If base_dir is given (folder mode), structure is preserved relative to
    base_dir. If base_dir is None (text file mode), absolute drive roots are
    stripped.
    """
    if base_dir:
        # Preserve directory structure relative to the input folder
        relative_path = src_path.relative_to(base_dir)
    elif src_path.is_absolute():
        # Strip absolute root (e.g. / on Linux/Mac or C:\ on Windows)
        relative_path = Path(*src_path.parts[1:])
    else:
        relative_path = src_path

    dest_path = Path(dest_root) / relative_path
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_path, dest_path)


def main():
    parser = argparse.ArgumentParser(
        description="Filter and copy files based on extension while preserving structure."
    )

    # Mutually exclusive group: force either --file-list OR --input-dir
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "-f",
        "--file-list",
        type=str,
        help="Path to a text file containing file paths (one per line)",
    )
    source_group.add_argument(
        "-d",
        "--input-dir",
        type=str,
        help="Path to a directory to scan recursively for files",
    )

    parser.add_argument(
        "-o",
        "--output-dir",
        type=str,
        default="output_files",
        help="Target folder to copy selected files into (default: 'output_files')",
    )

    args = parser.parse_args()

    file_paths = []
    base_dir = None

    # Option A: Read paths from a text file
    if args.file_list:
        input_txt = Path(args.file_list)
        if not input_txt.is_file():
            print(f"Error: Text file '{args.file_list}' not found.")
            return

        with open(input_txt, "r", encoding="utf-8") as f:
            for line in f:
                clean_line = line.strip()
                if clean_line and not clean_line.startswith("#"):
                    file_paths.append(Path(clean_line))

        if not file_paths:
            print("No valid file paths found in the input text file.")
            return

    # Option B: Recursively scan a directory
    elif args.input_dir:
        base_dir = Path(args.input_dir).resolve()
        if not base_dir.is_dir():
            print(f"Error: Directory '{args.input_dir}' not found.")
            return

        print(f"Scanning directory recursively: {base_dir} ...")
        # Recursively get all files
        file_paths = [p for p in base_dir.rglob("*") if p.is_file()]

        if not file_paths:
            print(f"No files found inside directory '{base_dir}'.")
            return

    # Extract extensions
    available_exts = extract_extensions(file_paths)

    if not available_exts:
        print("No file extensions found among the target files.")
        return

    print("\n--- Available Extensions Found ---")
    for idx, ext in enumerate(available_exts, 1):
        print(f" {idx}. {ext}")
    print("----------------------------------")

    # Prompt user for selection
    user_input = input(
        "\nEnter extensions to keep (comma-separated, e.g., 'jpg, .png, pdf'): "
    )

    selected_exts = set()
    for raw_ext in user_input.split(","):
        clean_ext = raw_ext.strip().lower()
        if clean_ext:
            if not clean_ext.startswith("."):
                clean_ext = f".{clean_ext}"
            selected_exts.add(clean_ext)

    if not selected_exts:
        print("No valid extensions selected. Exiting.")
        return

    print(f"\nSelected extensions: {', '.join(sorted(selected_exts))}")

    # Process copying
    dest_folder = Path(args.output_dir)
    dest_folder.mkdir(parents=True, exist_ok=True)

    copied_count = 0
    missing_count = 0

    print(f"\nCopying files to '{dest_folder.resolve()}'...\n")

    for file_path in file_paths:
        if file_path.suffix.lower() in selected_exts:
            if file_path.is_file():
                try:
                    copy_preserving_structure(
                        file_path, dest_folder, base_dir=base_dir
                    )
                    print(f"[COPIED] {file_path}")
                    copied_count += 1
                except Exception as e:
                    print(f"[ERROR] Could not copy {file_path}: {e}")
            else:
                print(f"[MISSING] File does not exist on disk: {file_path}")
                missing_count += 1

    print("\n--- Summary ---")
    print(f"Successfully copied: {copied_count} file(s)")
    if missing_count > 0:
        print(f"Files not found on disk: {missing_count} file(s)")


if __name__ == "__main__":
    main()