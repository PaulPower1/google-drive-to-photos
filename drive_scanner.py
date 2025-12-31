"""
Google Drive Scanner Module
Traverses Google Drive to find photos and identify empty folders.
Supports scanning specific folder paths and extracting photo metadata.
"""
import os
from pathlib import Path
from typing import Generator

from auth import get_drive_service

# Photo/image MIME types to look for
PHOTO_MIME_TYPES = [
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/bmp',
    'image/webp',
    'image/tiff',
    'image/heic',
    'image/heif',
    'image/raw',
    'image/x-raw',
    'image/x-canon-cr2',
    'image/x-nikon-nef',
    'image/x-sony-arw',
    'image/x-panasonic-rw2',
    'image/x-olympus-orf',
    'image/x-fuji-raf',
    'image/x-adobe-dng',
]

# Default known photo locations to scan
DEFAULT_PHOTO_LOCATIONS = [
    'My Drive/Photos',
]

OUTPUT_DIR = Path(__file__).parent / 'output'


class DriveScanner:
    """Scanner for traversing Google Drive and finding photos."""

    def __init__(self):
        self.service = get_drive_service()
        self.photos_found = []
        self.empty_folders = []

    def get_folder_name(self, folder_id: str) -> str:
        """Get the name of a folder by its ID."""
        if folder_id == 'root':
            return 'My Drive'
        try:
            result = self.service.files().get(
                fileId=folder_id,
                fields='name'
            ).execute()
            return result.get('name', folder_id)
        except Exception:
            return folder_id

    def resolve_folder_path(self, folder_path: str) -> str:
        """
        Resolve a folder path like 'My Drive/Photos' to a folder ID.

        Args:
            folder_path: Path like 'My Drive/Photos' or 'My Drive/Pictures/2024'

        Returns:
            Folder ID if found, None otherwise
        """
        parts = folder_path.strip('/').split('/')

        if not parts:
            return 'root'

        # Start from root if path starts with 'My Drive'
        if parts[0] == 'My Drive':
            current_folder_id = 'root'
            parts = parts[1:]  # Skip 'My Drive'
        else:
            current_folder_id = 'root'

        # Navigate through each folder in the path
        for folder_name in parts:
            if not folder_name:
                continue

            # Search for the folder by name within current folder
            query = f"'{current_folder_id}' in parents and name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='files(id, name)',
                pageSize=1
            ).execute()

            files = results.get('files', [])
            if not files:
                print(f"  Warning: Folder not found: '{folder_name}' in path '{folder_path}'")
                return None

            current_folder_id = files[0]['id']

        return current_folder_id

    def list_files_in_folder(self, folder_id: str) -> Generator[dict, None, None]:
        """List all files and folders in a given folder with full metadata."""
        page_token = None

        while True:
            query = f"'{folder_id}' in parents and trashed = false"
            results = self.service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, size, createdTime, modifiedTime, imageMediaMetadata, md5Checksum)',
                pageToken=page_token,
                pageSize=1000
            ).execute()

            for item in results.get('files', []):
                yield item

            page_token = results.get('nextPageToken')
            if not page_token:
                break

    def is_photo(self, mime_type: str) -> bool:
        """Check if a file is a photo based on MIME type."""
        return mime_type in PHOTO_MIME_TYPES

    def scan_folder(self, folder_id: str, current_path: str = '') -> tuple[int, int]:
        """
        Recursively scan a folder for photos and empty folders.

        Args:
            folder_id: Google Drive folder ID
            current_path: Current path string for building full paths

        Returns:
            Tuple of (file_count, folder_count) in this folder
        """
        file_count = 0
        subfolder_count = 0
        subfolders = []

        # Get folder name if not at root level with path
        if not current_path:
            folder_name = self.get_folder_name(folder_id)
            current_path = folder_name

        print(f"Scanning: {current_path}")

        # List all items in this folder
        for item in self.list_files_in_folder(folder_id):
            item_name = item['name']
            item_mime = item['mimeType']
            item_id = item['id']
            full_path = f"{current_path}/{item_name}"

            if item_mime == 'application/vnd.google-apps.folder':
                # It's a folder - add to list for recursive scanning
                subfolders.append((item_id, full_path))
                subfolder_count += 1
            else:
                file_count += 1
                # Check if it's a photo
                if self.is_photo(item_mime):
                    photo_data = {
                        'id': item_id,
                        'name': item_name,
                        'path': full_path,
                        'mimeType': item_mime,
                        'size': item.get('size'),
                        'createdTime': item.get('createdTime'),
                        'modifiedTime': item.get('modifiedTime'),
                        'md5Checksum': item.get('md5Checksum'),
                    }
                    # Add image metadata if available
                    image_meta = item.get('imageMediaMetadata', {})
                    if image_meta:
                        photo_data['metadata'] = {
                            'width': image_meta.get('width'),
                            'height': image_meta.get('height'),
                            'rotation': image_meta.get('rotation'),
                            'cameraMake': image_meta.get('cameraMake'),
                            'cameraModel': image_meta.get('cameraModel'),
                            'exposureTime': image_meta.get('exposureTime'),
                            'aperture': image_meta.get('aperture'),
                            'isoSpeed': image_meta.get('isoSpeed'),
                            'focalLength': image_meta.get('focalLength'),
                            'time': image_meta.get('time'),
                            'location': image_meta.get('location'),
                        }
                    self.photos_found.append(photo_data)

        # Recursively scan subfolders
        for subfolder_id, subfolder_path in subfolders:
            sub_files, sub_folders = self.scan_folder(subfolder_id, subfolder_path)
            # If subfolder and all its children are empty, it's effectively empty
            if sub_files == 0 and sub_folders == 0:
                self.empty_folders.append(subfolder_path)

        # Check if current folder is empty (no files and no subfolders)
        if file_count == 0 and subfolder_count == 0 and current_path:
            # This is an empty leaf folder
            pass  # Will be detected by parent

        return file_count, subfolder_count

    def scan(self, root_folder_id: str = None) -> tuple[list, list]:
        """
        Scan Google Drive starting from the specified folder.

        Args:
            root_folder_id: Folder ID to start from (None for root)

        Returns:
            Tuple of (photos_list, empty_folders_list)
        """
        folder_id = root_folder_id or 'root'
        self.photos_found = []
        self.empty_folders = []

        print(f"Starting Google Drive scan...")
        self.scan_folder(folder_id)
        print(f"\nScan complete!")
        print(f"Found {len(self.photos_found)} photos")
        print(f"Found {len(self.empty_folders)} empty folders")

        return self.photos_found, self.empty_folders

    def scan_paths(self, folder_paths: list[str] = None) -> tuple[list, list]:
        """
        Scan multiple folder paths in Google Drive.

        Args:
            folder_paths: List of folder paths to scan (e.g., ['My Drive/Photos'])
                         If None, uses DEFAULT_PHOTO_LOCATIONS

        Returns:
            Tuple of (photos_list, empty_folders_list)
        """
        if folder_paths is None:
            folder_paths = DEFAULT_PHOTO_LOCATIONS

        self.photos_found = []
        self.empty_folders = []

        print(f"Starting Google Drive scan of {len(folder_paths)} location(s)...")

        for folder_path in folder_paths:
            print(f"\nResolving path: {folder_path}")
            folder_id = self.resolve_folder_path(folder_path)

            if folder_id:
                print(f"  Found folder ID: {folder_id}")
                self.scan_folder(folder_id, folder_path)
            else:
                print(f"  Skipping: Path not found")

        print(f"\nScan complete!")
        print(f"Found {len(self.photos_found)} photos")
        print(f"Found {len(self.empty_folders)} empty folders")

        return self.photos_found, self.empty_folders

    def write_results(self):
        """Write scan results to output files (both text and JSON with metadata)."""
        import json

        OUTPUT_DIR.mkdir(exist_ok=True)

        # Write photos file (simple text format for backwards compatibility)
        photos_file = OUTPUT_DIR / 'photos.txt'
        with open(photos_file, 'w', encoding='utf-8') as f:
            f.write("# Google Drive Photos\n")
            f.write(f"# Total: {len(self.photos_found)} photos\n")
            f.write("# Format: file_id|path|mime_type|md5_checksum\n\n")
            for photo in self.photos_found:
                md5 = photo.get('md5Checksum', '')
                f.write(f"{photo['id']}|{photo['path']}|{photo['mimeType']}|{md5}\n")

        print(f"Photos written to: {photos_file}")

        # Write photos with full metadata as JSON
        photos_json_file = OUTPUT_DIR / 'photos_metadata.json'
        with open(photos_json_file, 'w', encoding='utf-8') as f:
            json.dump(self.photos_found, f, indent=2, default=str)

        print(f"Photos metadata written to: {photos_json_file}")

        # Write empty folders file
        empty_file = OUTPUT_DIR / 'empty_folders.txt'
        with open(empty_file, 'w', encoding='utf-8') as f:
            f.write("# Empty Google Drive Folders\n")
            f.write(f"# Total: {len(self.empty_folders)} empty folders\n\n")
            for folder_path in self.empty_folders:
                f.write(f"{folder_path}\n")

        print(f"Empty folders written to: {empty_file}")


def main():
    """Run the Drive scanner."""
    from dotenv import load_dotenv
    load_dotenv()

    scanner = DriveScanner()
    root_folder = os.environ.get('GOOGLE_DRIVE_FOLDER_ID') or None
    scanner.scan(root_folder)
    scanner.write_results()


if __name__ == '__main__':
    main()
