"""Utilities for handling backend functions."""
import os
import pickle
import subprocess
import sys
import threading

import numpy as np
import pandas as pd
import pygame
from PIL import Image

try:
    from tkinter import Tk, filedialog, messagebox, ttk
    from tkinter.constants import S
    from matplotlib import figure
    from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                                   NavigationToolbar2Tk)
except Exception:
    pass

def _mac_open_file(title="Open Thermal Image"):
    script = f'''
    try
        set chosen to (choose file with prompt "{title}" of type {{"public.image", "public.data", "public.item"}})
        return POSIX path of chosen
    on error
        return ""
    end try
    '''
    try:
        proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        return proc.stdout.strip()
    except Exception:
        return ""

def _mac_save_file(prompt="Save current image", default_name="thermal_output.png"):
    script = f'''
    try
        set chosen to (choose file name with prompt "{prompt}" default name "{default_name}")
        return POSIX path of chosen
    on error
        return ""
    end try
    '''
    try:
        proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        return proc.stdout.strip()
    except Exception:
        return ""

def _mac_ask_question(title, message):
    escaped_msg = message.replace('"', '\\"')
    script = f'''
    try
        set resp to button returned of (display dialog "{escaped_msg}" buttons {{"No", "Yes"}} default button "Yes")
        if resp is "Yes" then
            return "yes"
        else
            return "no"
        end if
    on error
        return "no"
    end try
    '''
    try:
        proc = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
        return proc.stdout.strip()
    except Exception:
        return "no"

def _mac_show_warning(title, message):
    escaped_msg = message.replace('"', '\\"')
    escaped_title = title.replace('"', '\\"')
    script = f'''
    try
        display dialog "{escaped_msg}" with title "{escaped_title}" buttons {{"OK"}} default button "OK" with icon caution
    on error
    end try
    '''
    try:
        subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    except Exception:
        pass

def _mac_show_info(title, message):
    escaped_msg = message.replace('"', '\\"')
    escaped_title = title.replace('"', '\\"')
    script = f'''
    try
        display dialog "{escaped_msg}" with title "{escaped_title}" buttons {{"OK"}} default button "OK"
    on error
    end try
    '''
    try:
        subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    except Exception:
        pass

def showwarning(title="Warning", message=""):
    if sys.platform == "darwin":
        _mac_show_warning(title, message)
    else:
        try:
            from tkinter import messagebox
            messagebox.showwarning(title=title, message=message)
        except Exception:
            print(f"[{title}] {message}")

class SaveData:
    """Empty data class."""

    pass


class TableView(threading.Thread):
    """Tkinter thread constituting the table."""

    def __init__(self):
        """Initializer for table thread."""
        threading.Thread.__init__(self)
        self.initialized = False
        self.data = []
        self.start()

    def addRow(self, entry):
        """Add row to table."""
        entry[1:] = [round(ent, 3) for ent in entry[1:]]
        if hasattr(self, 'treev'):
            try:
                self.treev.insert("", "end", text="L1", values=entry)
            except Exception:
                pass
        self.data.append(entry)

    def getDF(self):
        """Get table values as a pandas data frame."""
        data = pd.DataFrame(self.data, columns=["Element", "Min", "Max", "Average"])
        data.set_index("Element", inplace=True)
        return data

    def killTable(self):
        """Kill table thread."""
        if hasattr(self, 'root'):
            try:
                self.root.quit()
                self.root.update()
            except Exception:
                pass

    def run(self):
        """Run."""
        try:
            self.root = Tk()
            self.root.protocol("WM_DELETE_WINDOW", lambda: None)
            self.root.title("Table")

            self.treev = ttk.Treeview(self.root, selectmode="browse")
            self.treev.pack(side="right")
            self.treev.pack(side="right")

            verscrlbar = ttk.Scrollbar(
                self.root, orient="vertical", command=self.treev.yview
            )
            verscrlbar.pack(side="right", fill="x")

            self.treev.configure(xscrollcommand=verscrlbar.set)
            self.treev["columns"] = ("1", "2", "3", "4")
            self.treev["show"] = "headings"

            self.treev.column("1", width=100, anchor="c")
            self.treev.column("2", width=100, anchor="se")
            self.treev.column("3", width=100, anchor="se")
            self.treev.column("4", width=100, anchor="se")

            self.treev.heading("1", text="Element")
            self.treev.heading("2", text="min")
            self.treev.heading("3", text="max")
            self.treev.heading("4", text="average")

            self.initialized = True
            self.root.mainloop()
        except Exception as e:
            print(f"[Info] Tkinter Table GUI window skipped in secondary thread ({e}). Data recorded in background.")
            self.initialized = True


class Figure(threading.Thread):
    """Matplotlib threading using tkinter."""

    def __init__(self, plots):
        """Figure thread initializer."""
        threading.Thread.__init__(self)
        self.plots = plots
        self.start()

    def killFigure(self):
        """Kill figure thread."""
        if hasattr(self, 'root'):
            try:
                self.root.quit()
                self.root.update()
            except Exception:
                pass

    def saveFig(self, filename):
        """Save figure."""
        if hasattr(self, 'fig'):
            self.fig.savefig(filename)

    def run(self):
        """Run."""
        try:
            self.root = Tk()
            self.root.protocol("WM_DELETE_WINDOW", lambda: None)
            self.root.title("Plot")

            self.fig = figure.Figure()
            plot = self.fig.add_subplot(111)

            for x, y, label in self.plots:
                plot.plot(x, y, label=label)
            plot.legend()

            canvas = FigureCanvasTkAgg(self.fig, master=self.root)
            canvas.draw()
            canvas.get_tk_widget().pack()

            toolbar = NavigationToolbar2Tk(canvas, self.root)
            toolbar.update()

            canvas.get_tk_widget().pack()

            self.root.mainloop()
        except Exception as e:
            print(f"[Info] Tkinter Figure GUI window skipped in secondary thread ({e}).")


class WindowHandler:
    """Handles external(graphs/tables) windows."""

    def __init__(self):
        """Initializer for window handler."""
        self.mainTable = None
        self.mainFigure = None
        self.plots = []
        self.killed = False
        self.rects = []

    def __del__(self):
        if not self.killed:
            self.killThreads()

    def killThreads(self):
        """Kill all running threads."""
        if self.mainTable:
            self.mainTable.killTable()
            if self.mainTable.is_alive():
                self.mainTable.join(timeout=1.0)
        if self.mainFigure:
            self.mainFigure.killFigure()
            if self.mainFigure.is_alive():
                self.mainFigure.join(timeout=1.0)
        self.killed = True

    def addRects(self, rects):
        """Add rectangle coordinates."""
        for rect in rects:
            self.rects.append(rect)

    def addToTable(self, entry):
        """Add entry to table."""
        if self.mainTable is None:
            self.mainTable = TableView()
        self.mainTable.addRow(entry)

    def loadGraph(self, plots_in):
        """Load the graph window."""
        self.plots = plots_in
        if self.plots:
            self.mainFigure = Figure(self.plots)

    def linePlot(
        self, mat, label, startPoint, endPoint, resolution=100, interpolation="bilinear"
    ):
        """Plot line graph."""
        direcion = endPoint - startPoint
        distance = np.linalg.norm(direcion)
        distances = []
        values = []

        for i in range(resolution):

            point = startPoint + i * direcion / resolution

            if interpolation == "bilinear":
                x = int(point[0])
                y = int(point[1])
                dx = point[0] - x
                dy = point[1] - y
                val = (
                    np.array([[1 - dx, dx]])
                    @ mat[x : x + 2, y : y + 2]
                    @ np.array([[1 - dy], [dy]])
                )[0, 0]

            if interpolation == "nearest_neighbour":
                val = mat[round(point[0]), round(point[1])]

            values.append(val)
            distances.append(i * distance / resolution)

        self.addToTable([label, min(values), max(values), sum(values) / len(values)])

        if self.mainFigure:
            self.mainFigure.killFigure()
        self.plots.append([distances, values, label])
        self.mainFigure = Figure(self.plots)


def saveImage(window):
    """Save current image."""
    imageSurface = window.imsurf
    overlays = window.overlays
    exthandler = window.exthandler

    if sys.platform == "darwin":
        file = _mac_save_file("Save Thermal Image", "thermal_analysis.png")
    else:
        try:
            from tkinter import Tk, filedialog
            root = Tk()
            root.withdraw()
            file = filedialog.asksaveasfilename(
                filetypes=[("PNG Image", "*.png"), ("TIFF Image", "*.tiff"), ("CSV File", "*.csv")]
            )
            root.destroy()
        except Exception:
            file = ""

    if not file:
        return

    filename = file.split("/")[-1]

    if filename.endswith(".tiff"):
        ask = _mac_ask_question if sys.platform == "darwin" else messagebox.askquestion
        if ask("Before we proceed", f"Are you sure you want to export image as {filename} with Kelvin values and not a false colour mapping?") == "yes":
            tiffExport(window, file)
        else:
            if sys.platform == "darwin":
                _mac_show_info("Export Cancelled", f"You have cancelled the process of exporting {filename}")
            else:
                messagebox.showinfo("Export Cancelled", f"You have cancelled the process of exporting {filename}")

    elif filename.endswith(".csv"):
        ask = _mac_ask_question if sys.platform == "darwin" else messagebox.askquestion
        if ask("Before we proceed", f"Are you sure you want to export image as {filename} with Kelvin values and not a false colour mapping?") == "yes":
            csvExport(window, file)
        else:
            if sys.platform == "darwin":
                _mac_show_info("Export Cancelled", f"You have cancelled the process of exporting {filename}")
            else:
                messagebox.showinfo("Export Cancelled", f"You have cancelled the process of exporting {filename}")

    else:
        print(file)
        pngExport(window, file, imageSurface, overlays, exthandler)


def pngExport(window, filename, imageSurface, overlays, exthandler):
    """Function to export image as .PNG format

    Args:
        window (Window): object that refers to main window
        filename (str): Filename with extension. Eg: example.txt
        imageSurface (pygame.SURFACE): [description]
        overlays ([type]): [description]
        exthandler ([type]): [description]
    """
    ask = _mac_ask_question if sys.platform == "darwin" else messagebox.askquestion
    if ask("Save options", "Do you want to save with the annotations?") == "yes":
        imageSurface.blit(overlays, (0, 0))

        data = SaveData()
        data.plots = window.exthandler.plots
        data.rects = window.exthandler.rects
        data.tableEntries = []
        data.mat = window.mat
        data.mat_orig = window.mat_orig
        data.mat_emm = window.mat_emm
        data.raw = window.raw
        data.meta = window.meta
        data.overlays = pygame.image.tostring(overlays, "RGBA")

        if exthandler.mainFigure:
            exthandler.mainFigure.saveFig(
                ".".join(filename.split(".")[:-1]) + "_plot.png"
            )
        if exthandler.mainTable:
            with pd.ExcelWriter(
                ".".join(filename.split(".")[:-1]) + "_values.xlsx",
                engine="xlsxwriter",
            ) as writer:
                exthandler.mainTable.getDF().to_excel(writer, sheet_name="Table")
                if len(data.plots) > 0:
                    pd.DataFrame(
                        [plot[1] for plot in data.plots],
                        index=[f"l{i+1}" for i in range(len(data.plots))],
                    ).to_excel(writer, sheet_name="Lines")
                data.tableEntries = exthandler.mainTable.data
                for i, (x1, x2, y1, y2) in enumerate(data.rects):
                    pd.DataFrame(
                        data.mat_emm[y1:y2, x1:x2],
                        index=y1 + np.arange(y2 - y1),
                        columns=x1 + np.arange(x2 - x1),
                    ).to_excel(writer, sheet_name=f"Area{i+1}")

        with open(".".join(filename.split(".")[:-1]) + ".pkl", "wb") as f:
            pickle.dump(data, f, -1)

    imgdata = pygame.surfarray.pixels3d(imageSurface).astype(np.uint8)
    imgdata = np.swapaxes(imgdata, 0, 1)
    Image.fromarray(imgdata).save(filename)
    print("Saved successfully")


def tiffExport(window, filename):
    """Function to export as .tiff File

    Args:
        window (class Window object): Window object that refers to main window
        filename (str): Filename with full path and extension. Eg: /home/user/hello/example.txt
    """
    imgKelvin = Image.fromarray(window.thermalData)
    imgKelvin.save(filename)
    print(f"Sucessfully saved {filename} as tiff file")


def csvExport(window, filename):
    """Function to export as .csv File

    Args:
        window (class Window object): Window class object that refers to main window
        filename (str): Filename with full path and extension. Eg: /home/user/hello/example.txt
    """
    np.savetxt(filename, window.thermalData, delimiter=",")
    print(f"Sucessfully saved {filename} as .csv file")


def openImage():
    """Open new image."""
    if sys.platform == "darwin":
        return _mac_open_file("Open Thermal Image")
    try:
        from tkinter import Tk, filedialog
        root = Tk()
        root.withdraw()
        filename = filedialog.askopenfilename(title="Open Thermal Image")
        root.destroy()
        return filename
    except Exception:
        return ""
