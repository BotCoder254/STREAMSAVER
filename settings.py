import flet as ft
import platform
import psutil
import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio
import time
import threading
import os
import io
import base64
from PIL import Image
from typing import Callable, Dict, Any

VERSION = "1.2.0"  # StreamSaver Pro version

class SystemMonitor:
    """Class to monitor system resources and network usage"""
    def __init__(self):
        self.cpu_history = []
        self.memory_history = []
        self.network_history = []
        self.disk_history = []
        self.time_history = []
        self.max_history = 60  # 60 data points
        
        self.network_sent_prev = 0
        self.network_recv_prev = 0
        self.network_sent_total = 0
        self.network_recv_total = 0
        self.last_update = time.time()

    def get_cpu_percent(self):
        return psutil.cpu_percent(interval=0.1)
        
    def get_memory_percent(self):
        return psutil.virtual_memory().percent
        
    def get_network_speed(self):
        """Get network speed in KB/s and update total data transferred"""
        current_time = time.time()
        interval = current_time - self.last_update
        
        if interval < 0.1:
            return 0  # Avoid division by very small numbers
            
        net_io = psutil.net_io_counters()
        
        # Calculate speeds
        sent_speed = (net_io.bytes_sent - self.network_sent_prev) / interval / 1024  # KB/s
        recv_speed = (net_io.bytes_recv - self.network_recv_prev) / interval / 1024  # KB/s
        
        # Update total data transferred
        self.network_sent_total += net_io.bytes_sent - self.network_sent_prev
        self.network_recv_total += net_io.bytes_recv - self.network_recv_prev
        
        # Update previous values for next calculation
        self.network_sent_prev = net_io.bytes_sent
        self.network_recv_prev = net_io.bytes_recv
        self.last_update = current_time
        
        # Return total speed (sent + received)
        return sent_speed + recv_speed
        
    def get_disk_percent(self):
        return psutil.disk_usage('/').percent
        
    def get_formatted_total_data(self):
        """Format total data transferred in B, KB, MB, GB"""
        total_data = self.network_sent_total + self.network_recv_total
        
        if total_data < 1024:
            return f"{total_data:.2f} B"
        elif total_data < 1024 * 1024:
            return f"{total_data/1024:.2f} KB"
        elif total_data < 1024 * 1024 * 1024:
            return f"{total_data/(1024*1024):.2f} MB"
        else:
            return f"{total_data/(1024*1024*1024):.2f} GB"
        
    def update_history(self):
        """Update history arrays with current values"""
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Add new values
        self.cpu_history.append(self.get_cpu_percent())
        self.memory_history.append(self.get_memory_percent())
        self.network_history.append(self.get_network_speed())
        self.disk_history.append(self.get_disk_percent())
        self.time_history.append(current_time)
        
        # Trim arrays to max length
        if len(self.cpu_history) > self.max_history:
            self.cpu_history = self.cpu_history[-self.max_history:]
            self.memory_history = self.memory_history[-self.max_history:]
            self.network_history = self.network_history[-self.max_history:]
            self.disk_history = self.disk_history[-self.max_history:]
            self.time_history = self.time_history[-self.max_history:]


class SettingsPanel:
    def __init__(self, page: ft.Page, on_action: Callable[[Dict[str, Any]], None]):
        self.page = page
        self.on_action = on_action
        self.system_monitor = SystemMonitor()
        self.update_interval = 1  # seconds
        self.stop_event = threading.Event()
        self.init_controls()
        
        # Start background thread for updating stats
        self.monitoring_thread = threading.Thread(target=self.update_loop, daemon=True)
        self.monitoring_thread.start()
        
    def init_controls(self):
        # System info section
        self.system_info = ft.Container(
            content=ft.Column(
                [
                    ft.Text("System Information", size=16, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    ft.Text(f"OS: {platform.system()} {platform.release()}", size=14, color="#bbbbbb"),
                    ft.Text(f"Python: {platform.python_version()}", size=14, color="#bbbbbb"),
                    ft.Text(f"Processor: {platform.processor()}", size=14, color="#bbbbbb"),
                    ft.Text(f"StreamSaver Pro Version: {VERSION}", size=14, color="#bbbbbb"),
                ],
                spacing=5,
            ),
            padding=10,
            bgcolor="#111111",
            border_radius=8,
            margin=ft.margin.only(bottom=10)
        )
        
        # Current stats section
        self.cpu_text = ft.Text("CPU: 0%", size=14, color="#bbbbbb")
        self.memory_text = ft.Text("Memory: 0%", size=14, color="#bbbbbb")
        self.network_text = ft.Text("Network: 0 KB/s", size=14, color="#bbbbbb")
        self.disk_text = ft.Text("Disk: 0%", size=14, color="#bbbbbb")
        self.network_total_text = ft.Text("Total Data: 0 B", size=14, color="#bbbbbb")
        
        self.stats_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Current Statistics", size=16, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    self.cpu_text,
                    self.memory_text,
                    self.network_text,
                    self.disk_text,
                    self.network_total_text,
                ],
                spacing=5,
            ),
            padding=10,
            bgcolor="#111111",
            border_radius=8,
            margin=ft.margin.only(bottom=10)
        )
        
        # Graphs section - Use Image instead of WebView for cross-platform compatibility
        self.chart_image = ft.Image(
            src="",
            width=800,
            height=500,
            fit=ft.ImageFit.CONTAIN,
            visible=False,
        )
        
        self.plots_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Resource Monitoring", size=16, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    ft.Container(
                        content=self.chart_image,
                        bgcolor="#111111",
                        border_radius=8,
                        padding=10,
                    ),
                ],
                spacing=5,
            ),
            padding=10,
            bgcolor="#111111",
            border_radius=8,
            visible=False,
        )
        
        # Configuration section
        self.refresh_dropdown = ft.Dropdown(
            label="Update Interval",
            options=[
                ft.dropdown.Option("1", "1 second"),
                ft.dropdown.Option("2", "2 seconds"),
                ft.dropdown.Option("5", "5 seconds"),
                ft.dropdown.Option("10", "10 seconds"),
            ],
            value="1",
            width=200,
            on_change=self.change_refresh_rate,
            color="#ffffff",
            bgcolor="#222222",
        )
        
        self.monitor_switch = ft.Switch(
            label="Enable Resource Monitor",
            value=False,
            on_change=self.toggle_resource_monitor,
            active_color="#ff0000",
        )
        
        self.config_container = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Configuration", size=16, weight=ft.FontWeight.BOLD, color="#ffffff"),
                    ft.Row([self.refresh_dropdown]),
                    ft.Row([self.monitor_switch]),
                ],
                spacing=10,
            ),
            padding=10,
            bgcolor="#111111",
            border_radius=8,
            margin=ft.margin.only(bottom=10)
        )
        
        # Settings button (visible in main UI)
        self.settings_button = ft.IconButton(
            icon=ft.icons.SETTINGS,
            icon_color="#ffffff",
            icon_size=24,
            tooltip="Settings",
            on_click=self.toggle_settings,
        )
        
        # Settings panel container (hidden by default)
        self.settings_container = ft.Container(
            content=ft.Column(
                [
                    # Header with close button
                    ft.Row(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ft.icons.SETTINGS, color="#ff0000", size=20),
                                    ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD, color="#ffffff"),
                                ],
                                spacing=5,
                            ),
                            ft.IconButton(
                                icon=ft.icons.CLOSE,
                                icon_color="#ffffff",
                                icon_size=20,
                                tooltip="Close",
                                on_click=self.toggle_settings,
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
                    ),
                    
                    ft.Divider(height=1, color="#333333"),
                    
                    # Scrollable content
                    ft.Container(
                        content=ft.Column(
                            [
                                self.system_info,
                                self.stats_container,
                                self.config_container,
                                self.plots_container,
                            ],
                            spacing=0,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        expand=True,
                    ),
                ],
                spacing=10,
            ),
            width=850,
            height=700,
            bgcolor="#0f0f0f",
            border_radius=10,
            padding=20,
            visible=False,
        )
        
    def get_settings_button(self):
        return self.settings_button
        
    def get_settings_panel(self):
        return self.settings_container
        
    def toggle_settings(self, e=None):
        self.settings_container.visible = not self.settings_container.visible
        self.page.update()
        
    def change_refresh_rate(self, e):
        self.update_interval = int(self.refresh_dropdown.value)
        
    def toggle_resource_monitor(self, e):
        if self.monitor_switch.value:
            self.plots_container.visible = True
            self.chart_image.visible = True
            self.update_plots()
        else:
            self.plots_container.visible = False
            self.chart_image.visible = False
        
        self.page.update()
        
    def update_plots(self):
        """Generate plots using Plotly and display them as an image"""
        if not self.plots_container.visible:
            return
            
        try:
            # Create subplots with 2x2 grid
            fig = make_subplots(
                rows=2, cols=2, 
                subplot_titles=("CPU Usage", "Memory Usage", "Network Speed", "Disk Usage"),
                shared_xaxes=True
            )
            
            # Add CPU trace
            fig.add_trace(
                go.Scatter(x=self.system_monitor.time_history, y=self.system_monitor.cpu_history, 
                          line=dict(color="#ff0000", width=2), name="CPU"),
                row=1, col=1
            )
            
            # Add Memory trace
            fig.add_trace(
                go.Scatter(x=self.system_monitor.time_history, y=self.system_monitor.memory_history, 
                          line=dict(color="#00ff00", width=2), name="Memory"),
                row=1, col=2
            )
            
            # Add Network trace
            fig.add_trace(
                go.Scatter(x=self.system_monitor.time_history, y=self.system_monitor.network_history, 
                          line=dict(color="#0000ff", width=2), name="Network"),
                row=2, col=1
            )
            
            # Add Disk trace
            fig.add_trace(
                go.Scatter(x=self.system_monitor.time_history, y=self.system_monitor.disk_history, 
                          line=dict(color="#ffff00", width=2), name="Disk"),
                row=2, col=2
            )
            
            # Update layout
            fig.update_layout(
                height=500, width=800,
                paper_bgcolor="#111111",
                plot_bgcolor="#161616",
                font=dict(color="#bbbbbb"),
                margin=dict(l=50, r=50, t=50, b=30),
                showlegend=False,
            )
            
            # Set y-axis range for percentage values
            fig.update_yaxes(range=[0, 100], row=1, col=1)
            fig.update_yaxes(range=[0, 100], row=1, col=2)
            fig.update_yaxes(range=[0, max(max(self.system_monitor.network_history, default=0) * 1.2, 1)], row=2, col=1)
            fig.update_yaxes(range=[0, 100], row=2, col=2)
            
            # Add y-axis titles
            fig.update_yaxes(title_text="Percent (%)", row=1, col=1)
            fig.update_yaxes(title_text="Percent (%)", row=1, col=2)
            fig.update_yaxes(title_text="KB/s", row=2, col=1)
            fig.update_yaxes(title_text="Percent (%)", row=2, col=2)
            
            # Convert plot to image
            img_bytes = pio.to_image(fig, format="png")
            base64_image = base64.b64encode(img_bytes).decode("utf-8")
            
            # Update image widget
            self.chart_image.src_base64 = base64_image
            self.chart_image.visible = True
            self.page.update()
            
        except Exception as e:
            print(f"Error updating plots: {str(e)}")
        
    def update_stats(self):
        """Update the statistics text in UI"""
        try:
            # Get current stats
            cpu = self.system_monitor.get_cpu_percent()
            memory = self.system_monitor.get_memory_percent()
            network = self.system_monitor.get_network_speed()
            disk = self.system_monitor.get_disk_percent()
            total_data = self.system_monitor.get_formatted_total_data()
            
            # Update the UI
            self.cpu_text.value = f"CPU: {cpu:.1f}%"
            self.memory_text.value = f"Memory: {memory:.1f}%"
            self.network_text.value = f"Network: {network:.2f} KB/s"
            self.disk_text.value = f"Disk: {disk:.1f}%"
            self.network_total_text.value = f"Total Data: {total_data}"
            
            self.page.update()
        except Exception as e:
            print(f"Error updating stats: {str(e)}")
            
    def update_loop(self):
        """Background thread for updating stats and plots"""
        while not self.stop_event.is_set():
            try:
                # Update history
                self.system_monitor.update_history()
                
                # Update UI
                self.update_stats()
                
                # Update plots if visible
                if self.plots_container.visible:
                    self.update_plots()
                
                # Sleep according to update interval
                time.sleep(self.update_interval)
            except Exception as e:
                print(f"Error in update loop: {str(e)}")
                time.sleep(self.update_interval)
                
    def stop(self):
        """Stop the update thread"""
        self.stop_event.set()
        if self.monitoring_thread.is_alive():
            self.monitoring_thread.join(timeout=1.0) 