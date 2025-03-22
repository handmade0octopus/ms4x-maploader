import sys
import xml.etree.ElementTree as ET
import numpy as np
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QListWidget, QListWidgetItem, QLabel, QVBoxLayout, QHBoxLayout, QWidget, QFileDialog,
    QCheckBox, QLineEdit, QSplitter, QSlider, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy, QPushButton,
    QComboBox
)
from PyQt5.QtGui import QImage, QPixmap, QColor, QCursor, QIcon
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
import os

# Dark theme stylesheet
DARK_STYLESHEET = """
QWidget {
    background-color: #2D2D30;
    color: #FFFFFF;
}
QMainWindow, QDialog {
    background-color: #1E1E1E;
}
QTableWidget {
    background-color: #252526;
    color: #FFFFFF;
    gridline-color: #3F3F46;
    border: 1px solid #3F3F46;
}
QTableWidget::item {
    background-color: #252526;
}
QTableWidget::item:selected {
    background-color: #3F3F70;
}
QHeaderView::section {
    background-color: #2D2D30;
    color: #FFFFFF;
    border: 1px solid #3F3F46;
}
QPushButton {
    background-color: #3B3B3D;
    color: #FFFFFF;
    border: 1px solid #555555;
    padding: 5px;
    border-radius: 3px;
}
QPushButton:hover {
    background-color: #45454A;
}
QPushButton:pressed {
    background-color: #555555;
}
QLineEdit, QComboBox {
    background-color: #2A2A2A;
    color: #FFFFFF;
    border: 1px solid #3F3F46;
    padding: 2px;
}
QCheckBox {
    color: #FFFFFF;
}
QCheckBox::indicator {
    border: 1px solid #555555;
    background-color: #2A2A2A;
    width: 13px;
    height: 13px;
}
QCheckBox::indicator:checked {
    background-color: #3F3F70;
}
QSlider::groove:horizontal {
    background: #3F3F46;
    height: 8px;
    border-radius: 4px;
}
QSlider::handle:horizontal {
    background: #007ACC;
    width: 18px;
    margin-top: -5px;
    margin-bottom: -5px;
    border-radius: 9px;
}
QSlider::sub-page:horizontal {
    background: #007ACC;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: #3F3F46;
}
QLabel {
    color: #FFFFFF;
}
"""

# Color definitions
# Map visualization colors (RGB format)
COLOR_COMMON_MAP                    = [96, 96, 96]  # Light gray for common maps
COLOR_FILE_A_ONLY                   = [96, 0, 0]     # Dark red for File A only
COLOR_FILE_B_ONLY                   = [128, 0, 0]   # Dark orange for File B only
COLOR_HIGHLIGHT_DIFFERENT_ADDRESS_A = [96, 96, 0]  # Yellow for mismatched maps
COLOR_HIGHLIGHT_DIFFERENT_ADDRESS_B = [128, 128, 0]  # Yellow for mismatched maps
COLOR_BACKGROUND                    = [25, 25, 25]     # Dark gray for background
COLOR_HIGHLIGHT_MATCH               = [0, 255, 0]  # Green for matched maps (when hovered)

COLOR_HIGHLIGHT_MISMATCH            = [255, 0, 0]  # Red for mismatched maps (when hovered)
COLOR_HIGHLIGHT_HOVERED             = [0, 255, 255]  # Cyan for yellow category maps (when hovered)
COLOR_HIGHLIGHT_COUNTERPART         = [255, 0, 255]  # Magenta for counterpart maps
COLOR_CHECKED_MAP                   = [150, 150, 255]  # Light blue for checked maps

# Visualization dimensions - now used for aspect ratio reference
VISUALIZATION_WIDTH = 1024
VISUALIZATION_HEIGHT = 512

# List text colors (Qt colors)
COLOR_TEXT_MATCH = QColor('green')    # For maps that match exactly
COLOR_TEXT_PARTIAL = QColor(255, 150, 0) # For maps that exist in both files but with different addresses
COLOR_TEXT_UNIQUE = QColor('red')     # For maps that exist in only one file


# Convert NumPy array to QImage
def numpy_to_qimage(image):
    h, w, c = image.shape
    bytes_per_line = c * w
    return QImage(image.data, w, h, bytes_per_line, QImage.Format_RGB888)

# Custom QTableWidget for mouse leave events
class CustomTableWidget(QTableWidget):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setMouseTracking(True)
        self.ctrl_pressed = False  # Track Ctrl key state
        
    def leaveEvent(self, event):
        self.main_window.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.main_window.base_image)))
        super().leaveEvent(event)
        
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = True
        super().keyPressEvent(event)
        
    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key_Control:
            self.ctrl_pressed = False
        super().keyReleaseEvent(event)
        
    def mouseReleaseEvent(self, event):
        # Process normal click event first (this will toggle the checkbox if one was clicked)
        super().mousePressEvent(event)
        
        # Identify which item was clicked before passing the event to parent
        clicked_item = self.itemAt(event.pos())
        clicked_row = -1
        is_checkbox_column = False
        
        if clicked_item:
            clicked_row = clicked_item.row()
            is_checkbox_column  = self.columnAt(event.pos().x()) == 0  # Check if click was in checkbox column
        
        # After normal processing, handle Ctrl+click for multiple rows if it was a checkbox click
        if self.ctrl_pressed and event.button() == Qt.LeftButton and clicked_row >= 0 and (is_checkbox_column):
            # Get the current state of the checkbox after it was toggled by the normal click
            checkbox_item = self.item(clicked_row, 0)
            if checkbox_item:
                # Now apply this state to all other selected rows
                self.main_window.toggle_checkboxes_in_selected_rows(clicked_row)
        

# Custom QTableWidgetItem for proper numeric sorting
class NumericTableWidgetItem(QTableWidgetItem):
    def __init__(self, value=0, text=''):
        super().__init__(text)
        self.sort_value = value
        
    def __lt__(self, other):
        if isinstance(other, NumericTableWidgetItem):
            return self.sort_value < other.sort_value
        return super().__lt__(other)

# Custom QLabel for handling mouse events
class InteractiveMapLabel(QLabel):
    """Custom QLabel that handles mouse events for the map visualization"""
    map_hovered = pyqtSignal(int, int)  # x, y position
    map_clicked = pyqtSignal(int, int)  # x, y position
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)  # Enable mouse tracking
        self.setCursor(QCursor(Qt.PointingHandCursor))
        
    def mouseMoveEvent(self, event):
        """Handle mouse movement over the map visualization"""
        x, y = event.x(), event.y()
        self.map_hovered.emit(x, y)
        super().mouseMoveEvent(event)
    
    def mousePressEvent(self, event):
        """Handle mouse clicks on the map visualization"""
        if event.button() == Qt.LeftButton:
            x, y = event.x(), event.y()
            self.map_clicked.emit(x, y)
        super().mousePressEvent(event)
    
    def leaveEvent(self, event):
        """Handle mouse leaving the label area"""
        self.map_hovered.emit(-1, -1)  # Signal with invalid coordinates
        super().leaveEvent(event)

# MapEntry class to store persistent table data
class MapEntry:
    """Class to store persistent data for each map entry in the table"""
    def __init__(self, title="", address_a=None, size_a=None, description_a="", 
                 address_b=None, size_b=None, description_b="", category="red", checked=False):
        self.title = title
        self.address_a = address_a
        self.size_a = size_a
        self.description_a = description_a
        self.address_b = address_b
        self.size_b = size_b
        self.description_b = description_b
        self.category = category  # 'green', 'yellow', or 'red'
        self.checked = checked    # Default to checked
    #    self.use_file_b = False   # Default to use file A if available, else B
        self.row_index = -1       # Current row in the table (-1 if not displayed)
        self.second_name = None
    
    @property
    def display_address(self):
        """Get formatted address display string"""
        if self.address_a is not None and self.address_b is not None and self.address_a != self.address_b:
            return f"0x{self.address_a:05X} 0x{self.address_b:05X}"
        elif self.address_a is not None:
            return f"0x{self.address_a:05X}"
        elif self.address_b is not None:
            return f"0x{self.address_b:05X}"
        else:
            return ""
    
    @property
    def sort_address(self):
        """Get numeric value for address sorting"""
        if self.address_a is not None:
            return self.address_a
        elif self.address_b is not None:
            return self.address_b
        else:
            return 0
    
    @property
    def display_size(self):
        """Get formatted size display string"""
        if self.size_a is not None and self.size_b is not None and self.size_a != self.size_b:
            return f"A: {self.size_a}, B: {self.size_b}"
        elif self.size_a is not None:
            return f"{self.size_a}"
        elif self.size_b is not None:
            return f"{self.size_b}"
        else:
            return ""
    
    @property
    def sort_size(self):
        """Get numeric value for size sorting"""
        if self.size_a is not None:
            return self.size_a
        elif self.size_b is not None:
            return self.size_b
        else:
            return 0
    
    @property
    def display_description(self):
        """Get formatted description display string"""
        if self.description_a and self.description_b and self.description_a != self.description_b:
            return f"A: {self.description_a} B: {self.description_b}"
        elif self.description_a:
            return self.description_a
        elif self.description_b:
            return self.description_b
        else:
            return ""

# Main application window
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # Initialize empty data structures
        self.list_A = []
        self.list_B = []
        self.dict_A = {}
        self.dict_B = {}
        #self.checked_maps = set()  # To store checked map titles
        self.map_to_row_dict = {}  # To store mapping between map titles and table rows
        
        # New persistent map_entries dictionary
        self.map_entries = {}  # Dictionary to store all map entries by title
        
        # Track counts for each color category
        self.green_count = 0
        self.yellow_count = 0
        self.red_count = 0
        
        # Binary file data
        self.binary_data_a = None
        self.binary_data_b = None
        
        # Store file names
        self.file_a_name = "File A"
        self.file_b_name = "File B"
        
        # Track the current visualization dimensions
        self._current_width = VISUALIZATION_WIDTH
        self._current_height = VISUALIZATION_HEIGHT
        self._aspect_ratio = VISUALIZATION_WIDTH / VISUALIZATION_HEIGHT
        
        # Create empty base image
        self.base_image = np.zeros((VISUALIZATION_HEIGHT, VISUALIZATION_WIDTH, 3), dtype=np.uint8)
        
        # Create a timer for delayed resize updates
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.setInterval(100) 
        self.resize_timer.timeout.connect(self.update_after_resize)
        self.is_resizing = False

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)

        # File buttons layout
        file_buttons_layout = QVBoxLayout()
        
        # XDF file buttons
        xdf_buttons_layout = QHBoxLayout()
        self.load_file_a_button = QPushButton("Load XDF File A")
        self.load_file_b_button = QPushButton("Load XDF File B")
        self.load_file_a_button.clicked.connect(self.load_file_a)
        self.load_file_b_button.clicked.connect(self.load_file_b)
        xdf_buttons_layout.addWidget(self.load_file_a_button)
        xdf_buttons_layout.addWidget(self.load_file_b_button)
        file_buttons_layout.addLayout(xdf_buttons_layout)
        
        # Binary file buttons
        binary_buttons_layout = QHBoxLayout()
        self.load_binary_a_button = QPushButton("Load Binary File A")
        self.load_binary_a_button.setEnabled(False)  # Disable until XDF file is loaded
        self.load_binary_b_button = QPushButton("Load Binary File B")
        self.load_binary_b_button.setEnabled(False)  # Disable until XDF file is loaded
        self.load_binary_a_button.clicked.connect(self.load_binary_a)
        self.load_binary_b_button.clicked.connect(self.load_binary_b)
        
        binary_buttons_layout.addWidget(self.load_binary_a_button)
        binary_buttons_layout.addWidget(self.load_binary_b_button)
        file_buttons_layout.addLayout(binary_buttons_layout)

        # Filter layout
        filter_layout = QHBoxLayout()
        self.green_cb = QCheckBox("G (0)")  # Changed from "Green" to "G (0)"
        self.yellow_cb = QCheckBox("Y (0)")  # Changed from "Yellow" to "Y (0)"
        self.red_cb = QCheckBox("R (0)")  # Changed from "Red" to "R (0)"
        self.green_cb.setChecked(True)
        self.yellow_cb.setChecked(True)
        self.red_cb.setChecked(True)
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("Search...")
        filter_layout.addWidget(self.green_cb)
        filter_layout.addWidget(self.yellow_cb)
        filter_layout.addWidget(self.red_cb)
        filter_layout.addWidget(self.search_bar)

        # Create the table widget
        self.table_widget = CustomTableWidget(self)
        self.table_widget.setColumnCount(7)  # Checkbox, Address, Size, Name A, Name B, Description, Select A/B, Category (hidden)
        self.table_widget.setHorizontalHeaderLabels(["Incl", "Address", "Size", self.file_a_name, self.file_b_name, "Description", "Category"])
        # Change resize mode to make all columns resizable
        self.table_widget.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.table_widget.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)  # Checkbox column fixed width
        self.table_widget.horizontalHeader().setSectionResizeMode(5, QHeaderView.Stretch)  # Description stretches
        self.table_widget.horizontalHeader().setSectionResizeMode(6, QHeaderView.Fixed)  # Checkbox column fixed width
        self.table_widget.setColumnWidth(0, 10)  # Set width for checkbox column
        self.table_widget.setColumnWidth(1, 55)  # 
        self.table_widget.setColumnWidth(2, 12)  #  
        self.table_widget.setColumnHidden(6, True)  # Hide category column (used for filtering)
        self.table_widget.setSortingEnabled(True)
        
        # Add the merged list to the layout
        top_widget = QWidget()
        top_widget.setMinimumSize(700, 400)
        top_layout = QVBoxLayout()
        top_layout.addLayout(file_buttons_layout)
        top_layout.addLayout(filter_layout)
        top_layout.addWidget(self.table_widget)
        top_widget.setLayout(top_layout)

        # Offset controls
        offset_layout = QHBoxLayout()
        self.start_offset_slider = QSlider(Qt.Horizontal)
        self.start_offset_slider.setRange(0, 524287 // 16)  # Divide by 16 to make each step 16 bytes
        self.start_offset_slider.setValue(0)
        self.start_offset_box = QLineEdit("00000")  # Initialize with hex format
        self.start_offset_box.setFixedWidth(60)
        self.end_offset_slider = QSlider(Qt.Horizontal)
        self.end_offset_slider.setRange(0, 524287 // 16)
        self.end_offset_slider.setValue(524287 // 16)
        self.end_offset_box = QLineEdit("7FFFF")  # Initialize with hex format
        self.end_offset_box.setFixedWidth(60)
        offset_layout.addWidget(QLabel("Start:"))
        offset_layout.addWidget(self.start_offset_slider)
        offset_layout.addWidget(self.start_offset_box)
        offset_layout.addWidget(QLabel("End:"))
        offset_layout.addWidget(self.end_offset_slider)
        offset_layout.addWidget(self.end_offset_box)

        # Connect offset controls
        self.start_offset_slider.valueChanged.connect(self.update_start_offset)
        self.start_offset_box.textChanged.connect(self.update_start_offset_from_box)
        self.end_offset_slider.valueChanged.connect(self.update_end_offset)
        self.end_offset_box.textChanged.connect(self.update_end_offset_from_box)
        
        # Export button
        self.export_button = QPushButton("Export Merged Binary")
        self.export_button.clicked.connect(self.export_merged_binary)
        self.export_button.setEnabled(False)  # Disable until both binary files are loaded

        # Main splitter
        self.main_splitter = QSplitter(Qt.Horizontal)  # Change to horizontal splitter
        left_panel = QWidget()
        left_layout = QVBoxLayout()
        left_layout.addWidget(top_widget)
        offset_widget = QWidget()
        offset_widget.setLayout(offset_layout)
        left_layout.addWidget(offset_widget)
        left_layout.addWidget(self.export_button)
        left_panel.setLayout(left_layout)
        
        # Set size policy for left panel to expand in both directions
        left_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        self.main_splitter.addWidget(left_panel)
        
        # Right panel for visualization with fixed height policy
        self.right_panel = QWidget()
        right_layout = QVBoxLayout(self.right_panel)
        
        # Replace QLabel with InteractiveMapLabel
        self.label = InteractiveMapLabel()
        # Connect signals for mouse interaction
        self.label.map_hovered.connect(self.on_map_hovered)
        self.label.map_clicked.connect(self.on_map_clicked)
        
        # Set the label to have fixed height based on width only
        self.label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.label.setMinimumWidth(256)
        self.label.setMinimumHeight(256)
        self.label.setScaledContents(True)
        
        # Add orientation toggle button
        self.orientation_auto = True  # Track if orientation is automatic
        
        # Add the label to the right panel
        right_layout.addWidget(self.label)
        
        # Add address display label
        self.address_label = QLabel("Addr: 00000")
        self.address_label.setStyleSheet("background-color: rgba(0, 0, 0, 128); color: white; padding: 2px;")
        self.address_label.setAlignment(Qt.AlignLeft)
        right_layout.addWidget(self.address_label)
        
        # Add spacer to push visualization to top and allow independent height
        right_layout.addStretch(1)
        
        self.main_splitter.addWidget(self.right_panel)

        self.central_widget.setLayout(QVBoxLayout())
        self.central_widget.layout().addWidget(self.main_splitter)
        
        # Connect the splitter moved signal to update the visualization
        self.main_splitter.splitterMoved.connect(self.on_splitter_moved)

        # Connect filter signals
        self.green_cb.toggled.connect(self.filter_maps)
        self.yellow_cb.toggled.connect(self.filter_maps)
        self.red_cb.toggled.connect(self.filter_maps)
        self.search_bar.textChanged.connect(self.filter_maps)

        # Connect item selection signal
        self.table_widget.itemSelectionChanged.connect(self.on_item_selection_changed)
        self.table_widget.cellEntered.connect(self.on_cell_entered)
        self.table_widget.itemChanged.connect(self.on_item_check_changed)
        
        # Connect sorting signal to update map-to-row mapping
        self.table_widget.horizontalHeader().sortIndicatorChanged.connect(self.update_map_to_row_mapping_after_sort)

        self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.base_image)))


    # Function to parse XDF files and extract maps
    def parse_xdf(self, file_path):
        try:
            tree = ET.parse(file_path)
            root = tree.getroot()
            maps = []


            # Parse special MS43 BASEOFFSET with subtract attribute
            offset = 0
            subtract = 0
            baseoffset_elem = root.find('.//BASEOFFSET')
            if baseoffset_elem is not None:
                # Get offset attribute
                offset_text = baseoffset_elem.get('offset')
                if offset_text:
                    try:
                        # Try parsing offset as hex or decimal
                        if offset_text.lower().startswith('0x'):
                            offset = int(offset_text, 16)
                        else:
                            offset = int(offset_text)
                    except (ValueError, TypeError):
                        print(f"Warning: Could not parse BASEOFFSET offset value '{offset_text}', using 0")

                # Get subtract attribute
                subtract_text = baseoffset_elem.get('subtract')
                if subtract_text:
                    try:
                        # Try parsing subtract as hex or decimal
                        if subtract_text.lower().startswith('0x'):
                            subtract = int(subtract_text, 16)
                        else:
                            subtract = int(subtract_text)
                    except (ValueError, TypeError):
                        print(f"Warning: Could not parse BASEOFFSET subtract value '{subtract_text}', using 0")

                # Apply subtract to offset
                offset = offset - subtract
                print(f"Using BASEOFFSET: {offset} (offset {baseoffset_elem.get('offset')} - subtract {baseoffset_elem.get('subtract')})")

            self.start_offset_slider.setValue(offset//16)
            self.update_start_offset(offset//16)
            
            for table in root.findall('.//XDFTABLE'):
                title = table.find('.//title').text if table.find('.//title') is not None else "Untitled Table"
                description = table.find('.//description')
                desc_text = description.text if description is not None else ""
                z_axis = table.find('.//XDFAXIS[@id="z"]')
                if z_axis is not None:
                    embedded_data = z_axis.find('EMBEDDEDDATA')
                    if embedded_data is not None:
                        address = offset + int(embedded_data.get('mmedaddress'), 16)
                        elementsize = int(embedded_data.get('mmedelementsizebits')) // 8
                        rowcount = int(embedded_data.get('mmedrowcount', 1))
                        colcount = int(embedded_data.get('mmedcolcount', 1))
                        size = rowcount * colcount * elementsize
                        maps.append({'title': title, 'start': address, 'end': address + size, 'size': size, 'description': desc_text})
            for constant in root.findall('.//XDFCONSTANT'):
                title = constant.find('.//title').text if constant.find('.//title') is not None else "Untitled Constant"
                description = constant.find('.//description')
                desc_text = description.text if description is not None else ""
                embedded_data = constant.find('EMBEDDEDDATA')
                if embedded_data is not None:
                    address = offset + int(embedded_data.get('mmedaddress'), 16)
                    elementsize = int(embedded_data.get('mmedelementsizebits')) // 8
                    maps.append({'title': title, 'start': address, 'end': address + elementsize, 'size': elementsize, 'description': desc_text})

            # Extract patches - only load individual patch entries, not the whole patch
            for patch in root.findall('.//XDFPATCH'):
                title = patch.find('.//title').text if patch.find('.//title') is not None else "Untitled Patch"
                description = patch.find('.//description')
                desc_text = description.text if description is not None else ""

                # Process each patch entry individually
                for entry in patch.findall('.//XDFPATCHENTRY'):
                    entry_name = entry.get('name', '')
                    entry_address = offset + int(entry.get('address'), 16)
                    entry_size = int(entry.get('datasize'), 16)
                    entry_patchdata = entry.get('patchdata', '')
                    entry_basedata = entry.get('basedata', '')

                    entry_title = f"{title} - {entry_name}"
                    entry_description = f"{desc_text} | Patch: {entry_patchdata} (Base: {entry_basedata})"

                    maps.append({
                        'title': entry_title,
                        'start': entry_address,
                        'end': entry_address + entry_size,
                        'size': entry_size,
                        'description': entry_description,
                        'type': 'patch_entry',
                        'patchdata': entry_patchdata,
                        'basedata': entry_basedata
                    })
            maps.sort(key=lambda x: x['start'])
            return maps
        except ET.ParseError as e:
            print(f"Error parsing {file_path}: {e}")
            return []
    
    def load_file_a(self):
        """Handler for loading File A"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File A (XDF file)", "", "XDF Files (*.xdf)")
        if file_path:
            self.list_A = self.parse_xdf(file_path)
            self.dict_A = {map['title']: (map['start'], map['end']) for map in self.list_A}
            # Get file name from path
            self.file_a_name = file_path.split('/')[-1].split('\\')[-1]
            # Update button text
            self.load_file_a_button.setText(f"XDF A: {self.file_a_name}")
            self.update_map_entries_from_files()
            self.update_after_file_load()
            if self.file_a_name is not None:
                self.load_binary_a_button.setEnabled(True)
    
    def load_file_b(self):
        """Handler for loading File B"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select File B (XDF file)", "", "XDF Files (*.xdf)")
        if file_path:
            self.list_B = self.parse_xdf(file_path)
            self.dict_B = {map['title']: (map['start'], map['end']) for map in self.list_B}
            # Get file name from path
            self.file_b_name = file_path.split('/')[-1].split('\\')[-1]
            # Update button text
            self.load_file_b_button.setText(f"XDF B: {self.file_b_name}")
            self.update_map_entries_from_files()
            self.update_after_file_load()
            if self.file_b_name is not None:
                self.load_binary_b_button.setEnabled(True)

    def update_map_entries_from_files(self):
        """Update the persistent map_entries dictionary from loaded files"""
        ## Preserve existing entries' states where possible
        #preserved_states = {title: (entry.checked, entry.use_file_b) 
        #                    for title, entry in self.map_entries.items()}
        
        # Create a new combined map_entries dictionary
        new_entries = {}
        
        # Process maps from file A
        for map_a in self.list_A:
            title = map_a['title']
            if title not in new_entries:
                new_entries[title] = MapEntry(
                    title=title,
                    address_a=map_a['start'],
                    size_a=map_a['size'],
                    description_a=map_a.get('description', '')
                    #category=self.get_map_category(map_a, self.dict_B),
                )
        
        # Process maps from file B
        for map_b in self.list_B:
            title   = map_b['title']
            address = map_b['start']
            size    = map_b['size']
            if title in new_entries:
                # Update existing entry with file B data
                new_entries[title].address_b = map_b['start']
                new_entries[title].size_b = map_b['size']
                new_entries[title].description_b = map_b.get('description', '')
                new_entries[title].checked = True
                # Recalculate category now that we have both maps
                if map_b['title'] not in self.dict_A:
                    new_entries[title].category = 'red'
                    new_entries[title].checked = False
                elif new_entries[title].address_a != map_b['start'] or new_entries[title].size_a != map_b['size']:
                    new_entries[title].category = 'yellow'
                else:
                    new_entries[title].category = 'green'
                           
            else:
                # Check if there's a map in file A with the same address and size but different title
                match_by_address = None
                for map_a in self.list_A:
                    if map_a['start'] == address and map_a['size'] == size and map_a['title'] != title:
                        match_by_address = map_a
                        break
                    
                if match_by_address:
                    # We found a map with same address/size in file A but different title
                    if match_by_address['title'] in new_entries:
                        # Update existing entry with file B data
                        new_entries[match_by_address['title']].address_b = address
                        new_entries[match_by_address['title']].size_b = size
                        new_entries[match_by_address['title']].description_b = map_b.get('description', '')
                        new_entries[match_by_address['title']].category = 'yellow'
                        new_entries[match_by_address['title']].checked = True
                        new_entries[match_by_address['title']].second_name = title
                else:
                    # Create new entry for file B only
                    new_entries[title] = MapEntry(
                        title=title,
                        address_b=map_b['start'],
                        size_b=map_b['size'],
                        description_b=map_b.get('description', '')
                    )
        
        ## Restore any preserved states
        #for title, entry in new_entries.items():
        #    if title in preserved_states:
        #        entry.checked, entry.use_file_b = preserved_states[title]
        
        # Update the main dictionary
        self.map_entries = new_entries
        
        # Update color counts after processing all entries
        self.update_color_counts()

    def update_after_file_load(self):
        """Update visualization and table after loading a file"""
        # Update table column headers with current file names
        self.table_widget.setHorizontalHeaderLabels(["", "Address", "Size", self.file_a_name, self.file_b_name, "Description", "Category"])
    
        # Update color counts
        self.update_color_counts()
        
        # Update the table
        self.filter_maps()

    def resizeEvent(self, event):
        """Handle window resize events to update visualization size"""
        super().resizeEvent(event)
        # Mark that we're resizing and restart the timer
        self.is_resizing = True
        self.resize_timer.start()
        
    def on_splitter_moved(self, pos, index):
        """Handle splitter move events to update visualization size"""
        # Mark that we're resizing and restart the timer
        self.is_resizing = True
        self.resize_timer.start()
        
    def update_after_resize(self):
        """Called after resize events have stopped for the delay period"""
        self.is_resizing = False
        self.update_visualization_dimensions()
        self.update_visual_representation()
        
    def toggle_auto_orientation(self, checked):
        """Toggle between auto and fixed orientation"""
        self.orientation_auto = checked
        self.update_visualization_dimensions()
        self.update_visual_representation()
        
    def update_visualization_dimensions(self):
        """Update the visualization dimensions based on the current window size"""
        if not hasattr(self, 'label'):
            return
            
        # Get the available width and height for the image label
        available_width  = max(50, self.label.width())
        available_height = max(50, self.right_panel.height())
        
        
        # Determine optimal orientation if in auto mode
        if self.orientation_auto:
            # Use landscape if width > 1.5*height, otherwise portrait
            use_landscape = (available_width > available_height * 1.5)
        else:
            # Use current aspect ratio to determine orientation
            use_landscape = (self._aspect_ratio >= 1.0)
        
        #if use_landscape:
        #    # Landscape mode (width > height)
        #    self._aspect_ratio = 2.0  # 2:1 aspect ratio for landscape
        #    new_height = int(available_width / self._aspect_ratio)
        #    if new_height > available_height:
        #        # If height doesn't fit, adjust width
        #        new_height = available_height
        #        new_width = int(new_height * self._aspect_ratio)
        #    else:
        #        new_width = available_width
        #else:
        #    # Portrait mode (height > width)
        #    self._aspect_ratio = 0.5  # 1:2 aspect ratio for portrait
        #    new_width = int(available_height * self._aspect_ratio)
        #    if new_width > available_width:
        #        # If width doesn't fit, adjust height
        #        new_width = available_width
        #        new_height = int(new_width / self._aspect_ratio)
        #    else:
        #        new_height = available_height
                
        new_width = available_width
        if use_landscape:
            new_height = int(available_width / 2)
        else:
            new_height = available_width*2
            
        new_width  = available_width 
        new_height = available_height - 50
            
        #if new_height > available_height:
        #    new_height = available_height - 50
        #    new_width = int(new_height // 2)
                
        # Update the image dimensions
        #self.label.setMinimumHeight(new_height)
        #self.label.setMaximumHeight(new_height)
        
        #print(available_width, available_height, new_height, new_width)
        
        # Update current dimensions
        self._current_width  = max(20, new_width)
        self._current_height = max(20, new_height)
        
        #self.label.setMinimumSize(self._current_width, self._current_height)
        #self.label.setMaximumSize(self._current_width, self._current_height)
            
        
    
    @property
    def visualization_width(self):
        """Get the current visualization width"""
        return self._current_width
    
    @property
    def visualization_height(self):
        """Get the current visualization height"""
        return self._current_height

    def update_visual_representation(self):
        """Update the visual representation based on current settings"""
        # Skip updates during active resizing to avoid lag
        if self.is_resizing:
            return
            
        start_offset = self.start_offset_slider.value() * 16
        end_offset = self.end_offset_slider.value() * 16
        if start_offset >= end_offset:
            return

        # Get current image dimensions
        image_width, image_height = self.visualization_width, self.visualization_height
        # Ensure minimum dimensions to prevent division by zero
        image_width = max(1, image_width)
        image_height = max(1, image_height)
        
        selected_range = end_offset - start_offset

        # Calculate dynamic scale to fit the selected range
        bytes_needed = selected_range
        scale = self.get_scaling(selected_range)  # Ensure scale is at least 1
        
        # Calculate bytes per row based on orientation
        if self._aspect_ratio >= 1.0:  # Landscape orientation
            bytes_per_row = max(1, image_width // scale)  # Prevent division by zero
        else:  # Portrait orientation
            bytes_per_row = max(1, image_width // scale)  # Narrower rows in portrait mode
            
        max_rows = max(1, image_height // scale)      # Prevent division by zero
        total_bytes = min(bytes_needed, bytes_per_row * max_rows)
        
        # Initialize the image with current dimensions
        self.base_image = np.zeros((image_height, image_width, 3), dtype=np.uint8)

        # Render bytes within the selected range
        for title, map in self.map_entries.items():
            #maps = []
            #if map.address_a is not None and map.size_a is not None:
            #    maps.append([map.address_a, map.address_a + map.size_a])
            #if map.address_b is not None and map.size_b is not None:
            #    maps.append([map.address_b, map.address_b + map.size_b])
            for index in range(2):
                if index == 0:
                    if map.address_a is not None and map.size_a is not None:
                        start = map.address_a
                        end = map.address_a + map.size_a
                    else:
                        continue
                else:
                    if map.address_b is not None and map.size_b is not None:
                        start = map.address_b
                        end = map.address_b + map.size_b
                    else:
                        continue
                        
                
                category = map.category
                checked  = map.checked

                ## Determine color based on map properties and checked state
                #if map['title'] in self.dict_A and map['title'] not in self.dict_B:
                #    color = COLOR_FILE_A_ONLY  # Dark red for File A only
                #elif map['title'] in self.dict_B and map['title'] not in self.dict_A:
                #    color = COLOR_FILE_B_ONLY  # Dark orange for File B only
                #else:
                #    color = COLOR_COMMON_MAP  # Light gray for common maps
                    
                if category == 'yellow':
                    color = COLOR_HIGHLIGHT_DIFFERENT_ADDRESS_A.copy() if index < 1 else COLOR_HIGHLIGHT_DIFFERENT_ADDRESS_B.copy()
                elif category == 'red':
                    color = COLOR_FILE_A_ONLY.copy() if index < 1 else COLOR_FILE_B_ONLY.copy()
                else:
                    if index > 0:
                        continue
                    color = COLOR_COMMON_MAP.copy()
                    
                    
                if checked:
                    color[0] = min(255, (color[0] + 64))  # Light blue for checked maps
                    color[1] = min(255, (color[1] + 64))  # Light blue for checked maps
                    color[2] = min(255, (color[2] + 64))  # Light blue for checked maps
 
                #if category == 'yellow': print(color, checked)
                #else: print(index, title, start, end, checked, category, color)
                
                for address in range(max(start, start_offset), min(end, end_offset)):
                   relative_address = address - start_offset
                   if relative_address < total_bytes:
                       row = relative_address // bytes_per_row
                       col = relative_address %  bytes_per_row
                       block_x = col * scale
                       block_y = row * scale
                       for dx in range(scale):
                           for dy in range(scale):
                               x = block_x + dx
                               y = block_y + dy
                               if x < image_width and y < image_height:
                                   self.base_image[y, x] = color.copy()
                index += 1
        # Fill remaining space with dark gray
        if total_bytes > 0:
            last_byte_row = (total_bytes - 1) // bytes_per_row
            last_byte_col = (total_bytes - 1) %  bytes_per_row
            # Fill rows below the last byte with bounds checking
            for y in range(min((last_byte_row + 1) * scale, image_height), image_height):
                for x in range(min(image_width, image_width)):
                    self.base_image[y, x] = COLOR_BACKGROUND  # Dark gray
                    
            # Fill columns to the right of the last byte with bounds checking
            for x in range(min((last_byte_col + 1) * scale, image_width), image_width):
                for y in range(min(last_byte_row * scale, image_height), min((last_byte_row + 1) * scale, image_height)):
                    self.base_image[y, x] = COLOR_BACKGROUND  # Dark gray

        self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.base_image)))
        #print("----------")

    def filter_maps(self):
        """Filter and populate the table with maps based on current filters."""
        # Check if the signal is connected before disconnecting
        try:
            self.table_widget.itemChanged.disconnect(self.on_item_check_changed)
        except TypeError:
            # Signal was not connected yet, which is fine
            pass
        
        try:
            # Clear the table but keep our map entries
            self.table_widget.setSortingEnabled(False)
            self.table_widget.setRowCount(0)
            self.map_to_row_dict.clear()
            
            # Get current filter settings
            search_text = self.search_bar.text().lower()
            show_green = self.green_cb.isChecked()
            show_yellow = self.yellow_cb.isChecked()
            show_red = self.red_cb.isChecked()
            
            # Add entries that match the current filters
            row = 0
            for title, entry in self.map_entries.items():
                # Check if entry matches text filter
                if search_text not in title.lower():
                    entry.row_index = -1  # Not displayed
                    continue
                
                # Check if entry matches category filter
                if ((entry.category == 'green' and not show_green) or
                    (entry.category == 'yellow' and not show_yellow) or
                    (entry.category == 'red' and not show_red)):
                    entry.row_index = -1  # Not displayed
                    continue
                
                # Add entry to table
                self.table_widget.insertRow(row)
                entry.row_index = row  # Track current row position
                
                # Checkbox column
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                checkbox_item.setCheckState(Qt.Checked if entry.checked else Qt.Unchecked)
                
                # Address item with proper sorting
                address_item = NumericTableWidgetItem(entry.sort_address, entry.display_address)
                
                # Size item with proper sorting
                size_item = NumericTableWidgetItem(entry.sort_size, entry.display_size)
                
                # Create file name items
                file_a_item = QTableWidgetItem(title if entry.address_a is not None else "")
                file_b_item = QTableWidgetItem(entry.second_name if entry.second_name is not None else title if entry.address_b is not None else "")
                
                # Description item
                desc_item = QTableWidgetItem(entry.display_description)
                
                ## A/B selection checkbox
                #ab_combobox = QTableWidgetItem()
                #ab_combobox.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                #ab_combobox.setCheckState(Qt.Checked if entry.use_file_b else Qt.Unchecked)
                
                # Category for filtering (hidden column)
                category_item = QTableWidgetItem(entry.category)
                
                # Apply color according to category
                color = COLOR_TEXT_MATCH if entry.category == 'green' else COLOR_TEXT_PARTIAL if entry.category == 'yellow' else COLOR_TEXT_UNIQUE
                for item in [address_item, size_item, file_a_item, file_b_item, desc_item]:
                    item.setForeground(color)
                
                # Set items in table
                self.table_widget.setItem(row, 0, checkbox_item)
                self.table_widget.setItem(row, 1, address_item)
                self.table_widget.setItem(row, 2, size_item)
                self.table_widget.setItem(row, 3, file_a_item)
                self.table_widget.setItem(row, 4, file_b_item)
                self.table_widget.setItem(row, 5, desc_item)
                self.table_widget.setItem(row, 6, category_item)
                
                # Store the map title and its corresponding row
                self.map_to_row_dict[title] = row
                
                row += 1
                
            self.table_widget.setSortingEnabled(True)
            # Default sort by address
            self.table_widget.sortByColumn(1, Qt.AscendingOrder)
            
            # Update map_to_row_dict after sorting
            self.update_map_to_row_mapping()
            
            self.update_visual_representation()
        finally:
            # Always reconnect the signal, even if an error occurred
            self.table_widget.itemChanged.connect(self.on_item_check_changed)

    def get_map_category(self, map, other_dict):
        """Determine the category of a map based on its presence and properties in the other file"""
        if map['title'] not in other_dict:
            return 'red'
        elif other_dict[map['title']] == (map['start'], map['end']):
            return 'green'
        else:
            return 'yellow'

    def on_item_check_changed(self, item):
        """Handle when a checkbox is toggled in the table."""
        if item.column() == 0:  # Checkbox column
            if self.table_widget.ctrl_pressed: return
            row = item.row()
            file_a_title = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ""
            file_b_title = self.table_widget.item(row, 4).text() if self.table_widget.item(row, 4) else ""
            
            
            
            # Update map entry's checked state
            if file_a_title and file_a_title in self.map_entries:
                self.map_entries[file_a_title].checked = (item.checkState() == Qt.Checked)
                #print(file_a_title, self.map_entries[file_a_title].checked)
            if file_b_title and file_b_title in self.map_entries and file_b_title != file_a_title:
                self.map_entries[file_b_title].checked = (item.checkState() == Qt.Checked)
                #print(file_b_title, self.map_entries[file_b_title].checked)
            
            
            ## Update checked_maps set for backward compatibility
            #if item.checkState() == Qt.Checked:
            #    if file_a_title:
            #        self.checked_maps.add(file_a_title)
            #    if file_b_title and file_b_title != file_a_title:
            #        self.checked_maps.add(file_b_title)
            #else:
            #    self.checked_maps.discard(file_a_title)
            #    self.checked_maps.discard(file_b_title)
            
            # Handle linked maps with same start address
            if file_a_title:
                self.update_linked_map_checks(file_a_title, item.checkState() == Qt.Checked)
            
            # Update visualization
            self.update_visual_representation()
        #elif item.column() == 6:  # A/B selection checkbox
        #    row = item.row()
        #    file_a_title = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ""
        #    file_b_title = self.table_widget.item(row, 4).text() if self.table_widget.item(row, 4) else ""
        #    
        #    # Update map entry's use_file_b state
        #    if file_a_title and file_a_title in self.map_entries:
        #        self.map_entries[file_a_title].use_file_b = (item.checkState() == Qt.Checked)
        #    if file_b_title and file_b_title in self.map_entries and file_b_title != file_a_title:
        #        self.map_entries[file_b_title].use_file_b = (item.checkState() == Qt.Checked)

    def update_linked_map_checks(self, map_title, checked):
        """Update all maps that share the same start address when one is checked/unchecked"""
        if map_title not in self.map_entries:
            return
        
        target_map = self.map_entries[map_title]
        start_address_a = target_map.address_a
        start_address_b = target_map.address_b
        
        # Find all maps with the same start address in either file
        for title, entry in self.map_entries.items():
            if title != map_title:
                if ((start_address_a is not None and entry.address_a == start_address_a) or 
                    (start_address_b is not None and entry.address_b == start_address_b)):
                    # Update the entry's checked state
                    entry.checked = checked
                    
                    #print(title, entry.checked)
                    
                    # Update UI if the entry is visible in the table
                    if entry.row_index >= 0:
                        row = self.map_to_row_dict[title]
                        checkbox_item = self.table_widget.item(row, 0)
                        if checkbox_item:
                            checkbox_item.setCheckState(Qt.Checked if checked else Qt.Unchecked)
                    
                    # Update checked_maps set for backward compatibility
                    #if checked:
                    #    self.checked_maps.add(title)
                    #else:
                    #    self.checked_maps.discard(title)

    def update_map_to_row_mapping(self):
        """Update the map-to-row mapping after table sorting"""
        self.map_to_row_dict.clear()
        for row in range(self.table_widget.rowCount()):
            file_a_item = self.table_widget.item(row, 3)
            file_b_item = self.table_widget.item(row, 4)
            
            # Update the row_index in map entries
            if file_a_item and file_a_item.text() and file_a_item.text() in self.map_entries:
                self.map_entries[file_a_item.text()].row_index = row
                self.map_to_row_dict[file_a_item.text()] = row
                
            if file_b_item and file_b_item.text() and file_b_item.text() in self.map_entries:
                self.map_entries[file_b_item.text()].row_index = row
                if file_b_item.text() not in self.map_to_row_dict:
                    self.map_to_row_dict[file_b_item.text()] = row

    def export_merged_binary(self):
        """Export the merged binary based on map entries"""
        if not self.binary_data_a or not self.binary_data_b:
            print("Both binary files must be loaded before exporting")
            return
            
        # Create a new binary by starting with binary B as the base
        merged_data = bytearray(self.binary_data_b.copy())
        
        # For each map entry, apply data from file B if use_file_b is True
        for title, entry in self.map_entries.items():
            if entry.checked and entry.address_a is not None and entry.size_a is not None and entry.address_b is not None and entry.size_b is not None and entry.size_a == entry.size_b:
                start_addr  = entry.address_a
                target_addr = entry.address_b
                size = entry.size_a
                if start_addr + size <= len(self.binary_data_a) and target_addr + size <= len(merged_data):
                    if start_addr != target_addr: print("Merged: ", title, start_addr, target_addr, size)
                    for i in range(size):
                        merged_data[target_addr + i] = self.binary_data_a[start_addr + i]
        
        # Ask user for save location
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Merged Binary", "", "Binary Files (*.bin)")
        if file_path:
            try:
                with open(file_path, 'wb') as f:
                    f.write(merged_data)
                print(f"Merged binary saved successfully to {file_path}")
            except Exception as e:
                print(f"Error saving merged binary: {e}")

    def update_start_offset(self, value):
        """Update the start offset when the slider changes."""
        # Convert slider value (in 16-byte increments) to actual offset
        actual_value = value * 16
        
        # Update text box with hex representation without triggering its change event
        self.start_offset_box.blockSignals(True)
        self.start_offset_box.setText(f"{actual_value:05X}")  # 5-digit hex with leading zeros
        self.start_offset_box.blockSignals(False)
        
        # Ensure start is less than end
        end_actual_value = self.end_offset_slider.value() * 16
        if actual_value >= end_actual_value:
            self.start_offset_slider.setValue((end_actual_value - 16) // 16)
            return
            
        self.update_visual_representation()
        
    def update_start_offset_from_box(self):
        """Update the start offset when the text box changes."""
        try:
            # Parse hex value from text box
            hex_text = self.start_offset_box.text().strip()
            value = int(hex_text, 16)
            
            # Round to nearest 16-byte boundary
            value = (value // 16) * 16
            
            # Convert to slider value (divide by 16)
            slider_value = value // 16
            
            # Ensure within valid range
            end_actual_value = self.end_offset_slider.value() * 16
            if value >= end_actual_value:
                slider_value = (end_actual_value - 16) // 16
                value = slider_value * 16
            
            # Update slider without triggering its change event
            self.start_offset_slider.blockSignals(True)
            self.start_offset_slider.setValue(slider_value)
            self.start_offset_slider.blockSignals(False)
            
            # Update text box with formatted hex value
            self.start_offset_box.blockSignals(True)
            self.start_offset_box.setText(f"{value:05X}")
            self.start_offset_box.blockSignals(False)
            
            self.update_visual_representation()
        except ValueError:
            # Reset to current slider value if invalid input
            actual_value = self.start_offset_slider.value() * 16
            self.start_offset_box.setText(f"{actual_value:05X}")
            
    def update_end_offset(self, value):
        """Update the end offset when the slider changes."""
        # Convert slider value to actual offset
        actual_value = value * 16
        
        # Update text box with hex representation without triggering its change event
        self.end_offset_box.blockSignals(True)
        self.end_offset_box.setText(f"{actual_value:05X}")  # 5-digit hex with leading zeros
        self.end_offset_box.blockSignals(False)
        
        # Ensure end is greater than start
        start_actual_value = self.start_offset_slider.value() * 16
        if actual_value <= start_actual_value:
            self.end_offset_slider.setValue((start_actual_value + 16) // 16)
            return
            
        self.update_visual_representation()
        
    def update_end_offset_from_box(self):
        """Update the end offset when the text box changes."""
        try:
            # Parse hex value from text box
            hex_text = self.end_offset_box.text().strip()
            value = int(hex_text, 16)
            
            # Round to nearest 16-byte boundary
            value = (value // 16) * 16
            
            # Convert to slider value (divide by 16)
            slider_value = value // 16
            
            # Ensure within valid range
            start_actual_value = self.start_offset_slider.value() * 16
            if value <= start_actual_value:
                slider_value = (start_actual_value + 16) // 16
                value = slider_value * 16
                
            slider_value = min(slider_value, 524287 // 16)
            value = min(value, 524287)
            
            # Update slider without triggering its change event
            self.end_offset_slider.blockSignals(True)
            self.end_offset_slider.setValue(slider_value)
            self.end_offset_slider.blockSignals(False)
            
            # Update text box with formatted hex value
            self.end_offset_box.blockSignals(True)
            self.end_offset_box.setText(f"{value:05X}")
            self.end_offset_box.blockSignals(False)
            
            self.update_visual_representation()
        except ValueError:
            # Reset to current slider value if invalid input
            actual_value = self.end_offset_slider.value() * 16
            self.end_offset_box.setText(f"{actual_value:05X}")
            
    def get_scaling(self, selected_range):
        """Calculate appropriate scaling based on current orientation and selected range"""
        image_width, image_height = self.visualization_width, self.visualization_height
        
        size = image_width * image_height
        scale = max(1, round((size / selected_range)** 0.5 - 0.5))
        #print(selected_range, size, scale, (size / selected_range)** 0.5 - 0.5)            
        
        return scale
    
    def update_map_to_row_mapping_after_sort(self):
        """Schedule the mapping update after sorting completes"""
        # Use a short delay to ensure sorting has finished
        QTimer.singleShot(100, self.update_map_to_row_mapping)


    def update_map_to_row_mapping(self):
        """Update the map-to-row mapping after table sorting"""
        self.map_to_row_dict.clear()
        for row in range(self.table_widget.rowCount()):
            file_a_item = self.table_widget.item(row, 3)
            file_b_item = self.table_widget.item(row, 4)
            
            #print(file_a_item.text())
            
            if file_a_item and file_a_item.text():
                self.map_to_row_dict[file_a_item.text()] = row
            if file_b_item and file_b_item.text() and file_b_item.text() not in self.map_to_row_dict:
                self.map_to_row_dict[file_b_item.text()] = row

    def on_map_hovered(self, x, y):
        """Handle mouse hovering over the map visualization"""
        if x < 0 or y < 0:  # Mouse left the label area
            self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.base_image)))
            self.address_label.setText("Addr: 00000")
            return
            
        # Calculate the address at the hovered position
        start_offset = self.start_offset_slider.value() * 16
        end_offset = self.end_offset_slider.value() * 16
        selected_range = end_offset - start_offset
        
        scale = self.get_scaling(selected_range)
        bytes_per_row = self.visualization_width // scale
        
        # Convert pixel to byte offset
        block_x = x // scale
        block_y = y // scale
        
        # Calculate address from block coordinates
        relative_address = block_y * bytes_per_row + block_x
        
        # Check if the relative address is within bounds
        if relative_address >= selected_range:
            self.address_label.setText("Addr: 00000")
        else:
            address = start_offset + relative_address
            # Format address as 5-digit hex with leading zeros
            address_hex = f"{address:05X}"
            self.address_label.setText(f"Addr: {address_hex}")
            
        # Convert mouse position to address
        map_title = self.get_map_at_position(x, y)
        if not map_title:
            self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.base_image)))
            return
            
        # Find the corresponding row in the table
        if map_title in self.map_to_row_dict:
            row = self.map_to_row_dict[map_title]
            
            # Select the row to highlight it
            self.table_widget.selectRow(row)
            
            # Ensure the row is visible in the viewport
            self.table_widget.scrollToItem(self.table_widget.item(row, 0), QTableWidget.PositionAtCenter)
            
            # Highlight the map in the visualization
            self.highlight_map_from_table(row)
        else:
            self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(self.base_image)))
    
    def on_map_clicked(self, x, y):
        """Handle mouse click on the map visualization"""
        map_title = self.get_map_at_position(x, y)
        if not map_title or map_title not in self.map_to_row_dict:
            return
            
        #for map in self.list_A + self.list_B:
        #    if map['title'] == map_title:
        #        # List all matched maps and return all that has same start address
        #        for map_a in self.list_A + self.list_B:
        #            if map_a['start'] == map['start']:
        #                row = self.map_to_row_dict[map_a['title']]
        #                checkbox_item = self.table_widget.item(row, 0)
        #                current_state = checkbox_item.checkState()
        #                new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
        #                checkbox_item.setCheckState(new_state)
        #                break
            
        row = self.map_to_row_dict[map_title]
        checkbox_item = self.table_widget.item(row, 0)
        
        # Toggle the checkbox state
        current_state = checkbox_item.checkState()
        new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
        checkbox_item.setCheckState(new_state)
        
        # The on_item_check_changed handler will take care of updating the checked_maps set
        # and refreshing the visualization
    
    def get_map_at_position(self, x, y):
        """Convert pixel coordinates to map title"""
        # Get current visualization settings
        start_offset = self.start_offset_slider.value() * 16
        end_offset = self.end_offset_slider.value() * 16
        selected_range = end_offset - start_offset
        
        image_width, image_height = self.visualization_width, self.visualization_height
        
        # Skip if clicked outside the image bounds
        if x >= image_width or y >= image_height:
            return None
        
        # Use the exact same scale calculation as in update_visual_representation
        scale = self.get_scaling(selected_range)
        bytes_per_row = image_width // scale
        
        # Convert pixel to byte offset
        # First, find which block was clicked by integer division
        block_x = x // scale
        block_y = y // scale
        
        #print(image_width, x, block_x, image_height, y, block_y)
        
        # Calculate address from block coordinates
        # This needs to match the exact formula used in update_visual_representation
        relative_address = block_y * bytes_per_row + block_x
        
        # Check if the relative address is within bounds
        if relative_address >= selected_range:
            return None
            
        address = start_offset + relative_address
        
        # Find which map this address belongs to
        for map_list in [self.list_A, self.list_B]:
            for map_info in map_list:
                if map_info['start'] <= address < map_info['end']:
                    return map_info['title']
        
        return None

    def load_binary_a(self):
        """Handler for loading Binary File A"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Binary File A", "", "Binary Files (*.bin);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.binary_data_a = bytearray(f.read())
                
                # If file is not exactly 512KB, pad or truncate it
                if len(self.binary_data_a) != 512 * 1024:
                    if len(self.binary_data_a) < 512 * 1024:
                        # Pad with zeros if too small
                        self.binary_data_a.extend([0] * (512 * 1024 - len(self.binary_data_a)))
                    else:
                        # Truncate if too large
                        self.binary_data_a = self.binary_data_a[:512 * 1024]
                
                # Get file name from path
                binary_a_name = file_path.split('/')[-1].split('\\')[-1]
                self.load_binary_a_button.setText(f"Binary A: {binary_a_name}")
                
                # Enable export button if both binaries are loaded
                if self.binary_data_b is not None:
                    self.export_button.setEnabled(True)
            except Exception as e:
                print(f"Error loading binary file: {e}")
    
    def load_binary_b(self):
        """Handler for loading Binary File B"""
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Binary File B", "", "Binary Files (*.bin);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'rb') as f:
                    self.binary_data_b = bytearray(f.read())
                
                # If file is not exactly 512KB, pad or truncate it
                if len(self.binary_data_b) != 512 * 1024:
                    if len(self.binary_data_b) < 512 * 1024:
                        # Pad with zeros if too small
                        self.binary_data_b.extend([0] * (512 * 1024 - len(self.binary_data_b)))
                    else:
                        # Truncate if too large
                        self.binary_data_b = self.binary_data_b[:512 * 1024]
                
                # Get file name from path
                binary_b_name = file_path.split('/')[-1].split('\\')[-1]
                self.load_binary_b_button.setText(f"Binary B: {binary_b_name}")
                
                # Enable export button if both binaries are loaded
                if self.binary_data_a is not None:
                    self.export_button.setEnabled(True)
            except Exception as e:
                print(f"Error loading binary file: {e}")

    def on_item_selection_changed(self):
        """Handle when a different item is selected in the table."""
        selected_items = self.table_widget.selectedItems()
        if not selected_items:
            return
            
        # Since the selection is by row, all items in the row are selected
        # We can use the first item's row to access what we need
        row = selected_items[0].row()
        self.highlight_map_from_table(row)
    
    def on_cell_entered(self, row, column):
        """Handle when mouse hovers over a cell."""
        # Skip highlighting during active resize to improve performance
        if not self.is_resizing:
            self.highlight_map_from_table(row)
    
    def highlight_map_from_table(self, row):
        """Highlight the map based on the selected row in the table."""
        # Get map titles from the table
        file_a_title = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ""
        file_b_title = self.table_widget.item(row, 4).text() if self.table_widget.item(row, 4) else ""
        
        start_offset = self.start_offset_slider.value() * 16
        end_offset = self.end_offset_slider.value() * 16
        image_width, image_height = self.visualization_width, self.visualization_height
        selected_range = end_offset - start_offset
        
        scale = self.get_scaling(selected_range)
        bytes_per_row = image_width // scale

        highlighted_image = self.base_image.copy()
        
        # Highlight map from file A if available
        if file_a_title and file_a_title in self.map_entries:
            entry = self.map_entries[file_a_title]
            if entry.address_a is not None:
                color = COLOR_HIGHLIGHT_MATCH.copy() if entry.category == 'green' else COLOR_HIGHLIGHT_MISMATCH.copy() if entry.category == 'red' else COLOR_HIGHLIGHT_HOVERED.copy()
                #print(color)
                # Highlight the map
                for address in range(max(entry.address_a, start_offset), min(entry.address_a + entry.size_a, end_offset)):
                    relative_address = address - start_offset
                    row_idx = relative_address // bytes_per_row
                    col = relative_address % bytes_per_row
                    block_x = col * scale
                    block_y = row_idx * scale
                    for dx in range(scale):
                        for dy in range(scale):
                            x, y = block_x + dx, block_y + dy
                            if x < image_width and y < image_height:
                                highlighted_image[y, x] = color.copy()
        
        # Highlight map from file B if available and either:
        # 1. It's a different map (different title), or
        # 2. It's the same map but at a different address (yellow category)
        if file_b_title and file_b_title in self.map_entries:
            entry = self.map_entries[file_b_title]
            # Check if we should highlight file B region (different title or yellow category)
            if entry.address_b is not None and (file_b_title != file_a_title or entry.category == 'yellow'):
                color = COLOR_HIGHLIGHT_COUNTERPART.copy() if entry.category == 'yellow' else COLOR_HIGHLIGHT_MISMATCH.copy()
                
                # Highlight the map
                for address in range(max(entry.address_b, start_offset), min(entry.address_b + entry.size_b, end_offset)):
                    relative_address = address - start_offset
                    row_idx = relative_address // bytes_per_row
                    col = relative_address % bytes_per_row
                    block_x = col * scale
                    block_y = row_idx * scale
                    for dx in range(scale):
                        for dy in range(scale):
                            x, y = block_x + dx, block_y + dy
                            if x < image_width and y < image_height:
                                highlighted_image[y, x] = color.copy()
                
        self.label.setPixmap(QPixmap.fromImage(numpy_to_qimage(highlighted_image)))

    def toggle_checkboxes_in_selected_rows(self, clicked_row=None):
        """Set all checkboxes in the selected rows to the same state as the clicked checkbox."""
        selected_rows = set([index.row() for index in self.table_widget.selectedIndexes()])
        if not selected_rows:
            return
            
        # Get the state from the clicked checkbox if provided, otherwise use the first selected row
        if clicked_row is not None and clicked_row in selected_rows:
            clicked_checkbox = self.table_widget.item(clicked_row, 0)
            if clicked_checkbox:
                new_state = clicked_checkbox.checkState()
            else:
                return
        else:
            # Fallback - use the first selected row's state
            first_row = min(selected_rows)
            clicked_checkbox = self.table_widget.item(first_row, 0)
            if clicked_checkbox:
                new_state = clicked_checkbox.checkState()
            else:
                return
            
        
        # Temporarily disconnect the itemChanged signal to prevent multiple updates
        self.table_widget.itemChanged.disconnect(self.on_item_check_changed)
        
        try:
            # Set all checkboxes in selected rows to the same state as the clicked checkbox
            for row in selected_rows:
                # Set the "Include" checkbox (column 0)
                checkbox_item = self.table_widget.item(row, 0)
                if checkbox_item:
                    checkbox_item.setCheckState(new_state)
                    
                    # Update the map entry's checked state
                    file_a_title = self.table_widget.item(row, 3).text() if self.table_widget.item(row, 3) else ""
                    file_b_title = self.table_widget.item(row, 4).text() if self.table_widget.item(row, 4) else ""
                    
                    if file_a_title and file_a_title in self.map_entries:
                        self.map_entries[file_a_title].checked = (new_state == Qt.Checked)
                    if file_b_title and file_b_title in self.map_entries and file_b_title != file_a_title:
                        self.map_entries[file_b_title].checked = (new_state == Qt.Checked)
                    
                    # Handle linked maps with same start address
                    if file_a_title:
                        self.update_linked_map_checks(file_a_title, new_state == Qt.Checked)
        finally:
            # Reconnect the signal
            self.table_widget.itemChanged.connect(self.on_item_check_changed)
            
        # Update visualization
        self.update_visual_representation()

    def update_color_counts(self):
        """Update the checkbox labels with the current counts of each color category"""
        # Count maps in each color category
        green_count = yellow_count = red_count = 0
        
        for title, entry in self.map_entries.items():
            if entry.category == 'green':
                green_count += 1
            elif entry.category == 'yellow':
                yellow_count += 1
            elif entry.category == 'red':
                red_count += 1
        
        # Update instance variables
        self.green_count = green_count
        self.yellow_count = yellow_count
        self.red_count = red_count
        
        # Update checkbox labels
        self.green_cb.setText(f"G ({green_count})")
        self.yellow_cb.setText(f"Y ({yellow_count})")
        self.red_cb.setText(f"R ({red_count})")

# Main execution
if __name__ == '__main__':
    app = QApplication(sys.argv)
    
    # Apply dark theme stylesheet by default
    app.setStyleSheet(DARK_STYLESHEET)
    
    # Create main window without loading files
    main_window = MainWindow()
    main_window.setWindowTitle("MS4X Map Loader v1.0.0")
    
    # Set the window icon
    icon_path = "m:\\Programming\\python\\maploader\\icon.png"
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))
    
    main_window.resize(1200, 800)
    main_window.show()
    
    sys.exit(app.exec_())