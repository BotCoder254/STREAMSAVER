import flet as ft
import os
import re
import time
import subprocess
from threading import Thread, Lock
from pathlib import Path
from datetime import datetime
import yt_dlp
from pytubefix import YouTube
import traceback
import urllib.parse

# Import settings module
try:
    from settings import SettingsPanel
except ImportError:
    print("Settings module not found. Some features may not be available.")
    SettingsPanel = None

# Import the YouTube search library
try:
    from youtubesearchpython import VideosSearch
except ImportError:
    # If not installed, inform the user
    print("YouTube Search Python library not installed. Please install it with: pip install youtube-search-python==1.4.6")

# Create a workaround for the proxies issue
import sys
import importlib.util
if 'youtubesearchpython' in sys.modules:
    # Try to patch the library - this is a workaround for the proxies issue
    try:
        # This will patch any methods that might be using 'proxies' parameter
        import httpx
        
        # Save the original post method
        original_post = httpx.post
        
        # Create a wrapper that removes 'proxies' from kwargs
        def patched_post(*args, **kwargs):
            if 'proxies' in kwargs:
                del kwargs['proxies']
            return original_post(*args, **kwargs)
        
        # Replace the httpx.post with our patched version
        httpx.post = patched_post
        print("Successfully patched httpx.post to fix 'proxies' issue")
    except Exception as e:
        print(f"Failed to patch httpx for YouTube search: {e}")

# Import torrent panel
from torrent_panel import TorrentPanel


class ModernYouTubeDownloader:
    def __init__(self, page: ft.Page):
        self.page = page
        self.video_queue = []
        self.current_video_info = None
        self.countdown_timer = None
        self.countdown_value = 3
        self.active_downloads = {}  # Track active downloads by queue item ID
        self.update_lock = Lock()  # Add lock for thread-safe updates
        self.is_closing = False    # Flag to track if the app is closing
        
        # Pagination variables
        self.current_search_term = ""
        self.current_page = 1
        self.videos_search = None
        self.has_more_pages = False
        
        # Initialize settings panel if available
        self.settings_panel = None
        if SettingsPanel:
            self.settings_panel = SettingsPanel(page, self.handle_settings_action)
        
        # Initialize torrent panel
        self.torrent_panel = TorrentPanel(page, self.handle_settings_action)
        
        self.setup_page()
        self.init_controls()
        self.build_ui()
        
        # Add tab-like UI elements for switching between URL and Search
        self.display_url_mode()
        
        # Check for ffmpeg
        self.has_ffmpeg = self.check_ffmpeg()
        if not self.has_ffmpeg:
            self.status_text.value = "Warning: ffmpeg not found. Audio conversion features will be limited."
            self.update_ui()
            
    def handle_settings_action(self, action_data):
        """Handle settings panel actions"""
        try:
            if action_data.get("type") == "add_to_queue":
                item = action_data.get("item")
                if item and item.get("type") == "torrent":
                    # Create a unique ID for the queue item
                    item_id = f"torrent_{len(self.video_queue)}"
                    
                    # Create the queue item container
                    queue_item = self.create_queue_item(
                        item_id=item_id,
                        title=item["title"],
                        download_path=item["download_path"],
                        item_type="torrent",
                        torrent=item["torrent"]
                    )
                    
                    # Add to queue
                    self.video_queue.append({
                        "id": item_id,
                        "container": queue_item,
                        "type": "torrent",
                        "torrent": item["torrent"],
                        "status": "queued"
                    })
                    
                    # Add to queue list
                    self.queue_list.controls.append(queue_item)
                    self.update_ui()
                    
                    # Start download if it's the only item
                    if len(self.video_queue) == 1:
                        self.start_next_download()
            
            elif action_data.get("type") == "status":
                # Update status message
                self.status_text.value = action_data.get("message", "")
                self.update_ui()
                
        except Exception as e:
            print(f"Error handling action: {str(e)}")
            self.status_text.value = f"Error: {str(e)}"
            self.update_ui()

    def setup_page(self):
        self.page.title = "StreamSaver Pro"
        self.page.window_width = 1200
        self.page.window_height = 750
        self.page.window_resizable = True
        self.page.window_min_width = 950  # Minimum width to ensure UI elements don't collapse
        self.page.window_min_height = 600  # Minimum height to ensure UI elements don't collapse
        self.page.padding = 0
        self.page.spacing = 0
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = "#0f0f0f"
        
        # Handle page resize event
        self.page.on_resize = self.on_page_resize
        
        self.page.update()
        
    def on_page_resize(self, e):
        """Handle window resize event"""
        try:
            # Adjust UI elements based on window size if needed
            width = self.page.window_width
            height = self.page.window_height
            
            # Adjust left panel width based on window width
            if width < 1100:
                # Smaller screen, adjust left panel width
                new_width = max(380, width * 0.35)  # Min width of 380px or 35% of window
                
                # Make sure there's still room for the queue panel
                if new_width > width * 0.45:
                    new_width = width * 0.45
                
                # Update left panel width
                for control in self.page.controls:
                    if isinstance(control, ft.Row) and hasattr(control, "controls"):
                        for c in control.controls:
                            if hasattr(c, "width") and isinstance(c, ft.Container) and c.width == 450:
                                c.width = new_width
                
                # Also adjust the width of the search controls
                if hasattr(self, "url_input"):
                    self.url_input.width = max(250, new_width - 100)
                    self.search_input.width = max(250, new_width - 100)
                    self.search_results_container.width = new_width - 30
                    self.thumbnail.width = max(250, new_width - 100)
                    self.progress_bar.width = max(250, new_width - 100)
                    self.status_text.width = max(250, new_width - 100)
                    self.video_title.width = max(250, new_width - 100)
                    self.video_author.width = max(250, new_width - 100)
                    self.video_length.width = max(250, new_width - 100)
            else:
                # Restore normal width on larger screens
                for control in self.page.controls:
                    if isinstance(control, ft.Row) and hasattr(control, "controls"):
                        for c in control.controls:
                            if hasattr(c, "width") and isinstance(c, ft.Container) and c.width != 450 and c.width > 380:
                                c.width = 450
                
                # Restore standard widths
                if hasattr(self, "url_input"):
                    self.url_input.width = 350
                    self.search_input.width = 350
                    self.search_results_container.width = 420
                    self.thumbnail.width = 350
                    self.progress_bar.width = 350
                    self.status_text.width = 350
                    self.video_title.width = 350
                    self.video_author.width = 350
                    self.video_length.width = 350
            
            # Adjust search results container height based on window height
            if height < 700:
                # On smaller screens, reduce the height of the search results
                self.search_results_container.content.height = max(200, height - 500)
            else:
                # Restore normal height on larger screens
                self.search_results_container.content.height = 300
            
            # Ensure the vertical divider has proper height
            for control in self.page.controls:
                if isinstance(control, ft.Row) and len(control.controls) > 1:
                    for c in control.controls:
                        if isinstance(c, ft.Container) and hasattr(c, "content") and isinstance(c.content, ft.VerticalDivider):
                            # Ensure divider stretches properly
                            c.height = None
            
            self.update_ui()
        except Exception as e:
            print(f"Error in resize handler: {str(e)}")
            print(traceback.format_exc())

    def init_controls(self):
        # Tab-like buttons for mode switching
        self.url_tab = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.LINK, color="#ffffff", size=16),
                    ft.Text("URL Input", color="#ffffff", size=14),
                ],
                spacing=5,
            ),
            padding=ft.padding.symmetric(horizontal=15, vertical=10),
            bgcolor="#ff0000",
            border_radius=ft.border_radius.only(top_left=8, top_right=8),
            on_click=self.switch_to_url_mode,
        )
        
        self.search_tab = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.YOUTUBE_SEARCHED_FOR, color="#bbbbbb", size=16),
                    ft.Text("Search", color="#bbbbbb", size=14),
                ],
                spacing=5,
            ),
            padding=ft.padding.symmetric(horizontal=15, vertical=10),
            bgcolor="#1f1f1f",
            border_radius=ft.border_radius.only(top_left=8, top_right=8),
            on_click=self.switch_to_search_mode,
        )

        # Text input for media URL
        self.url_input = ft.TextField(
            label="Enter URL",
            hint_text="Paste YouTube or other supported video URL here...",
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            prefix_icon=ft.Icons.LINK,
            height=55,
            text_size=14,
            width=350,
            on_submit=self.validate_url,
        )

        # URL submit button
        self.url_submit_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            tooltip="Fetch Video Info",
            icon_color="white",
            bgcolor="#ff0000",
            icon_size=20,
            on_click=self.validate_url,
        )

        # Search input
        self.search_input = ft.TextField(
            label="Search YouTube",
            hint_text="Enter search terms...",
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            prefix_icon=ft.Icons.YOUTUBE_SEARCHED_FOR,
            height=55,
            text_size=14,
            width=350,
            on_submit=self.search_youtube,
            visible=False,  # Initially hidden
        )

        # Search button
        self.search_button = ft.IconButton(
            icon=ft.Icons.SEARCH,
            tooltip="Search YouTube",
            icon_color="white",
            bgcolor="#ff0000",
            icon_size=20,
            on_click=self.search_youtube,
            visible=False,  # Initially hidden
        )

        # Pagination controls for search results
        self.prev_page_button = ft.IconButton(
            icon=ft.Icons.ARROW_BACK,
            tooltip="Previous Page",
            icon_color="white",
            bgcolor="#333333",
            icon_size=18,
            on_click=self.load_prev_page,
            disabled=True,
            visible=False,
        )
        
        self.next_page_button = ft.IconButton(
            icon=ft.Icons.ARROW_FORWARD,
            tooltip="Next Page",
            icon_color="white",
            bgcolor="#ff0000",
            icon_size=18,
            on_click=self.load_next_page,
            disabled=True,
            visible=False,
        )
        
        self.page_text = ft.Text(
            "Page 1",
            size=14,
            color="white",
            visible=False,
        )
        
        self.pagination_row = ft.Row(
            [
                self.prev_page_button,
                self.page_text,
                self.next_page_button,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=10,
            visible=False,
        )

        # Search results container
        self.search_results_container = ft.Container(
            content=ft.Column(
                [],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                height=300,
            ),
            visible=False,
            bgcolor="#111111",
            border_radius=8,
            padding=10,
            margin=ft.margin.only(bottom=10),
            width=450,
        )

        # Download type selection
        self.download_type = ft.Dropdown(
            label="Download Type",
            hint_text="Select type",
            options=[
                ft.dropdown.Option("video", "Video (MP4)"),
                ft.dropdown.Option("audio", "Audio (MP3)"),
                ft.dropdown.Option("audio_hq", "Audio HQ (M4A)"),
            ],
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            content_padding=10,
            text_size=14,
            disabled=True,
            width=170,
        )

        # Video quality selection for video downloads
        self.video_quality = ft.Dropdown(
            label="Video Quality",
            hint_text="Select quality",
            options=[
                ft.dropdown.Option("best", "Best"),
                ft.dropdown.Option("1080p", "1080p"),
                ft.dropdown.Option("720p", "720p"),
                ft.dropdown.Option("480p", "480p"),
                ft.dropdown.Option("360p", "360p"),
                ft.dropdown.Option("240p", "240p"),
                ft.dropdown.Option("144p", "144p"),
            ],
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            content_padding=10,
            text_size=14,
            disabled=True,
            width=170,
            visible=False,
        )

        # Audio quality selection for audio downloads
        self.audio_quality = ft.Dropdown(
            label="Audio Quality",
            hint_text="Select quality",
            options=[
                ft.dropdown.Option("best", "Best"),
                ft.dropdown.Option("high", "High"),
                ft.dropdown.Option("medium", "Medium"),
                ft.dropdown.Option("low", "Low"),
            ],
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            content_padding=10,
            text_size=14,
            disabled=True,
            width=170,
            visible=False,
        )

        # Download path selection
        self.download_path = ft.TextField(
            label="Save to folder",
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            height=55,
            text_size=14,
            value=str(Path.home() / "Downloads"),
            read_only=True,
            width=290,
            content_padding=10,
            prefix_icon=ft.Icons.FOLDER,
        )

        # Browse button for selecting download path
        self.browse_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Browse",
            icon_color="white",
            bgcolor="#333333",
            icon_size=20,
            on_click=self.browse_directory,
            disabled=True,
        )

        # Download button
        self.download_button = ft.ElevatedButton(
            text="Download",
            icon=ft.Icons.DOWNLOAD,
            bgcolor="#ff0000",
            color="white",
            height=50,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            disabled=True,
            width=170,
            on_click=self.start_download,
        )

        # Add to queue button
        self.queue_button = ft.ElevatedButton(
            text="Add to Queue",
            icon=ft.Icons.PLAYLIST_ADD,
            bgcolor="#333333",
            color="white",
            height=50,
            style=ft.ButtonStyle(
                shape=ft.RoundedRectangleBorder(radius=8),
            ),
            disabled=True,
            width=170,
            on_click=self.add_to_queue,
        )

        # Video info display
        self.video_title = ft.Text(
            value="", 
            size=16, 
            weight=ft.FontWeight.BOLD,
            color="white",
            width=350,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=2,
        )
        
        self.video_author = ft.Text(
            value="", 
            size=14,
            color="#bbbbbb", 
            width=350,
            overflow=ft.TextOverflow.ELLIPSIS,
            max_lines=1,
        )
        
        self.video_length = ft.Text(
            value="", 
            size=14,
            color="#bbbbbb",
            width=350,
        )

        self.thumbnail = ft.Image(
            src="",
            width=350,
            height=200,
            fit=ft.ImageFit.COVER,
            border_radius=ft.border_radius.all(8),
            visible=False,
        )

        # Progress bar and status
        self.progress_bar = ft.ProgressBar(
            width=350, 
            color="#ff0000",
            bgcolor="#333333", 
            value=0,
            visible=False,
        )
        
        self.status_text = ft.Text(
            value="", 
            size=14,
            color="#bbbbbb",
            text_align=ft.TextAlign.LEFT,
            width=350,
        )

        # Loading spinner
        self.spinner_row = ft.Row(
            [
                ft.ProgressRing(
                    width=25,
                    height=25,
                    stroke_width=3,
                    color="#ff0000",
                ),
                ft.Text(
                    f"Fetching video info... {self.countdown_value}",
                    size=14,
                    color="#bbbbbb",
                )
            ],
            spacing=10,
            visible=False,
        )

        # Queue list
        self.queue_list = ft.ListView(
            spacing=5,
            padding=10,
            expand=True,
            auto_scroll=True,
        )

        # Footer with attribution
        self.footer = ft.Text(
            "StreamSaver Pro | Created with Flet, YT-DLP, and Python",
            size=12,
            color="#666666",
            text_align=ft.TextAlign.CENTER,
        )

        # Queue count
        self.queue_count = ft.Text(
            "Queue: 0 items",
            size=12,
            color="#bbbbbb",
            text_align=ft.TextAlign.LEFT,
        )

    def build_ui(self):
        # Header
        header = ft.Container(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.STREAM, color="#ff0000", size=32),
                    ft.Text(
                        "StreamSaver Pro",
                        size=24,
                        weight=ft.FontWeight.BOLD,
                        color="white",
                    ),
                    ft.Row(
                        [
                            # Add torrent button
                            ft.IconButton(
                                icon=ft.Icons.DOWNLOAD_ROUNDED,
                                tooltip="Torrent Downloader",
                                icon_color="white",
                                icon_size=24,
                                on_click=self.toggle_torrent_panel,
                            ),
                            # Settings button if available
                            self.settings_panel.get_settings_button() if self.settings_panel else ft.Container(width=0),
                        ],
                        spacing=10,
                    ),
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            padding=15,
            bgcolor="#0f0f0f",
        )

        # Left panel - Input controls
        left_panel = ft.Container(
            content=ft.Column(
                [
                    # Tab row for switching between URL and Search
                    ft.Row(
                        [self.url_tab, self.search_tab],
                        spacing=0,
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    
                    # Input container with border
                    ft.Container(
                        content=ft.Column(
                            [
                                # URL input row
                                ft.Container(
                                    content=ft.Row(
                                        [self.url_input, self.url_submit_button],
                                        alignment=ft.MainAxisAlignment.START,
                                        spacing=5,
                                    ),
                                    padding=ft.padding.only(bottom=10),
                                ),
            
                                # Search input row
                                ft.Container(
                                    content=ft.Row(
                                        [self.search_input, self.search_button],
                                        alignment=ft.MainAxisAlignment.START,
                                        spacing=5,
                                    ),
                                    padding=ft.padding.only(bottom=10),
                                ),
                                
                                # Pagination controls
                                self.pagination_row,
                                
                                # Search results
                                self.search_results_container,
                            ],
                            spacing=0,
                        ),
                        padding=15,
                        bgcolor="#0f0f0f",
                        border=ft.border.only(
                            left=ft.border.BorderSide(1, "#333333"),
                            right=ft.border.BorderSide(1, "#333333"),
                            bottom=ft.border.BorderSide(1, "#333333"),
                        ),
                        border_radius=ft.border_radius.only(
                            bottom_left=8,
                            bottom_right=8,
                        ),
                        margin=ft.margin.only(bottom=15),
                    ),
                    
                    # Spinner for loading
                    self.spinner_row,
                    
                    # Video info display
                    ft.Container(
                        content=ft.Column(
                            [
                                self.thumbnail,
                                self.video_title,
                                self.video_author,
                                self.video_length,
                            ],
                            spacing=5,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                        ),
                        padding=ft.padding.only(bottom=15),
                    ),
                    
                    # Download options
                    ft.Container(
                        content=ft.Column(
                            [
                                # Format row
                                ft.Row(
                                    [
                                        self.download_type,
                                        self.video_quality,
                                        self.audio_quality,
                                    ],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=10,
                                    wrap=True,
                                ),
                                
                                # Path row
                                ft.Row(
                                    [
                                        self.download_path,
                                        self.browse_button,
                                    ],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=5,
                                ),
                                
                                # Buttons row
                                ft.Row(
                                    [
                                        self.download_button,
                                        self.queue_button,
                                    ],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=10,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=ft.padding.only(bottom=15),
                    ),
                    
                    # Progress and status
                    ft.Container(
                        content=ft.Column(
                            [
                                self.progress_bar,
                                self.status_text,
                            ],
                            spacing=5,
                            horizontal_alignment=ft.CrossAxisAlignment.START,
                        ),
                    ),
                ],
                spacing=0,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            padding=20,
            bgcolor="#0f0f0f",
            border_radius=ft.border_radius.all(0),
            width=450,  # Fixed width to accommodate search
            alignment=ft.alignment.top_left,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
        )

        # Right panel - Queue list
        right_panel = ft.Container(
            content=ft.Column(
                [
                    # Queue header
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.QUEUE, color="#ff0000", size=20),
                            ft.Text(
                                "Download Queue",
                                size=18,
                                weight=ft.FontWeight.BOLD,
                                color="white",
                            ),
                            self.queue_count,
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    ft.Divider(height=1, color="#333333"),
                    
                    # Queue list
                    ft.Container(
                        content=self.queue_list,
                        expand=True,
                        bgcolor="#111111",
                        border_radius=8,
                        padding=5,
                    ),
                ],
                spacing=10,
                expand=True,
            ),
            padding=20,
            bgcolor="#0f0f0f",
            expand=True,
            alignment=ft.alignment.top_left,
        )

        # Main content - two-panel layout
        main_content = ft.Row(
            [
                left_panel,
                ft.Container(
                    content=ft.VerticalDivider(
                        width=1,
                        color="#333333",
                        thickness=1,
                    ),
                    height=None,  # Let it stretch to full height
                    margin=ft.margin.all(0),
                    padding=ft.padding.all(0),
                ),
                right_panel,
            ],
            expand=True,
            spacing=0,
            alignment=ft.MainAxisAlignment.START,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )

        # Footer
        footer = ft.Container(
            content=self.footer,
            padding=10,
            bgcolor="#050505",
        )

        # Add all sections to the page
        self.page.add(
            header,
            ft.Container(
                content=ft.Divider(height=1, color="#333333"),
                margin=ft.margin.all(0),
                padding=ft.padding.all(0),
            ),
            main_content,
            ft.Container(
                content=ft.Divider(height=1, color="#333333"),
                margin=ft.margin.all(0),
                padding=ft.padding.all(0),
            ),
            footer,
        )
        
        # Add settings panel to page overlay if available
        if self.settings_panel:
            self.page.overlay.append(self.settings_panel.get_settings_panel())

    def validate_url(self, e=None):
        url = self.url_input.value
        
        # Clear previous video info
        self.reset_video_info()
        
        # URL validation pattern
        url_pattern = r'^(https?:\/\/)?(www\.)?(youtube\.com|youtu\.be|vimeo\.com|dailymotion\.com|twitch\.tv).*'
        
        if re.match(url_pattern, url):
            # Show spinner with countdown
            self.spinner_row.visible = True
            self.status_text.value = "Preparing to fetch video information..."
            self.update_ui()
            
            # Start countdown
            self.countdown_value = 3
            self.update_countdown_text()
            self.countdown_timer = True
            
            # Start thread to fetch video info
            Thread(target=self.fetch_video_info, args=(url,)).start()
        else:
            self.status_text.value = "Invalid URL. Please enter a supported video URL"
            self.update_ui()

    def update_countdown_text(self):
        if not self.countdown_timer:
            return
            
        self.spinner_row.controls[1].value = f"Fetching video info... {self.countdown_value}"
        self.update_ui()
        
        if self.countdown_value > 0:
            self.countdown_value -= 1
            time.sleep(1)
            self.update_countdown_text()

    def reset_video_info(self):
        self.video_title.value = ""
        self.video_author.value = ""
        self.video_length.value = ""
        self.thumbnail.src = ""
        self.thumbnail.visible = False
        self.download_type.disabled = True
        self.video_quality.disabled = True
        self.video_quality.visible = False
        self.audio_quality.disabled = True
        self.audio_quality.visible = False
        self.browse_button.disabled = True
        self.download_button.disabled = True
        self.queue_button.disabled = True
        self.progress_bar.visible = False
        self.progress_bar.value = 0
        self.status_text.value = ""
        self.spinner_row.visible = False
        self.current_video_info = None
        self.countdown_timer = False
        # Hide search results container when resetting
        self.search_results_container.visible = False
        self.pagination_row.visible = False
        self.update_ui()

    def fetch_video_info(self, url):
        try:
            # YT-DLP extraction
            ydl_opts = {
                'quiet': True,
                'no_warnings': True,
                'skip_download': True,
                'ignoreerrors': False,
            }
            
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                
                if info:
                    # Store video info for later use
                    self.current_video_info = {
                        'id': info.get('id', ''),
                        'title': info.get('title', 'Unknown Title'),
                        'uploader': info.get('uploader', 'Unknown Uploader'),
                        'duration': info.get('duration', 0),
                        'thumbnail': info.get('thumbnail', ''),
                        'url': url,
                        'formats': info.get('formats', []),
                        'ext': info.get('ext', 'mp4')
                    }
                    
                    # Update UI with video information in a thread-safe manner
                    try:
                        self.update_video_info(
                            self.current_video_info['title'], 
                            self.current_video_info['uploader'], 
                            self.format_duration(self.current_video_info['duration']), 
                            self.current_video_info['thumbnail']
                        )
                        
                        # Enable download options
                        self.enable_download_options()
                    except Exception as ui_error:
                        print(f"UI update error: {str(ui_error)}")
                        print(traceback.format_exc())
                else:
                    self.show_error("Could not fetch video information. Please check URL.")
            
        except Exception as e:
            print(f"Error fetching video info: {str(e)}")
            print(traceback.format_exc())
            self.show_error(f"Error fetching video information: {str(e)}")

    def update_video_info(self, title, author, length, thumbnail_url):
        """Update UI with video information in a thread-safe manner"""
        try:
            self.spinner_row.visible = False
            self.countdown_timer = False
            
            self.video_title.value = title
            self.video_author.value = f"By: {author}"
            self.video_length.value = f"Duration: {length}"
            self.thumbnail.src = thumbnail_url
            self.thumbnail.visible = True
            self.status_text.value = "Video information loaded successfully"
            self.update_ui()
        except Exception as e:
            print(f"Error updating video info UI: {str(e)}")
            print(traceback.format_exc())
            
    def show_error(self, message):
        """Display error message in a thread-safe manner"""
        try:
            self.status_text.value = message
            self.progress_bar.value = 0
            self.progress_bar.visible = False
            
            # Re-enable UI
            self.enable_ui_after_download()
        except Exception as e:
            print(f"Error showing error message: {str(e)}")
            print(traceback.format_exc())

    def enable_download_options(self):
        self.download_type.disabled = False
        self.browse_button.disabled = False
        
        # Set handler for download type change
        self.download_type.on_change = self.on_download_type_change
        
        self.status_text.value = "Select download options"
        self.update_ui()

    def on_download_type_change(self, e):
        if self.download_type.value == "video":
            self.video_quality.visible = True
            self.video_quality.disabled = False
            self.audio_quality.visible = False
            self.audio_quality.disabled = True
        else:  # audio or audio_hq
            self.audio_quality.visible = True
            self.audio_quality.disabled = False
            self.video_quality.visible = False
            self.video_quality.disabled = True
            
        self.download_button.disabled = False
        self.queue_button.disabled = False
        self.update_ui()

    def browse_directory(self, e):
        def pick_folder_result(e: ft.FilePickerResultEvent):
            if e.path:
                self.download_path.value = e.path
                self.update_ui()

        picker = ft.FilePicker(on_result=pick_folder_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.get_directory_path()

    def add_to_queue(self, e):
        if not self.url_input.value or not self.download_type.value or not self.current_video_info:
            self.status_text.value = "Please fill in all required fields"
            self.update_ui()
            return
            
        # Check that user has selected a format
        if (self.download_type.value == "video" and not self.video_quality.value) or \
           (self.download_type.value in ["audio", "audio_hq"] and not self.audio_quality.value):
            self.status_text.value = "Please select quality before adding to queue"
            self.update_ui()
            return
            
        # Prepare queue item data
        queue_item = {
            'video_info': self.current_video_info,
            'download_type': self.download_type.value,
            'quality': self.get_selected_quality(),
            'download_path': self.download_path.value,
            'status': 'queued',
            'progress': 0,
            'id': f"queue_{len(self.video_queue)}_{int(time.time())}"
        }
        
        # Add to queue
        self.video_queue.append(queue_item)
        
        # Update queue UI
        self.add_item_to_queue_ui(queue_item)
        
        # Update queue count
        self.queue_count.value = f"Queue: {len(self.video_queue)} items"
        self.update_ui()
        
        # Show notification
        self.status_text.value = "Added to download queue"
        self.update_ui()
        
        # Reset for next video
        self.url_input.value = ""
        self.reset_video_info()

    def get_selected_quality(self):
        if self.download_type.value == "video":
            return self.video_quality.value or "best"
        else:
            return self.audio_quality.value or "best"

    def add_item_to_queue_ui(self, queue_item):
        # Create progress bar for this item
        progress_bar = ft.ProgressBar(
            width=None,  # Full width
            color="#ff0000",
            bgcolor="#333333",
            value=0,
            height=4,
        )
        
        # Create status text for this item
        status_text = ft.Text(
            value="Queued",
            size=11,
            color="white",
        )
        
        # Create status container
        status_container = ft.Container(
            content=status_text,
            bgcolor="#555555",
            padding=ft.padding.all(3),
            border_radius=ft.border_radius.all(4),
        )
        
        # Generate a unique color for this item's progress bar
        progress_color = self.generate_random_color()
        progress_bar.color = progress_color
        
        # Download button for this item
        download_button = ft.IconButton(
            icon=ft.Icons.DOWNLOAD,
            tooltip="Download",
            icon_color="#00C853",
            icon_size=18,
            on_click=lambda e, id=queue_item['id']: self.start_queue_item_download(id),
            disabled=False,
        )
        
        # Pause button for this item
        pause_button = ft.IconButton(
            icon=ft.Icons.PAUSE,
            tooltip="Pause",
            icon_color="#FFC107",
            icon_size=18,
            on_click=lambda e, id=queue_item['id']: self.pause_queue_item_download(id),
            disabled=True,
        )
        
        # Delete button for this item
        delete_button = ft.IconButton(
            icon=ft.Icons.DELETE_OUTLINE,
            tooltip="Remove from queue",
            icon_color="#ff0000",
            icon_size=18,
            on_click=lambda e, id=queue_item['id']: self.remove_from_queue(id),
        )
        
        # Folder access button for this item
        folder_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Open download location",
            icon_color="#4FC3F7",
            icon_size=18,
            on_click=lambda e, id=queue_item['id']: self.open_download_folder(id),
            disabled=True,
        )
        
        # Expand/collapse button
        expand_button = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            tooltip="Expand details",
            icon_color="#FFFFFF",
            icon_size=18,
            on_click=lambda e, id=queue_item['id']: self.toggle_item_details(id),
        )
        
        # Details section (initially collapsed)
        details_section = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        f"File will be saved to: {queue_item['download_path']}",
                        size=12,
                        color="#bbbbbb",
                    ),
                    ft.Text(
                        f"Format: {self.get_download_type_label(queue_item['download_type'])}",
                        size=12,
                        color="#bbbbbb",
                    ),
                    ft.Text(
                        f"Quality: {queue_item['quality']}",
                        size=12,
                        color="#bbbbbb",
                    ),
                ],
                spacing=2,
            ),
            visible=False,
            padding=5,
        )
        
        # Create queue item UI
        item = ft.Container(
            content=ft.Column(
                [
                    ft.Row(
                        [
                            # Thumbnail
                            ft.Container(
                                content=ft.Image(
                                    src=queue_item['video_info']['thumbnail'],
                                    width=100,
                                    height=60,
                                    fit=ft.ImageFit.COVER,
                                    border_radius=ft.border_radius.all(4),
                                ),
                                width=100,
                                height=60,
                            ),
                            
                            # Info
                            ft.Column(
                                [
                                    ft.Text(
                                        queue_item['video_info']['title'],
                                        size=14,
                                        weight=ft.FontWeight.BOLD,
                                        color="white",
                                        overflow=ft.TextOverflow.ELLIPSIS,
                                        max_lines=1,
                                    ),
                                    ft.Text(
                                        f"Type: {self.get_download_type_label(queue_item['download_type'])} | Quality: {queue_item['quality']}",
                                        size=12,
                                        color="#bbbbbb",
                                    ),
                                    status_container,
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            
                            # Actions
                            ft.Row(
                                [
                                    download_button,
                                    pause_button,
                                    folder_button,
                                    delete_button,
                                    expand_button,
                                ],
                                spacing=0,
                            ),
                        ],
                        spacing=10,
                        alignment=ft.MainAxisAlignment.START,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    # Progress bar for this item
                    progress_bar,
                    # Details section (expandable)
                    details_section,
                ],
                spacing=5,
            ),
            padding=10,
            margin=ft.margin.only(bottom=5),
            bgcolor="#1a1a1a",
            border_radius=ft.border_radius.all(8),
            key=queue_item['id'],
            data={
                "progress_bar": progress_bar,
                "status_container": status_container,
                "status_text": status_text,
                "download_button": download_button,
                "pause_button": pause_button,
                "folder_button": folder_button,
                "delete_button": delete_button,
                "expand_button": expand_button,
                "details_section": details_section,
                "progress_color": progress_color,
                "is_expanded": False,
                "download_path": queue_item['download_path'],
                "output_file": None,  # Will store the output file path when download completes
            },
        )
        
        self.queue_list.controls.append(item)
        self.update_ui()
        
    def toggle_item_details(self, item_id):
        # Find the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Get data elements
        details_section = container.data["details_section"]
        expand_button = container.data["expand_button"]
        is_expanded = container.data["is_expanded"]
        
        # Toggle expanded state
        if is_expanded:
            details_section.visible = False
            expand_button.icon = ft.Icons.EXPAND_MORE
            expand_button.tooltip = "Expand details"
            container.data["is_expanded"] = False
        else:
            details_section.visible = True
            expand_button.icon = ft.Icons.EXPAND_LESS
            expand_button.tooltip = "Collapse details"
            container.data["is_expanded"] = True
            
        # Update UI
        self.update_ui()

    def generate_random_color(self):
        """Generate a random color for progress bars to differentiate queue items"""
        import random
        colors = [
            "#FF5252",  # Red
            "#448AFF",  # Blue
            "#69F0AE",  # Green
            "#FFD740",  # Amber
            "#FF6E40",  # Deep Orange
            "#E040FB",  # Purple
            "#00B8D4",  # Cyan
            "#EEFF41",  # Lime
            "#F48FB1",  # Pink
            "#7986CB",  # Indigo
        ]
        return random.choice(colors)

    def get_download_type_label(self, download_type):
        if download_type == "video":
            return "Video"
        elif download_type == "audio":
            return "Audio MP3"
        elif download_type == "audio_hq":
            return "Audio HQ"
        return download_type

    def remove_from_queue(self, item_id):
        # Remove from active downloads if it's being downloaded
        if item_id in self.active_downloads:
            self.active_downloads[item_id]['status'] = 'cancelled'
        
        # Remove from queue list
        for i, item in enumerate(self.video_queue):
            if item['id'] == item_id:
                self.video_queue.pop(i)
                break
                
        # Remove from UI
        for i, control in enumerate(self.queue_list.controls):
            if control.key == item_id:
                self.queue_list.controls.pop(i)
                break
                
        # Update queue count
        self.queue_count.value = f"Queue: {len(self.video_queue)} items"
        self.update_ui()

    def start_download(self, e):
        if not self.url_input.value or not self.download_type.value or not self.current_video_info:
            self.status_text.value = "Please fill in all required fields"
            self.update_ui()
            return
            
        # Disable UI during download
        self.disable_ui_during_download()
        
        # Get download options
        download_type = self.download_type.value
        quality = self.get_selected_quality()
        download_path = self.download_path.value
        
        # Start download in a separate thread
        Thread(target=self.download_media, args=(
            self.current_video_info,
            download_type,
            quality,
            download_path
        )).start()

    def disable_ui_during_download(self):
        self.url_input.disabled = True
        self.url_submit_button.disabled = True
        self.download_type.disabled = True
        self.video_quality.disabled = True
        self.audio_quality.disabled = True
        self.browse_button.disabled = True
        self.download_button.disabled = True
        self.queue_button.disabled = True
        self.progress_bar.visible = True
        self.status_text.value = "Preparing download..."
        self.update_ui()

    def enable_ui_after_download(self):
        self.url_input.disabled = False
        self.url_submit_button.disabled = False
        self.download_type.disabled = False
        if self.download_type.value == "video":
            self.video_quality.disabled = False
        else:
            self.audio_quality.disabled = False
        self.browse_button.disabled = False
        self.download_button.disabled = False
        self.queue_button.disabled = False
        self.update_ui()

    def download_media(self, video_info, download_type, quality, download_path):
        try:
            url = video_info['url']
            
            # Update status
            self.update_status("Starting download...")
            
            # Create unique filename base
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"{video_info['title'].replace(' ', '_')}_{timestamp}"
            
            # Sanitize filename to remove invalid characters
            filename_base = re.sub(r'[\\/*?:"<>|]', "", filename_base)
            
            if download_type == "video":
                # Download video using YT-DLP
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                ydl_opts = {
                    'format': self.get_video_format_string(quality),
                    'outtmpl': output_template,
                    'progress_hooks': [self.yt_dlp_progress_hook],
                    'quiet': True,
                }
                
                # If ffmpeg is not available, adjust format to avoid merging
                if not self.has_ffmpeg:
                    ydl_opts['format'] = f'best[height<={self.get_height_for_quality(quality)}]'
                
                self.update_status(f"Downloading video in {quality} quality...")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    ydl.download([url])
                    
                # Get the actual output filename from the info dict
                info_dict = ydl.extract_info(url, download=False)
                output_file = ydl.prepare_filename(info_dict)
                    
                    # Update status on completion
                self.download_complete(output_file)
                
            elif download_type == "audio":
                # Download audio as MP3 using YT-DLP
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                if self.has_ffmpeg:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': self.get_audio_quality_string(quality),
                        }],
                        'progress_hooks': [self.yt_dlp_progress_hook],
                        'quiet': True,
                    }
                    
                    self.update_status(f"Downloading and converting to MP3 ({quality} quality)...")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                    # The output file will have .mp3 extension
                    output_file = os.path.join(download_path, f"{filename_base}.mp3")
                    
                    # Update status on completion
                    self.download_complete(output_file)
                else:
                    # Without ffmpeg, just download the best audio
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'progress_hooks': [self.yt_dlp_progress_hook],
                        'quiet': True,
                    }
                    
                    self.update_status(f"Downloading audio (ffmpeg not available, no conversion)...")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                    # Get the actual output filename
                    info_dict = ydl.extract_info(url, download=False)
                    output_file = ydl.prepare_filename(info_dict)
                    
                    # Update status on completion
                    self.download_complete(output_file)
                
            else:  # audio_hq
                # Download high quality audio (m4a) using YT-DLP
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                if self.has_ffmpeg:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'm4a',
                            'preferredquality': self.get_audio_quality_string(quality),
                        }],
                        'progress_hooks': [self.yt_dlp_progress_hook],
                        'quiet': True,
                    }
                    
                    self.update_status(f"Downloading high quality audio ({quality})...")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                    # The output file will have .m4a extension
                    output_file = os.path.join(download_path, f"{filename_base}.m4a")
                    
                    # Update status on completion
                    self.download_complete(output_file)
                else:
                    # Without ffmpeg, just download the best audio
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'progress_hooks': [self.yt_dlp_progress_hook],
                        'quiet': True,
                    }
                    
                    self.update_status(f"Downloading audio (ffmpeg not available, no conversion)...")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        ydl.download([url])
                        
                    # Get the actual output filename
                    info_dict = ydl.extract_info(url, download=False)
                    output_file = ydl.prepare_filename(info_dict)
                    
                    # Update status on completion
                    self.download_complete(output_file)
                
        except Exception as e:
            # Handle any exceptions
            self.show_error(f"Download error: {str(e)}")

    def get_video_format_string(self, quality):
        if quality == "best":
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
        elif quality == "1080p":
            return "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best"
        elif quality == "720p":
            return "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][ext=mp4]/best"
        elif quality == "480p":
            return "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best"
        elif quality == "360p":
            return "bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best"
        elif quality == "240p":
            return "bestvideo[height<=240][ext=mp4]+bestaudio[ext=m4a]/best[height<=240][ext=mp4]/best"
        elif quality == "144p":
            return "bestvideo[height<=144][ext=mp4]+bestaudio[ext=m4a]/best[height<=144][ext=mp4]/best"
        else:
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            
    def get_audio_quality_string(self, quality):
        if quality == "best":
            return "320"
        elif quality == "high":
            return "256"
        elif quality == "medium":
            return "192"
        elif quality == "low":
            return "128"
        else:
            return "192"
    
    def yt_dlp_progress_hook(self, d):
        if d['status'] == 'downloading':
            # Get download percentage
            if 'total_bytes' in d and d['total_bytes'] > 0:
                percentage = d['downloaded_bytes'] / d['total_bytes']
        
        # Update progress bar
                self.update_progress(percentage * 100)
                
                # Update status with download speed and ETA
                if 'speed' in d and d['speed']:
                    speed = self.format_size(d['speed']) + "/s"
                    eta = d.get('eta', 'N/A')
                    
                    if eta != 'N/A':
                        eta = self.format_duration(eta)
                        
                    status = f"Downloading: {percentage:.1%} | Speed: {speed} | ETA: {eta}"
                    self.update_status(status)
            
        elif d['status'] == 'finished':
            # Update status
            self.update_status("Download finished. Processing file...")

    def update_progress(self, percentage):
        self.progress_bar.value = percentage / 100  # Progress bar expects value between 0 and 1
        self.update_ui()

    def update_status(self, message):
        self.status_text.value = message
        self.update_ui()

    def download_complete(self, file_path):
        # Show completion status
        self.progress_bar.value = 1  # Set progress bar to 100%
        self.status_text.value = f"Download complete: {os.path.basename(file_path)}"
        
        # Re-enable UI
        self.enable_ui_after_download()

        # Show a popup to open the folder (optional)
        self.show_folder_option(file_path)
        
    def show_folder_option(self, file_path):
        """Show an option to open the downloaded file's folder"""
        def close_dialog(e):
            dialog.open = False
            self.page.update()
            
        def open_folder(e):
            try:
                if os.path.exists(file_path):
                    folder_path = os.path.dirname(file_path)
                    if sys.platform == "win32":
                        os.system(f'explorer /select,"{file_path}"')
                    elif sys.platform == "darwin":
                        os.system(f'open -R "{file_path}"')
                    else:
                        os.system(f'xdg-open "{folder_path}"')
                close_dialog(e)
            except Exception as e:
                self.status_text.value = f"Error opening folder: {str(e)}"
                self.update_ui()
                close_dialog(e)
                
        dialog = ft.AlertDialog(
            title=ft.Text("Download Complete"),
            content=ft.Text(f"File saved: {os.path.basename(file_path)}"),
            actions=[
                ft.TextButton("Open Folder", on_click=open_folder),
                ft.TextButton("Close", on_click=close_dialog),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        
        self.page.dialog = dialog
        dialog.open = True
        self.page.update()

    def format_size(self, bytes):
        """Format bytes to human readable size"""
        if bytes < 1024:
            return f"{bytes} B"
        elif bytes < 1024 * 1024:
            return f"{bytes/1024:.1f} KB"
        elif bytes < 1024 * 1024 * 1024:
            return f"{bytes/(1024*1024):.1f} MB"
        else:
            return f"{bytes/(1024*1024*1024):.2f} GB"

    def format_duration(self, seconds):
        """Format seconds into HH:MM:SS"""
        hours = int(seconds) // 3600
        minutes = (int(seconds) % 3600) // 60
        seconds = int(seconds) % 60
        
        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"

    def check_ffmpeg(self):
        """Check if ffmpeg is available in the system"""
        try:
            # Try both common commands
            subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            return True
        except FileNotFoundError:
            try:
                # Check in common Windows directories
                ffmpeg_paths = [
                    r"C:\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe",
                ]
                
                for path in ffmpeg_paths:
                    if os.path.exists(path):
                        # Set as environment variable
                        os.environ["PATH"] += os.pathsep + os.path.dirname(path)
                        return True
                        
                return False
            except:
                return False

    def search_youtube(self, e=None):
        """Search YouTube for videos based on the search input"""
        search_term = self.search_input.value.strip()
        
        if not search_term:
            self.status_text.value = "Please enter a search term"
            self.update_ui()
            return
        
        # If new search term, reset pagination
        if search_term != self.current_search_term:
            self.current_search_term = search_term
            self.current_page = 1
            self.videos_search = None
            
        # Show loading indicator
        self.status_text.value = "Searching YouTube..."
        self.search_results_container.visible = False
        self.pagination_row.visible = False
        self.update_ui()
        
        # Start search in a separate thread
        Thread(target=self.perform_youtube_search, args=(search_term,)).start()
    
    def perform_youtube_search(self, search_term):
        try:
            # Initialize search with version 1.4.6 of the library
            if self.videos_search is None:
                self.videos_search = VideosSearch(search_term, limit=10)
                
            # Get results
            results = self.videos_search.result()
            
            # Verify we can still update the UI before proceeding
            if self.is_closing:
                return
                
            # Clear previous results
            self.search_results_container.content.controls.clear()
            
            if results and 'result' in results and results['result']:
                # Create result items
                for video in results['result']:
                    self.add_search_result_item(video)
                
                # Show results container
                self.search_results_container.visible = True
                
                # Update page text
                self.page_text.value = f"Page {self.current_page}"
                
                # Update pagination controls visibility
                self.pagination_row.visible = True
                self.prev_page_button.visible = True
                self.next_page_button.visible = True
                self.page_text.visible = True
                
                # Enable/disable pagination buttons based on current state
                self.prev_page_button.disabled = self.current_page <= 1
                
                # Check if there are more pages
                self.has_more_pages = len(results['result']) == 10  # If we got the full requested amount
                self.next_page_button.disabled = not self.has_more_pages
                
                self.status_text.value = f"Found {len(results['result'])} results for '{search_term}' (Page {self.current_page})"
            else:
                self.search_results_container.visible = False
                self.pagination_row.visible = False
                self.status_text.value = f"No results found for '{search_term}'"
                
        except Exception as e:
            if not self.is_closing:
                self.search_results_container.visible = False
                self.pagination_row.visible = False
                self.status_text.value = f"Search error: {str(e)}"
                print(f"Search error details: {traceback.format_exc()}")
            
        # Update UI only if app is still running
        if not self.is_closing:
            self.update_ui()
            
    def load_next_page(self, e=None):
        """Load the next page of search results"""
        if not self.has_more_pages or not self.videos_search:
            return
            
        try:
            # Show loading indicator
            self.status_text.value = "Loading next page..."
            self.search_results_container.visible = False
            self.pagination_row.visible = False
            self.update_ui()
            
            # Use next() method to go to the next page
            more_results = self.videos_search.next()
            
            if more_results:
                self.current_page += 1
                # Fetch the new page of results
                self.perform_youtube_search(self.current_search_term)
            else:
                self.has_more_pages = False
                self.next_page_button.disabled = True
                self.status_text.value = "No more results available"
                self.update_ui()
        except Exception as e:
            self.status_text.value = f"Error loading next page: {str(e)}"
            print(f"Next page error: {traceback.format_exc()}")
            self.update_ui()
    
    def load_prev_page(self, e=None):
        """Load the previous page of search results"""
        if self.current_page <= 1 or not self.videos_search:
            return
            
        try:
            # For previous page, we need to reset and iterate forward
            self.status_text.value = "Loading previous page..."
            self.search_results_container.visible = False
            self.pagination_row.visible = False
            self.update_ui()
            
            # Reset search and iterate to the desired page
            target_page = self.current_page - 1
            self.videos_search = VideosSearch(self.current_search_term, limit=10)
            self.current_page = 1
            
            # Advance to the target page
            while self.current_page < target_page:
                more_results = self.videos_search.next()
                if more_results:
                    self.current_page += 1
                else:
                    break
                    
            # Now display the current page
            self.perform_youtube_search(self.current_search_term)
        except Exception as e:
            self.status_text.value = f"Error loading previous page: {str(e)}"
            print(f"Previous page error: {traceback.format_exc()}")
            self.update_ui()

    def add_search_result_item(self, video):
        # Create a container for the search result item
        title = video.get('title', 'Unknown Title')
        channel = video.get('channel', {}).get('name', 'Unknown Channel')
        duration = video.get('duration', '')
        thumbnail = video.get('thumbnails', [{}])[0].get('url', '')
        video_id = video.get('id', '')
        
        # Create URL for this video
        video_url = f"https://www.youtube.com/watch?v={video_id}"
        
        # Result container
        result_container = ft.Container(
            content=ft.Row(
                [
                    # Thumbnail
                    ft.Container(
                        content=ft.Image(
                            src=thumbnail,
                            width=120,
                            height=70,
                            fit=ft.ImageFit.COVER,
                            border_radius=ft.border_radius.all(4),
                        ),
                        width=120,
                        height=70,
                    ),
                    
                    # Video info
                    ft.Column(
                        [
                            ft.Text(
                                title,
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color="white",
                                overflow=ft.TextOverflow.ELLIPSIS,
                                max_lines=2,
                            ),
                            ft.Text(
                                f"By: {channel} | {duration}",
                                size=12,
                                color="#bbbbbb",
                                overflow=ft.TextOverflow.ELLIPSIS,
                                max_lines=1,
                            ),
                        ],
                        spacing=2,
                        expand=True,
                    ),
                    
                    # Select button
                    ft.IconButton(
                        icon=ft.Icons.DOWNLOAD,
                        tooltip="Use this video",
                        icon_color="#ffffff",
                        bgcolor="#ff0000",
                        icon_size=18,
                        on_click=lambda e, url=video_url: self.select_search_result(url),
                    ),
                ],
                spacing=10,
                alignment=ft.MainAxisAlignment.START,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            padding=10,
            bgcolor="#1a1a1a",
            border_radius=ft.border_radius.all(8),
            on_click=lambda e, url=video_url: self.select_search_result(url),
        )
        
        # Add hover effect to container
        def on_hover(e):
            if e.data == "true":
                result_container.bgcolor = "#2a2a2a"
            else:
                result_container.bgcolor = "#1a1a1a"
            self.update_ui()
            
        result_container.on_hover = on_hover
        
        # Add to search results container
        self.search_results_container.content.controls.append(result_container)
    
    def select_search_result(self, url):
        """Select a search result to download"""
        # Set the URL in the input field
        self.url_input.value = url
        
        # Hide search results
        self.search_results_container.visible = False
        
        # Validate the URL to get video info
        self.validate_url()

    def get_height_for_quality(self, quality):
        """Convert quality string to height value"""
        if quality == "best":
            return 1080  # Default to 1080p for best
        elif quality == "1080p":
            return 1080
        elif quality == "720p":
            return 720
        elif quality == "480p":
            return 480
        elif quality == "360p":
            return 360
        elif quality == "240p":
            return 240
        elif quality == "144p":
            return 144
        else:
            return 720  # Default to 720p

    def get_queue_item_by_id(self, item_id):
        for item in self.video_queue:
            if item['id'] == item_id:
                return item
        return None

    def get_queue_control_by_id(self, item_id):
        for control in self.queue_list.controls:
            if control.key == item_id:
                return control
        return None

    def start_queue_item_download(self, item_id):
        # Find the queue item
        queue_item = self.get_queue_item_by_id(item_id)
        if not queue_item:
            return
            
        # Get the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Update UI to show downloading status
        status_text = container.data["status_text"]
        status_container = container.data["status_container"]
        progress_bar = container.data["progress_bar"]
        download_button = container.data["download_button"]
        pause_button = container.data["pause_button"]
        
        # Update button states
        download_button.disabled = True
        pause_button.disabled = False
        
        # Update status
        status_text.value = "Downloading..."
        status_container.bgcolor = "#1976D2"  # Blue for downloading
        
        # Create a new download thread
        self.active_downloads[item_id] = {
            'status': 'downloading',
            'progress': 0,
        }
        
        # Update UI
        self.update_ui()
        
        # Start download in a thread
        Thread(target=self.download_queue_item, args=(queue_item, container)).start()

    def pause_queue_item_download(self, item_id):
        # Find the queue item
        queue_item = self.get_queue_item_by_id(item_id)
        if not queue_item:
            return
            
        # Get the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Toggle pause/resume
        if item_id in self.active_downloads:
            if self.active_downloads[item_id]['status'] == 'downloading':
                # Pause download
                self.active_downloads[item_id]['status'] = 'paused'
                
                # Update UI
                status_text = container.data["status_text"]
                status_container = container.data["status_container"]
                pause_button = container.data["pause_button"]
                progress_bar = container.data["progress_bar"]
                progress_color = container.data["progress_color"]
                
                # Change progress bar color for paused state
                progress_bar.color = "#FF9800"  # Orange for paused
                
                status_text.value = "Paused"
                status_container.bgcolor = "#FF9800"  # Orange for paused
                pause_button.icon = ft.Icons.PLAY_ARROW
                pause_button.tooltip = "Resume"
                
                self.update_ui()
            elif self.active_downloads[item_id]['status'] == 'paused':
                # Resume download
                self.active_downloads[item_id]['status'] = 'downloading'
                
                # Update UI
                status_text = container.data["status_text"]
                status_container = container.data["status_container"]
                pause_button = container.data["pause_button"]
                progress_bar = container.data["progress_bar"]
                progress_color = container.data["progress_color"]
                
                # Restore original progress bar color
                progress_bar.color = progress_color
                
                status_text.value = "Downloading..."
                status_container.bgcolor = "#1976D2"  # Blue for downloading
                pause_button.icon = ft.Icons.PAUSE
                pause_button.tooltip = "Pause"
                
                self.update_ui()

    def download_queue_item(self, queue_item, container):
        # Get UI elements
        progress_bar = container.data["progress_bar"]
        status_text = container.data["status_text"]
        status_container = container.data["status_container"]
        download_button = container.data["download_button"]
        pause_button = container.data["pause_button"]
        
        try:
            # Get parameters
            url = queue_item['video_info']['url']
            download_type = queue_item['download_type']
            quality = queue_item['quality']
            download_path = queue_item['download_path']
            item_id = queue_item['id']
            
            # Create unique filename base
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename_base = f"{queue_item['video_info']['title'].replace(' ', '_')}_{timestamp}"
            
            # Sanitize filename to remove invalid characters
            filename_base = re.sub(r'[\\/*?:"<>|]', "", filename_base)
            
            # Update status
            self.update_queue_item_status(item_id, "Starting download...", "#1976D2")
            
            output_file = None
            
            if download_type == "video":
                # Download video
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                ydl_opts = {
                    'format': self.get_video_format_string(quality),
                    'outtmpl': output_template,
                    'progress_hooks': [lambda d: self.queue_progress_hook(d, item_id)],
                    'quiet': True,
                }
                
                # If ffmpeg is not available, adjust format to avoid merging
                if not self.has_ffmpeg:
                    ydl_opts['format'] = f'best[height<={self.get_height_for_quality(quality)}]'
                
                self.update_queue_item_status(item_id, f"Downloading video ({quality})...", "#1976D2")
                
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Check if download was cancelled during setup
                    if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                        return
                        
                    # Get info to determine output file
                    info_dict = ydl.extract_info(url, download=False)
                    temp_output_file = ydl.prepare_filename(info_dict)
                        
                    # Start the download
                    ydl.download([url])
                    
                    # Check if download was cancelled during download
                    if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                        return
                    
                    # Determine the actual output file (it might have changed extension)
                    possible_extensions = ['mp4', 'webm', 'mkv']
                    for ext in possible_extensions:
                        test_path = os.path.splitext(temp_output_file)[0] + f".{ext}"
                        if os.path.exists(test_path):
                            output_file = test_path
                            break
                    
                    if not output_file and os.path.exists(temp_output_file):
                        output_file = temp_output_file
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file) if output_file else "Unknown file", output_file)
                
            elif download_type == "audio":
                # Audio (MP3)
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                if self.has_ffmpeg:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'mp3',
                            'preferredquality': self.get_audio_quality_string(quality),
                        }],
                        'progress_hooks': [lambda d: self.queue_progress_hook(d, item_id)],
                        'quiet': True,
                    }
                    
                    self.update_queue_item_status(item_id, f"Downloading MP3 ({quality})...", "#1976D2")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Check if download was cancelled
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Get info to determine output file
                        info_dict = ydl.extract_info(url, download=False)
                        temp_output_file = ydl.prepare_filename(info_dict)
                            
                        # Start the download
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # The output file will have .mp3 extension
                        output_file = os.path.splitext(temp_output_file)[0] + ".mp3"
                        
                        # Mark as complete
                        self.complete_queue_item(item_id, os.path.basename(output_file) if os.path.exists(output_file) else "Unknown file", output_file)
                else:
                    # Without ffmpeg, just download the best audio
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'progress_hooks': [lambda d: self.queue_progress_hook(d, item_id)],
                        'quiet': True,
                    }
                    
                    self.update_queue_item_status(item_id, "Downloading audio (no conversion)...", "#1976D2")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Check if download was cancelled
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Get info to determine output file
                        info_dict = ydl.extract_info(url, download=False)
                        output_file = ydl.prepare_filename(info_dict)
                            
                        # Start the download
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Mark as complete
                        self.complete_queue_item(item_id, os.path.basename(output_file) if os.path.exists(output_file) else "Unknown file", output_file)
                
            else:  # audio_hq
                # High quality audio (M4A)
                output_template = os.path.join(download_path, f"{filename_base}.%(ext)s")
                
                if self.has_ffmpeg:
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'postprocessors': [{
                            'key': 'FFmpegExtractAudio',
                            'preferredcodec': 'm4a',
                            'preferredquality': self.get_audio_quality_string(quality),
                        }],
                        'progress_hooks': [lambda d: self.queue_progress_hook(d, item_id)],
                        'quiet': True,
                    }
                    
                    self.update_queue_item_status(item_id, f"Downloading HQ audio ({quality})...", "#1976D2")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Check if download was cancelled
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Get info to determine output file
                        info_dict = ydl.extract_info(url, download=False)
                        temp_output_file = ydl.prepare_filename(info_dict)
                            
                        # Start the download
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # The output file will have .m4a extension
                        output_file = os.path.splitext(temp_output_file)[0] + ".m4a"
                        
                        # Mark as complete
                        self.complete_queue_item(item_id, os.path.basename(output_file) if os.path.exists(output_file) else "Unknown file", output_file)
                else:
                    # Without ffmpeg, just download the best audio
                    ydl_opts = {
                        'format': 'bestaudio/best',
                        'outtmpl': output_template,
                        'progress_hooks': [lambda d: self.queue_progress_hook(d, item_id)],
                        'quiet': True,
                    }
                    
                    self.update_queue_item_status(item_id, "Downloading audio (no conversion)...", "#1976D2")
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        # Check if download was cancelled
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Get info to determine output file
                        info_dict = ydl.extract_info(url, download=False)
                        output_file = ydl.prepare_filename(info_dict)
                            
                        # Start the download
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                        # Mark as complete
                        self.complete_queue_item(item_id, os.path.basename(output_file) if os.path.exists(output_file) else "Unknown file", output_file)
                
        except Exception as e:
            # Update with error
            self.update_queue_item_status(item_id, f"Error: {str(e)}", "#F44336")
            
            # Update UI
            if item_id in self.active_downloads:
                del self.active_downloads[item_id]
                
            download_button.disabled = False
            pause_button.disabled = True
            self.update_ui()

    def update_queue_item_status(self, item_id, status_message, color="#1976D2"):
        # Find the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Update status
        status_text = container.data["status_text"]
        status_container = container.data["status_container"]
        
        status_text.value = status_message
        status_container.bgcolor = color
        
        # Update UI
        self.update_ui()

    def update_queue_item_progress(self, item_id, percentage):
        # Find the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Update progress bar
        progress_bar = container.data["progress_bar"]
        progress_bar.value = percentage / 100
        
        # Update data store
        if item_id in self.active_downloads:
            self.active_downloads[item_id]['progress'] = percentage
        
        # Update UI
        self.update_ui()

    def complete_queue_item(self, item_id, filename, output_file=None):
        """Mark a queue item as completed and enable folder access"""
        # Find the UI container
        container = self.get_queue_control_by_id(item_id)
        if not container:
            return
            
        # Update UI elements
        status_text = container.data["status_text"]
        status_container = container.data["status_container"]
        progress_bar = container.data["progress_bar"]
        download_button = container.data["download_button"]
        pause_button = container.data["pause_button"]
        folder_button = container.data["folder_button"]
        
        # Set progress to 100%
        progress_bar.value = 1.0
        
        # Update status
        status_text.value = "Completed"
        status_container.bgcolor = "#4CAF50"  # Green for completed
        
        # Update button states
        download_button.disabled = True
        pause_button.disabled = True
        folder_button.disabled = False
        
        # Save output file path for folder access
        if output_file:
            container.data["output_file"] = output_file
        
        # Remove from active downloads
        if item_id in self.active_downloads:
            del self.active_downloads[item_id]
        
        # Update UI
        self.update_ui()

    def queue_progress_hook(self, d, item_id):
        """Progress hook for queue downloads with improved pause handling"""
        # Check if app is closing
        if self.is_closing:
            return
            
        # Check if download is paused
        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'paused':
            # When paused, we'll keep updating the UI but with a "paused" indicator
            # yt-dlp doesn't have native pause, but this will show the user the download is paused
            # and the download thread handles the actual slow-down when paused
            if not self.is_closing:
                if d['status'] == 'downloading' and 'total_bytes' in d and d['total_bytes'] > 0:
                    percentage = d['downloaded_bytes'] / d['total_bytes']
                    # Only update the progress, not the status text (to keep "Paused" visible)
                    self.update_queue_item_progress(item_id, percentage * 100)
            # Slow down processing while paused to reduce CPU usage
            time.sleep(0.5)
            return
            
        if d['status'] == 'downloading':
            # Get download percentage
            if 'total_bytes' in d and d['total_bytes'] > 0:
                percentage = d['downloaded_bytes'] / d['total_bytes']
                
                # Update progress bar
                self.update_queue_item_progress(item_id, percentage * 100)
                
                # Update status with download speed and ETA
                if 'speed' in d and d['speed']:
                    speed = self.format_size(d['speed']) + "/s"
                    eta = d.get('eta', 'N/A')
                    
                    if eta != 'N/A':
                        eta = self.format_duration(eta)
                        
                    status = f"DL: {percentage:.0%} | {speed} | ETA: {eta}"
                    
                    # Only update if not paused and app is not closing
                    if (item_id not in self.active_downloads or self.active_downloads[item_id]['status'] != 'paused') and not self.is_closing:
                        self.update_queue_item_status(item_id, status, "#1976D2")
                    
        elif d['status'] == 'finished':
            # Update status if app is not closing
            if not self.is_closing:
                self.update_queue_item_status(item_id, "Processing...", "#1976D2")

    def display_url_mode(self):
        """Show URL input and hide search input"""
        self.url_input.visible = True
        self.url_submit_button.visible = True
        self.search_input.visible = False
        self.search_button.visible = False
        self.search_results_container.visible = False
        self.pagination_row.visible = False
        self.update_ui()
        
    def display_search_mode(self):
        """Show search input and hide URL input"""
        self.url_input.visible = False
        self.url_submit_button.visible = False
        self.search_input.visible = True
        self.search_button.visible = True
        # Don't show results container or pagination yet
        self.search_results_container.visible = False
        self.pagination_row.visible = False
        self.update_ui()

    def switch_to_url_mode(self, e=None):
        """Switch to URL input mode"""
        # Update tabs appearance
        self.url_tab.bgcolor = "#ff0000"
        self.url_tab.content.controls[0].color = "#ffffff"
        self.url_tab.content.controls[1].color = "#ffffff"
        
        self.search_tab.bgcolor = "#1f1f1f"
        self.search_tab.content.controls[0].color = "#bbbbbb"
        self.search_tab.content.controls[1].color = "#bbbbbb"
        
        # Switch visibility
        self.display_url_mode()
        
    def switch_to_search_mode(self, e=None):
        """Switch to search mode"""
        # Update tabs appearance
        self.search_tab.bgcolor = "#ff0000"
        self.search_tab.content.controls[0].color = "#ffffff"
        self.search_tab.content.controls[1].color = "#ffffff"
        
        self.url_tab.bgcolor = "#1f1f1f"
        self.url_tab.content.controls[0].color = "#bbbbbb"
        self.url_tab.content.controls[1].color = "#bbbbbb"
        
        # Switch visibility
        self.display_search_mode()

    def safe_update_ui(self):
        """Thread-safe method to update UI"""
        try:
            if not self.is_closing:
                with self.update_lock:
                    self.page.update()
        except RuntimeError as e:
            if "Event loop is closed" in str(e):
                # App is closing, set flag to prevent further updates
                self.is_closing = True
                print("App is closing, updates stopped")
            else:
                print(f"UI update error: {str(e)}")
        except Exception as e:
            print(f"Error updating UI: {str(e)}")
            
    def update_ui(self):
        """Wrapper for page.update() that uses the safe method"""
        self.safe_update_ui()

    def open_download_folder(self, item_id):
        """Open the folder where downloaded file is stored"""
        try:
            # Find the UI container
            container = self.get_queue_control_by_id(item_id)
            if not container:
                return
                
            # Get file path information
            download_path = container.data.get("download_path")
            output_file = container.data.get("output_file")
            
            # If we have a specific file, open its folder with the file selected
            if output_file and os.path.exists(output_file):
                if sys.platform == "win32":
                    # On Windows, use explorer to select the file
                    os.system(f'explorer /select,"{output_file}"')
                elif sys.platform == "darwin":
                    # On macOS, use Finder
                    os.system(f'open -R "{output_file}"')
                else:
                    # On Linux, just open the folder
                    if os.path.exists(download_path):
                        os.system(f'xdg-open "{download_path}"')
            else:
                # Just open the folder if file doesn't exist or we don't know which file
                if os.path.exists(download_path):
                    if sys.platform == "win32":
                        os.system(f'explorer "{download_path}"')
                    elif sys.platform == "darwin":
                        os.system(f'open "{download_path}"')
                    else:
                        os.system(f'xdg-open "{download_path}"')
                else:
                    self.status_text.value = "Download folder not found."
                    self.update_ui()
        except Exception as e:
            self.status_text.value = f"Error opening folder: {str(e)}"
            self.update_ui()

    def toggle_torrent_panel(self, e=None):
        """Toggle the torrent panel visibility"""
        if not hasattr(self, '_torrent_panel_visible'):
            self._torrent_panel_visible = False
            
        self._torrent_panel_visible = not self._torrent_panel_visible
        
        # Find the main content row
        main_content = None
        for control in self.page.controls:
            if isinstance(control, ft.Row) and len(control.controls) >= 2:
                main_content = control
                break
                
        if main_content:
            if self._torrent_panel_visible:
                # Create a container for the torrent panel
                torrent_section = ft.Container(
                    content=ft.Column(
                        [
                            ft.Container(
                                content=ft.Row(
                                    [
                                        ft.Text(
                                            "Torrent Downloads",
                                            size=18,
                                            weight=ft.FontWeight.BOLD,
                                            color="white",
                                        ),
                                        ft.IconButton(
                                            icon=ft.Icons.CLOSE,
                                            icon_color="white",
                                            tooltip="Close Torrent Panel",
                                            on_click=self.toggle_torrent_panel,
                                        ),
                                    ],
                                    alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                                ),
                                padding=10,
                                bgcolor="#1a1a1a",
                                border_radius=ft.border_radius.only(
                                    top_left=8,
                                    top_right=8,
                                ),
                            ),
                            self.torrent_panel.get_panel(),
                            ft.Divider(height=1, color="#333333"),
                        ],
                        spacing=0,
                    ),
                    padding=0,
                    margin=ft.margin.only(bottom=10),
                )
                
                # Get the left panel (first control)
                left_panel = main_content.controls[0]
                
                # Store the original content
                if not hasattr(self, '_original_left_content'):
                    self._original_left_content = left_panel.content
                
                # Create a new column with torrent panel and original content
                left_panel.content = ft.Column(
                    [
                        torrent_section,
                        self._original_left_content,
                    ],
                    spacing=0,
                    scroll=ft.ScrollMode.AUTO,
                )
            else:
                # Restore the original content
                if hasattr(self, '_original_left_content'):
                    left_panel = main_content.controls[0]
                    left_panel.content = self._original_left_content
                    
        self.update_ui()

    def create_queue_item(self, item_id, title, download_path, item_type="video", torrent=None):
        """Create a queue item container"""
        try:
            # Create progress bar
            progress_bar = ft.ProgressBar(
                width=None,
                color="#1976D2",
                bgcolor="#333333",
                value=0,
                height=4,
            )
            
            # Create status text
            status_text = ft.Text(
                "Queued",
                size=12,
                color="white",
            )
            
            # Create status container
            status_container = ft.Container(
                content=status_text,
                bgcolor="#757575",
                padding=ft.padding.all(3),
                border_radius=ft.border_radius.all(4),
            )
            
            # Create control buttons
            pause_button = ft.IconButton(
                icon=ft.Icons.PAUSE,
                tooltip="Pause/Resume",
                icon_color="#FFA000",
                icon_size=18,
                on_click=lambda e: self.pause_download(item_id),
                disabled=True,
            )
            
            stop_button = ft.IconButton(
                icon=ft.Icons.STOP,
                tooltip="Stop",
                icon_color="#E53935",
                icon_size=18,
                on_click=lambda e: self.stop_download(item_id),
                disabled=True,
            )
            
            remove_button = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                tooltip="Remove",
                icon_color="#757575",
                icon_size=18,
                on_click=lambda e: self.remove_from_queue(item_id),
            )
            
            folder_button = ft.IconButton(
                icon=ft.Icons.FOLDER_OPEN,
                tooltip="Open Download Folder",
                icon_color="#4FC3F7",
                icon_size=18,
                on_click=lambda e: self.open_download_folder(item_id),
            )
            
            # Create torrent details section if it's a torrent
            details_section = None
            file_sections = {}
            if item_type == "torrent" and torrent:
                details = torrent.get_details()
                
                # Calculate total size of selected files
                total_size = sum(f['size'] for f in details['files'] if f['selected'])
                
                # Create collapsible file sections
                file_list = ft.Column(
                    spacing=2,
                    scroll=ft.ScrollMode.AUTO,
                    height=min(len(details['files']) * 30, 150),
                )
                
                # Group files by extension
                grouped_files = {}
                for i, f in enumerate(details['files']):
                    ext = os.path.splitext(f['path'])[1].lower() or 'Other'
                    if ext not in grouped_files:
                        grouped_files[ext] = []
                    grouped_files[ext].append((i, f))
                
                # Create sections for each file type
                for ext, files in grouped_files.items():
                    # Create section header
                    header_row = ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EXPAND_MORE,
                                icon_size=20,
                                data={'section': ext, 'expanded': True},
                                on_click=lambda e: self.toggle_queue_section(item_id, e.control.data['section']),
                            ),
                            ft.Text(
                                f"{ext.upper()} Files ({len(files)})",
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color="#bbbbbb",
                            ),
                        ],
                        spacing=5,
                    )
                    
                    # Create section content
                    section_content = ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Checkbox(
                                        value=f[1]['selected'],
                                        data={'index': f[0]},
                                        on_change=lambda e, idx=f[0]: self.update_queue_file_selection(
                                            item_id,
                                            idx,
                                            e.control.value
                                        ),
                                    ),
                                    ft.Text(
                                        f"{os.path.basename(f[1]['path'])} ({f[1].get('size_str', 'Unknown')})",
                                        size=12,
                                        color="#bbbbbb",
                                        expand=True,
                                    ),
                                ],
                                spacing=5,
                            ) for f in files
                        ],
                        spacing=2,
                        visible=True,
                    )
                    
                    file_sections[ext] = {
                        'header': header_row,
                        'content': section_content,
                    }
                    
                    file_list.controls.extend([header_row, section_content])
                
                # Create priority dropdown
                priority_dropdown = ft.Dropdown(
                    label="Priority",
                    value=torrent.priority,
                    options=[
                        ft.dropdown.Option("Normal"),
                        ft.dropdown.Option("High"),
                        ft.dropdown.Option("Low"),
                    ],
                    on_change=lambda e: self.update_torrent_priority(item_id, e.control.value),
                    width=100,
                    text_size=12,
                )
                
                details_section = ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Text(f"Size: {self._format_size(total_size)}", size=12, color="#bbbbbb"),
                                ft.Text(f"Seeds: {details['seeds']}", size=12, color="#bbbbbb"),
                                ft.Text(f"Peers: {details['peers']}", size=12, color="#bbbbbb"),
                                ft.Text(f"Ratio: {details['ratio']}", size=12, color="#bbbbbb"),
                            ],
                            spacing=10,
                        ),
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [
                                            ft.IconButton(
                                                icon=ft.Icons.EXPAND_MORE,
                                                icon_size=20,
                                                data={'expanded': True},
                                                on_click=lambda e: self.toggle_files_section(item_id, e.control),
                                            ),
                                            ft.Text("Selected Files:", size=12, color="#bbbbbb"),
                                        ],
                                        spacing=5,
                                    ),
                                    file_list,
                                ],
                                spacing=5,
                            ),
                            bgcolor="#111111",
                            padding=5,
                            border_radius=5,
                        ),
                        ft.Row(
                            [priority_dropdown],
                            spacing=10,
                        ),
                    ],
                    spacing=5,
                )
            
            # Create item container
            container = ft.Container(
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                # Title and type indicator
                                ft.Column(
                                    [
                                        ft.Row(
                                            [
                                                ft.Icon(
                                                    ft.Icons.FILE_DOWNLOAD if item_type == "video" else ft.Icons.DOWNLOADING,
                                                    color="#bbbbbb",
                                                    size=16,
                                                ),
                                                ft.Text(
                                                    title,
                                                    size=14,
                                                    weight=ft.FontWeight.BOLD,
                                                    color="white",
                                                ),
                                            ],
                                            spacing=5,
                                        ),
                                        ft.Text(
                                            download_path,
                                            size=12,
                                            color="#bbbbbb",
                                        ),
                                    ],
                                    spacing=5,
                                    expand=True,
                                ),
                                
                                # Controls
                                ft.Row(
                                    [
                                        status_container,
                                        pause_button,
                                        stop_button,
                                        folder_button,
                                        remove_button,
                                    ],
                                    spacing=5,
                                ),
                            ],
                            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                        ),
                        progress_bar,
                        details_section if details_section else ft.Container(),
                    ],
                    spacing=5,
                ),
                padding=10,
                margin=ft.margin.only(bottom=5),
                bgcolor="#1a1a1a",
                border_radius=ft.border_radius.all(8),
            )
            
            # Store references to controls
            container.data = {
                "id": item_id,
                "type": item_type,
                "progress_bar": progress_bar,
                "status_text": status_text,
                "status_container": status_container,
                "pause_button": pause_button,
                "stop_button": stop_button,
                "download_path": download_path,
                "torrent": torrent,
                "file_sections": file_sections
            }
            
            return container
            
        except Exception as e:
            print(f"Error creating queue item: {str(e)}")
            return None

    def toggle_queue_section(self, item_id, section):
        """Toggle visibility of a file section in queue item"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if container and container.data["file_sections"]:
                sections = container.data["file_sections"]
                if section in sections:
                    section_data = sections[section]
                    header = section_data['header']
                    content = section_data['content']
                    
                    # Toggle visibility
                    content.visible = not content.visible
                    
                    # Update icon
                    header.controls[0].icon = ft.Icons.EXPAND_LESS if content.visible else ft.Icons.EXPAND_MORE
                    
                    self.update_ui()
        except Exception as e:
            print(f"Error toggling queue section: {str(e)}")

    def update_queue_file_selection(self, item_id, file_index, selected):
        """Update file selection in queue item"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if container and container.data["type"] == "torrent":
                torrent = container.data["torrent"]
                if torrent:
                    # Get current selected indices
                    selected_indices = [i for i, f in enumerate(torrent.files) if f['selected']]
                    
                    # Update selection
                    if selected and file_index not in selected_indices:
                        selected_indices.append(file_index)
                    elif not selected and file_index in selected_indices:
                        selected_indices.remove(file_index)
                    
                    # Update torrent
                    torrent.select_files(selected_indices)
                    
                    # Update total size display
                    details = torrent.get_details()
                    total_size = sum(f['size'] for f in details['files'] if f['selected'])
                    
                    # Update size text
                    details_section = container.content.controls[-1]
                    if isinstance(details_section, ft.Column):
                        size_text = details_section.controls[0].controls[0]
                        size_text.value = f"Size: {self._format_size(total_size)}"
                    
                    # Update status if no files selected
                    if not selected_indices:
                        container.data["status_text"].value = "No files selected"
                        container.data["status_container"].bgcolor = "#FFA000"
                    
                    self.update_ui()
        except Exception as e:
            print(f"Error updating queue file selection: {str(e)}")

    def _format_size(self, size):
        """Format size to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"

    def pause_download(self, item_id):
        """Pause/Resume a download"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if not container:
                return
                
            if container.data["type"] == "torrent":
                torrent = container.data["torrent"]
                if torrent:
                    if torrent.is_paused:
                        torrent.resume()
                        container.data["pause_button"].icon = ft.Icons.PAUSE
                        container.data["status_container"].bgcolor = "#1976D2"
                    else:
                        torrent.pause()
                        container.data["pause_button"].icon = ft.Icons.PLAY_ARROW
                        container.data["status_container"].bgcolor = "#FFA000"
                    
                    self.update_ui()
            else:
                # Handle video download pause/resume
                if item_id in self.active_downloads:
                    if self.active_downloads[item_id]["status"] == "paused":
                        self.active_downloads[item_id]["status"] = "downloading"
                        container.data["pause_button"].icon = ft.Icons.PAUSE
                        container.data["status_container"].bgcolor = "#1976D2"
                    else:
                        self.active_downloads[item_id]["status"] = "paused"
                        container.data["pause_button"].icon = ft.Icons.PLAY_ARROW
                        container.data["status_container"].bgcolor = "#FFA000"
                    
                    self.update_ui()
                    
        except Exception as e:
            print(f"Error pausing download: {str(e)}")
    
    def stop_download(self, item_id):
        """Stop a download"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if not container:
                return
                
            if container.data["type"] == "torrent":
                torrent = container.data["torrent"]
                if torrent:
                    torrent.stop()
            
            if item_id in self.active_downloads:
                self.active_downloads[item_id]["status"] = "cancelled"
            
            container.data["status_text"].value = "Stopped"
            container.data["status_container"].bgcolor = "#757575"
            container.data["pause_button"].disabled = True
            container.data["stop_button"].disabled = True
            
            self.update_ui()
            
        except Exception as e:
            print(f"Error stopping download: {str(e)}")
    
    def format_speed(self, bytes_per_sec):
        """Format speed in bytes/sec to human readable format"""
        if bytes_per_sec < 1024:
            return f"{bytes_per_sec:.0f} B/s"
        elif bytes_per_sec < 1024 * 1024:
            return f"{bytes_per_sec/1024:.1f} KB/s"
        else:
            return f"{bytes_per_sec/(1024*1024):.1f} MB/s"

    def update_torrent_priority(self, item_id, priority):
        """Update torrent priority"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if container and container.data["type"] == "torrent":
                torrent = container.data["torrent"]
                if torrent:
                    torrent.set_priority(priority)
                    
        except Exception as e:
            print(f"Error updating torrent priority: {str(e)}")

    def start_next_download(self):
        """Start the next download in the queue"""
        try:
            # Find the next queued item
            for item in self.video_queue:
                if item["status"] == "queued":
                    container = item["container"]
                    item_id = item["id"]
                    
                    # Update status
                    container.data["status_text"].value = "Starting..."
                    container.data["status_container"].bgcolor = "#1976D2"
                    container.data["pause_button"].disabled = False
                    container.data["stop_button"].disabled = False
                    self.update_ui()
                    
                    # Start download based on type
                    if item["type"] == "torrent":
                        self.start_torrent_download(item_id, container)
                    else:
                        self.start_video_download(item_id, container)
                    
                    break
                    
        except Exception as e:
            print(f"Error starting next download: {str(e)}")
            
    def start_torrent_download(self, item_id, container):
        """Start a torrent download"""
        try:
            torrent = container.data["torrent"]
            if not torrent:
                return
                
            # Check if any files are selected
            if not any(f['selected'] for f in torrent.files):
                container.data["status_text"].value = "No files selected"
                container.data["status_container"].bgcolor = "#FFA000"
                container.data["pause_button"].disabled = True
                container.data["stop_button"].disabled = True
                self.update_ui()
                return
                
            # Mark as downloading
            self.active_downloads[item_id] = {"status": "downloading"}
            
            def download_loop():
                try:
                    # Start the torrent
                    torrent.start()
                    
                    # Update progress until complete or cancelled
                    while (
                        item_id in self.active_downloads
                        and self.active_downloads[item_id]["status"] != "cancelled"
                        and torrent.progress < 100
                    ):
                        if not torrent.is_paused:
                            # Update progress
                            container.data["progress_bar"].value = torrent.progress / 100
                            
                            # Update status text
                            details = torrent.get_details()
                            status = f"Downloading: {details['progress']} | ↓ {details['download_speed']} ↑ {details['upload_speed']} | Seeds: {details['seeds']} | ETA: {details['estimated_time']}"
                            container.data["status_text"].value = status
                            
                            # Update status color
                            container.data["status_container"].bgcolor = "#1976D2"
                            
                            self.update_ui()
                            
                        time.sleep(0.5)
                    
                    # Check if cancelled
                    if (
                        item_id not in self.active_downloads
                        or self.active_downloads[item_id]["status"] == "cancelled"
                    ):
                        container.data["status_text"].value = "Cancelled"
                        container.data["status_container"].bgcolor = "#757575"
                    else:
                        container.data["status_text"].value = "Completed"
                        container.data["status_container"].bgcolor = "#43A047"
                        container.data["progress_bar"].value = 1
                    
                    # Cleanup
                    if item_id in self.active_downloads:
                        del self.active_downloads[item_id]
                    
                    # Disable controls
                    container.data["pause_button"].disabled = True
                    container.data["stop_button"].disabled = True
                    
                    self.update_ui()
                    
                    # Start next download
                    self.start_next_download()
                    
                except Exception as e:
                    print(f"Error in torrent download loop: {str(e)}")
                    container.data["status_text"].value = f"Error: {str(e)}"
                    container.data["status_container"].bgcolor = "#E53935"
                    self.update_ui()
            
            # Start download thread
            Thread(target=download_loop, daemon=True).start()
            
        except Exception as e:
            print(f"Error starting torrent download: {str(e)}")
            container.data["status_text"].value = f"Error: {str(e)}"
            container.data["status_container"].bgcolor = "#E53935"
            self.update_ui()

    def toggle_files_section(self, item_id, button):
        """Toggle visibility of the files section"""
        try:
            container = self.get_queue_control_by_id(item_id)
            if container and container.data["type"] == "torrent":
                details_section = container.content.controls[-1]
                if isinstance(details_section, ft.Column):
                    files_container = details_section.controls[1]
                    file_list = files_container.content.controls[1]
                    
                    # Toggle visibility
                    file_list.visible = not file_list.visible
                    
                    # Update icon
                    button.icon = ft.Icons.EXPAND_LESS if file_list.visible else ft.Icons.EXPAND_MORE
                    button.data['expanded'] = file_list.visible
                    
                    self.update_ui()
        except Exception as e:
            print(f"Error toggling files section: {str(e)}")

    def prepare_torrent(self, e=None):
        """Prepare torrent for adding to queue by showing file selection dialog"""
        link = self.magnet_input.value.strip()
        if not link:
            if self.on_action:
                self.on_action({"type": "status", "message": "Please enter a magnet link or torrent URL"})
            return
            
        try:
            # Parse magnet link parameters safely
            if link.startswith('magnet:?'):
                params = {}
                # Split parameters and handle each one
                for param in link.replace('magnet:?', '').split('&'):
                    if '=' in param:
                        key, value = param.split('=', 1)
                        params[key] = value
                
                # Get hash from xt parameter
                info_hash = None
                if 'xt' in params:
                    xt = params['xt']
                    if xt.startswith('urn:btih:'):
                        info_hash = xt.replace('urn:btih:', '')
                
                # Get name from dn parameter
                name = urllib.parse.unquote_plus(params.get('dn', 'Unknown'))
                
                # Create torrent instance with parsed data
                t = TorrentDownloader(
                    magnet_link=link,
                    download_path=self.download_path.value
                )
                t.name = name
                if info_hash:
                    t.info_hash = info_hash
            else:
                # Handle direct torrent file URL or path
                t = TorrentDownloader(
                    torrent_path=link if os.path.exists(link) else None,
                    magnet_link=link if link.startswith('http') else None,
                    download_path=self.download_path.value
                )
            
            self.current_torrent = t
            self.show_file_selection_dialog(t)
            
        except Exception as e:
            print(f"Error preparing torrent: {str(e)}")
            self.status_text.value = f"Error preparing torrent: {str(e)}"
            self.update_ui()

def main(page: ft.Page):
    app = ModernYouTubeDownloader(page)
    
    # Handle app close event
    def on_page_close(e):
        app.is_closing = True
        print("App is closing, cleaning up...")
        
    page.on_close = on_page_close

# Run the app
if __name__ == "__main__":
    ft.app(target=main)