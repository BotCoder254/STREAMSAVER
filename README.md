# StreamSaver Pro

A modern YouTube downloader application with a clean UI, built with Python and Flet.

## Features

- Download videos from YouTube and other supported platforms
- Choose between video (MP4) and audio (MP3, M4A) formats
- Select quality for both video and audio downloads
- Search YouTube directly within the app
- Queue multiple downloads
- Track download progress
- Pause and resume downloads
- Settings panel with system resource monitoring
- Real-time statistics for CPU, memory, network usage

## Screenshots

![StreamSaver Pro](https://i.imgur.com/qQJZc97.png)

## Requirements

- Python 3.7+
- Required packages (see `requirements.txt`)
- ffmpeg (optional, for audio conversion)

## Installation

1. Clone the repository or download the source code
2. Install required packages:

```
pip install -r requirements.txt
```

3. Run the application:

```
python app.py
```

### Optional: Install ffmpeg

For full audio conversion functionality, ffmpeg is recommended:

- **Windows**: Download from [ffmpeg.org](https://ffmpeg.org/download.html) and add to PATH
- **macOS**: Install with Homebrew: `brew install ffmpeg`
- **Linux**: Install with your package manager (e.g., `apt install ffmpeg`)

## Usage

1. **URL Mode**:
   - Paste a YouTube URL and click the search icon
   - Select format (video/audio) and quality
   - Click "Download" or "Add to Queue"

2. **Search Mode**:
   - Click the "Search" tab
   - Enter search terms and click the search icon
   - Browse results, click on a video to select it
   - Choose format and quality, then download or queue

3. **Queue Management**:
   - Add multiple videos to the queue
   - Use the play/pause button to control downloads
   - Click the folder button to access downloaded files
   - Remove items from the queue as needed

4. **Settings Panel**:
   - Click the settings icon in the top-right corner
   - View system information and statistics
   - Monitor real-time resource usage with graphs

## New Features in v1.2.0

- Added Settings panel with system information
- Real-time resource monitoring with interactive graphs
- System statistics tracking (CPU, memory, network)
- Network usage monitoring
- Enhanced UI with better responsive design
- Improved download management system

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- [Flet](https://flet.dev/) - Flutter-powered UI toolkit for Python
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) - YouTube downloader
- [plotly](https://plotly.com/python/) - Interactive graphing library
- [psutil](https://github.com/giampaolo/psutil) - Process and system utilities 