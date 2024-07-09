from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash, send_from_directory
import json
import datetime
import os
from apscheduler.schedulers.background import BackgroundScheduler
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

app = Flask(__name__)
app.secret_key = 'GW_23PayMod'

STAFF_FILE = 'staff.json'
DATA_FILE = 'attendance_data.json'
SCHEDULE_FILE = 'schedule.json'
SECURITY_QUESTIONS = {
    "favourite_colour": "What is your favourite colour?",
    "birth_place": "Where were you born?",
    "mother_maiden_name": "What is your mother's maiden name?"
}

# Utility functions to load and save JSON data
def read_json_file(filename):
    with open(filename, 'r') as file:
        return json.load(file)

def write_json_file(filename, data):
    with open(filename, 'w') as file:
        json.dump(data, file, indent=4)

def strptime(value, format):
    return datetime.datetime.strptime(value, format)

app.jinja_env.filters['strptime'] = strptime        

def calculate_hours_worked(corrected_clock_in, corrected_clock_out):
    corrected_clock_in = datetime.datetime.strptime(corrected_clock_in, '%Y-%m-%d %H:%M')
    corrected_clock_out = datetime.datetime.strptime(corrected_clock_out, '%Y-%m-%d %H:%M')
    return (corrected_clock_out - corrected_clock_in).total_seconds() / 3600

app.jinja_env.filters['calculate_hours_worked'] = calculate_hours_worked        

# Load and save data functions
load_staff_data = lambda: read_json_file(STAFF_FILE)
save_staff_data = lambda data: write_json_file(STAFF_FILE, data)
load_attendance_data = lambda: read_json_file(DATA_FILE)
save_attendance_data = lambda data: write_json_file(DATA_FILE, data)

# Ensure the JSON files exist
def ensure_json_files():
    try:
        with open(STAFF_FILE, 'x') as f:
            f.write('{"manager": {"password": "password", "pin": "12345", "state": "WA", "staff_password": "Pizza"}}')
    except FileExistsError:
        pass

    try:
        with open(DATA_FILE, 'x') as f:
            f.write('[]')
    except FileExistsError:
        pass

    try:
        with open(SCHEDULE_FILE, 'x') as f:
            f.write('{}')
    except FileExistsError:
        pass

ensure_json_files()

def safe_int(value, default=0):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def round_to_nearest_15(minutes):
    return round(minutes / 15) * 15

def round_datetime(dt):
    minute = round_to_nearest_15(dt.minute)
    if minute == 60:
        dt += datetime.timedelta(hours=1)
        minute = 0
    return dt.replace(minute=minute, second=0, microsecond=0)

def format_datetime(value):
    if isinstance(value, str):
        value = datetime.datetime.strptime(value, '%Y-%m-%d %H:%M')
    return value.strftime("%d %B %y %H:%M")

app.jinja_env.filters['format_datetime'] = format_datetime

def calculate_easter(year):
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return datetime.date(year, month, day)

def nth_weekday_of_month(year, month, weekday, n):
    count = 0
    for day in range(1, 32):  # Maximum days in a month is 31
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            break
        if date.weekday() == weekday:
            count += 1
            if count == n:
                return date
    return None

def first_weekday_of_month(year, month, weekday):
    for day in range(1, 8):  # First seven days of the month
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            continue
        if date.weekday() == weekday:
            return date
    return None

def last_weekday_of_month(year, month, weekday):
    for day in range(31, 0, -1):
        try:
            date = datetime.date(year, month, day)
        except ValueError:
            continue
        if date.weekday() == weekday:
            return date
    return None

def get_public_holidays(state, year):
    easter_sunday = calculate_easter(year)
    good_friday = easter_sunday - datetime.timedelta(days=2)
    easter_monday = easter_sunday + datetime.timedelta(days=1)
    
    public_holidays = {
        'NSW': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            nth_weekday_of_month(year, 10, 0, 1),  # Labour Day (1st Monday in October)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'VIC': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            first_weekday_of_month(year, 11, 1),  # Melbourne Cup Day (1st Tuesday in November)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'WA': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            nth_weekday_of_month(year, 3, 0, 1),  # Labour Day (1st Monday in March)
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            first_weekday_of_month(year, 6, 0),  # Western Australia Day (1st Monday in June)
            last_weekday_of_month(year, 9, 0),  # King's Birthday (Last Monday in September)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'QLD': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 5, 0, 1),  # Labour Day (1st Monday in May)
            nth_weekday_of_month(year, 10, 0, 1),  # Queen's Birthday (1st Monday in October)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'SA': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            nth_weekday_of_month(year, 10, 0, 1),  # Labour Day (1st Monday in October)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'TAS': [
            datetime.date(year, 1, 1),  # New Year's```python
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            nth_weekday_of_month(year, 3, 0, 2),  # Eight Hours Day (2nd Monday in March)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'ACT': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            nth_weekday_of_month(year, 3, 0, 2),  # Canberra Day (2nd Monday in March)
            last_weekday_of_month(year, 5, 0),  # Reconciliation Day (Last Monday in May)
            nth_weekday_of_month(year, 10, 0, 1),  # Labour Day (1st Monday in October)
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
        'NT': [
            datetime.date(year, 1, 1),  # New Year's Day
            datetime.date(year, 1, 26),  # Australia Day
            good_friday,  # Good Friday
            easter_monday,  # Easter Monday
            datetime.date(year, 4, 25),  # ANZAC Day
            nth_weekday_of_month(year, 5, 0, 1),  # May Day (1st Monday in May)
            nth_weekday_of_month(year, 6, 0, 2),  # Queen's Birthday (2nd Monday in June)
            datetime.date(year, 7, 1),  # Territory Day
            datetime.date(year, 12, 25),  # Christmas Day
            datetime.date(year, 12, 26)   # Boxing Day
        ],
    }
    return public_holidays.get(state, [])

def is_public_holiday(date, state):
    current_year = date.year
    holidays = get_public_holidays(state, current_year)
    return date in holidays

def load_schedule():
    if not os.path.exists(SCHEDULE_FILE):
        print(f"{SCHEDULE_FILE} does not exist. Returning empty schedule.")  # Debug statement
        return {}
    with open(SCHEDULE_FILE, 'r') as file:
        print(f"Loading schedule from {SCHEDULE_FILE}")  # Debug statement
        return json.load(file)

def save_schedule(schedule):
    with open(SCHEDULE_FILE, 'w') as file:
        json.dump(schedule, file, indent=4)
    print(f"Saved schedule to {SCHEDULE_FILE}: {schedule}")  # Debug statement

@app.route('/', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        if 'pin' in request.form:
            pin = request.form['pin']
            staff_data = load_staff_data()
            if pin == '000':  # Special PIN to access manager page
                return redirect(url_for('reset_password_page'))
            for name, details in staff_data.items():
                if details.get('pin') == pin:
                    session['user'] = name
                    if name == 'manager':
                        return redirect(url_for('manager'))
                    else:
                        return redirect(url_for('login'))
            flash('Invalid PIN', 'error')
        else:
            flash('PIN not provided', 'error')
    staff_data = load_staff_data()
    return render_template('index.html', staff_data=staff_data)

@app.route('/reset_password_page', methods=['GET'])
def reset_password_page():
    questions = {
        "favourite_colour": "What is your favourite colour?",
        "birth_place": "Where were you born?",
        "mother_maiden_name": "What is your mother's maiden name?"
    }
    return render_template('reset_password.html', questions=questions)


@app.route('/update_manager_pin', methods=['POST'])
def update_manager_pin():
    new_pin = request.form.get('new_pin')
    if new_pin:
        staff_data = load_staff_data()
        staff_data['manager']['pin'] = new_pin
        save_staff_data(staff_data)
    return redirect(url_for('manager'))


@app.route('/manager', methods=['GET'])
def manager():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login_page'))

    staff_data = load_staff_data()
    attendance_data = load_attendance_data()
    staff_clocked_in = [record['name'] for record in attendance_data if 'clock_out' not in record]
    schedule = load_schedule()
    current_backup_schedule = f"{schedule['day_of_week'].capitalize()} at {schedule['backup_time']}" if schedule else "No backup scheduled"
    
    return render_template('manager.html', 
                           staff=staff_data.keys(), 
                           state=staff_data['manager'], 
                           staff_clocked_in=staff_clocked_in, 
                           current_backup_schedule=current_backup_schedule)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user' not in session:
        return redirect(url_for('login_page'))

    name = session['user']
    if request.method == 'POST':
        action = request.form.get('action')
        staff_data = load_staff_data()

        if name in staff_data:
            attendance_data = load_attendance_data()
            if action == 'clock_in':
                if any(record['name'] == name and 'clock_out' not in record for record in attendance_data):
                    flash('You are already clocked in', 'error')
                else:
                    attendance_data.append({'name': name, 'clock_in': datetime.datetime.now().strftime('%Y-%m-%d %H:%M')})
                    save_attendance_data(attendance_data)
            elif action == 'clock_out':
                for record in attendance_data:
                    if record['name'] == name and 'clock_out' not in record:
                        record['clock_out'] = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
                        deliveries = request.form.get('deliveries', '0')
                        record['deliveries'] = safe_int(deliveries)
                        save_attendance_data(attendance_data)
                        break
            return redirect(url_for('login_page'))
        else:
            flash('Invalid credentials', 'error')
            return redirect(url_for('login'))

    staff_data = load_staff_data()
    attendance_data = load_attendance_data()
    staff_clocked_in = [record['name'] for record in attendance_data if 'clock_out' not in record]
    return render_template('login.html', staff_clocked_in=staff_clocked_in)

import traceback

import collections  # Add this import at the top of your file

from datetime import datetime as dt

@app.route('/summary')
def summary():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login'))

    try:
        attendance_data = load_attendance_data()
        staff_data = load_staff_data()
        state = staff_data['manager'].get('state', 'WA')

        summary_data = {}
        for record in attendance_data:
            name = record['name']
            if name not in summary_data:
                summary_data[name] = {'midweek': 0, 'weekend': 0, 'public_holiday': 0, 'deliveries': 0}

            clock_in = dt.strptime(record['clock_in'], '%Y-%m-%d %H:%M')
            corrected_clock_in = round_datetime(clock_in)
            record['corrected_clock_in'] = corrected_clock_in.strftime('%Y-%m-%d %H:%M')

            clock_out_str = record.get('clock_out')
            if clock_out_str and clock_out_str.strip():
                clock_out = dt.strptime(clock_out_str, '%Y-%m-%d %H:%M')
                corrected_clock_out = round_datetime(clock_out)
                record['corrected_clock_out'] = corrected_clock_out.strftime('%Y-%m-%d %H:%M')

                if is_public_holiday(corrected_clock_in.date(), state):
                    summary_data[name]['public_holiday'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)
                elif corrected_clock_in.weekday() < 5:
                    summary_data[name]['midweek'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)
                else:
                    summary_data[name]['weekend'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)

            summary_data[name]['deliveries'] += safe_int(record.get('deliveries', '0'))

        logging_data = {}
        total_daily_hours = {}
        for record in attendance_data:
            clock_in = dt.strptime(record['clock_in'], '%Y-%m-%d %H:%M')
            day = clock_in.strftime('%A %d %B %Y')
            if day not in logging_data:
                logging_data[day] = []
                total_daily_hours[day] = 0
            logging_data[day].append(record)

        for day in logging_data:
            total_daily_hours[day] = sum(
                (dt.strptime(record['corrected_clock_out'], '%Y-%m-%d %H:%M') - dt.strptime(record['corrected_clock_in'], '%Y-%m-%d %H:%M')).total_seconds() / 3600
                for record in logging_data[day] if record.get('corrected_clock_out')
            )

        for day in logging_data:
            logging_data[day] = sorted(logging_data[day], key=lambda x: x['name'])

        sorted_logging_data = dict(sorted(logging_data.items(), key=lambda x: dt.strptime(x[0], '%A %d %B %Y')))

        return render_template('summary.html', summary_data=summary_data, sorted_logging_data=sorted_logging_data, total_daily_hours=total_daily_hours, strptime=dt.strptime)
    except Exception as e:
        print(f"Error occurred in summary route: {e}")
        traceback.print_exc()
        return str(e), 500

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.pop('user', None)
    return redirect(url_for('login_page'))

@app.route('/manager_override', methods=['GET', 'POST'])
def manager_override():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login_page'))

    attendance_data = load_attendance_data()
    staff_data = load_staff_data()

    questions = SECURITY_QUESTIONS  # Add this line to define the questions variable

    if request.method == 'POST':
        action = request.form.get('action')
        record_id = request.form.get('record_id', -1)
        if record_id != -1:
            record_id = int(record_id)
        name = request.form.get('name')
        clock_in = request.form.get('clock_in')
        clock_out = request.form.get('clock_out')
        deliveries = request.form.get('deliveries', 0)

        if action == 'add':
            clock_in = clock_in.replace('T', ' ')
            clock_out = clock_out.replace('T', ' ')
            attendance_data.append({
                'name': name,
                'clock_in': clock_in,
                'clock_out': clock_out,
                'deliveries': deliveries
            })
        elif action == 'edit' and 0 <= record_id < len(attendance_data):
            clock_in = clock_in.replace('T', ' ')
            clock_out = clock_out.replace('T', ' ')
            attendance_data[record_id] = {
                'name': name,
                'clock_in': clock_in,
                'clock_out': clock_out,
                'deliveries': deliveries
            }
        elif action == 'delete' and 0 <= record_id < len(attendance_data):
            del attendance_data[record_id]

        save_attendance_data(attendance_data)
        return redirect(url_for('manager_override'))

    return render_template('manager_override.html', attendance_data=attendance_data, staff=staff_data.keys(), enumerate=enumerate, questions=questions)  # Pass the questions variable


@app.route('/add_staff', methods=['POST'])
def add_staff():
    new_staff_name = request.form.get('new_staff_name')
    new_staff_pin = request.form.get('new_staff_pin')
    if new_staff_name and new_staff_pin:
        staff_data = load_staff_data()
        if new_staff_name not in staff_data:
            staff_data[new_staff_name] = {"pin": new_staff_pin}
            save_staff_data(staff_data)
            flash(f'Staff member {new_staff_name} added successfully.', 'success')
        else:
            flash('Staff member already exists', 'error')
    else:
        flash('Both name and pin are required', 'error')
    return redirect(url_for('manager'))


@app.route('/remove_staff', methods=['POST'])
def remove_staff():
    staff_name = request.form.get('remove_name')
    if staff_name:
        staff_data = load_staff_data()
        if staff_name in staff_data:
            del staff_data[staff_name]
            save_staff_data(staff_data)
        else:
            flash('Staff member not found', 'error')
    return redirect(url_for('manager'))

@app.route('/delete_shift', methods=['POST'])
def delete_shift():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login_page'))

    name = request.form['name']
    clock_in = request.form['clock_in']

    attendance_data = load_attendance_data()
    attendance_data = [record for record in attendance_data if not (record['name'] == name and record['clock_in'] == clock_in)]
    save_attendance_data(attendance_data)

    return redirect(url_for('manager_override'))

@app.route('/reset_password', methods=['POST'])
def reset_password():
    answers = {
        "favourite_colour": request.form['favourite_colour'],
        "birth_place": request.form['birth_place'],
        "mother_maiden_name": request.form['mother_maiden_name']
    }
    
    staff_data = load_staff_data()
    if (staff_data['manager'].get('favourite_colour') == answers['favourite_colour'] and
        staff_data['manager'].get('birth_place') == answers['birth_place'] and
        staff_data['manager'].get('mother_maiden_name') == answers['mother_maiden_name']):
        session['user'] = 'manager'
        return redirect(url_for('manager'))
    else:
        flash('Incorrect answers to security questions', 'error')
        questions = {
            "favourite_colour": "What is your favourite colour?",
            "birth_place": "Where were you born?",
            "mother_maiden_name": "What is your mother's maiden name?"
        }
        return render_template('reset_password.html', questions=questions)


@app.route('/manage_backup', methods=['GET', 'POST'])
def manage_backup():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login_page'))

    if request.method == 'POST':
        day_of_week = request.form.get('day_of_week')
        backup_time = request.form.get('backup_time')
        
        print(f"Received day_of_week: {day_of_week}, backup_time: {backup_time}")  # Debug statement

        if day_of_week and backup_time:
            hour, minute = map(int, backup_time.split(':'))

            scheduler.remove_all_jobs()
            scheduler.add_job(perform_backup, 'cron', day_of_week=day_of_week, hour=hour, minute=minute)

            if not scheduler.running:
                scheduler.start()

            schedule = {
                'day_of_week': day_of_week,
                'backup_time': backup_time
            }
            save_schedule(schedule)
            print(f"Scheduled backup for {day_of_week} at {hour}:{minute}")  # Debug statement
            flash('Backup schedule updated successfully')
            return redirect(url_for('manager'))

    return render_template('manager.html')

def perform_backup():
    print("Starting backup process")  # Debug statement
    try:
        with app.app_context():
            attendance_data = load_attendance_data()
            staff_data = load_staff_data()
            state = staff_data['manager'].get('state', 'WA')
            print(f"State: {state}")  # Debug statement

            summary_data = {}
            for record in attendance_data:
                name = record['name']
                if name not in summary_data:
                    summary_data[name] = {'midweek': 0, 'weekend': 0, 'public_holiday': 0, 'deliveries': 0}

                clock_in = datetime.datetime.strptime(record['clock_in'], '%Y-%m-%d %H:%M')
                clock_out_str = record.get('clock_out', None)
                if clock_out_str and clock_out_str != '':
                    try:
                        clock_out = datetime.datetime.strptime(clock_out_str, '%Y-%m-%d %H:%M')
                        corrected_clock_in = round_datetime(clock_in)
                        corrected_clock_out = round_datetime(clock_out)

                        if is_public_holiday(corrected_clock_in.date(), state):
                            summary_data[name]['public_holiday'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)
                        elif corrected_clock_in.weekday() < 5:
                            summary_data[name]['midweek'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)
                        else:
                            summary_data[name]['weekend'] += round((corrected_clock_out - corrected_clock_in).total_seconds() / 3600, 2)

                        summary_data[name]['deliveries'] += safe_int(record.get('deliveries', '0'))

                        record['corrected_clock_in'] = corrected_clock_in.strftime('%Y-%m-%d %H:%M')
                        record['corrected_clock_out'] = corrected_clock_out.strftime('%Y-%m-%d %H:%M')
                    except ValueError as e:
                        print(f"Error parsing clock out time: {e}")
                        record['corrected_clock_out'] = None
                else:
                    record['corrected_clock_in'] = round_datetime(clock_in).strftime('%Y-%m-%d %H:%M')
                    record['corrected_clock_out'] = None

            print(f"Summary data: {summary_data}")  # Debug statement
            generate_pdf(summary_data, attendance_data)
            save_attendance_data([])

            print("Data backed up and reset successfully")  # Debug statement
    except Exception as e:
        print(f"Error in backup and reset: {e}")  # Debug statement

def generate_pdf(summary_data, attendance_data):
    print("Generating PDF")  # Debug statement
    backup_dir = 'static/backups'
    os.makedirs(backup_dir, exist_ok=True)
    pdf_filename = f"Weekly_Report_Generated_{datetime.datetime.now().strftime('%Y-%m-%d')}.pdf"
    pdf_path = os.path.join(backup_dir, pdf_filename)

    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    elements = []
    styles = getSampleStyleSheet()
    title_style = styles['Title']
    subtitle_style = styles['Heading2']
    body_style = styles['BodyText']
    table_header_style = styles['Heading4']
    table_body_style = styles['BodyText']

    title = Paragraph(f"Weekly Report. Generated: {datetime.datetime.now().strftime('%A %d %B %Y')}", title_style)
    elements.append(title)
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph("Staff Summary", subtitle_style))
    summary_table_data = [['Staff Name', 'Midweek Hours', 'Weekend Hours', 'Public Holiday Hours', 'Deliveries']]
    for name, data in sorted(summary_data.items()):
        summary_table_data.append([name, data['midweek'], data['weekend'], data['public_holiday'], data['deliveries']])

    summary_table = Table(summary_table_data)
    summary_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
        ('GRID', (0, 0), (-1, -1), 1, colors.black),
    ]))
    elements.append(summary_table)
    elements.append(Spacer(1, 0.25 * inch))

    elements.append(Paragraph("Daily Logs", subtitle_style))
    
    logging_data = {}
    total_daily_hours = {}
    for record in attendance_data:
        clock_in = datetime.datetime.strptime(record['clock_in'], '%Y-%m-%d %H:%M')
        day = clock_in.strftime('%A %d %B %Y')
        if day not in logging_data:
            logging_data[day] = []
            total_daily_hours[day] = 0.0
        logging_data[day].append(record)

    for day in sorted(logging_data.keys(), key=lambda x: datetime.datetime.strptime(x, '%A %d %B %Y')):
        elements.append(Paragraph(day, table_header_style))
        log_table_data = [['Staff Name', 'Actual Clock In', 'Rounded Clock In', 'Actual Clock Out', 'Rounded Clock Out', 'Deliveries', 'Hours Worked']]
        day_total_hours = 0.0
        for record in logging_data[day]:
            if record.get('corrected_clock_out'):
                hours_worked = (datetime.datetime.strptime(record['corrected_clock_out'], '%Y-%m-%d %H:%M') - datetime.datetime.strptime(record['corrected_clock_in'], '%Y-%m-%d %H:%M')).total_seconds() / 3600
                day_total_hours += hours_worked
                log_table_data.append([
                    record['name'],
                    record['clock_in'][11:],  # Only time part
                    record['corrected_clock_in'][11:],  # Only time part
                    record.get('clock_out', '')[11:],  # Only time part
                    record.get('corrected_clock_out', '')[11:],  # Only time part
                    record.get('deliveries', ''),
                    f"{hours_worked:.2f}"
                ])
            else:
                log_table_data.append([
                    record['name'],
                    record['clock_in'][11:],  # Only time part
                    record['corrected_clock_in'][11:],  # Only time part
                    record.get('clock_out', '')[11:],  # Only time part
                    record.get('corrected_clock_out', '')[11:],  # Only time part
                    record.get('deliveries', ''),
                    '0.00'
                ])

        log_table_data.append(['', '', '', '', '', 'Total Hours', f"{day_total_hours:.2f}"])
        total_daily_hours[day] = day_total_hours

        log_table = Table(log_table_data)
        log_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black),
        ]))
        elements.append(log_table)
        elements.append(Spacer(1, 0.25 * inch))

    doc.build(elements)
    print(f"PDF generated: {pdf_path}")  # Debug statement


# Ensure that the scheduler starts with the saved schedule if it exists
schedule = load_schedule()
scheduler = BackgroundScheduler()
if schedule:
    day_of_week = schedule.get('day_of_week')
    backup_time = schedule.get('backup_time')
    if day_of_week and backup_time:
        hour, minute = map(int, backup_time.split(':'))
        scheduler.add_job(perform_backup, 'cron', day_of_week=day_of_week, hour=hour, minute=minute)
        scheduler.start()
        print(f"Rescheduled backup for {day_of_week} at {hour}:{minute}")  # Debug statement
else:
    print("No existing backup schedule found")  # Debug statement

@app.route('/update_location', methods=['POST'])
def update_location():
    staff_data = load_staff_data()
    staff_data['manager']['state'] = request.form.get('state')
    save_staff_data(staff_data)
    return redirect(url_for('manager'))

@app.route('/update_security_questions', methods=['POST'])
def update_security_questions():
    staff_data = load_staff_data()
    staff_data['manager']['favourite_colour'] = request.form.get('favourite_colour')
    staff_data['manager']['birth_place'] = request.form.get('birth_place')
    staff_data['manager']['mother_maiden_name'] = request.form.get('mother_maiden_name')
    save_staff_data(staff_data)
    return redirect(url_for('manager'))

@app.route('/list_pdfs')
def list_pdfs():
    if 'user' not in session or session['user'] != 'manager':
        return redirect(url_for('login_page'))

    backup_dir = 'static/backups'
    pdf_files = sorted([f for f in os.listdir(backup_dir) if f.endswith('.pdf')], reverse=True)
    return render_template('list_pdfs.html', pdf_files=pdf_files)

@app.route('/download_pdf/<filename>')
def download_pdf(filename):
    return send_from_directory('static/backups', filename)

if __name__ == '__main__':
    app.run(debug=True)
