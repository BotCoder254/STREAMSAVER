import flet as ft
import os
import re
import time
import subprocess
from threading import Thread
from pathlib import Path
from datetime import datetime
import yt_dlp
from pytubefix import YouTube
from youtubesearchpython import VideosSearch


class ModernYouTubeDownloader:
    def __init__(self, page: ft.Page):
        self.page = page
        self.video_queue = []
        self.current_video_info = None
        self.countdown_timer = None
        self.countdown_value = 3
        self.active_downloads = {}  # Track active downloads by queue item ID
        self.setup_page()
        self.init_controls()
        self.build_ui()
        
        # Add tab-like UI elements for switching between URL and Search
        self.display_url_mode()
        
        # Check for ffmpeg
        self.has_ffmpeg = self.check_ffmpeg()
        if not self.has_ffmpeg:
            self.status_text.value = "Warning: ffmpeg not found. Audio conversion features will be limited."
            self.page.update()

    def setup_page(self):
        self.page.title = "StreamSaver Pro"
        self.page.window_width = 1200
        self.page.window_height = 750
        self.page.window_resizable = True
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.bgcolor = "#0f0f0f"
        self.page.update()

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
                ],
                alignment=ft.MainAxisAlignment.CENTER,
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
            ),
            padding=20,
            bgcolor="#0f0f0f",
            border_radius=ft.border_radius.all(0),
            width=450,  # Increased width to accommodate search
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
        )

        # Main content - two-panel layout
        main_content = ft.Row(
            [
                left_panel,
                ft.VerticalDivider(width=1, color="#333333"),
                right_panel,
            ],
            expand=True,
            spacing=0,
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
            ft.Divider(height=1, color="#333333"),
            main_content,
            ft.Divider(height=1, color="#333333"),
            footer,
        )

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
            self.page.update()
            
            # Start countdown
            self.countdown_value = 3
            self.update_countdown_text()
            self.countdown_timer = True
            
            # Start thread to fetch video info
            Thread(target=self.fetch_video_info, args=(url,)).start()
        else:
            self.status_text.value = "Invalid URL. Please enter a supported video URL"
            self.page.update()

    def update_countdown_text(self):
        if not self.countdown_timer:
            return
            
        self.spinner_row.controls[1].value = f"Fetching video info... {self.countdown_value}"
        self.page.update()
        
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
        self.page.update()

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
                    
                    # Update UI with video information - don't return from the method call
                    self.update_video_info(
                        self.current_video_info['title'], 
                        self.current_video_info['uploader'], 
                        self.format_duration(self.current_video_info['duration']), 
                        self.current_video_info['thumbnail']
                    )
                    
                    # Enable download options
                    self.enable_download_options()
                    
                else:
                    self.show_error("Could not fetch video information. Please check URL.")
            
        except Exception as e:
            self.show_error(f"Error fetching video information: {str(e)}")

    def update_video_info(self, title, author, length, thumbnail_url):
        self.spinner_row.visible = False
        self.countdown_timer = False
        
        self.video_title.value = title
        self.video_author.value = f"By: {author}"
        self.video_length.value = f"Duration: {length}"
        self.thumbnail.src = thumbnail_url
        self.thumbnail.visible = True
        self.status_text.value = "Video information loaded successfully"
        self.page.update()

    def enable_download_options(self):
        self.download_type.disabled = False
        self.browse_button.disabled = False
        
        # Set handler for download type change
        self.download_type.on_change = self.on_download_type_change
        
        self.status_text.value = "Select download options"
        self.page.update()

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
        self.page.update()

    def browse_directory(self, e):
        def pick_folder_result(e: ft.FilePickerResultEvent):
            if e.path:
                self.download_path.value = e.path
                self.page.update()

        picker = ft.FilePicker(on_result=pick_folder_result)
        self.page.overlay.append(picker)
        self.page.update()
        picker.get_directory_path()

    def add_to_queue(self, e):
        if not self.url_input.value or not self.download_type.value or not self.current_video_info:
            self.status_text.value = "Please fill in all required fields"
            self.page.update()
            return
            
        # Check that user has selected a format
        if (self.download_type.value == "video" and not self.video_quality.value) or \
           (self.download_type.value in ["audio", "audio_hq"] and not self.audio_quality.value):
            self.status_text.value = "Please select quality before adding to queue"
            self.page.update()
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
        self.page.update()
        
        # Show notification
        self.status_text.value = "Added to download queue"
        self.page.update()
        
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
                "delete_button": delete_button,
                "expand_button": expand_button,
                "details_section": details_section,
                "progress_color": progress_color,
                "is_expanded": False,
            },
        )
        
        self.queue_list.controls.append(item)
        self.page.update()
        
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
        self.page.update()

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
        self.page.update()

    def start_download(self, e):
        if not self.url_input.value or not self.download_type.value or not self.current_video_info:
            self.status_text.value = "Please fill in all required fields"
            self.page.update()
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
        self.page.update()

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
        self.page.update()

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
        self.page.update()

    def update_status(self, message):
        self.status_text.value = message
        self.page.update()

    def download_complete(self, file_path):
        # Show completion status
        self.progress_bar.value = 1  # Set progress bar to 100%
        self.status_text.value = f"Download complete: {os.path.basename(file_path)}"
        
        # Re-enable UI
        self.enable_ui_after_download()

    def show_error(self, message):
        self.status_text.value = message
        self.progress_bar.value = 0
        self.progress_bar.visible = False
        
        # Re-enable UI
        self.enable_ui_after_download()

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
            self.page.update()
            return
            
        # Show loading indicator
        self.status_text.value = "Searching YouTube..."
        self.search_results_container.visible = False
        self.page.update()
        
        # Start search in a separate thread
        Thread(target=self.perform_youtube_search, args=(search_term,)).start()
    
    def perform_youtube_search(self, search_term):
        try:
            # Use youtube-search-python to search for videos
            search = VideosSearch(search_term, limit=10)
            results = search.result()
            
            # Clear previous results
            self.search_results_container.content.controls.clear()
            
            if results and 'result' in results and results['result']:
                # Create result items
                for video in results['result']:
                    self.add_search_result_item(video)
                
                # Show results container
                self.search_results_container.visible = True
                self.status_text.value = f"Found {len(results['result'])} results for '{search_term}'"
            else:
                self.search_results_container.visible = False
                self.status_text.value = f"No results found for '{search_term}'"
                
        except Exception as e:
            self.search_results_container.visible = False
            self.status_text.value = f"Search error: {str(e)}"
            
        self.page.update()
    
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
            self.page.update()
            
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
        self.page.update()
        
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
                
                self.page.update()
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
                
                self.page.update()

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
                    if self.active_downloads[item_id]['status'] == 'cancelled':
                        return
                        
                    ydl.download([url])
                    
                    # Check if download was cancelled during download
                    if self.active_downloads[item_id]['status'] == 'cancelled':
                        return
                        
                    # Get the actual output filename from the info dict
                    info_dict = ydl.extract_info(url, download=False)
                    output_file = ydl.prepare_filename(info_dict)
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file))
                
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
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                            
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                    # The output file will have .mp3 extension
                    output_file = os.path.join(download_path, f"{filename_base}.mp3")
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file))
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
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                            
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                    # Get the actual output filename
                    info_dict = ydl.extract_info(url, download=False)
                    output_file = ydl.prepare_filename(info_dict)
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file))
                
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
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                            
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                    # The output file will have .m4a extension
                    output_file = os.path.join(download_path, f"{filename_base}.m4a")
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file))
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
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                            
                        ydl.download([url])
                        
                        # Check if download was cancelled during download
                        if self.active_downloads[item_id]['status'] == 'cancelled':
                            return
                        
                    # Get the actual output filename
                    info_dict = ydl.extract_info(url, download=False)
                    output_file = ydl.prepare_filename(info_dict)
                    
                    # Mark as complete
                    self.complete_queue_item(item_id, os.path.basename(output_file))
                
        except Exception as e:
            # Update with error
            self.update_queue_item_status(item_id, f"Error: {str(e)}", "#F44336")
            
            # Update UI
            if item_id in self.active_downloads:
                del self.active_downloads[item_id]
                
            download_button.disabled = False
            pause_button.disabled = True
            self.page.update()

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
        self.page.update()

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
        self.page.update()

    def complete_queue_item(self, item_id, filename):
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
        
        # Set progress to 100%
        progress_bar.value = 1.0
        
        # Update status
        status_text.value = "Completed"
        status_container.bgcolor = "#4CAF50"  # Green for completed
        
        # Update button states
        download_button.disabled = True
        pause_button.disabled = True
        
        # Remove from active downloads
        if item_id in self.active_downloads:
            del self.active_downloads[item_id]
        
        # Update UI
        self.page.update()

    def queue_progress_hook(self, d, item_id):
        # Check if download is paused
        if item_id in self.active_downloads and self.active_downloads[item_id]['status'] == 'paused':
            # This is a simple approach - it would be better to actually pause the download
            # but yt-dlp doesn't have a built-in pause functionality, so we'd need to implement
            # a more sophisticated approach with process control
            time.sleep(0.5)  # Slow down processing while paused
            
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
                    
                    # Only update if not paused
                    if item_id not in self.active_downloads or self.active_downloads[item_id]['status'] != 'paused':
                        self.update_queue_item_status(item_id, status, "#1976D2")
                    
        elif d['status'] == 'finished':
            # Update status
            self.update_queue_item_status(item_id, "Processing...", "#1976D2")

    def display_url_mode(self):
        """Show URL input and hide search input"""
        self.url_input.visible = True
        self.url_submit_button.visible = True
        self.search_input.visible = False
        self.search_button.visible = False
        self.search_results_container.visible = False
        self.page.update()
        
    def display_search_mode(self):
        """Show search input and hide URL input"""
        self.url_input.visible = False
        self.url_submit_button.visible = False
        self.search_input.visible = True
        self.search_button.visible = True
        self.page.update()

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

def main(page: ft.Page):
    app = ModernYouTubeDownloader(page)

# Run the app
if __name__ == "__main__":
    ft.app(target=main)