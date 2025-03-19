import os
import glob
import queue
import logging
import threading
import platform
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from PIL import Image, ImageTk, ExifTags
import pillow_heif
import sv_ttk  # Modern Fluent/Sun Valley theme for tkinter

# Register HEIF opener with Pillow
pillow_heif.register_heif_opener()

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("heif_converter.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("HeifConverter")

# Application color scheme
COLOR_SCHEME = {
    "light": {
        "bg": "#f5f5f5",
        "fg": "#333333",
        "accent": "#0078d7",
        "accent_hover": "#005fa3",
        "success": "#5cb85c",
        "warning": "#f0ad4e",
        "error": "#d9534f",
        "border": "#e0e0e0"
    },
    "dark": {
        "bg": "#1e1e1e",
        "fg": "#f5f5f5",
        "accent": "#2b88d8",
        "accent_hover": "#5ca8e0",
        "success": "#5cb85c",
        "warning": "#f0ad4e",
        "error": "#d9534f",
        "border": "#444444"
    }
}


class ImageConverter:
    """Business logic for image conversion separate from UI"""
    
    def __init__(self):
        self.stop_requested = False
        self.queue = queue.Queue()
        self.current_files = []
    
    @staticmethod
    def find_heif_files(directory, include_subdirs=False):
        """Find all HEIF files in the given directory"""
        heif_files = []
        extensions = ["*.heif", "*.heic", "*.hif", "*.HEIF", "*.HEIC", "*.HIF"]
        
        if include_subdirs:
            for root, _, _ in os.walk(directory):
                for ext in extensions:
                    heif_files.extend(glob.glob(os.path.join(root, ext)))
        else:
            for ext in extensions:
                heif_files.extend(glob.glob(os.path.join(directory, ext)))
                
        return heif_files
    
    @staticmethod
    def convert_image(heif_path, output_dir, quality=90, preserve_structure=False, 
                     keep_exif=True, rename_pattern=None):
        """Convert a single HEIF image to JPEG"""
        try:
            # Determine output path
            if preserve_structure and os.path.isabs(heif_path):
                rel_path = os.path.dirname(heif_path)
                if not rel_path.startswith(output_dir):
                    # Create relative path structure in output dir
                    rel_path = os.path.relpath(os.path.dirname(heif_path), os.path.dirname(output_dir))
                    new_output_dir = os.path.join(output_dir, rel_path)
                    os.makedirs(new_output_dir, exist_ok=True)
                    output_dir = new_output_dir
            
            # Get filename and create output path
            filename = os.path.basename(heif_path)
            name, _ = os.path.splitext(filename)
            
            # Apply rename pattern if provided
            if rename_pattern:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                counter = 1  # You could make this dynamic if needed
                name = rename_pattern.replace("{name}", name) \
                                    .replace("{timestamp}", timestamp) \
                                    .replace("{counter}", str(counter))
            
            jpeg_path = os.path.join(output_dir, f"{name}.jpg")
            
            # Open HEIF image
            heif_image = Image.open(heif_path)
            
            # Extract EXIF data if needed
            exif_data = None
            if keep_exif:
                try:
                    exif_data = heif_image.getexif()
                except Exception as e:
                    logger.warning(f"Could not extract EXIF from {filename}: {e}")
            
            # Convert to RGB if needed
            if heif_image.mode in ('RGBA', 'LA'):
                background = Image.new('RGB', heif_image.size, (255, 255, 255))
                background.paste(heif_image, mask=heif_image.split()[3])
                final_image = background
            else:
                final_image = heif_image.convert('RGB')
            
            # Save as JPEG with EXIF if available
            if exif_data and keep_exif:
                final_image.save(jpeg_path, 'JPEG', quality=quality, exif=exif_data)
            else:
                final_image.save(jpeg_path, 'JPEG', quality=quality)
                
            return True, jpeg_path
            
        except Exception as e:
            logger.error(f"Error converting {heif_path}: {e}")
            return False, str(e)


class PreviewWindow(tk.Toplevel):
    """Window to preview original and converted images"""
    
    def __init__(self, parent, image_path, theme="light"):
        super().__init__(parent)
        self.title("Image Preview")
        self.geometry("800x600")
        self.minsize(600, 400)
        
        # Set window icon and styling
        self.theme = theme
        colors = COLOR_SCHEME[theme]
        
        self.image_path = image_path
        
        # Create preview frame with padding
        frame = ttk.Frame(self, padding=15)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Add a header
        header = ttk.Frame(frame)
        header.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(header, text="Image Preview", style="Title.TLabel").pack(side=tk.LEFT)
        ttk.Button(header, text="Close", command=self.destroy, style="Accent.TButton").pack(side=tk.RIGHT)
        
        # Create a card-like container for the image
        card_frame = ttk.Frame(frame, style="Card.TFrame")
        card_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)
        
        # Add a scrollable view for the image
        canvas = tk.Canvas(card_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(card_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load image
        try:
            img = Image.open(self.image_path)
            
            # Calculate appropriate size while maintaining aspect ratio
            canvas_width = 750
            canvas_height = 450
            
            width, height = img.size
            ratio = min(canvas_width/width, canvas_height/height)
            new_width = int(width * ratio)
            new_height = int(height * ratio)
            
            img = img.resize((new_width, new_height), Image.LANCZOS)
            photo_img = ImageTk.PhotoImage(img)
            
            # Display image with a subtle border
            image_frame = ttk.Frame(scrollable_frame, borderwidth=1, relief="solid", style="ImageBorder.TFrame")
            image_frame.pack(padx=15, pady=15)
            
            label = ttk.Label(image_frame, image=photo_img)
            label.image = photo_img  # Keep reference
            label.pack()
            
            # Image metadata section
            info_frame = ttk.LabelFrame(scrollable_frame, text="Image Information", padding=15)
            info_frame.pack(fill=tk.X, expand=True, padx=15, pady=15)
            
            # Two-column grid for metadata
            info_grid = ttk.Frame(info_frame)
            info_grid.pack(fill=tk.X)
            
            # Row 1
            ttk.Label(info_grid, text="Filename:", style="Bold.TLabel").grid(row=0, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(info_grid, text=os.path.basename(image_path)).grid(row=0, column=1, sticky=tk.W, pady=3)
            
            # Row 2
            ttk.Label(info_grid, text="Dimensions:", style="Bold.TLabel").grid(row=1, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(info_grid, text=f"{width} × {height} pixels").grid(row=1, column=1, sticky=tk.W, pady=3)
            
            # Row 3
            ttk.Label(info_grid, text="Format:", style="Bold.TLabel").grid(row=2, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(info_grid, text=f"{img.format}").grid(row=2, column=1, sticky=tk.W, pady=3)
            
            # Row 4
            ttk.Label(info_grid, text="Color Mode:", style="Bold.TLabel").grid(row=3, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            ttk.Label(info_grid, text=f"{img.mode}").grid(row=3, column=1, sticky=tk.W, pady=3)
            
            # Row 5
            ttk.Label(info_grid, text="File Size:", style="Bold.TLabel").grid(row=4, column=0, sticky=tk.W, padx=(0, 10), pady=3)
            file_size = os.path.getsize(image_path)
            size_str = self.format_file_size(file_size)
            ttk.Label(info_grid, text=size_str).grid(row=4, column=1, sticky=tk.W, pady=3)
            
            # Try to extract EXIF data
            try:
                exif = img._getexif()
                if exif:
                    exif_frame = ttk.LabelFrame(scrollable_frame, text="EXIF Metadata", padding=15)
                    exif_frame.pack(fill=tk.X, expand=True, padx=15, pady=(0, 15))
                    
                    exif_grid = ttk.Frame(exif_frame)
                    exif_grid.pack(fill=tk.X)
                    
                    row = 0
                    for tag_id in exif:
                        # Get the tag name
                        tag_name = ExifTags.TAGS.get(tag_id, tag_id)
                        value = exif[tag_id]
                        
                        # Skip binary data
                        if isinstance(value, bytes):
                            continue
                            
                        # Format value as string
                        if isinstance(value, tuple) or isinstance(value, list):
                            value = ", ".join(str(x) for x in value)
                        
                        ttk.Label(exif_grid, text=f"{tag_name}:", style="Bold.TLabel").grid(row=row, column=0, sticky=tk.W, padx=(0, 10), pady=2)
                        ttk.Label(exif_grid, text=str(value)).grid(row=row, column=1, sticky=tk.W, pady=2)
                        row += 1
                        
                        # Limit to first 10 EXIF tags to avoid overwhelming
                        if row >= 10:
                            ttk.Label(exif_grid, text="...more tags available").grid(row=row, column=0, columnspan=2, pady=5)
                            break
            except Exception as e:
                logger.debug(f"Could not read EXIF data: {e}")
            
        except Exception as e:
            error_frame = ttk.Frame(scrollable_frame, padding=20)
            error_frame.pack(fill=tk.BOTH, expand=True)
            
            error_icon = ttk.Label(error_frame, text="⚠️", font=("", 48))
            error_icon.pack(pady=20)
            
            error_msg = ttk.Label(error_frame, text=f"Error loading image", style="Title.TLabel")
            error_msg.pack(pady=5)
            
            error_details = ttk.Label(error_frame, text=str(e))
            error_details.pack(pady=5)
    
    def format_file_size(self, size_bytes):
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"


class FileDropTarget:
    """Enables drag and drop of files to a widget"""
    
    def __init__(self, widget, callback):
        self.widget = widget
        self.callback = callback
        
        if platform.system() == "Windows":
            try:
                # For Windows, you might use the tkinterdnd2 library
                # This is a placeholder that would be implemented if tkinterdnd2 is available
                self.setup_windows_dnd()
            except Exception:
                pass
        elif platform.system() == "Darwin":  # macOS
            try:
                # For macOS, you might use TkDnD
                # This is a placeholder that would be implemented if TkDnD is available
                self.setup_macos_dnd()
            except Exception:
                pass
    
    def setup_windows_dnd(self):
        """Set up drag and drop for Windows using tkinterdnd2"""
        # This is a placeholder. In a real implementation, you would:
        # 1. Import tkinterdnd2
        # 2. Register the widget with TkinterDnD
        # 3. Bind drop events to your callback
        pass
    
    def setup_macos_dnd(self):
        """Set up drag and drop for macOS using TkDnD"""
        # This is a placeholder. In a real implementation, you would:
        # 1. Import TkDnD
        # 2. Register the widget with TkDnD
        # 3. Bind drop events to your callback
        pass


class ModernTooltip:
    """Modern-looking tooltip for widgets"""
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tooltip_window = None
        self.widget.bind("<Enter>", self.show_tooltip)
        self.widget.bind("<Leave>", self.hide_tooltip)
    
    def show_tooltip(self, event=None):
        x, y, _, _ = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 25
        
        # Create tooltip window
        self.tooltip_window = tk.Toplevel(self.widget)
        self.tooltip_window.wm_overrideredirect(True)
        self.tooltip_window.wm_geometry(f"+{x}+{y}")
        
        # Create tooltip content
        frame = ttk.Frame(self.tooltip_window, style="Tooltip.TFrame", padding=8)
        frame.pack()
        
        label = ttk.Label(frame, text=self.text, style="Tooltip.TLabel", wraplength=250)
        label.pack()
        
        # Show tooltip with animation
        self.tooltip_window.attributes("-alpha", 0.0)
        self.fade_in()
    
    def hide_tooltip(self, event=None):
        if self.tooltip_window:
            self.tooltip_window.destroy()
            self.tooltip_window = None
    
    def fade_in(self, alpha=0.0):
        if self.tooltip_window:
            if alpha < 1.0:
                self.tooltip_window.attributes("-alpha", alpha)
                self.widget.after(20, self.fade_in, alpha + 0.1)


class CustomNotification:
    """Modern toast-like notification system"""
    
    def __init__(self, parent, message, type_="info", duration=3000):
        self.parent = parent
        self.duration = duration
        
        # Create notification window
        self.window = tk.Toplevel(parent)
        self.window.withdraw()
        self.window.overrideredirect(True)
        self.window.attributes("-topmost", True)
        
        # Determine notification style based on type
        bg_color = "#333333"
        icon = "ℹ️"
        
        if type_ == "success":
            bg_color = "#4caf50"
            icon = "✅"
        elif type_ == "warning":
            bg_color = "#ff9800"
            icon = "⚠️"
        elif type_ == "error":
            bg_color = "#f44336"
            icon = "❌"
        
        # Create notification content
        frame = tk.Frame(self.window, bg=bg_color, padx=15, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        icon_label = tk.Label(frame, text=icon, bg=bg_color, fg="white", font=("", 16))
        icon_label.pack(side=tk.LEFT, padx=(0, 10))
        
        message_label = tk.Label(frame, text=message, bg=bg_color, fg="white", font=("", 10), wraplength=250)
        message_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        close_btn = tk.Label(frame, text="✕", bg=bg_color, fg="white", cursor="hand2")
        close_btn.pack(side=tk.RIGHT, padx=(10, 0))
        close_btn.bind("<Button-1>", lambda e: self.destroy())
        
        # Position the notification in bottom right
        self.window.update_idletasks()
        width = self.window.winfo_width()
        height = self.window.winfo_height()
        screen_width = self.parent.winfo_screenwidth()
        screen_height = self.parent.winfo_screenheight()
        
        x = screen_width - width - 20
        y = screen_height - height - 40
        
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        
        # Apply rounded corners if possible (Windows and macOS)
        if platform.system() == "Windows":
            try:
                from ctypes import windll
                hwnd = windll.user32.GetParent(self.window.winfo_id())
                style = windll.user32.GetWindowLongW(hwnd, -16)
                style |= 0x00080000  # WS_EX_LAYERED
                windll.user32.SetWindowLongW(hwnd, -16, style)
            except Exception:
                pass
        
        # Show with animation
        self.window.deiconify()
        self.fade_in()
        
        # Schedule auto-close
        self.parent.after(self.duration, self.fade_out)
    
    def fade_in(self, alpha=0.0):
        if alpha < 1.0:
            self.window.attributes("-alpha", alpha)
            self.parent.after(20, self.fade_in, alpha + 0.1)
    
    def fade_out(self, alpha=1.0):
        if alpha > 0.0:
            self.window.attributes("-alpha", alpha)
            self.parent.after(20, self.fade_out, alpha - 0.1)
        else:
            self.destroy()
    
    def destroy(self):
        self.window.destroy()


class CustomSwitch(ttk.Checkbutton):
    """Modern toggle switch widget"""
    
    def __init__(self, master=None, **kwargs):
        # Store original command if provided
        self.original_command = kwargs.pop('command', None)
        
        # Initialize the checkbutton
        super().__init__(master, style="Switch.TCheckbutton", **kwargs)


class HEIFtoJPEGConverterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("HEIF to JPEG Converter")
        self.root.geometry("800x700")
        self.root.minsize(750, 650)
        
        # Set icon (placeholder)
        if platform.system() == "Windows":
            try:
                self.root.iconbitmap("icon.ico")
            except:
                pass
        
        # Initialize variables
        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.quality = tk.IntVar(value=90)
        self.preserve_exif = tk.BooleanVar(value=True)
        self.include_subdirs = tk.BooleanVar(value=False)
        self.preserve_structure = tk.BooleanVar(value=True)
        self.rename_pattern = tk.StringVar(value="{name}")
        self.max_workers = tk.IntVar(value=min(4, os.cpu_count() or 2))
        self.dark_mode = tk.BooleanVar(value=False)
        
        # Converter object for business logic
        self.converter = ImageConverter()
        self.conversion_running = False
        self.file_list = []
        
        # Apply Sun Valley theme
        sv_ttk.set_theme("light")
        self.theme = "light"
        
        # Set up the GUI
        self.create_menu()
        self.setup_styles()
        self.create_widgets()
        
        # Set up keyboard shortcuts
        self.setup_shortcuts()
        
        # Set up drag and drop
        self.setup_drag_drop()
        
        # Bind theme toggle
        self.dark_mode.trace_add("write", self.toggle_theme)

    def setup_styles(self):
        """Configure custom styles for widgets"""
        style = ttk.Style()
        
        # Title label style
        style.configure("Title.TLabel", font=("", 14, "bold"))
        
        # Bold label style
        style.configure("Bold.TLabel", font=("", 10, "bold"))
        
        # Subtitle style
        style.configure("Subtitle.TLabel", font=("", 11))
        
        # Accent button style
        style.configure("Accent.TButton", font=("", 10))
        
        # Card frame style
        style.configure("Card.TFrame", borderwidth=1, relief="solid")
        
        # Image border style
        style.configure("ImageBorder.TFrame", borderwidth=1, relief="solid")
        
        # Tooltip styles
        style.configure("Tooltip.TFrame", background="#333333")
        style.configure("Tooltip.TLabel", background="#333333", foreground="white")
        
        # Custom switch style (placeholder - would be better implemented with custom drawing)
        style.configure("Switch.TCheckbutton", indicatorsize=20)
        
        # Heading style
        style.configure("Heading.TLabel", font=("", 12, "bold"))
        
        # Info panel style
        style.configure("Info.TFrame", borderwidth=1, relief="solid")

    def toggle_theme(self, *args):
        """Toggle between light and dark themes"""
        if self.dark_mode.get():
            sv_ttk.set_theme("dark")
            self.theme = "dark"
        else:
            sv_ttk.set_theme("light")
            self.theme = "light"

    def setup_shortcuts(self):
        """Set up keyboard shortcuts"""
        self.root.bind("<Control-o>", lambda e: self.select_input_folder())
        self.root.bind("<Control-s>", lambda e: self.select_output_folder())
        self.root.bind("<Control-r>", lambda e: self.refresh_file_list())
        self.root.bind("<F5>", lambda e: self.refresh_file_list())
        self.root.bind("<Control-c>", lambda e: self.start_conversion())
        self.root.bind("<Escape>", lambda e: self.cancel_conversion())

    def setup_drag_drop(self):
        """Set up drag and drop functionality"""
        # Create drop target for the tree view
        # This is a placeholder that would be implemented if drag-and-drop libraries are available
        FileDropTarget(self.tree, self.process_dropped_files)
    
    def process_dropped_files(self, files):
        """Process files dropped onto the application"""
        self.process_selected_files(files)

    def create_menu(self):
        """Create application menu"""
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)
        
        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Select Input Folder", command=self.select_input_folder, 
                             accelerator="Ctrl+O", compound=tk.LEFT)
        file_menu.add_command(label="Select Output Folder", command=self.select_output_folder, 
                             accelerator="Ctrl+S", compound=tk.LEFT)
        file_menu.add_separator()
        file_menu.add_command(label="Select Individual Files", command=self.select_individual_files,
                             compound=tk.LEFT)
        file_menu.add_separator()
        file_menu.add_command(label="Save Settings", command=self.save_settings,
                             compound=tk.LEFT)
        file_menu.add_command(label="Load Settings", command=self.load_settings,
                             compound=tk.LEFT)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.destroy,
                             compound=tk.LEFT)
        
        # Conversion menu
        convert_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Conversion", menu=convert_menu)
        convert_menu.add_command(label="Start Conversion", command=self.start_conversion, 
                                accelerator="Ctrl+C", compound=tk.LEFT)
        convert_menu.add_command(label="Cancel Conversion", command=self.cancel_conversion, 
                                accelerator="Esc", compound=tk.LEFT)
        convert_menu.add_separator()
        convert_menu.add_command(label="Refresh File List", command=self.refresh_file_list, 
                                accelerator="F5", compound=tk.LEFT)
        
        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_checkbutton(label="Dark Mode", variable=self.dark_mode, 
                                 compound=tk.LEFT)
        
        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="Tutorial", command=self.show_tutorial,
                             compound=tk.LEFT)
        help_menu.add_command(label="Keyboard Shortcuts", command=self.show_shortcuts,
                             compound=tk.LEFT)
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self.show_about,
                             compound=tk.LEFT)

    def create_widgets(self):
        """Create and arrange all widgets in the UI"""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Create header with app title and actions
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(header_frame, text="HEIF to JPEG Converter", style="Title.TLabel").pack(side=tk.LEFT)
        
        # Create a notebook for tabbed interface
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Main tab
        main_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(main_tab, text="Conversion")
        
        # Options tab
        options_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(options_tab, text="Advanced Options")
        
        # Log tab
        log_tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(log_tab, text="Log")
        
        # ---- Main Tab Content ----
        # Folders card
        folder_card = ttk.Frame(main_tab, style="Card.TFrame", padding=15)
        folder_card.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(folder_card, text="Folders", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        # Input folder row
        input_frame = ttk.Frame(folder_card)
        input_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(input_frame, text="Input Folder:").pack(side=tk.LEFT)
        input_entry = ttk.Entry(input_frame, textvariable=self.input_dir)
        input_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        browse_btn = ttk.Button(input_frame, text="Browse...", command=self.select_input_folder)
        browse_btn.pack(side=tk.LEFT)
        
        # Add tooltip
        ModernTooltip(browse_btn, "Select a folder containing HEIF/HEIC images")
        
        # Output folder row
        output_frame = ttk.Frame(folder_card)
        output_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(output_frame, text="Output Folder:").pack(side=tk.LEFT)
        output_entry = ttk.Entry(output_frame, textvariable=self.output_dir)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        browse_output_btn = ttk.Button(output_frame, text="Browse...", command=self.select_output_folder)
        browse_output_btn.pack(side=tk.LEFT)
        
        # Add tooltip
        ModernTooltip(browse_output_btn, "Select where to save the converted JPEG images")
        
        # Quality card
        quality_card = ttk.Frame(main_tab, style="Card.TFrame", padding=15)
        quality_card.pack(fill=tk.X, pady=(0, 15))
        
        quality_header = ttk.Frame(quality_card)
        quality_header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(quality_header, text="JPEG Quality", style="Heading.TLabel").pack(side=tk.LEFT)
        self.quality_label = ttk.Label(quality_header, text=f"{self.quality.get()}%")
        self.quality_label.pack(side=tk.RIGHT)
        
        # Quality slider with markers
        quality_slider_frame = ttk.Frame(quality_card)
        quality_slider_frame.pack(fill=tk.X)
        
        ttk.Label(quality_slider_frame, text="Low").pack(side=tk.LEFT)
        
        quality_slider = ttk.Scale(
            quality_slider_frame, 
            from_=1, 
            to=100, 
            orient=tk.HORIZONTAL,
            variable=self.quality,
            command=self.update_quality_label
        )
        quality_slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)
        
        ttk.Label(quality_slider_frame, text="High").pack(side=tk.RIGHT)
        
        # File list card
        file_card = ttk.Frame(main_tab, style="Card.TFrame", padding=15)
        file_card.pack(fill=tk.BOTH, expand=True)
        
        file_header = ttk.Frame(file_card)
        file_header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(file_header, text="HEIF Files", style="Heading.TLabel").pack(side=tk.LEFT)
        
        # File toolbar
        file_toolbar = ttk.Frame(file_card)
        file_toolbar.pack(fill=tk.X, pady=(0, 10))
        
        refresh_btn = ttk.Button(file_toolbar, text="Refresh", command=self.refresh_file_list)
        refresh_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        add_files_btn = ttk.Button(file_toolbar, text="Add Files", command=self.select_individual_files)
        add_files_btn.pack(side=tk.LEFT, padx=5)
        
        preview_btn = ttk.Button(file_toolbar, text="Preview", command=self.preview_selected)
        preview_btn.pack(side=tk.LEFT, padx=5)
        
        remove_btn = ttk.Button(file_toolbar, text="Remove", command=self.remove_selected)
        remove_btn.pack(side=tk.LEFT, padx=5)
        
        # Add tooltips
        ModernTooltip(refresh_btn, "Refresh the file list from the input folder")
        ModernTooltip(add_files_btn, "Add individual files to the list")
        ModernTooltip(preview_btn, "Preview the selected image")
        ModernTooltip(remove_btn, "Remove selected files from the list")
        
        # File list with scrollbar
        file_list_frame = ttk.Frame(file_card)
        file_list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("filename", "size", "path")
        self.tree = ttk.Treeview(file_list_frame, columns=columns, show="headings", selectmode="extended")
        
        # Add column headings
        self.tree.heading("filename", text="Filename")
        self.tree.heading("size", text="Size")
        self.tree.heading("path", text="Path")
        
        # Configure column widths
        self.tree.column("filename", width=150, anchor=tk.W)
        self.tree.column("size", width=100, anchor=tk.E)
        self.tree.column("path", width=300, anchor=tk.W)
        
        # Scrollbars
        vsb = ttk.Scrollbar(file_list_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(file_list_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        # Layout scrollbars
        self.tree.grid(column=0, row=0, sticky=tk.NSEW)
        vsb.grid(column=1, row=0, sticky=tk.NS)
        hsb.grid(column=0, row=1, sticky=tk.EW)
        
        file_list_frame.columnconfigure(0, weight=1)
        file_list_frame.rowconfigure(0, weight=1)
        
        # Status and progress frame
        status_frame = ttk.Frame(main_tab)
        status_frame.pack(fill=tk.X, pady=(15, 0))
        
        self.status_var = tk.StringVar(value="Ready")
        status_label = ttk.Label(status_frame, textvariable=self.status_var)
        status_label.pack(side=tk.LEFT)
        
        # Progress bar
        self.progress = ttk.Progressbar(main_tab, mode="determinate")
        self.progress.pack(fill=tk.X, pady=(5, 10))
        
        # Convert button
        self.convert_btn = ttk.Button(
            main_tab, 
            text="Convert Images", 
            command=self.start_conversion, 
            style="Accent.TButton"
        )
        self.convert_btn.pack(pady=(0, 1), fill=tk.X)
        
        # ---- Options Tab Content ----
        options_frame = ttk.Frame(options_tab)
        options_frame.pack(fill=tk.BOTH, expand=True)
        
        # Options in a grid layout
        left_column = ttk.Frame(options_frame)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        
        right_column = ttk.Frame(options_frame)
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        
        # Left column cards
        # EXIF Options card
        exif_card = ttk.Frame(left_column, style="Card.TFrame", padding=15)
        exif_card.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(exif_card, text="EXIF Options", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        exif_switch = CustomSwitch(exif_card, text="Preserve EXIF metadata", variable=self.preserve_exif)
        exif_switch.pack(anchor=tk.W, pady=5)
        
        ttk.Label(exif_card, text="Keep original photo metadata like date, camera settings, and location.",
                 wraplength=300).pack(anchor=tk.W, pady=(0, 5))
        
        # Directory Options card
        dir_card = ttk.Frame(left_column, style="Card.TFrame", padding=15)
        dir_card.pack(fill=tk.X)
        
        ttk.Label(dir_card, text="Directory Options", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        subdir_switch = CustomSwitch(dir_card, text="Include subdirectories", variable=self.include_subdirs)
        subdir_switch.pack(anchor=tk.W, pady=5)
        
        structure_switch = CustomSwitch(dir_card, text="Preserve folder structure", variable=self.preserve_structure)
        structure_switch.pack(anchor=tk.W, pady=5)
        
        ttk.Label(dir_card, text="Maintain the same folder hierarchy in the output location.",
                 wraplength=300).pack(anchor=tk.W, pady=(0, 5))
        
        # Right column cards
        # Rename Options card
        rename_card = ttk.Frame(right_column, style="Card.TFrame", padding=15)
        rename_card.pack(fill=tk.X, pady=(0, 15))
        
        ttk.Label(rename_card, text="Rename Options", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        ttk.Label(rename_card, text="Rename Pattern:").pack(anchor=tk.W, pady=(5, 5))
        ttk.Entry(rename_card, textvariable=self.rename_pattern).pack(fill=tk.X, pady=(0, 10))
        
        pattern_info = ttk.Frame(rename_card, style="Info.TFrame", padding=10)
        pattern_info.pack(fill=tk.X)
        
        ttk.Label(pattern_info, text="Available variables:", style="Bold.TLabel").pack(anchor=tk.W)
        ttk.Label(pattern_info, text="{name} - Original filename\n{timestamp} - Current date/time\n{counter} - Sequential number").pack(anchor=tk.W, pady=(5, 0))
        
        # Performance Options card
        perf_card = ttk.Frame(right_column, style="Card.TFrame", padding=15)
        perf_card.pack(fill=tk.X)
        
        ttk.Label(perf_card, text="Performance", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        workers_frame = ttk.Frame(perf_card)
        workers_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(workers_frame, text="Parallel Workers:").pack(side=tk.LEFT)
        ttk.Spinbox(
            workers_frame, 
            from_=1, 
            to=max(16, os.cpu_count() or 2), 
            textvariable=self.max_workers, 
            width=5
        ).pack(side=tk.LEFT, padx=10)
        
        ttk.Label(perf_card, text=f"More workers can speed up conversion but may use more system resources. Recommended: {min(4, os.cpu_count() or 2)} for your system.",
                 wraplength=300).pack(anchor=tk.W, pady=(5, 0))
        
        # ---- Log Tab Content ----
        log_frame = ttk.Frame(log_tab, padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True)
        
        # Log header
        log_header = ttk.Frame(log_frame)
        log_header.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(log_header, text="Conversion Log", style="Heading.TLabel").pack(side=tk.LEFT)
        ttk.Button(log_header, text="Clear Log", command=self.clear_log).pack(side=tk.RIGHT)
        
        # Log text area with scrollbar
        log_container = ttk.Frame(log_frame, style="Card.TFrame")
        log_container.pack(fill=tk.BOTH, expand=True)
        
        self.log_text = tk.Text(log_container, height=15, width=70, wrap=tk.WORD, padx=10, pady=10)
        log_scrollbar = ttk.Scrollbar(log_container, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)
        
        self.log_text.grid(row=0, column=0, sticky=tk.NSEW)
        log_scrollbar.grid(row=0, column=1, sticky=tk.NS)
        
        log_container.columnconfigure(0, weight=1)
        log_container.rowconfigure(0, weight=1)
        
        # Custom logging handler to update log text widget
        class TextHandler(logging.Handler):
            def __init__(self, text_widget):
                logging.Handler.__init__(self)
                self.text_widget = text_widget
            
            def emit(self, record):
                msg = self.format(record) + '\n'
                
                def append():
                    self.text_widget.configure(state='normal')
                    
                    # Color-code based on level
                    if record.levelno >= logging.ERROR:
                        self.text_widget.insert(tk.END, msg, "error")
                    elif record.levelno >= logging.WARNING:
                        self.text_widget.insert(tk.END, msg, "warning")
                    elif record.levelno >= logging.INFO:
                        self.text_widget.insert(tk.END, msg, "info")
                    else:
                        self.text_widget.insert(tk.END, msg)
                    
                    self.text_widget.see(tk.END)
                    self.text_widget.configure(state='disabled')
                
                # Schedule append to be called from the main thread
                self.text_widget.after(0, append)
        
        # Configure log text tags for colorized output
        self.log_text.tag_configure("error", foreground="#d9534f")
        self.log_text.tag_configure("warning", foreground="#f0ad4e")
        self.log_text.tag_configure("info", foreground="#5bc0de")
        
        # Add TextHandler to the logger
        text_handler = TextHandler(self.log_text)
        text_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(text_handler)
        
        # Initial state - read-only
        self.log_text.configure(state='disabled')

    def update_quality_label(self, *args):
        """Update quality label when slider moves"""
        self.quality_label.config(text=f"{self.quality.get()}%")

    def clear_log(self):
        """Clear the log text area"""
        self.log_text.config(state='normal')
        self.log_text.delete(1.0, tk.END)
        self.log_text.config(state='disabled')
        logger.info("Log cleared")

    def select_input_folder(self):
        """Open dialog to select input folder"""
        folder = filedialog.askdirectory(title="Select Input Folder")
        if folder:
            self.input_dir.set(folder)
            logger.info(f"Input folder set to: {folder}")
            
            # If output dir is not set, set it to same as input
            if not self.output_dir.get():
                self.output_dir.set(folder)
            
            # Auto-refresh file list
            self.refresh_file_list()

    def select_output_folder(self):
        """Open dialog to select output folder"""
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_dir.set(folder)
            logger.info(f"Output folder set to: {folder}")

    def select_individual_files(self):
        """Open dialog to select individual HEIF files"""
        files = filedialog.askopenfilenames(
            title="Select HEIF Files",
            filetypes=[("HEIF Files", "*.heif *.heic *.hif *.HEIF *.HEIC *.HIF")]
        )
        if files:
            self.process_selected_files(files)

    def process_selected_files(self, files):
        """Add selected files to the list"""
        added = 0
        for file_path in files:
            # Check if file is already in the list
            if file_path not in self.file_list:
                self.file_list.append(file_path)
                
                # Get file info
                file_size = os.path.getsize(file_path)
                size_str = self.format_file_size(file_size)
                
                # Add to treeview
                self.tree.insert("", tk.END, values=(
                    os.path.basename(file_path),
                    size_str,
                    os.path.dirname(file_path)
                ))
                added += 1
        
        if added > 0:
            self.status_var.set(f"Added {added} file(s). Total: {len(self.file_list)} files.")
            logger.info(f"Added {added} files to the conversion list")
            
            # Show notification
            CustomNotification(self.root, f"Added {added} files to the list", "info")

    def refresh_file_list(self):
        """Refresh the file list based on input directory"""
        input_dir = self.input_dir.get()
        if not input_dir or not os.path.isdir(input_dir):
            messagebox.showerror("Error", "Please select a valid input folder!")
            return
        
        # Clear current list
        self.tree.delete(*self.tree.get_children())
        self.file_list = []
        
        # Find all HEIF files
        heif_files = self.converter.find_heif_files(input_dir, self.include_subdirs.get())
        
        if not heif_files:
            self.status_var.set("No HEIF files found in the selected folder!")
            CustomNotification(self.root, "No HEIF files found in the selected folder!", "warning")
            return
        
        # Add files to the list
        for file_path in heif_files:
            self.file_list.append(file_path)
            
            # Get file info
            file_size = os.path.getsize(file_path)
            size_str = self.format_file_size(file_size)
            
            # Add to treeview
            self.tree.insert("", tk.END, values=(
                os.path.basename(file_path),
                size_str,
                os.path.dirname(file_path)
            ))
        
        self.status_var.set(f"Found {len(heif_files)} HEIF files")
        logger.info(f"Found {len(heif_files)} HEIF files in {input_dir}")
        
        # Show notification
        CustomNotification(self.root, f"Found {len(heif_files)} HEIF files", "info")

    def format_file_size(self, size_bytes):
        """Format file size in human-readable format"""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes/1024:.1f} KB"
        elif size_bytes < 1024 * 1024 * 1024:
            return f"{size_bytes/(1024*1024):.1f} MB"
        else:
            return f"{size_bytes/(1024*1024*1024):.1f} GB"

    def preview_selected(self):
        """Preview the selected image"""
        selected_items = self.tree.selection()
        if not selected_items:
            CustomNotification(self.root, "Please select an image to preview", "warning")
            return
        
        # Get file path from the first selected item
        item = selected_items[0]
        values = self.tree.item(item, "values")
        filename = values[0]
        path = values[2]
        file_path = os.path.join(path, filename)
        
        # Open preview window
        PreviewWindow(self.root, file_path, self.theme)

    def remove_selected(self):
        """Remove selected files from the list"""
        selected_items = self.tree.selection()
        if not selected_items:
            return
        
        # Remove from tree and file list
        for item in selected_items:
            values = self.tree.item(item, "values")
            filename = values[0]
            path = values[2]
            file_path = os.path.join(path, filename)
            
            if file_path in self.file_list:
                self.file_list.remove(file_path)
            
            self.tree.delete(item)
        
        self.status_var.set(f"Removed {len(selected_items)} file(s). Total: {len(self.file_list)} files.")
        
        # Show notification for multiple files
        if len(selected_items) > 1:
            CustomNotification(self.root, f"Removed {len(selected_items)} files", "info")

    def start_conversion(self):
        """Start the conversion process"""
        if self.conversion_running:
            CustomNotification(self.root, "Conversion is already running!", "warning")
            return
            
        if not self.file_list:
            CustomNotification(self.root, "No files to convert!", "error")
            return
            
        output_dir = self.output_dir.get()
        if not output_dir:
            # Use input directory if output is not specified
            output_dir = self.input_dir.get()
            self.output_dir.set(output_dir)
            
        if not os.path.exists(output_dir):
            try:
                os.makedirs(output_dir)
                logger.info(f"Created output directory: {output_dir}")
            except Exception as e:
                CustomNotification(self.root, f"Failed to create output directory", "error")
                logger.error(f"Failed to create output directory: {e}")
                return
                
        # Update UI state
        self.conversion_running = True
        self.convert_btn.config(state="disabled", text="Converting...")
        self.progress["maximum"] = len(self.file_list)
        self.progress["value"] = 0
        self.converter.stop_requested = False
        
        # Start conversion thread
        threading.Thread(target=self.conversion_thread, daemon=True).start()
        logger.info(f"Starting conversion of {len(self.file_list)} files")
        
        # Show notification
        CustomNotification(self.root, f"Starting conversion of {len(self.file_list)} files", "info")

    def conversion_thread(self):
        """Thread function for conversion process"""
        try:
            total_files = len(self.file_list)
            success_count = 0
            error_count = 0
            
            # Create a thread pool for parallel processing
            with ThreadPoolExecutor(max_workers=self.max_workers.get()) as executor:
                # Submit all conversion tasks
                future_to_file = {
                    executor.submit(
                        self.converter.convert_image,
                        file_path,
                        self.output_dir.get(),
                        self.quality.get(),
                        self.preserve_structure.get(),
                        self.preserve_exif.get(),
                        self.rename_pattern.get() if self.rename_pattern.get() != "{name}" else None
                    ): file_path for file_path in self.file_list
                }
                
                # Process results as they complete
                for i, future in enumerate(future_to_file):
                    if self.converter.stop_requested:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break
                        
                    file_path = future_to_file[future]
                    filename = os.path.basename(file_path)
                    
                    try:
                        success, result = future.result()
                        
                        if success:
                            success_count += 1
                            logger.info(f"Converted {filename} -> {os.path.basename(result) if isinstance(result, str) else 'JPEG'}")
                        else:
                            error_count += 1
                            logger.error(f"Failed to convert {filename}: {result}")
                            
                    except Exception as e:
                        error_count += 1
                        logger.error(f"Error processing {filename}: {e}")
                        
                    # Update progress
                    self.root.after(10, self.update_progress, i + 1, total_files, filename)
                    
            # Final update on the main thread
            self.root.after(10, self.conversion_complete, total_files, success_count, error_count)
                
        except Exception as e:
            logger.error(f"Conversion process error: {e}")
            # Update UI on the main thread
            self.root.after(0, self.conversion_error, str(e))

    def update_progress(self, current, total, current_file):
        """Update progress bar and status (called from main thread)"""
        self.progress["value"] = current
        percent = int((current / total) * 100) if total > 0 else 0
        self.status_var.set(f"Converting {current}/{total}: {current_file} ({percent}%)")

    def conversion_complete(self, total, success, errors):
        """Handle conversion completion (called from main thread)"""
        self.conversion_running = False
        self.convert_btn.config(state="normal", text="Convert Images")
        
        if self.converter.stop_requested:
            self.status_var.set(f"Conversion cancelled. Completed {success} out of {total} files.")
            CustomNotification(self.root, f"Conversion cancelled. Completed {success} out of {total} files.", "warning")
        else:
            self.status_var.set(f"Conversion complete! {success} files converted, {errors} errors.")
            
            # Show appropriate notification
            if errors == 0:
                CustomNotification(self.root, f"All {success} files converted successfully!", "success")
            else:
                CustomNotification(self.root, f"Conversion complete with {errors} errors. See log for details.", "warning")
            
        logger.info(f"Conversion finished. Total: {total}, Success: {success}, Errors: {errors}")

    def conversion_error(self, error_message):
        """Handle conversion error (called from main thread)"""
        self.conversion_running = False
        self.convert_btn.config(state="normal", text="Convert Images")
        self.status_var.set(f"Conversion failed: {error_message}")
        CustomNotification(self.root, f"Conversion failed. See log for details.", "error")

    def cancel_conversion(self):
        """Cancel ongoing conversion"""
        if not self.conversion_running:
            return
            
        self.converter.stop_requested = True
        self.status_var.set("Cancelling conversion...")
        CustomNotification(self.root, "Cancelling conversion...", "warning")
        logger.info("User requested to cancel conversion")

    def save_settings(self):
        """Save current settings to a file"""
        file_path = filedialog.asksaveasfilename(
            title="Save Settings",
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            import json
            settings = {
                "input_dir": self.input_dir.get(),
                "output_dir": self.output_dir.get(),
                "quality": self.quality.get(),
                "preserve_exif": self.preserve_exif.get(),
                "include_subdirs": self.include_subdirs.get(),
                "preserve_structure": self.preserve_structure.get(),
                "rename_pattern": self.rename_pattern.get(),
                "max_workers": self.max_workers.get(),
                "dark_mode": self.dark_mode.get()
            }
            
            with open(file_path, 'w') as f:
                json.dump(settings, f, indent=4)
                
            logger.info(f"Settings saved to {file_path}")
            CustomNotification(self.root, "Settings saved successfully", "success")
            
        except Exception as e:
            logger.error(f"Error saving settings: {e}")
            CustomNotification(self.root, f"Failed to save settings", "error")

    def load_settings(self):
        """Load settings from a file"""
        file_path = filedialog.askopenfilename(
            title="Load Settings",
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if not file_path:
            return
            
        try:
            import json
            with open(file_path, 'r') as f:
                settings = json.load(f)
                
            # Apply settings
            if "input_dir" in settings:
                self.input_dir.set(settings["input_dir"])
            if "output_dir" in settings:
                self.output_dir.set(settings["output_dir"])
            if "quality" in settings:
                self.quality.set(settings["quality"])
            if "preserve_exif" in settings:
                self.preserve_exif.set(settings["preserve_exif"])
            if "include_subdirs" in settings:
                self.include_subdirs.set(settings["include_subdirs"])
            if "preserve_structure" in settings:
                self.preserve_structure.set(settings["preserve_structure"])
            if "rename_pattern" in settings:
                self.rename_pattern.set(settings["rename_pattern"])
            if "max_workers" in settings:
                self.max_workers.set(settings["max_workers"])
            if "dark_mode" in settings:
                self.dark_mode.set(settings["dark_mode"])
                
            logger.info(f"Settings loaded from {file_path}")
            CustomNotification(self.root, "Settings loaded successfully", "success")
            
            # Refresh file list if input directory is valid
            if os.path.isdir(self.input_dir.get()):
                self.refresh_file_list()
                
        except Exception as e:
            logger.error(f"Error loading settings: {e}")
            CustomNotification(self.root, f"Failed to load settings", "error")

    def show_about(self):
        """Show about dialog"""
        about_window = tk.Toplevel(self.root)
        about_window.title("About HEIF Converter")
        about_window.geometry("450x350")
        about_window.resizable(False, False)
        
        # Center on parent
        about_window.transient(self.root)
        about_window.grab_set()
        
        # Content
        frame = ttk.Frame(about_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # App icon (placeholder)
        app_icon_label = ttk.Label(frame, text="🖼️", font=("", 48))
        app_icon_label.pack(pady=(10, 0))
        
        ttk.Label(frame, text="HEIF to JPEG Converter", style="Title.TLabel").pack(pady=5)
        ttk.Label(frame, text="Version 2.0").pack()
        
        # Description
        desc_frame = ttk.Frame(frame, style="Card.TFrame", padding=15)
        desc_frame.pack(fill=tk.X, pady=15)
        
        ttk.Label(desc_frame, text="A professional tool to convert HEIF/HEIC images to JPEG format with advanced options for quality control and metadata preservation.", 
                 wraplength=380, justify=tk.CENTER).pack()
        
        # Technologies
        tech_frame = ttk.Frame(frame)
        tech_frame.pack(fill=tk.X)
        
        ttk.Label(tech_frame, text="Technologies:", style="Bold.TLabel").pack(anchor=tk.W)
        ttk.Label(tech_frame, text="• Pillow for image processing\n• pillow_heif for HEIF support\n• Python tkinter for the interface").pack(anchor=tk.W, padx=15)
        
        # Close button with accent style
        ttk.Button(frame, text="Close", command=about_window.destroy, style="Accent.TButton").pack(pady=15)

    def show_shortcuts(self):
        """Show keyboard shortcuts dialog"""
        shortcuts_window = tk.Toplevel(self.root)
        shortcuts_window.title("Keyboard Shortcuts")
        shortcuts_window.geometry("400x350")
        shortcuts_window.resizable(False, False)
        
        # Center on parent
        shortcuts_window.transient(self.root)
        shortcuts_window.grab_set()
        
        # Content
        frame = ttk.Frame(shortcuts_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="Keyboard Shortcuts", style="Title.TLabel").pack(pady=10)
        
        # Shortcuts in a card
        shortcuts_card = ttk.Frame(frame, style="Card.TFrame", padding=15)
        shortcuts_card.pack(fill=tk.BOTH, expand=True)
        
        # Create a two-column grid for shortcuts
        grid = ttk.Frame(shortcuts_card)
        grid.pack(fill=tk.BOTH, expand=True)
        
        # Row 1
        ttk.Label(grid, text="Ctrl+O", style="Bold.TLabel").grid(row=0, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Select input folder").grid(row=0, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Row 2
        ttk.Label(grid, text="Ctrl+S", style="Bold.TLabel").grid(row=1, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Select output folder").grid(row=1, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Row 3
        ttk.Label(grid, text="F5", style="Bold.TLabel").grid(row=2, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Refresh file list").grid(row=2, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Row 4
        ttk.Label(grid, text="Ctrl+C", style="Bold.TLabel").grid(row=3, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Start conversion").grid(row=3, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Row 5
        ttk.Label(grid, text="Esc", style="Bold.TLabel").grid(row=4, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Cancel conversion").grid(row=4, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Row 6
        ttk.Label(grid, text="Delete", style="Bold.TLabel").grid(row=5, column=0, sticky=tk.W, padx=10, pady=5)
        ttk.Label(grid, text="Remove selected files").grid(row=5, column=1, sticky=tk.W, padx=10, pady=5)
        
        # Close button
        ttk.Button(frame, text="Close", command=shortcuts_window.destroy, style="Accent.TButton").pack(pady=15)

    def show_tutorial(self):
        """Show tutorial dialog"""
        tutorial_window = tk.Toplevel(self.root)
        tutorial_window.title("HEIF Converter Tutorial")
        tutorial_window.geometry("600x500")
        
        # Center on parent
        tutorial_window.transient(self.root)
        tutorial_window.grab_set()
        
        # Content with tabs
        frame = ttk.Frame(tutorial_window, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)
        
        ttk.Label(frame, text="HEIF Converter Tutorial", style="Title.TLabel").pack(pady=5)
        
        # Create notebook for tutorial sections
        tutorial_notebook = ttk.Notebook(frame)
        tutorial_notebook.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Getting Started tab
        getting_started = ttk.Frame(tutorial_notebook, padding=15)
        tutorial_notebook.add(getting_started, text="Getting Started")
        
        ttk.Label(getting_started, text="Basic Usage", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        steps_text = """
1. Select an input folder containing HEIF files using the "Browse..." button.

2. Choose an output folder where JPEGs will be saved (optional - defaults to input folder).

3. Adjust the JPEG quality slider (higher quality = larger files).

4. Click "Convert Images" to start the conversion process.

The application will scan for HEIF files and convert them to JPEGs with the selected quality setting.
"""
        ttk.Label(getting_started, text=steps_text, justify=tk.LEFT, wraplength=530).pack(fill=tk.X)
        
        # Advanced Options tab
        advanced_tab = ttk.Frame(tutorial_notebook, padding=15)
        tutorial_notebook.add(advanced_tab, text="Advanced Options")
        
        ttk.Label(advanced_tab, text="Advanced Features", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        advanced_text = """
EXIF Options:
• Preserve EXIF metadata - Keep original photo information such as camera settings, date and GPS data.

Directory Options:
• Include subdirectories - Search for HEIF files in all folders inside the input folder.
• Preserve folder structure - Maintain the same folder organization in the output location.

Renaming Options:
• Rename Pattern - Customize filenames using variables like {name}, {timestamp}, and {counter}.

Performance:
• Parallel Workers - Control how many files are processed simultaneously. More workers = faster conversion but higher system resource usage.
"""
        ttk.Label(advanced_tab, text=advanced_text, justify=tk.LEFT, wraplength=530).pack(fill=tk.X)
        
        # Tips tab
        tips_tab = ttk.Frame(tutorial_notebook, padding=15)
        tutorial_notebook.add(tips_tab, text="Tips")
        
        ttk.Label(tips_tab, text="Pro Tips", style="Heading.TLabel").pack(anchor=tk.W, pady=(0, 10))
        
        tips_text = """
• Use the Preview button to check images before conversion.

• Higher quality settings (90-100) are best for photos you want to preserve with maximum detail.

• Medium quality (70-85) works well for most general-purpose photos while saving space.

• Lower quality (below 70) is suitable for temporary use or where file size is critical.

• Save your common settings for quick reuse with different folders.

• For large batches, adjust worker count based on your CPU and available memory.

• You can drag and drop files directly into the file list area.

• Use the right-click menu on files for additional options.
"""
        ttk.Label(tips_tab, text=tips_text, justify=tk.LEFT, wraplength=530).pack(fill=tk.X)
        
        # Close button
        ttk.Button(frame, text="Close", command=tutorial_window.destroy, style="Accent.TButton").pack(pady=10)


def main():
    # Create the main window
    root = tk.Tk()
    
    # Set theme first
    try:
        import sv_ttk
        sv_ttk.set_theme("light")
    except ImportError:
        logger.warning("Sun Valley theme not available. Using default theme.")
    
    # Create app
    app = HEIFtoJPEGConverterApp(root)
    
    # Set window icon (if available)
    if platform.system() == "Windows":
        try:
            root.iconbitmap("icon.ico")
        except:
            pass
            
    # Start app
    root.mainloop()


if __name__ == "__main__":
    main()