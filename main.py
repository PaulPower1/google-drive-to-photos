"""
Google Drive to Photos Migration Tool
Main orchestration script.

Usage:
    python main.py [--scan-only] [--upload-only] [--album "Album Name"]
                   [--paths "My Drive/Photos,My Drive/Pictures"]
                   [--no-skip-duplicates]

Options:
    --scan-only           Only scan Google Drive (don't upload to Photos)
    --upload-only         Only upload to Photos (use existing photos.txt)
    --album               Name of the Google Photos album to create and upload to
    --paths               Comma-separated folder paths to scan (e.g., "My Drive/Photos")
    --no-skip-duplicates  Disable duplicate detection (upload all photos)
"""
import argparse
import os
import sys

from dotenv import load_dotenv


def check_environment():
    """Verify required environment variables are set."""
    required_vars = ['GOOGLE_CLIENT_ID', 'GOOGLE_CLIENT_SECRET']
    missing = [var for var in required_vars if not os.environ.get(var)]

    if missing:
        print("ERROR: Missing required environment variables:")
        for var in missing:
            print(f"  - {var}")
        print("\nSet these variables in a .env file or export them.")
        print("See .env.example for reference.")
        sys.exit(1)


def run_scan(folder_paths: list[str] = None):
    """Run the Google Drive scan."""
    print("=" * 60)
    print("STEP 1: Scanning Google Drive")
    print("=" * 60)

    from drive_scanner import DriveScanner, DEFAULT_PHOTO_LOCATIONS

    scanner = DriveScanner()

    # Use folder paths if provided, otherwise check for folder ID, otherwise use defaults
    if folder_paths:
        print(f"Scanning folder paths: {folder_paths}")
        scanner.scan_paths(folder_paths)
    else:
        root_folder = os.environ.get('GOOGLE_DRIVE_FOLDER_ID') or None
        if root_folder:
            print(f"Starting from folder ID: {root_folder}")
            scanner.scan(root_folder)
        else:
            print(f"Scanning default photo locations: {DEFAULT_PHOTO_LOCATIONS}")
            scanner.scan_paths()

    scanner.write_results()
    print()

    return scanner.photos_found


def run_upload(photos=None, album_name=None, skip_duplicates=True):
    """Run the Google Photos upload."""
    print("=" * 60)
    print("STEP 2: Uploading to Google Photos")
    print("=" * 60)

    from photos_uploader import PhotosUploader

    uploader = PhotosUploader(album_name=album_name, skip_duplicates=skip_duplicates)
    uploader.upload_all(photos)
    uploader.write_results()
    print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Migrate photos from Google Drive to Google Photos'
    )
    parser.add_argument(
        '--scan-only',
        action='store_true',
        help='Only scan Google Drive (skip upload)'
    )
    parser.add_argument(
        '--upload-only',
        action='store_true',
        help='Only upload to Photos (use existing photos.txt)'
    )
    parser.add_argument(
        '--album',
        type=str,
        default=None,
        help='Name of the Google Photos album to create (default: "Drive Import YYYY-MM-DD HH:MM")'
    )
    parser.add_argument(
        '--paths',
        type=str,
        default=None,
        help='Comma-separated folder paths to scan (e.g., "My Drive/Photos,My Drive/Pictures")'
    )
    parser.add_argument(
        '--no-skip-duplicates',
        action='store_true',
        help='Disable duplicate detection (upload all photos even if already uploaded)'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Verify environment
    check_environment()

    print()
    print("=" * 60)
    print("Google Drive to Photos Migration Tool")
    print("=" * 60)
    print()

    if args.scan_only and args.upload_only:
        print("ERROR: Cannot use both --scan-only and --upload-only")
        sys.exit(1)

    # Parse folder paths if provided
    folder_paths = None
    if args.paths:
        folder_paths = [p.strip() for p in args.paths.split(',') if p.strip()]

    photos = None

    # Run scan unless upload-only
    if not args.upload_only:
        photos = run_scan(folder_paths)

    # Run upload unless scan-only
    if not args.scan_only:
        skip_duplicates = not args.no_skip_duplicates
        run_upload(photos, album_name=args.album, skip_duplicates=skip_duplicates)

    print("=" * 60)
    print("Migration complete!")
    print("=" * 60)
    print()
    print("Output files:")
    print("  - output/photos.txt           : List of photos found in Drive")
    print("  - output/photos_metadata.json : Photos with full metadata (JSON)")
    print("  - output/empty_folders.txt    : List of empty folders in Drive")
    print("  - output/upload_status.txt    : Upload results to Google Photos")
    print("  - output/uploaded_photos.json : Tracker for duplicate detection")


if __name__ == '__main__':
    main()
