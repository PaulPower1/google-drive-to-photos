"""
Google Photos Uploader Module
Downloads photos from Google Drive and uploads them to Google Photos.
Includes duplicate detection using MD5 checksums.
"""
import io
import json
import os
from datetime import datetime
from pathlib import Path

import requests
from googleapiclient.http import MediaIoBaseDownload

from auth import get_drive_service, get_photos_credentials

OUTPUT_DIR = Path(__file__).parent / 'output'
PHOTOS_API_URL = 'https://photoslibrary.googleapis.com/v1'
UPLOADED_TRACKER_FILE = OUTPUT_DIR / 'uploaded_photos.json'


class PhotosUploader:
    """Uploads photos from Google Drive to Google Photos."""

    def __init__(self, album_name: str = None, skip_duplicates: bool = True):
        self.drive_service = get_drive_service()
        self.photos_creds = get_photos_credentials()
        self.upload_results = []
        self.album_name = album_name or f"Drive Import {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        self.album_id = None
        self.skip_duplicates = skip_duplicates
        self.uploaded_photos = self._load_uploaded_tracker()

    def _load_uploaded_tracker(self) -> dict:
        """Load the tracker of previously uploaded photos."""
        if UPLOADED_TRACKER_FILE.exists():
            try:
                with open(UPLOADED_TRACKER_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    # Tracker stores: {md5_checksum: {file_id, photos_id, path, uploaded_at}}
                    return data
            except (json.JSONDecodeError, IOError):
                pass
        return {}

    def _save_uploaded_tracker(self):
        """Save the tracker of uploaded photos."""
        OUTPUT_DIR.mkdir(exist_ok=True)
        with open(UPLOADED_TRACKER_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.uploaded_photos, f, indent=2)

    def is_duplicate(self, md5_checksum: str, file_id: str) -> bool:
        """
        Check if a photo has already been uploaded.

        Args:
            md5_checksum: MD5 hash of the file
            file_id: Google Drive file ID

        Returns:
            True if the photo is a duplicate (already uploaded)
        """
        if not self.skip_duplicates:
            return False

        # Check by MD5 checksum (content-based duplicate)
        if md5_checksum and md5_checksum in self.uploaded_photos:
            return True

        # Check by file ID (same file re-upload)
        for entry in self.uploaded_photos.values():
            if entry.get('file_id') == file_id:
                return True

        return False

    def record_upload(self, md5_checksum: str, file_id: str, photos_id: str, path: str):
        """Record a successful upload to the tracker."""
        if md5_checksum:
            self.uploaded_photos[md5_checksum] = {
                'file_id': file_id,
                'photos_id': photos_id,
                'path': path,
                'uploaded_at': datetime.now().isoformat()
            }
            self._save_uploaded_tracker()

    def create_album(self) -> str:
        """
        Create a new album in Google Photos.

        Returns:
            Album ID of the created album
        """
        url = f'{PHOTOS_API_URL}/albums'
        headers = {
            'Authorization': f'Bearer {self.photos_creds.token}',
            'Content-Type': 'application/json'
        }
        body = {
            'album': {
                'title': self.album_name
            }
        }

        response = requests.post(url, headers=headers, json=body)

        if response.status_code != 200:
            raise Exception(f"Failed to create album: {response.status_code} - {response.text}")

        result = response.json()
        self.album_id = result.get('id')
        print(f"Created album: '{self.album_name}' (ID: {self.album_id})")
        return self.album_id

    def load_photos_list(self) -> list[dict]:
        """Load the photos list from the output file (prefers JSON with metadata)."""
        # Try loading from JSON first (has full metadata)
        photos_json_file = OUTPUT_DIR / 'photos_metadata.json'
        if photos_json_file.exists():
            try:
                with open(photos_json_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

        # Fall back to text file
        photos_file = OUTPUT_DIR / 'photos.txt'

        if not photos_file.exists():
            raise FileNotFoundError(
                f"Photos file not found: {photos_file}\n"
                "Run the drive scanner first to generate this file."
            )

        photos = []
        with open(photos_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip comments and empty lines
                if not line or line.startswith('#'):
                    continue

                parts = line.split('|')
                if len(parts) >= 3:
                    photo = {
                        'id': parts[0],
                        'path': parts[1],
                        'mimeType': parts[2]
                    }
                    # Include MD5 checksum if available
                    if len(parts) >= 4 and parts[3]:
                        photo['md5Checksum'] = parts[3]
                    photos.append(photo)

        return photos

    def download_from_drive(self, file_id: str, file_name: str) -> bytes:
        """Download a file from Google Drive."""
        request = self.drive_service.files().get_media(fileId=file_id)
        file_buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(file_buffer, request)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_buffer.seek(0)
        return file_buffer.read()

    def upload_to_photos(self, file_data: bytes, file_name: str, mime_type: str, album_id: str = None) -> dict:
        """
        Upload a photo to Google Photos.

        This uses the Google Photos Library API upload process:
        1. Upload bytes to get an upload token
        2. Create a media item using the token (optionally in an album)

        Args:
            file_data: Raw bytes of the photo
            file_name: Name of the file
            mime_type: MIME type of the photo
            album_id: Optional album ID to add the photo to
        """
        # Step 1: Upload the bytes
        upload_url = f'{PHOTOS_API_URL}/uploads'
        headers = {
            'Authorization': f'Bearer {self.photos_creds.token}',
            'Content-Type': 'application/octet-stream',
            'X-Goog-Upload-Content-Type': mime_type,
            'X-Goog-Upload-Protocol': 'raw',
            'X-Goog-Upload-File-Name': file_name
        }

        response = requests.post(upload_url, headers=headers, data=file_data)

        if response.status_code != 200:
            return {
                'success': False,
                'error': f'Upload failed: {response.status_code} - {response.text}'
            }

        upload_token = response.text

        # Step 2: Create the media item (in album if specified)
        create_url = f'{PHOTOS_API_URL}/mediaItems:batchCreate'
        headers = {
            'Authorization': f'Bearer {self.photos_creds.token}',
            'Content-Type': 'application/json'
        }
        body = {
            'newMediaItems': [{
                'description': f'Uploaded from Google Drive: {file_name}',
                'simpleMediaItem': {
                    'uploadToken': upload_token,
                    'fileName': file_name
                }
            }]
        }

        # Add to album if specified
        if album_id:
            body['albumId'] = album_id

        response = requests.post(create_url, headers=headers, json=body)

        if response.status_code != 200:
            return {
                'success': False,
                'error': f'Media item creation failed: {response.status_code} - {response.text}'
            }

        result = response.json()
        new_items = result.get('newMediaItemResults', [])

        if new_items and new_items[0].get('status', {}).get('message') == 'Success':
            return {
                'success': True,
                'mediaItem': new_items[0].get('mediaItem', {})
            }
        else:
            error_msg = new_items[0].get('status', {}) if new_items else 'Unknown error'
            return {
                'success': False,
                'error': str(error_msg)
            }

    def upload_all(self, photos: list[dict] = None) -> list[dict]:
        """
        Upload all photos from Drive to Photos.

        Args:
            photos: List of photo dicts (if None, loads from file)

        Returns:
            List of upload results
        """
        if photos is None:
            photos = self.load_photos_list()

        total = len(photos)
        skipped_count = 0

        # Create album first
        print(f"Creating album '{self.album_name}'...")
        self.create_album()
        print()

        if self.skip_duplicates:
            print(f"Duplicate detection enabled. {len(self.uploaded_photos)} photos already tracked.")

        print(f"Starting upload of {total} photos to Google Photos...")

        self.upload_results = []

        for i, photo in enumerate(photos, 1):
            file_id = photo['id']
            file_path = photo['path']
            file_name = Path(file_path).name
            mime_type = photo['mimeType']
            md5_checksum = photo.get('md5Checksum', '')

            # Check for duplicates
            if self.is_duplicate(md5_checksum, file_id):
                print(f"[{i}/{total}] Skipping (duplicate): {file_name}")
                skipped_count += 1
                self.upload_results.append({
                    'path': file_path,
                    'file_id': file_id,
                    'timestamp': datetime.now().isoformat(),
                    'success': True,
                    'status': 'SKIPPED_DUPLICATE',
                    'md5Checksum': md5_checksum
                })
                continue

            print(f"[{i}/{total}] Uploading: {file_name}")

            result = {
                'path': file_path,
                'file_id': file_id,
                'timestamp': datetime.now().isoformat(),
                'md5Checksum': md5_checksum
            }

            try:
                # Download from Drive
                file_data = self.download_from_drive(file_id, file_name)

                # Upload to Photos (in the album)
                upload_result = self.upload_to_photos(file_data, file_name, mime_type, self.album_id)

                result['success'] = upload_result['success']
                if upload_result['success']:
                    result['status'] = 'SUCCESS'
                    photos_id = upload_result.get('mediaItem', {}).get('id', '')
                    result['photos_id'] = photos_id
                    # Record successful upload to prevent future duplicates
                    self.record_upload(md5_checksum, file_id, photos_id, file_path)
                else:
                    result['status'] = 'FAILED'
                    result['error'] = upload_result.get('error', 'Unknown error')

            except Exception as e:
                result['success'] = False
                result['status'] = 'ERROR'
                result['error'] = str(e)

            self.upload_results.append(result)

            # Print status
            if result['success']:
                print(f"    SUCCESS")
            else:
                print(f"    FAILED: {result.get('error', 'Unknown error')}")

        # Summary
        success_count = sum(1 for r in self.upload_results if r.get('status') == 'SUCCESS')
        fail_count = sum(1 for r in self.upload_results if r.get('status') in ('FAILED', 'ERROR'))
        print(f"\nUpload complete!")
        print(f"  Uploaded: {success_count}")
        print(f"  Skipped (duplicates): {skipped_count}")
        print(f"  Failed: {fail_count}")

        return self.upload_results

    def write_results(self):
        """Write upload results to output file."""
        OUTPUT_DIR.mkdir(exist_ok=True)

        results_file = OUTPUT_DIR / 'upload_status.txt'
        with open(results_file, 'w', encoding='utf-8') as f:
            f.write("# Google Photos Upload Status\n")
            f.write(f"# Generated: {datetime.now().isoformat()}\n")
            f.write(f"# Album: {self.album_name}\n")
            f.write(f"# Album ID: {self.album_id}\n")
            f.write(f"# Total: {len(self.upload_results)} files\n")

            success_count = sum(1 for r in self.upload_results if r.get('status') == 'SUCCESS')
            skipped_count = sum(1 for r in self.upload_results if r.get('status') == 'SKIPPED_DUPLICATE')
            fail_count = sum(1 for r in self.upload_results if r.get('status') in ('FAILED', 'ERROR'))
            f.write(f"# Uploaded: {success_count}\n")
            f.write(f"# Skipped (duplicates): {skipped_count}\n")
            f.write(f"# Failed: {fail_count}\n")
            f.write("# Format: status|path|photos_id_or_error\n\n")

            for result in self.upload_results:
                status = result['status']
                path = result['path']
                if result.get('status') == 'SKIPPED_DUPLICATE':
                    extra = f"md5:{result.get('md5Checksum', '')}"
                elif result['success']:
                    extra = result.get('photos_id', '')
                else:
                    extra = result.get('error', 'Unknown error')

                f.write(f"{status}|{path}|{extra}\n")

        print(f"Upload status written to: {results_file}")


def main():
    """Run the Photos uploader."""
    from dotenv import load_dotenv
    load_dotenv()

    uploader = PhotosUploader()
    uploader.upload_all()
    uploader.write_results()


if __name__ == '__main__':
    main()
