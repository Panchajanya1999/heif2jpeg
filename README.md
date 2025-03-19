# HEIF to JPEG Converter

A modern, user-friendly application to convert HEIF/HEIC images to JPEG format with advanced options.

## Features

- Batch convert HEIF/HEIC images to JPEG
- Adjust JPEG quality
- Preserve EXIF metadata
- Preserve folder structure
- Modern and intuitive user interface
- Cross-platform (Windows, macOS, Linux)

## Installation

### Download Prebuilt Binaries

Download the latest release for your platform from the [Releases](https://github.com/Panchajanya1999/heif2jpeg/releases) page.

- **Windows**: Download `heif-converter-windows.zip`, extract and run `HEIF_Converter_Windows.exe`
- **macOS**: Download `heif-converter-macos.zip`, extract and run `HEIF_Converter_macOS`
- **Linux**: Download `heif-converter-linux.zip`, extract and run `HEIF_Converter_Linux`

### Building from Source

1. Clone the repository:

   ```bash
   git clone https://github.com/yourusername/heif-converter.git
   cd heif-converter
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the application:

   ```bash
   python hif2jpegUI.py
   ```

## Development

### Setup Development Environment

1. Create a virtual environment:

   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. Install development dependencies:

   ```bash
   pip install -r requirements.txt
   pip install pyinstaller pytest
   ```

### Building Locally

To build the executable locally:

```bash
pyinstaller heif_converter.spec
```

or, you can run the full command with options:

```bash
pyinstaller --name="HEIF_Converter" --windowed --onefile --add-data="$(pip show sv-ttk | grep Location | cut -d ' ' -f 2)/sv_ttk:sv_ttk" hif2jpegUI.py
```

The executable will be created in the `dist` directory.

## Continuous Integration & Deployment

This project uses GitHub Actions for continuous integration and deployment. The workflow automatically builds executables for Windows, macOS, and Linux, and publishes them as GitHub Releases.

### Release Process

#### Automatic Releases

1. To create a new release, use the provided release script:

   ```bash
   python release.py --patch --message "Fixed bug in EXIF handling"
   ```

   Options:
   - `--major`: Bump major version (1.0.0 → 2.0.0)
   - `--minor`: Bump minor version (1.0.0 → 1.1.0)
   - `--patch`: Bump patch version (1.0.0 → 1.0.1)
   - `--version`: Set specific version
   - `--message` or `-m`: Release message

2. Push the changes and tag:

   ```bash
   git push origin main
   git push origin v1.0.1  # Use the tag shown in the script output
   ```

3. GitHub Actions will automatically:
   - Build the application for all platforms
   - Create a GitHub Release
   - Attach the executables to the release

#### Manual Releases

1. Update the version in `hif2jpegUI.py`
2. Commit the changes
3. Create and push a tag starting with 'v' (e.g., v1.0.0):

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

### Workflow Details

The GitHub Actions workflow runs on tag pushes and consists of:

1. **Build Job**: Builds the application on Windows, macOS, and Linux
2. **Release Job**: Creates a GitHub Release with the built executables

The workflow configuration is located in `.github/workflows/build-and-release.yml`.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the Apache License - see the LICENSE file for details.
