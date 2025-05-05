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
        self._download_thread = None
        self._stop_event = False
        self._total_selected_size = 0
        self._downloaded_size = 0
        
        if torrent_path:
            try:
                self.torrent = torf.Torrent.read(torrent_path)
                self.name = self.torrent.name
                self.size = self.torrent.size
                self.files = []
                for f in self.torrent.files:
                    try:
                        size = os.path.getsize(f) if os.path.exists(f) else self.size / len(self.torrent.files)
                        self.files.append({
                            'path': str(f),
                            'size': size,
                            'size_str': self._format_size(size),
                            'selected': True,
                            'priority': 'Normal',
                            'downloaded': 0
                        })
                    except:
                        # If can't get actual size, estimate it
                        est_size = self.size / len(self.torrent.files)
                        self.files.append({
                            'path': str(f),
                            'size': est_size,
                            'size_str': self._format_size(est_size),
                            'selected': True,
                            'priority': 'Normal',
                            'downloaded': 0
                        })
                self._update_total_selected_size()
            except Exception as e:
                print(f"Error reading torrent file: {str(e)}")
                self.files = []
        elif magnet_link:
            self.info_hash = self._parse_magnet_link(magnet_link)
            self.name = self._get_name_from_magnet(magnet_link)
            
    def _format_size(self, size):
        """Format size to human readable format"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} PB"
        
    def _parse_magnet_link(self, magnet_link):
        parts = dict(p.split('=') for p in magnet_link.replace('magnet:?', '').split('&'))
        return parts.get('xt', '').replace('urn:btih:', '')
        
    def _get_name_from_magnet(self, magnet_link):
        parts = dict(p.split('=') for p in magnet_link.replace('magnet:?', '').split('&'))
        name = parts.get('dn', 'Unknown')
        return urllib.parse.unquote_plus(name)
        
    def _update_total_selected_size(self):
        """Update total size of selected files"""
        self._total_selected_size = sum(f['size'] for f in self.files if f['selected'])
        
    def start(self):
        if self._download_thread and self._download_thread.is_alive():
            return
            
        self.is_paused = False
        self.is_stopped = False
        self._stop_event = False
        self.status = "Downloading"
        self._downloaded_size = 0
        
        def download_loop():
            try:
                while not self._stop_event and self.progress < 100:
                    if not self.is_paused:
                        time.sleep(0.5)
                        # Simulate varying download speeds based on seeds/peers
                        self.seeds = random.randint(1, 100)
                        self.peers = random.randint(1, 50)
                        speed_factor = min(1.0, (self.seeds + self.peers) / 100)
                        
                        # Only progress if there are selected files
                        if any(f['selected'] for f in self.files):
                            # Calculate progress for each selected file
                            for f in self.files:
                                if f['selected']:
                                    # Simulate download progress for this file
                                    remaining = f['size'] - f['downloaded']
                                    if remaining > 0:
                                        download_amount = min(
                                            remaining,
                                            random.uniform(100000, 1000000) * speed_factor
                                        )
                                        f['downloaded'] += download_amount
                                        self._downloaded_size += download_amount
                            
                            # Update overall progress based on downloaded size
                            if self._total_selected_size > 0:
                                self.progress = (self._downloaded_size / self._total_selected_size) * 100
                            
                            # Update speeds and stats
                            self.download_speed = random.uniform(100000, 1000000) * speed_factor
                            self.upload_speed = random.uniform(10000, 100000) * speed_factor
                            self.downloaded = self._downloaded_size
                            self.uploaded = self.downloaded * random.uniform(0.1, 0.5)
                            self.ratio = self.uploaded / max(1, self.downloaded)
                            
                            # Calculate estimated time
                            if self.download_speed > 0:
                                remaining_bytes = self._total_selected_size - self._downloaded_size
                                seconds = remaining_bytes / self.download_speed
                                self.estimated_time = self._format_time(seconds)
                            else:
                                self.estimated_time = "Unknown"
                        else:
                            self.status = "No files selected"
                            time.sleep(1)
                    else:
                        time.sleep(0.1)
                        
                self.status = "Completed" if self.progress >= 100 else "Stopped"
                
            except Exception as e:
                self.status = f"Error: {str(e)}"
                print(f"Download error: {str(e)}")
                
        self._download_thread = Thread(target=download_loop, daemon=True)
        self._download_thread.start()
        
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
        """Pause the download"""
        self.is_paused = True
        self.status = "Paused"
        
    def resume(self):
        """Resume the download"""
        self.is_paused = False
        self.status = "Downloading"
        
    def stop(self):
        """Stop the download"""
        self.is_stopped = True
        self._stop_event = True
        self.status = "Stopped"
        if self._download_thread and self._download_thread.is_alive():
            self._download_thread.join(timeout=1.0)
        
    def set_priority(self, priority):
        self.priority = priority
        
    def select_files(self, file_indices):
        """Update selected files and recalculate total size"""
        for i, file in enumerate(self.files):
            file['selected'] = i in file_indices
            if not file['selected']:
                file['downloaded'] = 0
        self._update_total_selected_size()
        self._downloaded_size = sum(f['downloaded'] for f in self.files if f['selected'])
        
        # If no files are selected, pause the download
        if not any(f['selected'] for f in self.files):
            self.pause()
            
    def set_file_priority(self, file_index, priority):
        if 0 <= file_index < len(self.files):
            self.files[file_index]['priority'] = priority
            
    def get_details(self):
        """Get detailed information about the torrent"""
        return {
            'name': self.name,
            'size': self._format_size(self._total_selected_size),
            'progress': f"{self.progress:.1f}%",
            'status': self.status,
            'download_speed': self._format_size(self.download_speed) + "/s",
            'upload_speed': self._format_size(self.upload_speed) + "/s",
            'seeds': self.seeds,
            'peers': self.peers,
            'ratio': f"{self.ratio:.2f}",
            'estimated_time': self.estimated_time,
            'files': self.files,
            'downloaded_size': self._downloaded_size,
            'total_size': self._total_selected_size
        }

class TorrentPanel:
    def __init__(self, page: ft.Page, on_action=None):
        self.page = page
        self.on_action = on_action
        self.update_lock = Lock()
        self.is_closing = False
        self.update_interval = 1  # seconds
        self.current_torrent = None
        
        self.init_controls()
        
    def init_controls(self):
        # File selection dialog
        self.file_selection_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Select Files to Download", size=16, weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text("Loading torrent details...", color="#bbbbbb"),
                ],
                scroll=ft.ScrollMode.AUTO,
                height=300,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=self.close_file_selection),
                ft.TextButton("Add to Queue", on_click=self.confirm_file_selection),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )

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
            on_submit=self.prepare_torrent,
        )
        
        self.add_button = ft.IconButton(
            icon=ft.Icons.ADD,
            tooltip="Add Torrent",
            icon_color="white",
            bgcolor="#ff0000",
            icon_size=20,
            on_click=self.prepare_torrent,
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
        
        # Add file selection dialog to page overlay
        self.page.overlay.append(self.file_selection_dialog)
    
    def prepare_torrent(self, e=None):
        """Prepare torrent for adding to queue by showing file selection dialog"""
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
            
            self.current_torrent = t
            self.show_file_selection_dialog(t)
            
        except Exception as e:
            self.status_text.value = f"Error preparing torrent: {str(e)}"
            self.update_ui()
            
    def show_file_selection_dialog(self, torrent):
        """Show dialog for selecting files to download"""
        try:
            details = torrent.get_details()
            
            # Create file selection list
            file_list = ft.Column(
                spacing=2,
                scroll=ft.ScrollMode.AUTO,
                height=250,
            )
            
            # Add "Select All" checkbox
            select_all_row = ft.Row(
                [
                    ft.Checkbox(
                        value=True,
                        on_change=lambda e: self.toggle_all_files(e.control.value),
                    ),
                    ft.Text(
                        "Select All Files",
                        size=14,
                        weight=ft.FontWeight.BOLD,
                        color="white",
                    ),
                ],
                spacing=10,
            )
            
            # Add collapsible sections for file types
            file_sections = {}
            for i, f in enumerate(details['files']):
                ext = os.path.splitext(f['path'])[1].lower()
                if not ext:
                    ext = 'Other'
                if ext not in file_sections:
                    # Create section header
                    header_row = ft.Row(
                        [
                            ft.IconButton(
                                icon=ft.Icons.EXPAND_MORE,
                                icon_size=20,
                                data={'section': ext, 'expanded': True},
                                on_click=lambda e: self.toggle_section(e.control.data['section']),
                            ),
                            ft.Text(
                                f"{ext.upper()} Files",
                                size=14,
                                weight=ft.FontWeight.BOLD,
                                color="#bbbbbb",
                            ),
                        ],
                        spacing=5,
                    )
                    
                    # Create section content
                    section_content = ft.Column(
                        [],
                        spacing=2,
                        visible=True,
                    )
                    
                    file_sections[ext] = {
                        'header': header_row,
                        'content': section_content,
                        'files': [],
                    }
                    
                    file_list.controls.extend([header_row, section_content])
                
                # Add file to section
                checkbox = ft.Checkbox(
                    value=True,
                    data={'index': i},
                )
                
                file_row = ft.Row(
                    [
                        checkbox,
                        ft.Text(
                            f"{os.path.basename(f['path'])} ({f.get('size_str', 'Unknown')})",
                            size=12,
                            color="#bbbbbb",
                            expand=True,
                        ),
                    ],
                    spacing=5,
                )
                
                file_sections[ext]['content'].controls.append(file_row)
                file_sections[ext]['files'].append({'checkbox': checkbox, 'row': file_row})
            
            # Update dialog content
            self.file_selection_dialog.content.controls = [
                ft.Text("Select files to download:", size=14, color="#bbbbbb"),
                select_all_row,
                ft.Divider(height=1, color="#333333"),
                file_list,
            ]
            
            # Store sections for later use
            self.file_sections = file_sections
            
            # Show dialog
            self.file_selection_dialog.open = True
            self.update_ui()
            
        except Exception as e:
            self.status_text.value = f"Error showing file selection: {str(e)}"
            self.update_ui()
            
    def toggle_section(self, section):
        """Toggle visibility of a file section"""
        if section in self.file_sections:
            section_data = self.file_sections[section]
            header = section_data['header']
            content = section_data['content']
            
            # Toggle visibility
            content.visible = not content.visible
            
            # Update icon
            header.controls[0].icon = ft.Icons.EXPAND_LESS if content.visible else ft.Icons.EXPAND_MORE
            
            self.update_ui()
            
    def toggle_all_files(self, value):
        """Toggle all file checkboxes"""
        for section in self.file_sections.values():
            for file_data in section['files']:
                file_data['checkbox'].value = value
        self.update_ui()
            
    def close_file_selection(self, e):
        """Close the file selection dialog"""
        self.file_selection_dialog.open = False
        self.current_torrent = None
        self.update_ui()
        
    def confirm_file_selection(self, e):
        """Add selected files to queue"""
        if not self.current_torrent:
            return
            
        try:
            # Get selected file indices
            selected_indices = []
            for section in self.file_sections.values():
                for file_data in section['files']:
                    if file_data['checkbox'].value:
                        selected_indices.append(file_data['checkbox'].data['index'])
            
            # Update torrent with selected files
            self.current_torrent.select_files(selected_indices)
            
            # Add to queue through callback
            if self.on_action:
                self.on_action({
                    "type": "add_to_queue",
                    "item": {
                        "type": "torrent",
                        "torrent": self.current_torrent,
                        "title": self.current_torrent.name,
                        "download_path": self.current_torrent.download_path,
                        "status": "queued",
                        "progress": 0
                    }
                })
            
            # Clear input and close dialog
            self.magnet_input.value = ""
            self.file_selection_dialog.open = False
            self.current_torrent = None
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
                        
                        self.current_torrent = t
                        self.show_file_selection_dialog(t)
                        break
                
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