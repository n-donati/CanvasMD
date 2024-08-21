import os
import json
import requests
import curses
from datetime import datetime, timezone
import pytz
from typing import List, Dict, Optional, Any, Tuple, Union

# Constants
API_BASE_URL = 'https://experiencia21.tec.mx/api/v1'
ENV_FILE = '.env'
SETTINGS_FILE = 'canvas_cli_settings.json'
USER_TIMEZONE = pytz.timezone('America/Mexico_City')

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
        
        current_time = datetime.now(USER_TIMEZONE)
        filtered_assignments = []

        for assignment in assignments:
            if assignment.get('is_quiz_assignment'):
                continue

            due_date = self.parse_date(assignment.get('due_at'))
            
            if due_date is None or due_date > current_time:
                assignment['submitted'] = submissions.get(str(assignment['id']), {}).get('workflow_state') == 'submitted'
                filtered_assignments.append(assignment)

        return sorted(filtered_assignments, key=lambda x: (self.parse_date(x.get('due_at')) is None, self.parse_date(x.get('due_at')) or datetime.max.replace(tzinfo=USER_TIMEZONE)))

    @staticmethod
    def parse_date(date_string: Optional[str]) -> Optional[datetime]:
        if not date_string:
            return None
        try:
            parsed_date = datetime.strptime(date_string, "%Y-%m-%dT%H:%M:%SZ")
            return parsed_date.replace(tzinfo=timezone.utc).astimezone(USER_TIMEZONE)
        except ValueError:
            return None

    def get_bulk_assignment_submissions(self, course_id: int, assignment_ids: List[int]) -> Dict[str, Any]:
        params = {'student_ids[]': 'self', 'assignment_ids[]': assignment_ids}
        response = self._make_request("GET", f"courses/{course_id}/students/submissions", params=params)
        if response and response.status_code == 200:
            return {str(sub['assignment_id']): sub for sub in response.json()}
        return {}

    def submit_file_assignment(self, course_id: int, assignment_id: int, file_path: str) -> Tuple[bool, str]:
        params = {
            'name': os.path.basename(file_path),
            'size': os.path.getsize(file_path),
            'content_type': 'application/octet-stream',
        }
        response = self._make_request("POST", f"courses/{course_id}/assignments/{assignment_id}/submissions/self/files", data=params)
        if not response or response.status_code != 200:
            return False, f"Failed to get upload URL. Status: {response.status_code if response else 'N/A'}"

        upload_data = response.json()
        upload_url = upload_data.get('upload_url')
        upload_params = upload_data.get('upload_params', {})
        
        if not upload_url:
            return False, f"Upload URL not found in response. Response: {upload_data}"
        
        with open(file_path, 'rb') as file:
            upload_response = requests.post(upload_url, data=upload_params, files={'file': file}, timeout=30)
        
        if upload_response.status_code != 201:
            return False, f"File upload failed. Status: {upload_response.status_code}"
        
        file_id = upload_response.json().get('id')
        if not file_id:
            return False, f"File ID not found in upload response."
        
        submit_params = {
            'submission': {
                'submission_type': 'online_upload',
                'file_ids': [file_id]
            }
        }
        submit_response = self._make_request("POST", f"courses/{course_id}/assignments/{assignment_id}/submissions", json=submit_params)
        
        if not submit_response or submit_response.status_code != 201:
            return False, f"Assignment submission failed. Status: {submit_response.status_code if submit_response else 'N/A'}"
        
        return True, "File uploaded and assignment submitted successfully!"

class Settings:
    def __init__(self):
        self.confirm_submit = True
        self.load_settings()

    def load_settings(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r') as f:
                    saved_settings = json.load(f)
                    self.confirm_submit = saved_settings.get('confirm_submit', True)
            except json.JSONDecodeError:
                print(f"Error reading settings file. Using default settings.")

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump({'confirm_submit': self.confirm_submit}, f)
        except IOError:
            print(f"Error saving settings to file.")

class EnvironmentManager:
    @staticmethod
    def load_env():
        if os.path.exists(ENV_FILE):
            with open(ENV_FILE) as f:
                for line in f:
                    if line.strip() and not line.strip().startswith('#'):
                        key, value = line.strip().split('=', 1)
                        os.environ[key] = value

    @staticmethod
    def save_access_token(token: str):
        try:
            with open(ENV_FILE, 'w') as f:
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

    def _draw_content(self, content: str):
        content_lines = content.split('\n')
        start_y = 5
        start_x = 2
        max_width = self.width - self.ascii_width - 4

        for idx, line in enumerate(content_lines):
            if start_y + idx < self.height - 3:
                self.stdscr.addstr(start_y + idx, start_x, line[:max_width])

    def _draw_menu_items(self, items: List[str], current_row: int, selectable_indices: List[int]):
        menu_start_y = self.height - len(items) - 2
        menu_width = self.width - self.ascii_width - 4
        x_start = 2

        for idx, item in enumerate(items):
            y = menu_start_y + idx
            if y >= self.height:
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

    def show_message(self, message: str, title: str = "Message"):
        self.stdscr.clear()
        self._draw_layout(title, message)
        self.stdscr.refresh()

    def get_input(self, prompt: str) -> str:
        self.stdscr.clear()
        self._draw_layout("Input", prompt)
        
        curses.echo()
        curses.curs_set(1)
        
        input_y, input_x = 6, 2
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
        while True:
            choice = self.ui.display_menu(["Canvas", "Settings", "Exit"], "Main Menu")
            if choice == 0:
                self.canvas_menu()
            elif choice == 1:
                self.settings_menu()
            elif choice == 2 or choice is None:
                break

    def load_initial_token(self):
        self.ui.show_message("Initializing Canvas CLI...", "Loading")
        
        access_token = os.getenv('ACCESS_TOKEN')
        if access_token:
            self.ui.show_message("Validating saved access token...", "Loading")
            if self.validate_and_set_token(access_token):
                self.ui.show_message("Access token loaded successfully!", "Success")
            else:
                self.ui.show_message("Saved access token is invalid. Please set a new token in Settings.", "Error")
        else:
            self.ui.show_message("No access token found. Please set a token in Settings.", "Notice")

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
            course_idx = self.ui.display_menu(course_names + ["[ Go Back ]"], "Available Courses")
            if course_idx is None or course_idx == len(course_names):
                return

            self.display_assignments(courses[course_idx])

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

        self.ui.show_message(f"Uploading file: {os.path.basename(file_path)}...", "Upload")
        success, message = self.api.submit_file_assignment(
            assignment['course_id'],
            assignment['id'],
            file_path
        )
        if success:
            self.ui.show_message(message, "Success")
        else:
            error_message = f"Failed to upload file or submit assignment.\n\nError details:\n{message}"
            self.ui.show_message(error_message, "Error")

    def save_token(self, token: str):
        self.ui.show_message("Validating token...", "Please Wait")
        if self.validate_and_set_token(token):
            EnvironmentManager.save_access_token(token)
            self.ui.show_message("Access Token saved and validated successfully!", "Success")
        else:
            self.ui.show_message("Invalid Token. Please try again.", "Error")

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
            return due_date.astimezone(USER_TIMEZONE).strftime("%d/%m %H:%M")
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
            elif choice == 1:
                self.settings.confirm_submit = not self.settings.confirm_submit
                self.settings.save_settings()
                self.ui.show_message(f"Confirmation prompt {'enabled' if self.settings.confirm_submit else 'disabled'}.", "Settings Updated")
            elif choice == 2:
                self.logout()
            elif choice == 3 or choice is None:
                break

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