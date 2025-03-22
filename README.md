# MS4X Map Loader

Simple tool for MS43 (for now) based ECUs that let you easily copy maps between different versions of Firmware of MS43 Siemens ECU using TunerPro definitions.

Get latest release exe [HERE](https://github.com/handmade0octopus/ms4x-maploader/releases/latest/download/maploader.exe) <==


# Manual run

You need Python and pip.

```sh
pip install PyQt5 numpy
```

Run:
```sh
python maploader.pyw
```

# Create binary

Get PyInstaller:
```sh
pip install pyinstaller
```

Then package using:
```sh
pyinstaller --onefile maploader.pyw -i icon.ico --version-file file_version_info.txt
```

# License MIT
Please use with caution.
