import flet as ft
import asyncio
import torf
import os
import plotly.graph_objects as go
from threading import Thread, Lock
from datetime import datetime
import tempfile
from pathlib import Path
import urllib.request
import socket
import struct
import random
import time
import sys
import subprocess

class TorrentDownloader:
    def __init__(self, magnet_link=None, torrent_path=None, download_path=None):
        self.magnet_link = magnet_link
        self.torrent_path = torrent_path
        self.download_path = download_path or str(Path.home() / "Downloads")
        self.is_paused = False
        self.is_stopped = False
        self.download_speed = 0
        self.upload_speed = 0
        self.progress = 0
        self.status = "Initializing"
        self.torrent = None
        self.name = "Unknown"
        self.size = 0
        self.seeds = 0
        self.peers = 0
        self.downloaded = 0
        self.uploaded = 0
        self.ratio = 0.0
        self.estimated_time = "Unknown"
        self.files = []
        self.selected_files = []
        self.priority = "Normal"  # Normal, High, Low
        
        if torrent_path:
            self.torrent = torf.Torrent.read(torrent_path)
            self.name = self.torrent.name
            self.size = self.torrent.size
            self.files = [{'path': f, 'selected': True, 'priority': 'Normal'} for f in self.torrent.files]
        elif magnet_link:
            # Parse magnet link to get info hash and name
            self.info_hash = self._parse_magnet_link(magnet_link)
            self.name = self._get_name_from_magnet(magnet_link)
            
    def _parse_magnet_link(self, magnet_link):
        parts = dict(p.split('=') for p in magnet_link.replace('magnet:?', '').split('&'))
        return parts.get('xt', '').replace('urn:btih:', '')
        
    def _get_name_from_magnet(self, magnet_link):
        parts = dict(p.split('=') for p in magnet_link.replace('magnet:?', '').split('&'))
        name = parts.get('dn', 'Unknown')
        return urllib.parse.unquote_plus(name)
        
    def start(self):
        self.is_paused = False
        self.is_stopped = False
        self.status = "Downloading"
        # Simulate download progress with more realistic behavior
        def download_loop():
            while not self.is_stopped and self.progress < 100:
                if not self.is_paused:
                    time.sleep(0.5)
                    # Simulate varying download speeds based on seeds/peers
                    self.seeds = random.randint(1, 100)
                    self.peers = random.randint(1, 50)
                    speed_factor = min(1.0, (self.seeds + self.peers) / 100)
                    
                    progress_increment = random.uniform(0.1, 1.0) * speed_factor
                    self.progress += progress_increment
                    self.progress = min(100, self.progress)
                    
                    # Update speeds and stats
                    self.download_speed = random.uniform(100000, 1000000) * speed_factor
                    self.upload_speed = random.uniform(10000, 100000) * speed_factor
                    self.downloaded = (self.progress / 100) * (self.size or 1000000000)
                    self.uploaded = self.downloaded * random.uniform(0.1, 0.5)
                    self.ratio = self.uploaded / max(1, self.downloaded)
                    
                    # Calculate estimated time
                    if self.download_speed > 0:
                        remaining_bytes = (self.size or 1000000000) * (1 - self.progress / 100)
                        seconds = remaining_bytes / self.download_speed
                        self.estimated_time = self._format_time(seconds)
                    else:
                        self.estimated_time = "Unknown"
            
            self.status = "Completed" if self.progress >= 100 else "Stopped"
        Thread(target=download_loop, daemon=True).start()
        
    def _format_time(self, seconds):
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            return f"{int(seconds/60)}m {int(seconds%60)}s"
        else:
            hours = int(seconds/3600)
            minutes = int((seconds%3600)/60)
            return f"{hours}h {minutes}m"
        
    def pause(self):
        self.is_paused = True
        self.status = "Paused"
        
    def resume(self):
        self.is_paused = False
        self.status = "Downloading"
        
    def stop(self):
        self.is_stopped = True
        self.status = "Stopped"
        
    def set_priority(self, priority):
        self.priority = priority
        
    def select_files(self, file_indices):
        for i, file in enumerate(self.files):
            file['selected'] = i in file_indices
            
    def set_file_priority(self, file_index, priority):
        if 0 <= file_index < len(self.files):
            self.files[file_index]['priority'] = priority

class TorrentPanel:
    def __init__(self, page: ft.Page, on_action=None):
        self.page = page
        self.on_action = on_action
        self.update_lock = Lock()
        self.is_closing = False
        self.update_interval = 1  # seconds
        
        self.init_controls()
        
    def init_controls(self):
        # Torrent input section
        self.magnet_input = ft.TextField(
            label="Magnet Link or Torrent URL",
            hint_text="Enter magnet link or torrent URL...",
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            prefix_icon=ft.Icons.LINK,
            height=55,
            text_size=14,
            width=350,
            on_submit=self.add_torrent,
        )
        
        self.add_button = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="Add Torrent",
            icon_color="white",
            bgcolor="#ff0000",
            icon_size=20,
            on_click=self.add_torrent,
        )
        
        # File picker for torrent files
        self.pick_files_dialog = ft.FilePicker(
            on_result=self.handle_file_picked
        )
        self.page.overlay.append(self.pick_files_dialog)
        
        # Drop zone for torrent files
        self.drop_zone = ft.Container(
            content=ft.Column(
                [
                    ft.IconButton(
                        icon=ft.Icons.UPLOAD_FILE,
                        icon_size=32,
                        icon_color="#666666",
                        tooltip="Select .torrent file",
                        on_click=lambda _: self.pick_files_dialog.pick_files(
                            allowed_extensions=["torrent"]
                        ),
                    ),
                    ft.Text("Click to select .torrent file", size=14, color="#666666"),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=10,
            ),
            width=350,
            height=100,
            border=ft.border.all(2, "#333333"),
            border_radius=8,
            bgcolor="#1a1a1a",
            alignment=ft.alignment.center,
        )
        
        # Download path selection
        self.download_path = ft.TextField(
            value=str(Path.home() / "Downloads"),
            label="Download Path",
            border_radius=8,
            border_color="#333333",
            focused_border_color="#ff0000",
            bgcolor="#1f1f1f",
            color="white",
            prefix_icon=ft.Icons.FOLDER,
            height=55,
            text_size=14,
            width=350,
            read_only=True,
        )
        
        self.browse_button = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            tooltip="Browse",
            icon_color="white",
            bgcolor="#333333",
            icon_size=20,
            on_click=self.browse_directory,
        )
        
        # Status text
        self.status_text = ft.Text(
            "",
            size=14,
            color="white",
        )
        
        # Build the panel layout
        self.panel = ft.Container(
            content=ft.Column(
                [
                    # Input section
                    ft.Container(
                        content=ft.Column(
                            [
                                ft.Row(
                                    [self.magnet_input, self.add_button],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=5,
                                ),
                                self.drop_zone,
                                ft.Row(
                                    [self.download_path, self.browse_button],
                                    alignment=ft.MainAxisAlignment.START,
                                    spacing=5,
                                ),
                            ],
                            spacing=10,
                        ),
                        padding=15,
                        bgcolor="#0f0f0f",
                        border=ft.border.all(1, "#333333"),
                        border_radius=8,
                        margin=ft.margin.only(bottom=15),
                    ),
                    
                    # Status text
                    self.status_text,
                ],
                spacing=10,
                scroll=ft.ScrollMode.AUTO,
                expand=True,
            ),
            expand=True,
            padding=20,
        )
    
    def add_torrent(self, e=None):
        """Add a new torrent to the main queue"""
        link = self.magnet_input.value.strip()
        if not link:
            if self.on_action:
                self.on_action({"type": "status", "message": "Please enter a magnet link or torrent URL"})
            return
            
        try:
            # Create a new torrent instance
            t = TorrentDownloader(
                magnet_link=link,
                download_path=self.download_path.value
            )
            
            # Add to queue through callback
            if self.on_action:
                self.on_action({
                    "type": "add_to_queue",
                    "item": {
                        "type": "torrent",
                        "torrent": t,
                        "title": t.name,
                        "download_path": t.download_path,
                        "status": "queued",
                        "progress": 0
                    }
                })
            
            # Clear input
            self.magnet_input.value = ""
            self.status_text.value = "Torrent added successfully"
            self.update_ui()
            
        except Exception as e:
            self.status_text.value = f"Error adding torrent: {str(e)}"
            self.update_ui()
    
    def handle_file_picked(self, e: ft.FilePickerResultEvent):
        """Handle selected .torrent files"""
        try:
            if e.files:
                for file in e.files:
                    if file.path.endswith('.torrent'):
                        # Create torrent instance
                        t = TorrentDownloader(
                            torrent_path=file.path,
                            download_path=self.download_path.value
                        )
                        
                        # Add to queue through callback
                        if self.on_action:
                            self.on_action({
                                "type": "add_to_queue",
                                "item": {
                                    "type": "torrent",
                                    "torrent": t,
                                    "title": t.name,
                                    "download_path": t.download_path,
                                    "status": "queued",
                                    "progress": 0
                                }
                            })
                
                self.status_text.value = "Torrent file(s) added successfully"
                self.update_ui()
                
        except Exception as e:
            self.status_text.value = f"Error processing torrent file: {str(e)}"
            self.update_ui()
    
    def browse_directory(self, e):
        """Open directory picker for download location"""
        def result_handler(e: ft.FilePickerResultEvent):
            if e.path:
                self.download_path.value = e.path
                self.update_ui()
        
        picker = ft.FilePicker(
            on_result=result_handler
        )
        self.page.overlay.append(picker)
        self.page.update()
        picker.get_directory_path()
    
    def update_ui(self):
        """Thread-safe method to update UI"""
        try:
            if not self.is_closing:
                with self.update_lock:
                    self.page.update()
        except Exception as e:
            print(f"Error updating UI: {str(e)}")
    
    def get_panel(self):
        """Return the main panel container"""
        return self.panel 