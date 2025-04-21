import numpy as np
import pandas as pd
import cv2
import os
import time
import base64
import csv
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, redirect, url_for, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)

DATASET_FOLDER = 'dataset/'  # Path to student images
ATTENDANCE_FILE = 'attendance.csv'  # CSV file to store attendance
EXCEL_FILE = 'attendance_report.xlsx'  # New Excel file for attendance

# Create dataset folder if not exists
if not os.path.exists('dataset'):
    os.makedirs('dataset')
    
# Create attendance file with headers if it doesn't exist
if not os.path.exists(ATTENDANCE_FILE):
    with open(ATTENDANCE_FILE, 'w', newline='') as file:
        writer = csv.writer(file)
        writer.writerow(['Name', 'Date', 'Day', 'Time', 'Status'])

# Folder where images are stored
dataset_folder = 'dataset/'
# Load the dataset images
def load_dataset():
    images = []
    labels = []
    student_names = []
    label_map = {}
    
    for idx, filename in enumerate(os.listdir(dataset_folder)):
        if filename.endswith(('.jpg', '.jpeg', '.png')):
            img_path = os.path.join(dataset_folder, filename)
            img = cv2.imread(img_path, cv2.IMREAD_GRAYSCALE)
            
            if img is None or img.size == 0:
                continue
                
            # Extract student name from filename
            student_name = os.path.splitext(filename)[0]
            if '_' in student_name:  # Remove timestamp if present
                student_name = student_name.split('_')[0]
            
            images.append(img)
            labels.append(idx)  # Use index as label
            student_names.append(student_name)
            label_map[idx] = student_name
    
    return images, labels, student_names, label_map
# Path to the CSV file where attendance data will be saved
attendance_file = 'attendance.csv'

# Function to append student data to CSV file and update Excel
def append_to_csv(name, date, time_str, img_path=None, status="Present"):
    """Add attendance record to CSV file with proper formatting."""
    # Get the day of the week from the date
    try:
        day = datetime.strptime(date, '%Y-%m-%d').strftime('%A')
    except:
        day = datetime.now().strftime('%A')  # Fallback to current day
    
    # Open CSV file in append mode
    with open(ATTENDANCE_FILE, mode='a', newline='') as file:
        writer = csv.writer(file)
        
        # Write the data in the CSV format: [Name, Date, Day, Time, Status]
        writer.writerow([name, date, day, time_str, status])
    
    # Update Excel file if it exists
    update_excel_file()

def update_excel_file():
    """Update the Excel file with latest attendance data from CSV"""
    try:
        if os.path.exists(ATTENDANCE_FILE):
            # Read CSV into pandas DataFrame
            df = pd.read_csv(ATTENDANCE_FILE)
            
            # Save to Excel with formatting
            with pd.ExcelWriter(EXCEL_FILE, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Attendance')
                
                # Get the workbook and the worksheet
                workbook = writer.book
                worksheet = writer.sheets['Attendance']
                
                # Format headers
                header_format = workbook.add_format({
                    'bold': True,
                    'bg_color': '#D3D3D3',
                    'border': 1
                })
                
                # Apply formatting to headers
                for col_num, value in enumerate(df.columns.values):
                    worksheet.write(0, col_num, value, header_format)
                
                # Adjust column widths
                for i, col in enumerate(df.columns):
                    max_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
                    worksheet.set_column(i, i, max_len)
    except Exception as e:
        print(f"Error updating Excel file: {str(e)}")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        if name:
            return render_template('register.html')
    return render_template('register.html')

@app.route('/register-student', methods=['POST'])
def register_student():
    name = request.form['name']
    image_data = request.form['image']
    
    # Clean the base64 image data (remove the prefix)
    image_data = image_data.split(',')[1]
    
    # Convert base64 to image
    img_data = base64.b64decode(image_data)
    
    # Create a unique filename using the student's name and timestamp
    timestamp = time.time()
    filename = f"dataset/{name}_{timestamp}.jpg"
    
    # Save the image in the 'dataset' folder
    with open(filename, 'wb') as f:
        f.write(img_data)
    
    # Get the current date and time
    current_time = datetime.now()
    date = current_time.strftime('%Y-%m-%d')
    day = current_time.strftime('%A')  # Get day name (Monday, Tuesday, etc.)
    time_str = current_time.strftime('%H:%M:%S')
    
    # Save the student registration with proper format including day and status
    with open(ATTENDANCE_FILE, 'a', newline='') as file:
        writer = csv.writer(file)
        # Format: Name, Date, Day, Time, Status (mark as Present by default for registration)
        writer.writerow([name, date, day, time_str, "Present"])
    
    # Update Excel file if it exists
    update_excel_file()

    return jsonify({"success": True, "message": "Student Registered!", "image_path": filename})

@app.route('/view-attendance', methods=['GET'])
def view_attendance():
    """Retrieve and show the attendance records with analytics."""
    try:
        # Default headers in case file doesn't exist or is empty
        headers = ['Name', 'Date', 'Day', 'Time', 'Status']
        attendance_records = []
        analytics = {}
        
        # Check if attendance file exists
        if os.path.exists(ATTENDANCE_FILE):
            with open(ATTENDANCE_FILE, 'r', newline='') as file:
                reader = csv.reader(file)
                
                # Read header and use default if missing
                try:
                    file_headers = next(reader)
                    if file_headers and len(file_headers) >= len(headers):
                        headers = file_headers
                except StopIteration:
                    # File is empty, use default headers
                    pass
                
                # Read and validate each record
                valid_records = []
                for record in reader:
                    # Skip empty records
                    if not record:
                        continue
                    
                    # Ensure record has all required fields
                    if len(record) < len(headers):
                        record = record + [''] * (len(headers) - len(record))
                    elif len(record) > len(headers):
                        record = record[:len(headers)]
                    
                    # Ensure first two fields (name and date) are not empty
                    if len(record) >= 2 and record[0] and record[1]:
                        valid_records.append(record)
                
                attendance_records = valid_records
            
            # Calculate analytics only if we have valid records
            if attendance_records:
                try:
                    # Get unique students and dates
                    students = set()
                    all_dates = set()
                    
                    for record in attendance_records:
                        if len(record) >= 2 and record[0] and record[1]:
                            students.add(record[0])
                            all_dates.add(record[1])
                    
                    # Calculate attendance per student
                    student_analytics = {}
                    for student in students:
                        student_records = [r for r in attendance_records if len(r) >= 1 and r[0] == student]
                        attendance_dates = set(r[1] for r in student_records if len(r) >= 2)
                        
                        total_days = len(all_dates)
                        present_days = len(attendance_dates)
                        
                        attendance_rate = (present_days / total_days * 100) if total_days > 0 else 0
                        
                        student_analytics[student] = {
                            'total_days': total_days,
                            'present_days': present_days,
                            'attendance_rate': round(attendance_rate, 2),
                            'records': student_records
                        }
                    
                    # Calculate attendance per day
                    day_analytics = {}
                    for date in all_dates:
                        day_records = [r for r in attendance_records if len(r) >= 2 and r[1] == date]
                        
                        # Count present students
                        present_students = 0
                        for r in day_records:
                            if len(r) >= 5 and r[4] == "Present":
                                present_students += 1
                        
                        day_analytics[date] = {
                            'total_students': len(students),
                            'present_students': present_students,
                            'records': day_records
                        }
                    
                    analytics = {
                        'total_students': len(students),
                        'total_days': len(all_dates),
                        'student_analytics': student_analytics,
                        'day_analytics': day_analytics,
                        'students': list(students),
                        'dates': sorted(list(all_dates))
                    }
                except Exception as e:
                    print(f"Error calculating analytics: {str(e)}")
        
        return render_template('view_attendance.html', 
                            headers=headers, 
                            attendance_records=attendance_records,
                            analytics=analytics)
    except Exception as e:
        print(f"Error in view_attendance: {str(e)}")
        # Return a basic error page
        return render_template('view_attendance.html', 
                            headers=['Name', 'Date', 'Day', 'Time', 'Status'], 
                            attendance_records=[],
                            message=f"Error retrieving attendance data: {str(e)}",
                            analytics={})

@app.route('/mark-attendance', methods=['GET'])
def display_mark_attendance():
    """Display the mark attendance page."""
    return render_template('mark_attendance.html')

@app.route('/mark-attendance', methods=['POST'])
def mark_attendance():
    """Mark student attendance based on captured image."""
    try:
        # Check if the request contains JSON data
        if not request.is_json:
            return jsonify({"message": "Invalid request format", "status": "error"}), 400
            
        data = request.get_json()
        
        # Check if image data exists in the request
        if not data or 'image' not in data:
            return jsonify({"message": "Missing image data", "status": "error"}), 400
            
        # Get the base64 image data and remove header if present
        img_data = data['image']
        if ',' in img_data:
            img_data = img_data.split(',')[1]
            
        # Decode base64 to image
        img_bytes = base64.b64decode(img_data)
        
        # Convert to numpy array for OpenCV
        np_arr = np.frombuffer(img_bytes, np.uint8)
        captured_img = cv2.imdecode(np_arr, cv2.IMREAD_GRAYSCALE)
        
        # Load dataset
        images, labels, student_names, label_map = load_dataset()
        
        if not images:
            return jsonify({"message": "No student data found in database!", "status": "error"})
        
        # Create and train face recognizer
        recognizer = cv2.face.LBPHFaceRecognizer_create()
        recognizer.train(images, np.array(labels))
        
        # Predict
        try:
            student_id, confidence = recognizer.predict(captured_img)
            
            # Lower confidence value means better match
            if confidence < 100:  # Adjust threshold as needed
                student_name = label_map[student_id]
                
                # Get current date and time
                current_time = datetime.now()
                date = current_time.strftime('%Y-%m-%d')
                day = current_time.strftime('%A')  # Ensure we capture the day name correctly
                time_str = current_time.strftime('%H:%M:%S')
                
                # Save the image with timestamp in the dataset folder
                img_filename = f"dataset/{student_name}_{int(time.time())}.jpg"
                cv2.imwrite(img_filename, captured_img)
                
                # Check if attendance already marked for today
                with open(ATTENDANCE_FILE, 'r', newline='') as file:
                    reader = csv.reader(file)
                    next(reader)  # Skip header
                    attendance_data = list(reader)
                
                if any(row[0] == student_name and row[1] == date for row in attendance_data):
                    return jsonify({
                        "message": f"Attendance already marked for {student_name} today!",
                        "status": "error"
                    })
                
                # Mark attendance
                with open(ATTENDANCE_FILE, 'a', newline='') as file:
                    writer = csv.writer(file)
                    writer.writerow([student_name, date, day, time_str, "Present"])
                
                # Update Excel file
                update_excel_file()
                
                return jsonify({
                    "message": f"Attendance marked for {student_name}!",
                    "status": "success",
                    "confidence": f"{100-confidence:.2f}% match"
                })
            else:
                return jsonify({
                    "message": f"Face not recognized clearly. Confidence too low ({100-confidence:.2f}%). Please try again.",
                    "status": "error"
                })
                
        except Exception as e:
            return jsonify({
                "message": f"Error in face recognition: {str(e)}",
                "status": "error"
            })
            
    except Exception as e:
        print(f"Error: {str(e)}")
        return jsonify({
            "message": f"Error marking attendance: {str(e)}",
            "status": "error"
        }), 500

@app.route('/get-students', methods=['GET'])
def get_students():
    """Fetch all student images and names from the dataset folder."""
    students = []

    for filename in os.listdir(DATASET_FOLDER):
        if filename.endswith(('.jpg', '.jpeg', '.png')):  # Only process images
            student_name = os.path.splitext(filename)[0]  # Remove file extension
            image_path = os.path.join(DATASET_FOLDER, filename)

            # Convert image to base64 for frontend display
            with open(image_path, "rb") as img_file:
                base64_image = base64.b64encode(img_file.read()).decode('utf-8')

            students.append({"name": student_name, "image": base64_image})

    return jsonify(students)

@app.route('/update-attendance', methods=['POST'])
def update_attendance():
    """Update an attendance record manually."""
    try:
        data = request.get_json()
        
        if not data or 'name' not in data or 'date' not in data or 'status' not in data:
            return jsonify({"message": "Missing required fields", "status": "error"}), 400
            
        name = data['name']
        date = data['date']
        status = data['status']
        
        # Read all records
        all_records = []
        with open(ATTENDANCE_FILE, 'r', newline='') as file:
            reader = csv.reader(file)
            headers = next(reader)  # Save headers
            all_records = list(reader)
        
        # Find and update the record
        record_updated = False
        for record in all_records:
            if record[0] == name and record[1] == date:
                record[4] = status  # Update status
                record_updated = True
                break
        
        # If record not found, create a new one
        if not record_updated:
            day = datetime.strptime(date, '%Y-%m-%d').strftime('%A')
            time_str = datetime.now().strftime('%H:%M:%S')
            new_record = [name, date, day, time_str, status]
            all_records.append(new_record)
        
        # Write all records back
        with open(ATTENDANCE_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(all_records)
        
        # Update Excel file
        update_excel_file()
        
        return jsonify({
            "message": f"Attendance {status} for {name} on {date}!",
            "status": "success"
        })
        
    except Exception as e:
        print(f"Error updating attendance: {str(e)}")
        return jsonify({
            "message": f"Error updating attendance: {str(e)}",
            "status": "error"
        }), 500

@app.route('/delete-attendance', methods=['POST'])
def delete_attendance():
    """Delete an attendance record."""
    try:
        data = request.get_json()
        
        if not data or 'name' not in data or 'date' not in data:
            return jsonify({"message": "Missing required fields", "status": "error"}), 400
            
        name = data['name']
        date = data['date']
        
        # Read all records
        all_records = []
        with open(ATTENDANCE_FILE, 'r', newline='') as file:
            reader = csv.reader(file)
            headers = next(reader)  # Save headers
            all_records = list(reader)
        
        # Filter out the record to delete
        initial_count = len(all_records)
        all_records = [r for r in all_records if not (r[0] == name and r[1] == date)]
        
        if len(all_records) == initial_count:
            return jsonify({
                "message": f"Record for {name} on {date} not found.",
                "status": "error"
            }), 404
        
        # Write all records back
        with open(ATTENDANCE_FILE, 'w', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(headers)
            writer.writerows(all_records)
        
        # Update Excel file
        update_excel_file()
        
        return jsonify({
            "message": f"Attendance record for {name} on {date} has been deleted.",
            "status": "success"
        })
        
    except Exception as e:
        print(f"Error deleting attendance: {str(e)}")
        return jsonify({
            "message": f"Error deleting attendance: {str(e)}",
            "status": "error"
        }), 500

@app.route('/download-excel')
def download_excel():
    try:
        # Check if Excel file exists, if not create it
        if not os.path.exists(EXCEL_FILE):
            update_excel_file()
        
        # Return the Excel file for download
        return send_file(
            EXCEL_FILE,
            as_attachment=True,
            download_name='attendance_report.xlsx',
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    except Exception as e:
        print(f"Error downloading Excel file: {str(e)}")
        flash("Error downloading Excel file", "error")
        return redirect(url_for('view_attendance'))

if __name__ == '__main__':
    app.run(debug=True)
