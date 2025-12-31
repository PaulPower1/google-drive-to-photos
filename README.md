# Google Drive to Photos Migration Tool

Migrate photos from Google Drive to Google Photos.

## Features

- Scans Google Drive for photos (supports JPEG, PNG, GIF, RAW formats, etc.)
- **Scan specific folder paths** (e.g., "My Drive/Photos") instead of entire drive
- **Duplicate detection** - automatically skips photos that have already been uploaded
- **Metadata export** - exports full photo metadata (EXIF, camera info, GPS) to JSON
- Identifies empty folders in Google Drive
- Uploads photos to Google Photos
- Tracks upload status with detailed logging

## Setup

### 1. Google Cloud Project Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select existing
3. Enable the following APIs:
   - Google Drive API
   - Google Photos Library API

### 2. Create OAuth Credentials

1. Go to APIs & Services > Credentials
2. Click "Create Credentials" > "OAuth client ID"
3. Choose "Desktop application"
4. Note your Client ID and Client Secret

### 3. Configure OAuth Consent Screen

1. Go to APIs & Services > OAuth consent screen
2. Choose "External" user type
3. Fill in app name, support email
4. Add scopes:
   - drive.readonly
   - photoslibrary.appendonly
   - photoslibrary.sharing
5. Add your email as a test user

### 4. Environment Variables

Copy .env.example to .env and fill in your credentials:

    cp .env.example .env

Edit .env:

    GOOGLE_CLIENT_ID=your_client_id_here
    GOOGLE_CLIENT_SECRET=your_client_secret_here
    GOOGLE_DRIVE_FOLDER_ID=optional_folder_id

### 5. Install Dependencies

    pip install -r requirements.txt

## Usage

### Full Migration (Default: My Drive/Photos)

    python main.py

By default, scans "My Drive/Photos" folder. Duplicates are automatically skipped.

### Scan Specific Folder Paths

    python main.py --paths "My Drive/Photos,My Drive/Pictures,My Drive/Camera"

### With Custom Album Name

    python main.py --album "My Vacation Photos"

### Scan Only (no upload)

    python main.py --scan-only

### Upload Only (use existing photos.txt)

    python main.py --upload-only --album "My Album"

### Disable Duplicate Detection

    python main.py --no-skip-duplicates

### Run Individual Scripts

    # Scan Drive only
    python drive_scanner.py

    # Upload to Photos only
    python photos_uploader.py

## Output Files

All output files are written to the output/ directory:

- photos.txt - List of photos found with Drive IDs, paths, and MD5 checksums
- photos_metadata.json - Full photo metadata including EXIF data (camera, dimensions, GPS, etc.)
- empty_folders.txt - List of empty folders found
- upload_status.txt - Upload results (success/skipped/failure for each file)
- uploaded_photos.json - Tracker for duplicate detection (maps MD5 checksums to uploaded photos)

## Authentication

On first run, a browser window will open for Google OAuth authentication.
- You will need to authorize access for both Google Drive and Google Photos
- Tokens are saved locally (token_drive.pickle, token_photos.pickle) for future runs

### Token Expiration During Long Uploads

**Important:** Google Photos OAuth tokens expire after approximately 500-1000 uploads. For large photo libraries, you may encounter 401 UNAUTHENTICATED errors mid-upload.

**How to resume after token expiration:**

1. The upload will stop with authentication errors
2. Delete the expired token: rm token_photos.pickle (or del token_photos.pickle on Windows)
3. Restart with upload-only mode: python main.py --upload-only
4. Re-authenticate when the browser opens
5. The duplicate detection will automatically skip already-uploaded photos

Your progress is preserved in output/uploaded_photos.json (tracks by MD5 checksum).

## Known Limitations

### No Direct Drive-to-Photos Transfer

There is **no server-side direct transfer** between Google Drive and Google Photos. The Google Photos Library API only accepts raw file bytes - it does not support:
- Uploading from a URL
- Uploading from a Google Drive file ID
- Server-to-server transfers

All transfers require downloading from Drive and re-uploading to Photos.

### March 2025 API Restrictions

As of March 31, 2025, Google Photos Library API has significant restrictions:
- The API can only manage photos/videos **created by your app**
- Scopes photoslibrary.readonly and photoslibrary.sharing have been removed for new apps
- This tool uses photoslibrary.appendonly which remains available

### Google Photos API Rate Limits

- Upload rate: approximately 2 files per second
- Frequent 429 (rate limit) errors on large batch uploads
- The tool handles this automatically but large libraries take time

### File Type Restrictions

Google Photos only accepts:
- Images: JPG, GIF, WebP, TIFF, RAW formats
- Minimum dimension: 256 pixels
- Maximum file size: 200MB for photos, 10GB for videos

## Supported Photo Formats

- JPEG, PNG, GIF, BMP, WebP, TIFF
- HEIC/HEIF
- RAW formats (CR2, NEF, ARW, RW2, ORF, RAF, DNG)
