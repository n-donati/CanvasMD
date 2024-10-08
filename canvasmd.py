import os
import json
import requests
import curses
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional, Any, Tuple, Union

# Constants
API_BASE_URL = 'https://experiencia21.tec.mx/api/v1'
ENV_FILE = '.env'
SETTINGS_FILE = 'canvasmd_settings.json'
USER_TIMEZONE_OFFSET = -6

# Get the directory of the script
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

class CanvasAPI:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.headers = {'Authorization': f'Bearer {access_token}'}
        self.session = requests.Session()

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Optional[requests.Response]:
        try:
            url = f"{API_BASE_URL}/{endpoint}"
            response = self.session.request(method, url, headers=self.headers, timeout=10, **kwargs)
            response.raise_for_status()
            return response
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            return None

    def check_token_validity(self) -> bool:
        response = self._make_request("GET", "users/self")
        return response is not None and response.status_code == 200

    def get_username(self) -> str:
        response = self._make_request("GET", "users/self")
        if response and response.status_code == 200:
            return response.json().get('name', '')
        return ''

    def get_courses(self) -> List[Dict[str, Any]]:
        response = self._make_request("GET", "courses")
        if response and response.status_code == 200:
            return [course for course in response.json() if 'name' in course]
        return []

    def get_assignments(self, course_id: int) -> List[Dict[str, Any]]:
        response = self._make_request("GET", f"courses/{course_id}/assignments")
        if not response or response.status_code != 200:
            return []

        assignments = response.json()
        submissions = self.get_bulk_assignment_submissions(course_id, [a['id'] for a in assignments])
        
        current_time = datetime.now(timezone(timedelta(hours=USER_TIMEZONE_OFFSET)))
        filtered_assignments = []

        for assignment in assignments:
            if assignment.get('is_quiz_assignment'):
                continue

            due_date = self.parse_date(assignment.get('due_at'))
            
            if due_date is None or due_date > current_time:
                assignment['submitted'] = submissions.get(str(assignment['id']), {}).get('workflow_state') == 'submitted'
                filtered_assignments.append(assignment)

        return sorted(filtered_assignments, key=lambda x: (self.parse_date(x.get('due_at')) is None, self.parse_date(x.get('due_at')) or datetime.max.replace(tzinfo=timezone(timedelta(hours=USER_TIMEZONE_OFFSET)))))

    @staticmethod
    def parse_date(date_string: Optional[str]) -> Optional[datetime]:
        if not date_string:
            return None
        try:
            parsed_date = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")
            return parsed_date.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=USER_TIMEZONE_OFFSET)))
        except ValueError:
            return None

    def get_bulk_assignment_submissions(self, course_id: int, assignment_ids: List[int]) -> Dict[str, Any]:
        params = {'student_ids[]': 'self', 'assignment_ids[]': assignment_ids}
        response = self._make_request("GET", f"courses/{course_id}/students/submissions", params=params)
        if response and response.status_code == 200:
            return {str(sub['assignment_id']): sub for sub in response.json()}
        return {}

    def submit_file_assignment(self, course_id: int, assignment_id: int, file_path: str) -> Tuple[bool, str]:
        try:
            # Step 1: Get file upload URL
            file_params = {
                'name': os.path.basename(file_path),
                'size': os.path.getsize(file_path),
                'content_type': self._get_content_type(file_path),
            }
            response = self._make_request("POST", f"courses/{course_id}/assignments/{assignment_id}/submissions/self/files", data=file_params)
            if not response or response.status_code != 200:
                return False, f"Failed to get upload URL. Status: {response.status_code if response else 'N/A'}, Response: {response.text if response else 'No response'}"

            upload_data = response.json()
            upload_url = upload_data.get('upload_url')
            upload_params = upload_data.get('upload_params', {})

            if not upload_url:
                return False, f"Upload URL not found in response. Response: {upload_data}"

            # Step 2: Upload the file
            with open(file_path, 'rb') as file:
                files = {
                    'file': (os.path.basename(file_path), file, self._get_content_type(file_path))
                }
                upload_response = requests.post(upload_url, data=upload_params, files=files, timeout=60)

            if upload_response.status_code != 201:
                return False, f"File upload failed. Status: {upload_response.status_code}, Response: {upload_response.text}"

            file_data = upload_response.json()
            file_id = file_data.get('id')
            if not file_id:
                return False, f"File ID not found in upload response. Response: {file_data}"

            # Step 3: Submit the assignment
            submit_params = {
                'submission': {
                    'submission_type': 'online_upload',
                    'file_ids': [file_id]
                }
            }
            submit_response = self._make_request("POST", f"courses/{course_id}/assignments/{assignment_id}/submissions", json=submit_params)

            if not submit_response or submit_response.status_code != 201:
                return False, f"Assignment submission failed. Status: {submit_response.status_code if submit_response else 'N/A'}, Response: {submit_response.text if submit_response else 'No response'}"

            return True, "File uploaded and assignment submitted successfully!"

        except Exception as e:
            return False, f"An error occurred during file submission: {str(e)}"

    def _get_content_type(self, file_path: str) -> str:
        """Determine the correct MIME type for the file."""
        import mimetypes
        content_type, _ = mimetypes.guess_type(file_path)
        if content_type is None:
            # Default to application/octet-stream if type can't be guessed
            return 'application/octet-stream'
        return content_type

class Settings:
    def __init__(self):
        self.confirm_submit = True
        self.load_settings()

    def load_settings(self):
        settings_path = os.path.join(SCRIPT_DIR, SETTINGS_FILE)
        if os.path.exists(settings_path):
            try:
                with open(settings_path, 'r') as f:
                    saved_settings = json.load(f)
                    self.confirm_submit = saved_settings.get('confirm_submit', True)
            except json.JSONDecodeError:
                print(f"Error reading settings file. Using default settings.")

    def save_settings(self):
        settings_path = os.path.join(SCRIPT_DIR, SETTINGS_FILE)
        try:
            with open(settings_path, 'w') as f:
                json.dump({'confirm_submit': self.confirm_submit}, f)
        except IOError:
            print(f"Error saving settings to file.")

class EnvironmentManager:
    @staticmethod
    def load_env():
        env_path = os.path.join(SCRIPT_DIR, ENV_FILE)
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value

    @staticmethod
    def save_access_token(token: str):
        env_path = os.path.join(SCRIPT_DIR, ENV_FILE)
        try:
            with open(env_path, 'w') as f:
                f.write(f"ACCESS_TOKEN={token}\n")
            os.environ['ACCESS_TOKEN'] = token
        except IOError:
            print(f"Error saving access token to file.")

class UI:
    def __init__(self, stdscr):
        self.stdscr = stdscr
        self.height, self.width = stdscr.getmaxyx()
        self.ascii_width = 35
        self._init_colors()

    def _init_colors(self):
        curses.start_color()
        curses.init_pair(1, curses.COLOR_WHITE, curses.COLOR_BLACK)  # Normal
        curses.init_pair(2, curses.COLOR_BLACK, curses.COLOR_WHITE)  # Highlight
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)  # Title
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)  # Header
        curses.init_pair(5, curses.COLOR_GREEN, curses.COLOR_BLACK)  # Due Date
        curses.init_pair(6, curses.COLOR_MAGENTA, curses.COLOR_BLACK)  # Category

    def display_menu(self, items: List[str], title: str, content: str = "", selectable_indices: Optional[List[int]] = None) -> Optional[int]:
        if selectable_indices is None:
            selectable_indices = list(range(len(items)))
        
        current_row = min(selectable_indices) if selectable_indices else 0
        while True:
            self.stdscr.clear()
            self._draw_layout(title, content)
            self._draw_menu_items(items, current_row, selectable_indices)
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key == curses.KEY_UP:
                current_row = self._get_previous_selectable(current_row, selectable_indices)
            elif key == curses.KEY_DOWN:
                current_row = self._get_next_selectable(current_row, selectable_indices)
            elif key in [curses.KEY_ENTER, 10, 13]:
                return current_row
            elif key == 27:  # ESC
                return None

    def _get_next_selectable(self, current: int, selectable: List[int]) -> int:
        for i in selectable:
            if i > current:
                return i
        return current

    def _get_previous_selectable(self, current: int, selectable: List[int]) -> int:
        for i in reversed(selectable):
            if i < current:
                return i
        return current

    def _draw_layout(self, title: str, content: str):
        self._draw_header()
        self._draw_ascii_art()
        self._draw_title(title)
        self._draw_content(content)

    def _draw_content(self, content: str):
        content_lines = content.split('\n')
        start_y = 5
        start_x = 2
        max_width = self.width - self.ascii_width - 4
        max_lines = self.height - start_y - 3  # Leave space for the footer

        for idx, line in enumerate(content_lines):
            if idx < max_lines:
                truncated_line = line[:max_width]
                self.stdscr.addstr(start_y + idx, start_x, truncated_line)
            else:
                self.stdscr.addstr(start_y + max_lines - 1, start_x, "... (message truncated)")
                break

    def _draw_header(self):
        login_status = f"Logged in: {CanvasApp.logged_in}"
        current_time = datetime.now().strftime("%H:%M - %d/%m/%Y")
        self.stdscr.attron(curses.color_pair(4))
        self.stdscr.addstr(0, 0, login_status)
        self.stdscr.addstr(0, self.width - len(current_time) - 1, current_time)
        name_section = f"Name: {CanvasApp.username if CanvasApp.logged_in else 'N/A'}"
        self.stdscr.addstr(1, 0, name_section)
        self.stdscr.attroff(curses.color_pair(4))

    def _draw_ascii_art(self):
        ascii_art = [
            "         ████████          ",
            "     ███  ██████   ███     ",
            "   █████           ████    ",
            " █████      ██      █████  ",
            "       ██        ██        ",
            "██                       ██",
            "████ ██             ██ ████",
            "████                   ████",
            "██                      ███",
            "       ██        ██        ",
            " █████      ██      █████  ",
            "   █████           █████   ",
            "     ███   █████   ███     ",
            "         ████████          ",
            "                           "
        ]
        start_y = (self.height - len(ascii_art)) // 2
        start_x = self.width - self.ascii_width

        for idx, line in enumerate(ascii_art):
            self.stdscr.addstr(start_y + idx, start_x, line.center(self.ascii_width), curses.color_pair(1))

    def _draw_title(self, title: str):
        self.stdscr.attron(curses.color_pair(3) | curses.A_BOLD)
        self.stdscr.addstr(3, 2, title)
        self.stdscr.attroff(curses.color_pair(3) | curses.A_BOLD)


    def display_menu_with_horizontal_options(self, items: List[str], title: str, horizontal_options: List[str]) -> Union[int, str, None]:
        current_row = 0
        current_col = 0
        while True:
            self.stdscr.clear()
            self._draw_layout(title, "")
            self._draw_menu_items(items, current_row, list(range(len(items))))
            self._draw_horizontal_options(horizontal_options, current_row, current_col, len(items))
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key == curses.KEY_UP and current_row > 0:
                current_row -= 1
            elif key == curses.KEY_DOWN and current_row < len(items):
                current_row += 1
            elif key == curses.KEY_LEFT and current_col > 0:
                current_col -= 1
            elif key == curses.KEY_RIGHT and current_col < len(horizontal_options) - 1:
                current_col += 1
            elif key in [curses.KEY_ENTER, 10, 13]:
                if current_row == len(items):
                    return horizontal_options[current_col].lower()[2:-2]  # Return "exit" or "config"
                else:
                    return current_row
            elif key == 27:  # ESC
                return None

    def _draw_menu_items(self, items: List[str], current_row: int, selectable_indices: List[int]):
        menu_start_y = self.height - len(items) - 4  # Adjusted to leave space for horizontal options
        menu_width = self.width - self.ascii_width - 4
        x_start = 2

        for idx, item in enumerate(items):
            y = menu_start_y + idx
            if y >= self.height - 3:  # Adjusted to leave space for horizontal options
                break
            
            if idx not in selectable_indices:
                self.stdscr.attron(curses.color_pair(6) | curses.A_BOLD)
                self.stdscr.addstr(y, x_start, item.center(menu_width))
                self.stdscr.attroff(curses.color_pair(6) | curses.A_BOLD)
            else:
                color_pair = 2 if idx == current_row else 1
                self.stdscr.attron(curses.color_pair(color_pair))
                prefix = '> ' if idx == current_row else '  '
                self.stdscr.addstr(y, x_start, f"{prefix}{item:<{menu_width-2}}")
                self.stdscr.attroff(curses.color_pair(color_pair))
    
    def _draw_horizontal_options(self, options: List[str], current_row: int, current_col: int, num_items: int):
        y = self.height - 2
        total_width = sum(len(option) for option in options) + len(options) - 1  # -1 for spacing
        start_x = (self.width - self.ascii_width - total_width) // 2  # Centered in the main content area

        for idx, option in enumerate(options):
            x = start_x + sum(len(opt) for opt in options[:idx]) + idx
            if current_row == num_items and idx == current_col:
                self.stdscr.attron(curses.color_pair(2))
                self.stdscr.addstr(y, x, option)
                self.stdscr.attroff(curses.color_pair(2))
            else:
                self.stdscr.attron(curses.color_pair(1))
                self.stdscr.addstr(y, x, option)
                self.stdscr.attroff(curses.color_pair(1))


    def show_message(self, message: str, title: str):
        self.stdscr.clear()
        self._draw_layout(title, message)
        self.stdscr.refresh()

    def show_dismissable_message(self, message: str, title: str):
        while True:
            self.stdscr.clear()
            self._draw_layout(title, message)
            self.stdscr.addstr(self.height - 3, 2, "Press Enter to continue or ESC to go back")
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in [curses.KEY_ENTER, 10, 13]:  # Enter key
                break
            elif key == 27:  # ESC key
                return

    def wait(self, seconds: int):
        import time
        time.sleep(seconds)

    def get_input(self, prompt: str) -> str:
        self.stdscr.clear()
        self._draw_layout("Input", prompt)
        
        curses.echo()
        curses.curs_set(1)
        
        input_y, input_x = self.height - 3, 2
        self.stdscr.move(input_y, input_x)
        
        input_str = self.stdscr.getstr().decode('utf-8')
        
        curses.noecho()
        curses.curs_set(0)
        
        return input_str

    def file_browser(self, start_path: str = '.') -> Optional[str]:
        current_path = os.path.abspath(start_path)
        current_selection = 0

        while True:
            self.stdscr.clear()
            self._draw_layout("File Browser", f"Current directory: {current_path}")

            items = ['..'] + sorted([f for f in os.listdir(current_path) if os.path.isdir(os.path.join(current_path, f))]) + \
                    sorted([f for f in os.listdir(current_path) if os.path.isfile(os.path.join(current_path, f))])

            for idx, item in enumerate(items):
                y = 6 + idx
                if y >= self.height - 3:
                    break

                is_dir = os.path.isdir(os.path.join(current_path, item))
                item_str = f"{item}/" if is_dir else item
                color_pair = 2 if idx == current_selection else 1
                self.stdscr.attron(curses.color_pair(color_pair))
                self.stdscr.addstr(y, 2, f"{'>' if idx == current_selection else ' '} {item_str}")
                self.stdscr.attroff(curses.color_pair(color_pair))

            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key == curses.KEY_UP and current_selection > 0:
                current_selection -= 1
            elif key == curses.KEY_DOWN and current_selection < len(items) - 1:
                current_selection += 1
            elif key in [curses.KEY_ENTER, 10, 13]:
                if current_selection == 0:
                    current_path = os.path.dirname(current_path)
                    current_selection = 0
                else:
                    selected = items[current_selection]
                    selected_path = os.path.join(current_path, selected)
                    if os.path.isdir(selected_path):
                        current_path = selected_path
                        current_selection = 0
                    elif os.path.isfile(selected_path):
                        return selected_path
            elif key == 27:  # ESC
                return None

    def confirm_dialog(self, message: str) -> bool:
        while True:
            self.stdscr.clear()
            self._draw_layout("Confirm", message)
            self.stdscr.addstr(self.height - 3, 2, "Press Enter to confirm or ESC to cancel")
            self.stdscr.refresh()

            key = self.stdscr.getch()
            if key in [curses.KEY_ENTER, 10, 13]:
                return True
            elif key == 27:  # ESC
                return False

class CanvasApp:
    logged_in = False
    username = ''

    def __init__(self, stdscr):
        self.ui = UI(stdscr)
        self.api = None
        self.settings = Settings()

    def run(self):
        self.load_initial_token()
        if not self.logged_in:
            self.settings_menu()
        
        if self.logged_in:
            self.canvas_menu()

    def load_initial_token(self):
        self.ui.show_message("Initializing Canvas CLI...", "Loading")
        
        access_token = os.getenv('ACCESS_TOKEN')
        if access_token:
            self.ui.show_message("Validating saved access token...", "Loading")
            if self.validate_and_set_token(access_token):
                self.ui.show_message("Access token loaded successfully!", "Success")
                self.ui.wait(1)
            else:
                self.ui.show_message("Saved access token is invalid. Please set a new token in Settings.", "Error")
                self.ui.wait(2)
    
    def save_token(self, token: str):
        self.ui.show_message("Validating token...", "Please Wait")
        if self.validate_and_set_token(token):
            EnvironmentManager.save_access_token(token)
            self.ui.show_message("Access Token saved and validated successfully!", "Success")
            self.ui.wait(2)  # Wait for 2 seconds to show the success message
        else:
            self.ui.show_dismissable_message("Invalid Token. Please try again.", "Error")

    def validate_and_set_token(self, token: str) -> bool:
        temp_api = CanvasAPI(token)
        if temp_api.check_token_validity():
            self.api = temp_api
            CanvasApp.logged_in = True
            CanvasApp.username = self.api.get_username()
            return True
        return False

    def canvas_menu(self):
        if not self.logged_in:
            self.ui.show_message("Please log in first.", "Error")
            return

        courses = self.api.get_courses()
        if not courses:
            self.ui.show_message("No courses found.", "Error")
            return

        while True:
            course_names = [course['name'] for course in courses]
            horizontal_options = ["[ Exit ]", "[ Config ]"]
            
            choice = self.ui.display_menu_with_horizontal_options(
                course_names, 
                "Available Courses", 
                horizontal_options
            )
            
            if choice == "exit":
                return
            elif choice == "config":
                self.settings_menu()
            elif choice is not None:
                self.display_assignments(courses[choice])

    def display_assignments(self, course: Dict[str, Any]):
        assignments = self.api.get_assignments(course['id'])
        if not assignments:
            self.ui.show_message("No assignments found for this course.", "Notice")
            return

        not_submitted = [a for a in assignments if not a['submitted']]
        submitted = [a for a in assignments if a['submitted']]

        while True:
            menu_items = ["NOT SUBMITTED"] + [self.format_assignment_item(a) for a in not_submitted] + \
                         ["SUBMITTED"] + [self.format_assignment_item(a) for a in submitted] + \
                         ["[ Go Back ]"]

            selectable_indices = list(range(1, len(not_submitted) + 1)) + \
                                 list(range(len(not_submitted) + 2, len(menu_items)))

            choice = self.ui.display_menu(menu_items, f"Assignments for {course['name']}", selectable_indices=selectable_indices)
            
            if choice is None or menu_items[choice] == "[ Go Back ]":
                break
            elif choice < len(not_submitted) + 1:
                selected_assignment = not_submitted[choice - 1]
            else:
                selected_assignment = submitted[choice - len(not_submitted) - 2]
            self.display_assignment_details(selected_assignment)

    def format_assignment_item(self, assignment: Dict[str, Any]) -> str:
        due_date = self.format_due_date(assignment.get('due_at'))
        return f"{assignment['name']} (Due: {due_date})"

    def display_assignment_details(self, assignment: Dict[str, Any]):
        due_date = self.format_due_date(assignment.get('due_at'))
        file_format = assignment.get('submission_types', ['No File Format'])[0]

        details = (
            f"Assignment: {assignment['name']}\n"
            f"Due Date: {due_date}\n"
            f"File Format: {file_format}\n"
        )

        while True:
            choice = self.ui.display_menu(["Upload Local File", "[ Go Back ]"], "Assignment Details", details)
            if choice == 0:
                self.upload_file(assignment)
            elif choice == 1 or choice is None:
                break

    def upload_file(self, assignment: Dict[str, Any]):
        file_path = self.ui.file_browser()
        if not file_path:
            return

        if self.settings.confirm_submit:
            confirm_message = (
                f"You are about to submit the following file:\n\n"
                f"File: {os.path.basename(file_path)}\n"
                f"For assignment: {assignment['name']}\n\n"
                f"Do you want to proceed with the submission?"
            )
            if not self.ui.confirm_dialog(confirm_message):
                self.ui.show_message("File upload cancelled.", "Notice")
                return

        content_type = self.api._get_content_type(file_path)
        self.ui.show_message(f"Uploading file: {os.path.basename(file_path)}...\nContent-Type: {content_type}", "Upload")
        
        success, message = self.api.submit_file_assignment(
            assignment['course_id'],
            assignment['id'],
            file_path
        )
        if success:
            self.ui.show_message(f"{message}\nContent-Type used: {content_type}", "Success")
            # Wait for a short time to show the success message
            self.ui.wait(0.5)
        else:
            error_message = f"Failed to upload file or submit assignment.\n\nError details:\n{message}\nContent-Type used: {content_type}"
            self.ui.show_dismissable_message(error_message, "Error")

    def logout(self):
        self.api = None
        CanvasApp.logged_in = False
        CanvasApp.username = ''
        EnvironmentManager.save_access_token('')
        self.ui.show_message("Logged out successfully!", "Success")

    @staticmethod
    def format_due_date(due_date: Optional[Union[str, datetime]]) -> str:
        if not due_date:
            return "No Due Date"
        if isinstance(due_date, str):
            try:
                due_date = datetime.strptime(due_date, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
            except ValueError:
                return "Invalid Date Format"
        if isinstance(due_date, datetime):
            if due_date.tzinfo is None:
                due_date = due_date.replace(tzinfo=timezone.utc)
            local_due_date = due_date.astimezone(timezone(timedelta(hours=USER_TIMEZONE_OFFSET)))
            return local_due_date.strftime("%d/%m %H:%M")
        return "Invalid Date Format"

    def settings_menu(self):
        while True:
            current_token = self.api.access_token if self.api else "Not Set"
            confirm_status = "Enabled" if self.settings.confirm_submit else "Disabled"
            menu_items = [
                "Save Token", 
                f"Toggle Confirmation Prompt ({confirm_status})",
                "Logout", 
                "[ Go Back ]"
            ]
            choice = self.ui.display_menu(menu_items, "Settings", f"Current Access Token: {current_token}")

            if choice == 0:
                new_token = self.ui.get_input("Enter new Access Token:")
                self.save_token(new_token)
                if self.logged_in:
                    return  # Exit settings menu after successful login
            elif choice == 1:
                self.settings.confirm_submit = not self.settings.confirm_submit
                self.settings.save_settings()
                self.ui.show_message(f"Confirmation prompt {'enabled' if self.settings.confirm_submit else 'disabled'}.", "Settings Updated")
                self.ui.wait(0.5)
            elif choice == 2:
                self.logout()
            elif choice == 3 or choice is None:
                if self.logged_in:
                    return
                else:
                    self.ui.show_message("Please set a valid token before exiting settings.", "Notice")
                    self.ui.wait(2)

def main(stdscr):
    try:
        curses.curs_set(0)
        EnvironmentManager.load_env()
        app = CanvasApp(stdscr)
        app.run()
    except Exception as e:
        curses.endwin()
        print(f"An unexpected error occurred: {e}")
        raise

if __name__ == "__main__":
    curses.wrapper(main)