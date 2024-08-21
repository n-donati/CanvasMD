# CanvasMD

## Overview

CanvasMD is a powerful command-line interface application that allows you to interact with the Canvas Learning Management System directly from your terminal. This tool is designed for students and educators who prefer a streamlined, keyboard-driven workflow and want to manage their Canvas tasks efficiently without the need to open a web browser.

## Features

- **Authentication**: Securely log in to your Canvas account using an access token.
- **Course Management**: View and navigate through your enrolled courses.
- **Assignment Tracking**: 
  - List all assignments for a selected course.
  - View assignment details including due dates and submission status.
  - Distinguish between submitted and not-submitted assignments.
- **File Submission**: Upload and submit files for assignments directly from your local machine.
- **User-Friendly Interface**: Navigate through menus using arrow keys and enter key.
- **Offline Settings**: Configure and save preferences for a personalized experience.

## Getting Started

### Prerequisites

- Python 3.6 or higher
- `pip` for installing dependencies

### Installation

1. Clone this repository:
   ```
   git clone https://github.com/ndonatti/CanvasMD.git
   cd CanvasMD
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

### Usage

1. Run the tool using:
   ```
   python canvasmd.py
   ```

2. When you first run the application, you'll be prompted to enter your Canvas access token. To get your token:
   - Log in to your Canvas account in a web browser
   - Go to Account > Settings > New Access Token
   - Generate a new token and copy it
   - In the CanvasMD application, choose the "Settings" option from the main menu
   - Select "Save Token" and paste your access token when prompted

3. Navigate through the menus using the arrow keys and press Enter to select an option.

### Optional: Create a Direct Alias

To launch CanvasMD more conveniently, you can create an alias:

1. Open your shell configuration file (e.g., `~/.bashrc`, `~/.zshrc`, or `~/.bash_profile`)
2. Add the following line, replacing `/path/to/CanvasMD` with the actual path to your CanvasMD directory:
   ```
   alias canvas='python /path/to/CanvasMD/canvasmd.py'
   ```
3. Save the file and reload your shell configuration:
   ```
   source ~/.bashrc  # or ~/.zshrc, ~/.bash_profile, etc.
   ```
4. Now you can launch CanvasMD from anywhere by simply typing `canvas` in your terminal

## Why Use CanvasMD?

1. **Efficiency**: Quickly access your courses and assignments without waiting for web pages to load.
2. **Distraction-Free**: Focus on your tasks without the clutter of a full web interface.
3. **Terminal Integration**: Seamlessly integrate Canvas interactions into your existing terminal workflow.
4. **Keyboard-Centric**: Perfect for users who prefer keyboard navigation over mouse interactions.
5. **Low-Bandwidth**: Ideal for situations where you have limited internet connectivity.

## Contributing

We welcome contributions to CanvasMD! Please feel free to submit issues, feature requests, or pull requests.

---

Happy Canvas-ing from your terminal!
