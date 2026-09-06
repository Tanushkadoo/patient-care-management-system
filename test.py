from io import BytesIO
from datetime import date

import os
from dotenv import load_dotenv

import mysql.connector

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    jsonify,
    send_file
)

from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle
)

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY")

connection = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=int(os.getenv("DB_PORT", 3306)),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    connection_timeout=10,
    autocommit=False
)

cursor = connection.cursor()


@app.before_request
def check_database_connection():
    global connection, cursor


    try:
        connection.ping(
            reconnect=True,
            attempts=3,
            delay=1
        )

        cursor.close()
        cursor = connection.cursor()

    except mysql.connector.Error as e:
        print("Database connection error:", e)

        connection = mysql.connector.connect(
            host=os.getenv("DB_HOST"),
            port=int(os.getenv("DB_PORT", 3306)),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            database=os.getenv("DB_NAME"),
            connection_timeout=10,
            autocommit=False
        )

        cursor = connection.cursor()


@app.route("/")
def home_page():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        query = """
        SELECT * FROM users
        WHERE email = %s AND password = %s
        """
        cursor.execute(query, (email, password))
        user = cursor.fetchone()
        print(user)

        if user:
            role = user[4]

            session["user_id"] = user[0]
            session["user"] = user[1]
            session["role"] = role

            if role == "pharmacist":
                return redirect("/pharmacist_dashboard")

            return redirect("/dashboard")

        else:
            return "Invalid Email or Password"

    return render_template("login.html")
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        query = """
        INSERT INTO users (full_name, email, password, role)
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(query, (full_name, email, password, role))
        connection.commit()

        new_user_id = cursor.lastrowid

        if role == "patient":
            cursor.execute("""
                INSERT INTO patients (patient_name, user_id)
                VALUES (%s, %s)
            """, (full_name, new_user_id))
            connection.commit()

        if role == "doctor":
            cursor.execute("""
                INSERT INTO doctors (doctor_name, user_id)
                VALUES (%s, %s)
            """, (full_name, new_user_id))
            connection.commit()

        return redirect("/login")

    return render_template("register.html")

@app.route("/add_user", methods=["GET", "POST"])
def add_user():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        print(full_name)
        print(email)
        print(password)
        print(role)

        query = """
        INSERT INTO users (full_name, email, password, role)
        VALUES (%s, %s, %s, %s)
        """

        cursor.execute(query, (full_name, email, password, role))
        connection.commit()

        return redirect("/view_users")

    return render_template("add_user.html")

@app.route("/view_users")
def view_users():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("SELECT * FROM users")
    users = cursor.fetchall()

    return render_template("view_users.html", users=users)

@app.route("/book_appointment", methods=["GET", "POST"])
def book_appointment():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    if request.method == "POST":

        doctor_id = request.form["doctor_id"]
        appointment_date = request.form["appointment_date"]
        appointment_time = request.form["appointment_time"]

        print(doctor_id)
        print(appointment_date)
        print(appointment_time)

        query = """
        INSERT INTO appointments
        (patient_id, doctor_id, appointment_date, appointment_time, status)
        VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                session["user_id"],
                doctor_id,
                appointment_date,
                appointment_time,
                "Pending"
            )
        )

        connection.commit()

        return redirect("/book_appointment")

    cursor.execute("""
        SELECT
            id,
            doctor_name,
            specialization,
            available_from,
            available_to
        FROM doctors
    """)

    doctors = cursor.fetchall()

    return render_template(
        "book_appointment.html",
        doctors=doctors
    )
@app.route("/nearby_hospitals")
def nearby_hospitals():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    return render_template("nearby_hospitals.html")



@app.route("/my_appointments")
def my_appointments():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    cursor.execute("""
        SELECT
            appointments.id,
            doctors.doctor_name,
            appointments.appointment_date,
            appointments.appointment_time,
            appointments.status
        FROM appointments
        JOIN doctors
        ON appointments.doctor_id = doctors.id
        WHERE appointments.patient_id = %s
    """, (session["user_id"],))

    appointments = cursor.fetchall()

    return render_template(
        "my_appointments.html",
        appointments=appointments
    )

@app.route("/doctor_appointments")
def doctor_appointments():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "doctor":
        return "Access Denied"

    # Find the doctor's ID using the logged-in user's ID
    cursor.execute("""
        SELECT id
        FROM doctors
        WHERE user_id = %s
    """, (session["user_id"],))

    doctor = cursor.fetchone()

    # Safety check
    if doctor is None:
        return "Doctor profile not found."

    doctor_id = doctor[0]

    cursor.execute("""
    SELECT
        appointments.id,
        users.full_name,
        appointments.appointment_date,
        appointments.appointment_time,
        appointments.status
    FROM appointments
    JOIN users
    ON appointments.patient_id = users.id
    WHERE appointments.doctor_id = %s
    """, (doctor_id,))

    appointments = cursor.fetchall()

    return render_template(
        "doctor_appointments.html",
        appointments=appointments
    )

@app.route("/admin_appointments")
def admin_appointments():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
    SELECT
        appointments.id,
        users.full_name,
        doctors.doctor_name,
        appointments.appointment_date,
        appointments.appointment_time,
        appointments.status
    FROM appointments
    JOIN users
        ON appointments.patient_id = users.id
    JOIN doctors
        ON appointments.doctor_id = doctors.id
    """)

    appointments = cursor.fetchall()

    return render_template(
        "admin_appointments.html",
        appointments=appointments
    )

@app.route("/approve_appointment/<int:appointment_id>")
def approve_appointment(appointment_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "doctor":
        return "Access Denied"

    query = """
    UPDATE appointments
    SET status = %s
    WHERE id = %s
    """

    cursor.execute(query, ("Approved", appointment_id))
    connection.commit()

    return redirect("/doctor_appointments")

@app.route("/reject_appointment/<int:appointment_id>")
def reject_appointment(appointment_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "doctor":
        return "Access Denied"

    query = """
    UPDATE appointments
    SET status = %s
    WHERE id = %s
    """

    cursor.execute(query, ("Rejected", appointment_id))
    connection.commit()

    return redirect("/doctor_appointments")

@app.route("/edit_user/<int:id>", methods=["GET", "POST"])
def edit_user(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    if request.method == "GET":

        cursor.execute(
            "SELECT * FROM users WHERE id=%s",
            (id,)
        )

        user = cursor.fetchone()

        return render_template(
            "edit_user.html",
            user=user
        )

    if request.method == "POST":

        full_name = request.form["full_name"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]

        cursor.execute("""
            UPDATE users
            SET full_name=%s,
                email=%s,
                password=%s,
                role=%s
            WHERE id=%s
        """, (full_name, email, password, role, id))

        connection.commit()

        return redirect("/view_users")

@app.route("/delete_user/<int:id>")
def delete_user(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("DELETE FROM users WHERE id=%s", (id,))
    connection.commit()

    return redirect("/view_users")
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")
    
@app.route("/dashboard")
def dashboard():

    if "user" not in session:
        return redirect("/login")

    role = session["role"]


    # =========================
    # ADMIN DASHBOARD
    # =========================

    if role == "admin":

        # Total doctors
        cursor.execute("SELECT COUNT(*) FROM doctors")
        total_doctors = cursor.fetchone()[0]


        # Total patients
        cursor.execute("SELECT COUNT(*) FROM patients")
        total_patients = cursor.fetchone()[0]


        # Total nurses
        cursor.execute("SELECT COUNT(*) FROM nurses")
        total_nurses = cursor.fetchone()[0]


        # Total appointments
        cursor.execute("SELECT COUNT(*) FROM appointments")
        total_appointments = cursor.fetchone()[0]


        # Pending appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE status='Pending'
        """)
        pending = cursor.fetchone()[0]


        # Approved appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE status='Approved'
        """)
        approved = cursor.fetchone()[0]


        # Rejected appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE status='Rejected'
        """)
        rejected = cursor.fetchone()[0]
        # =========================
        # RECENT ACTIVITY LOGS
        # =========================

        cursor.execute("""
            SELECT
                user_name,
                role,
                action,
                created_at
            FROM activity_logs
            ORDER BY log_id DESC
            LIMIT 10
        """)

        activity_logs = cursor.fetchall()

        # =========================
        # ANALYTICS
        # =========================

        # Today's appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE appointment_date = CURDATE()
        """)
        today_appointments = cursor.fetchone()[0]


        # Completed consultations
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE status='Completed'
        """)
        completed_consultations = cursor.fetchone()[0]


        # Cancelled appointments
        cursor.execute("""
            SELECT COUNT(*)
            FROM appointments
            WHERE status='Cancelled'
        """)
        cancelled_appointments = cursor.fetchone()[0]


        # Pending laboratory reports
        cursor.execute("""
            SELECT COUNT(*)
            FROM laboratory
            WHERE status='Pending'
        """)
        pending_lab_reports = cursor.fetchone()[0]


        # =========================
        # DOCTOR SPECIALIZATION
        # =========================

        cursor.execute("""
            SELECT specialization, COUNT(*)
            FROM doctors
            GROUP BY specialization
        """)

        specialization_data = cursor.fetchall()

        # Doctor-wise consultation count
        cursor.execute("""
            SELECT d.doctor_name, COUNT(c.consultation_id)
            FROM consultation c
            JOIN doctors d
                ON c.doctor_id = d.id
            GROUP BY c.doctor_id, d.doctor_name
            ORDER BY COUNT(c.consultation_id) DESC
        """)

        doctor_consultations = cursor.fetchall()


        # =========================
        # MONTHLY PATIENT REGISTRATIONS
        # =========================

        cursor.execute("""
            SELECT
                MONTHNAME(created_at) AS month,
                COUNT(*) AS total
            FROM patients
            GROUP BY MONTH(created_at), MONTHNAME(created_at)
            ORDER BY MONTH(created_at)
        """)

        monthly_patients = cursor.fetchall()

        # =========================
        # PATIENT DEMOGRAPHICS
        # =========================

        # Gender distribution
        cursor.execute("""
            SELECT gender, COUNT(*)
            FROM patients
            WHERE gender IS NOT NULL
            GROUP BY gender
            ORDER BY gender
        """)

        gender_data = cursor.fetchall()


        # Age distribution
        cursor.execute("""
            SELECT
                CASE
                    WHEN age BETWEEN 0 AND 18 THEN '0-18'
                    WHEN age BETWEEN 19 AND 30 THEN '19-30'
                    WHEN age BETWEEN 31 AND 50 THEN '31-50'
                    WHEN age BETWEEN 51 AND 65 THEN '51-65'
                    ELSE '65+'
                END AS age_group,
                COUNT(*) AS total
            FROM patients
            GROUP BY
                CASE
                    WHEN age BETWEEN 0 AND 18 THEN '0-18'
                    WHEN age BETWEEN 19 AND 30 THEN '19-30'
                    WHEN age BETWEEN 31 AND 50 THEN '31-50'
                    WHEN age BETWEEN 51 AND 65 THEN '51-65'
                    ELSE '65+'
                END
            ORDER BY
                CASE
                    WHEN age_group = '0-18' THEN 1
                    WHEN age_group = '19-30' THEN 2
                    WHEN age_group = '31-50' THEN 3
                    WHEN age_group = '51-65' THEN 4
                    ELSE 5
                END
        """)

        age_data = cursor.fetchall()

        # Monthly appointment trends

        cursor.execute("""
            SELECT
                MONTHNAME(appointment_date) AS month,
                COUNT(*) AS total
            FROM appointments
            GROUP BY MONTH(appointment_date), MONTHNAME(appointment_date)
            ORDER BY MONTH(appointment_date)
        """)

        monthly_appointments = cursor.fetchall()


        # =========================
        # DOCTOR-WISE APPOINTMENTS
        # =========================

        cursor.execute("""
            SELECT
                d.doctor_name,
                COUNT(a.id) AS total
            FROM doctors d
            LEFT JOIN appointments a
                ON d.id = a.doctor_id
            GROUP BY d.id, d.doctor_name
            ORDER BY total DESC
        """)

        doctor_appointments = cursor.fetchall()


        return render_template(
            "admin_dashboard.html",

            # Existing dashboard data
            total_doctors=total_doctors,
            total_patients=total_patients,
            total_nurses=total_nurses,
            total_appointments=total_appointments,

            pending=pending,
            approved=approved,
            rejected=rejected,

            specialization_data=specialization_data,
            doctor_consultations=doctor_consultations,

            # Analytics data
            today_appointments=today_appointments,
            completed_consultations=completed_consultations,
            cancelled_appointments=cancelled_appointments,
            pending_lab_reports=pending_lab_reports,

            monthly_patients=monthly_patients,
            monthly_appointments=monthly_appointments,
            doctor_appointments=doctor_appointments,

            gender_data=gender_data,
            age_data=age_data,

            activity_logs=activity_logs
        )


    # =========================
    # DOCTOR DASHBOARD
    # =========================

    elif role == "doctor":

        cursor.execute("""
            SELECT id, doctor_name
            FROM doctors
            WHERE user_id=%s
        """, (session["user_id"],))

        doctor = cursor.fetchone()


        if doctor is None:
            return "Doctor record not found"


        doctor_id = doctor[0]


        cursor.execute("""
            SELECT
                notification_id,
                title,
                message,
                notification_type,
                status,
                created_at
            FROM notifications
            WHERE doctor_id=%s
            ORDER BY created_at DESC
        """, (doctor_id,))

        notifications = cursor.fetchall()


        return render_template(
            "doctor_dashboard.html",
            notifications=notifications
        )


    # =========================
    # NURSE DASHBOARD
    # =========================

    elif role == "nurse":

        notifications = []


        return render_template(
            "nurse_dashboard.html",
            notifications=notifications
        )


    # =========================
    # PATIENT DASHBOARD
    # =========================

    elif role == "patient":

        cursor.execute("""
            SELECT user_id, patient_name
            FROM patients
            WHERE user_id=%s
        """, (session["user_id"],))

        patient = cursor.fetchone()


        if patient is None:
            return "Patient record not found"


        patient_id = patient[0]


        cursor.execute("""
            SELECT
                notification_id,
                title,
                message,
                notification_type,
                status,
                created_at
            FROM notifications
            WHERE patient_id=%s
            ORDER BY created_at DESC
        """, (patient_id,))

        notifications = cursor.fetchall()


        return render_template(
            "patient_dashboard.html",
            notifications=notifications
        )


    return "Invalid Role"



@app.route("/reports_dashboard")
def reports_dashboard():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    return render_template("reports_dashboard.html")

def log_activity(action):
    if "user_id" not in session:
        return

    cursor.execute("""
        INSERT INTO activity_logs
        (
            user_id,
            user_name,
            role,
            action
        )
        VALUES (%s, %s, %s, %s)
    """, (
        session["user_id"],
        session["user"],
        session["role"],
        action
    ))

    connection.commit()




@app.route("/add_doctor", methods=["GET", "POST"])
def add_doctor():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"
    
    if request.method == "POST":
        doctor_name = request.form["doctor_name"]
        specialization = request.form["specialization"]
        phone = request.form["phone"]
        experience = request.form["experience"]
        user_id = request.form["user_id"]
        available_from = request.form["available_from"]
        available_to = request.form["available_to"]
        user_id = request.form["user_id"]

        query = """
        INSERT INTO doctors
        (
        doctor_name,
        specialization,
        phone,
        experience,
        available_from,
        available_to,
        user_id
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        """

        cursor.execute(
            query,
            (
                doctor_name,
                specialization,
                phone,
                experience,
                available_from,
                available_to,
                user_id
            )
        )

        connection.commit()
        log_activity("Added a new doctor")
        return redirect("/view_doctors")
    
    cursor.execute("""
    SELECT id, full_name
    FROM users
    WHERE role = 'doctor'
    """)

    doctor_users = cursor.fetchall()

    return render_template(
        "add_doctor.html",
        doctor_users=doctor_users
    )

@app.route("/edit_doctor/<int:id>", methods=["GET", "POST"])
def edit_doctor(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    if request.method == "GET":
        cursor.execute("SELECT * FROM doctors WHERE id=%s", (id,))
        doctor = cursor.fetchone()
        return render_template("edit_doctor.html", doctor=doctor)

    if request.method == "POST":
        doctor_name = request.form["doctor_name"]
        specialization = request.form["specialization"]
        phone = request.form["phone"]
        experience = request.form["experience"]
        available_from = request.form["available_from"]
        available_to = request.form["available_to"]

        cursor.execute("""
            UPDATE doctors
            SET doctor_name=%s,
                specialization=%s,
                phone=%s,
                experience=%s,
                available_from=%s,
                available_to=%s
            WHERE id=%s
        """, (
            doctor_name,
            specialization,
            phone,
            experience,
            available_from,
            available_to,
            id
        ))

        connection.commit()
        
        return redirect("/view_doctors")

@app.route("/view_doctors")
def view_doctors():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"
    
    cursor.execute("SELECT * FROM doctors")
    doctors = cursor.fetchall()

    print(doctors)

    return render_template("view_doctors.html", doctors=doctors)

@app.route("/delete_doctor/<int:id>")
def delete_doctor(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("DELETE FROM doctors WHERE id=%s", (id,))
    connection.commit()

    return redirect("/view_doctors")


@app.route("/add_nurse", methods=["GET", "POST"])
def add_nurse():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"


    if request.method == "POST":
        nurse_name = request.form["nurse_name"]
        department = request.form["department"]
        shift = request.form["shift"]
        phone = request.form["phone"]
        experience = request.form["experience"]

        query = """
        INSERT INTO nurses
        (nurse_name, department, shift, phone, experience)
        VALUES (%s, %s, %s, %s, %s)
        """

        cursor.execute(query, (nurse_name, department, shift, phone, experience))
        connection.commit()

        return redirect("/view_nurses")

    return render_template("add_nurse.html")

@app.route("/edit_nurse/<int:id>", methods=["GET", "POST"])
def edit_nurse(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    if request.method == "GET":
        cursor.execute("SELECT * FROM nurses WHERE id=%s", (id,))
        nurse = cursor.fetchone()
        return render_template("edit_nurse.html", nurse=nurse)

    if request.method == "POST":
        nurse_name = request.form["nurse_name"]
        department = request.form["department"]
        shift = request.form["shift"]
        phone = request.form["phone"]
        experience = request.form["experience"]

        cursor.execute("""
            UPDATE nurses
            SET nurse_name=%s,
                department=%s,
                shift=%s,
                phone=%s,
                experience=%s
            WHERE id=%s
        """, (nurse_name, department, shift, phone, experience, id))

        connection.commit()
        return redirect("/view_nurses")

@app.route("/view_nurses")
def view_nurses():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"
    cursor.execute("SELECT * FROM nurses")
    nurses = cursor.fetchall()

    return render_template("view_nurses.html", nurses=nurses)

@app.route("/delete_nurse/<int:id>")
def delete_nurse(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("DELETE FROM nurses WHERE id=%s", (id,))
    connection.commit()

    return redirect("/view_nurses")

@app.route("/add_patient", methods=["GET", "POST"])
def add_patient():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    if request.method == "POST":
        patient_name = request.form["patient_name"]
        age = request.form["age"]
        disease = request.form["disease"]
        phone = request.form["phone"]
        gender = request.form["gender"]
        blood_group = request.form["blood_group"]
        address = request.form["address"]
        aadhaar_number = request.form["aadhaar_number"]

        cursor.execute("""
            INSERT INTO patients
            (patient_name, age, disease, phone, gender, blood_group, aadhaar_number, address)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            patient_name,
            age,
            disease,
            phone,
            gender,
            blood_group,
            aadhaar_number,
            address
        ))

        connection.commit()
        log_activity("Added a new patient")
        return redirect("/view_patients")


    return render_template("add_patient.html")

@app.route("/edit_patient/<int:id>", methods=["GET", "POST"])
def edit_patient(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    if request.method == "GET":
        cursor.execute("SELECT * FROM patients WHERE id=%s", (id,))
        patient = cursor.fetchone()
        return render_template("edit_patient.html", patient=patient)

    if request.method == "POST":
        patient_name = request.form["patient_name"]
        age = request.form["age"]
        disease = request.form["disease"]
        phone = request.form["phone"]
        gender = request.form["gender"]
        blood_group = request.form["blood_group"]
        address = request.form["address"]
        aadhaar_number = request.form["aadhaar_number"]

        cursor.execute("""
            UPDATE patients
            SET patient_name=%s,
                age=%s,
                disease=%s,
                phone=%s,
                gender = %s,
                blood_group =%s,
                address =%s,
                aadhaar_number =%s
            WHERE id=%s
        """, (patient_name, age, disease, phone, gender, blood_group, address, aadhar_number, id))

        connection.commit()
        return redirect("/view_patients")

@app.route("/add_ehr", methods=["GET", "POST"])
def add_ehr():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        medical_history = request.form["medical_history"]
        allergies = request.form["allergies"]
        diagnosis = request.form["diagnosis"]
        medications = request.form["medications"]

        cursor.execute("""
            INSERT INTO ehr
            (patient_id, medical_history, allergies, diagnosis, medications)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            patient_id,
            medical_history,
            allergies,
            diagnosis,
            medications
        ))

        connection.commit()

        return redirect("/view_ehr")

    return render_template("add_ehr.html", patients=patients)


@app.route("/view_ehr")
def view_ehr():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    cursor.execute("""
        SELECT
            ehr.ehr_id,
            patients.patient_name,
            ehr.medical_history,
            ehr.allergies,
            ehr.diagnosis,
            ehr.medications
        FROM ehr
        JOIN patients
        ON ehr.patient_id = patients.id
    """)

    ehr_records = cursor.fetchall()

    return render_template("view_ehr.html", ehr_records=ehr_records)


@app.route("/edit_ehr/<int:ehr_id>", methods=["GET", "POST"])
def edit_ehr(ehr_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    if request.method == "POST":

        medical_history = request.form["medical_history"]
        allergies = request.form["allergies"]
        diagnosis = request.form["diagnosis"]
        medications = request.form["medications"]

        cursor.execute("""
            UPDATE ehr
            SET
                medical_history = %s,
                allergies = %s,
                diagnosis = %s,
                medications = %s
            WHERE ehr_id = %s
        """, (
            medical_history,
            allergies,
            diagnosis,
            medications,
            ehr_id
        ))

        connection.commit()

        return redirect("/view_ehr")

    cursor.execute("""
        SELECT *
        FROM ehr
        WHERE ehr_id = %s
    """, (ehr_id,))

    ehr = cursor.fetchone()

    return render_template("edit_ehr.html", ehr=ehr)

@app.route("/my_ehr")
def my_ehr():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    cursor.execute("""
        SELECT e.*
        FROM ehr e
        JOIN patients p
        ON e.patient_id = p.id
        WHERE p.user_id = %s
    """, (session["user_id"],))

    ehr = cursor.fetchone()

    return render_template("my_ehr.html", ehr=ehr)

@app.route("/add_consultation", methods=["GET", "POST"])
def add_consultation():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        symptoms = request.form["symptoms"]
        diagnosis = request.form["diagnosis"]
        treatment = request.form["treatment"]
        consultation_date = request.form["consultation_date"]

        cursor.execute("""
            INSERT INTO consultation
            (patient_id, doctor_id, symptoms, diagnosis, treatment, consultation_date)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            patient_id,
            doctor_id,
            symptoms,
            diagnosis,
            treatment,
            consultation_date
        ))

        connection.commit()

        return redirect("/view_consultation")
    return render_template(
        "add_consultation.html",
        patients=patients,
        doctors=doctors
    )

@app.route("/view_consultation")
def view_consultation():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    cursor.execute("""
        SELECT
            c.consultation_id,
            p.patient_name,
            d.doctor_name,
            c.symptoms,
            c.diagnosis,
            c.treatment,
            c.consultation_date
        FROM consultation c
        JOIN patients p
            ON c.patient_id = p.id
        JOIN doctors d
            ON c.doctor_id = d.id
    """)

    consultations = cursor.fetchall()

    return render_template(
        "view_consultation.html",
        consultations=consultations
    )

@app.route("/edit_consultation/<int:consultation_id>", methods=["GET", "POST"])
def edit_consultation(consultation_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        symptoms = request.form["symptoms"]
        diagnosis = request.form["diagnosis"]
        treatment = request.form["treatment"]
        consultation_date = request.form["consultation_date"]

        cursor.execute("""
            UPDATE consultation
            SET
                patient_id = %s,
                doctor_id = %s,
                symptoms = %s,
                diagnosis = %s,
                treatment = %s,
                consultation_date = %s
            WHERE consultation_id = %s
        """, (
            patient_id,
            doctor_id,
            symptoms,
            diagnosis,
            treatment,
            consultation_date,
            consultation_id
        ))

        connection.commit()

        return redirect("/view_consultation")

    cursor.execute("""
        SELECT *
        FROM consultation
        WHERE consultation_id = %s
    """, (consultation_id,))

    consultation = cursor.fetchone()

    return render_template(
        "edit_consultation.html",
        consultation=consultation,
        patients=patients,
        doctors=doctors
    )

    return render_template(
        "add_consultation.html",
        patients=patients,
        doctors=doctors
    )

@app.route("/my_consultations")
def my_consultations():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    cursor.execute("""
        SELECT
            c.consultation_id,
            d.doctor_name,
            c.symptoms,
            c.diagnosis,
            c.treatment,
            c.consultation_date
        FROM consultation c
        JOIN patients p
            ON c.patient_id = p.id
        JOIN doctors d
            ON c.doctor_id = d.id
        WHERE p.user_id = %s
    """, (session["user_id"],))

    consultations = cursor.fetchall()

    return render_template(
        "my_consultations.html",
        consultations=consultations
    )

@app.route("/add_prescription", methods=["GET", "POST"])
def add_prescription():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        medicine_name = request.form["medicine_name"]
        dosage = request.form["dosage"]
        frequency = request.form["frequency"]
        duration = request.form["duration"]
        instructions = request.form["instructions"]
        prescribed_date = request.form["prescribed_date"]

        cursor.execute("""
            INSERT INTO prescriptions
            (patient_id, doctor_id, medicine_name, dosage,
             frequency, duration, instructions, prescribed_date)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            patient_id,
            doctor_id,
            medicine_name,
            dosage,
            frequency,
            duration,
            instructions,
            prescribed_date
        ))

        connection.commit()

        return redirect("/view_prescriptions")

    return render_template(
        "add_prescription.html",
        patients=patients,
        doctors=doctors
    )

@app.route("/view_prescriptions")
def view_prescriptions():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    cursor.execute("""
        SELECT
            pr.prescription_id,
            p.patient_name,
            d.doctor_name,
            pr.medicine_name,
            pr.dosage,
            pr.frequency,
            pr.duration,
            pr.instructions,
            pr.prescribed_date
        FROM prescriptions pr
        JOIN patients p
            ON pr.patient_id = p.id
        JOIN doctors d
            ON pr.doctor_id = d.id
    """)

    prescriptions = cursor.fetchall()

    return render_template(
        "view_prescriptions.html",
        prescriptions=prescriptions
    )

@app.route("/edit_prescription/<int:prescription_id>", methods=["GET", "POST"])
def edit_prescription(prescription_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        medicine_name = request.form["medicine_name"]
        dosage = request.form["dosage"]
        frequency = request.form["frequency"]
        duration = request.form["duration"]
        instructions = request.form["instructions"]
        prescribed_date = request.form["prescribed_date"]

        cursor.execute("""
            UPDATE prescriptions
            SET
                patient_id = %s,
                doctor_id = %s,
                medicine_name = %s,
                dosage = %s,
                frequency = %s,
                duration = %s,
                instructions = %s,
                prescribed_date = %s
            WHERE prescription_id = %s
        """, (
            patient_id,
            doctor_id,
            medicine_name,
            dosage,
            frequency,
            duration,
            instructions,
            prescribed_date,
            prescription_id
        ))

        connection.commit()

        return redirect("/view_prescriptions")

    cursor.execute("""
        SELECT *
        FROM prescriptions
        WHERE prescription_id = %s
    """, (prescription_id,))

    prescription = cursor.fetchone()

    return render_template(
        "edit_prescription.html",
        prescription=prescription,
        patients=patients,
        doctors=doctors
    )

@app.route("/my_prescriptions")
def my_prescriptions():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    cursor.execute("""
        SELECT
            pr.prescription_id,
            d.doctor_name,
            pr.medicine_name,
            pr.dosage,
            pr.frequency,
            pr.duration,
            pr.instructions,
            pr.prescribed_date
        FROM prescriptions pr
        JOIN patients p
            ON pr.patient_id = p.id
        JOIN doctors d
            ON pr.doctor_id = d.id
        WHERE p.user_id = %s
    """, (session["user_id"],))

    prescriptions = cursor.fetchall()

    return render_template(
        "my_prescriptions.html",
        prescriptions=prescriptions
    )

@app.route("/add_lab", methods=["GET", "POST"])
def add_lab():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    # Fetch patients
    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    # Fetch doctors
    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        test_name = request.form["test_name"]
        test_date = request.form["test_date"]
        result = request.form["result"]
        status = request.form["status"]

        cursor.execute("""
            INSERT INTO laboratory
            (patient_id, doctor_id, test_name, test_date, result, status)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            patient_id,
            doctor_id,
            test_name,
            test_date,
            result,
            status
        ))

        connection.commit()

        return redirect("/view_lab")

    return render_template(
        "add_lab.html",
        patients=patients,
        doctors=doctors
    )

@app.route("/view_lab")
def view_lab():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    cursor.execute("""
        SELECT
            l.lab_id,
            p.patient_name,
            d.doctor_name,
            l.test_name,
            l.test_date,
            l.result,
            l.status
        FROM laboratory l
        JOIN patients p
            ON l.patient_id = p.id
        JOIN doctors d
            ON l.doctor_id = d.id
    """)

    lab_reports = cursor.fetchall()

    return render_template(
        "view_lab.html",
        lab_reports=lab_reports
    )

@app.route("/edit_lab/<int:lab_id>", methods=["GET", "POST"])
def edit_lab(lab_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    cursor.execute("SELECT id, doctor_name FROM doctors")
    doctors = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]
        doctor_id = request.form["doctor_id"]
        test_name = request.form["test_name"]
        test_date = request.form["test_date"]
        result = request.form["result"]
        status = request.form["status"]

        cursor.execute("""
            UPDATE laboratory
            SET
                patient_id = %s,
                doctor_id = %s,
                test_name = %s,
                test_date = %s,
                result = %s,
                status = %s
            WHERE lab_id = %s
        """, (
            patient_id,
            doctor_id,
            test_name,
            test_date,
            result,
            status,
            lab_id
        ))

        connection.commit()

        return redirect("/view_lab")

    cursor.execute("""
        SELECT *
        FROM laboratory
        WHERE lab_id = %s
    """, (lab_id,))

    lab = cursor.fetchone()

    return render_template(
        "edit_lab.html",
        lab=lab,
        patients=patients,
        doctors=doctors
    )

@app.route("/my_lab_reports")
def my_lab_reports():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "patient":
        return "Access Denied"

    cursor.execute("""
        SELECT
            l.lab_id,
            d.doctor_name,
            l.test_name,
            l.test_date,
            l.result,
            l.status
        FROM laboratory l
        JOIN patients p
            ON l.patient_id = p.id
        JOIN doctors d
            ON l.doctor_id = d.id
        WHERE p.user_id = %s
    """, (session["user_id"],))

    reports = cursor.fetchall()

    return render_template(
        "my_lab_reports.html",
        reports=reports
    )

@app.route("/search_patient_history", methods=["GET", "POST"])
def search_patient_history():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    cursor.execute("SELECT id, patient_name FROM patients")
    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        return redirect(f"/patient_history/{patient_id}")

    return render_template(
        "search_patient_history.html",
        patients=patients
    )

@app.route("/patient_history/<int:patient_id>")
def patient_history(patient_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor"]:
        return "Access Denied"

    # Patient Details
    cursor.execute("""
        SELECT * FROM patients
        WHERE id = %s
    """, (patient_id,))
    patient = cursor.fetchone()

    # EHR
    cursor.execute("""
        SELECT * FROM ehr
        WHERE patient_id = %s
    """, (patient_id,))
    ehr = cursor.fetchall()

    # Consultations
    cursor.execute("""
        SELECT * FROM consultation
        WHERE patient_id = %s
    """, (patient_id,))
    consultations = cursor.fetchall()

    # Prescriptions
    cursor.execute("""
        SELECT * FROM prescriptions
        WHERE patient_id = %s
    """, (patient_id,))
    prescriptions = cursor.fetchall()

    # Laboratory
    cursor.execute("""
        SELECT * FROM laboratory
        WHERE patient_id = %s
    """, (patient_id,))
    labs = cursor.fetchall()

    return render_template(
        "patient_history.html",
        patient=patient,
        ehr=ehr,
        consultations=consultations,
        prescriptions=prescriptions,
        labs=labs
    )


from io import BytesIO
from flask import send_file
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet

@app.route("/generate_report/<int:patient_id>")
def generate_report(patient_id):

    if "user" not in session:
        return redirect("/login")

    # Patient Details
    cursor.execute("SELECT * FROM patients WHERE id=%s", (patient_id,))
    patient = cursor.fetchone()

    # EHR
    cursor.execute("SELECT * FROM ehr WHERE patient_id=%s", (patient_id,))
    ehr = cursor.fetchall()

    # Consultation
    cursor.execute("SELECT * FROM consultation WHERE patient_id=%s", (patient_id,))
    consultations = cursor.fetchall()

    # Prescriptions
    cursor.execute("SELECT * FROM prescriptions WHERE patient_id=%s", (patient_id,))
    prescriptions = cursor.fetchall()

    # Laboratory
    cursor.execute("SELECT * FROM laboratory WHERE patient_id=%s", (patient_id,))
    labs = cursor.fetchall()

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    story = []

    # ---------------- HEADER ----------------

    story.append(Paragraph("Hospital Management System", styles["Title"]))
    story.append(Paragraph("Patient Medical Report", styles["Heading1"]))

    # ---------------- PATIENT ----------------

    story.append(Paragraph("<br/><b>Patient Information</b>", styles["Heading2"]))

    story.append(Paragraph(f"Name : {patient[1]}", styles["Normal"]))
    story.append(Paragraph(f"Age : {patient[2]}", styles["Normal"]))
    story.append(Paragraph(f"Disease : {patient[3]}", styles["Normal"]))
    story.append(Paragraph(f"Phone : {patient[4]}", styles["Normal"]))
    story.append(Paragraph(f"Gender : {patient[5]}", styles["Normal"]))
    story.append(Paragraph(f"Blood Group : {patient[6]}", styles["Normal"]))
    story.append(Paragraph(f"Address : {patient[7]}", styles["Normal"]))

    # ---------------- EHR ----------------

    story.append(Paragraph("<br/><b>Electronic Health Record</b>", styles["Heading2"]))

    if ehr:

        for record in ehr:

            story.append(Paragraph(f"Medical History : {record[2]}", styles["Normal"]))
            story.append(Paragraph(f"Allergies : {record[3]}", styles["Normal"]))
            story.append(Paragraph(f"Diagnosis : {record[4]}", styles["Normal"]))
            story.append(Paragraph(f"Medications : {record[5]}", styles["Normal"]))

    else:

        story.append(Paragraph("No EHR Records Found", styles["Normal"]))

    # ---------------- CONSULTATION ----------------

    story.append(Paragraph("<br/><b>Consultation History</b>", styles["Heading2"]))

    if consultations:

        for c in consultations:

            story.append(Paragraph(f"Doctor ID : {c[2]}", styles["Normal"]))
            story.append(Paragraph(f"Symptoms : {c[3]}", styles["Normal"]))
            story.append(Paragraph(f"Diagnosis : {c[4]}", styles["Normal"]))
            story.append(Paragraph(f"Treatment : {c[5]}", styles["Normal"]))
            story.append(Paragraph(f"Date : {c[6]}", styles["Normal"]))
            story.append(Paragraph("----------------------------", styles["Normal"]))

    else:

        story.append(Paragraph("No Consultation Records Found", styles["Normal"]))

    # ---------------- PRESCRIPTION ----------------

    story.append(Paragraph("<br/><b>Prescription History</b>", styles["Heading2"]))

    if prescriptions:

        for p in prescriptions:

            story.append(Paragraph(f"Medicine : {p[3]}", styles["Normal"]))
            story.append(Paragraph(f"Dosage : {p[4]}", styles["Normal"]))
            story.append(Paragraph(f"Frequency : {p[5]}", styles["Normal"]))
            story.append(Paragraph(f"Duration : {p[6]}", styles["Normal"]))
            story.append(Paragraph(f"Instructions : {p[7]}", styles["Normal"]))
            story.append(Paragraph(f"Date : {p[8]}", styles["Normal"]))
            story.append(Paragraph("----------------------------", styles["Normal"]))

    else:

        story.append(Paragraph("No Prescription Records Found", styles["Normal"]))

    # ---------------- LAB REPORTS ----------------

    story.append(Paragraph("<br/><b>Laboratory Reports</b>", styles["Heading2"]))

    if labs:

        for lab in labs:

            story.append(Paragraph(f"Test Name : {lab[3]}", styles["Normal"]))
            story.append(Paragraph(f"Test Date : {lab[4]}", styles["Normal"]))
            story.append(Paragraph(f"Result : {lab[5]}", styles["Normal"]))
            story.append(Paragraph(f"Status : {lab[6]}", styles["Normal"]))
            story.append(Paragraph("----------------------------", styles["Normal"]))

    else:

        story.append(Paragraph("No Laboratory Reports Found", styles["Normal"]))

    doc.build(story)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"medical_report_{patient_id}.pdf",
        mimetype="application/pdf"
    )


@app.route("/view_patients")
def view_patients():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"
    cursor.execute("SELECT * FROM patients")
    patients = cursor.fetchall()

    return render_template("view_patients.html", patients = patients)


@app.route("/add_medicine", methods=["GET", "POST"])
def add_medicine():

    if "user" not in session:
        return redirect("/login")

    if request.method == "POST":

        medicine_name = request.form["medicine_name"]
        category = request.form["category"]
        manufacturer = request.form["manufacturer"]
        batch_no = request.form["batch_no"]
        stock = request.form["stock"]
        unit_price = request.form["unit_price"]
        expiry_date = request.form["expiry_date"]

        cursor.execute("""
            INSERT INTO medicines
            (medicine_name, category, manufacturer, batch_no,
             stock, unit_price, expiry_date)

            VALUES (%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            medicine_name,
            category,
            manufacturer,
            batch_no,
            stock,
            unit_price,
            expiry_date
        ))

        connection.commit()

        return redirect("/view_medicines")

    return render_template("add_medicine.html")

@app.route("/view_medicines")
def view_medicines():

    cursor.execute("""
        SELECT *
        FROM medicines
    """)

    medicines = cursor.fetchall()

    return render_template(
        "view_medicines.html",
        medicines=medicines
    )

@app.route("/edit_medicine/<int:medicine_id>", methods=["GET", "POST"])
def edit_medicine(medicine_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    if request.method == "POST":

        medicine_name = request.form["medicine_name"]
        category = request.form["category"]
        manufacturer = request.form["manufacturer"]
        batch_no = request.form["batch_no"]
        stock = request.form["stock"]
        unit_price = request.form["unit_price"]
        expiry_date = request.form["expiry_date"]

        cursor.execute("""
            UPDATE medicines
            SET
                medicine_name=%s,
                category=%s,
                manufacturer=%s,
                batch_no=%s,
                stock=%s,
                unit_price=%s,
                expiry_date=%s
            WHERE medicine_id=%s
        """,
        (
            medicine_name,
            category,
            manufacturer,
            batch_no,
            stock,
            unit_price,
            expiry_date,
            medicine_id
        ))

        connection.commit()

        return redirect("/view_medicines")

    cursor.execute("""
        SELECT *
        FROM medicines
        WHERE medicine_id=%s
    """, (medicine_id,))

    medicine = cursor.fetchone()

    return render_template(
        "edit_medicine.html",
        medicine=medicine
    )

@app.route("/dispense_medicine", methods=["GET", "POST"])
def dispense_medicine():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    cursor.execute("""
        SELECT medicine_id, medicine_name
        FROM medicines
    """)
    medicines = cursor.fetchall()

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)
    patients = cursor.fetchall()

    if request.method == "POST":

        medicine_id = request.form["medicine_id"]
        patient_id = request.form["patient_id"]
        quantity = int(request.form["quantity"])
        dispensed_date = request.form["dispensed_date"]

        cursor.execute("""
            SELECT stock
            FROM medicines
            WHERE medicine_id = %s
        """, (medicine_id,))

        stock = cursor.fetchone()[0]

        if stock < quantity:
            return "Not enough stock available."

        cursor.execute("""
            INSERT INTO dispensed_medicines
            (medicine_id, patient_id, quantity, dispensed_date)
            VALUES (%s, %s, %s, %s)
        """, (
            medicine_id,
            patient_id,
            quantity,
            dispensed_date
        ))

        cursor.execute("""
            UPDATE medicines
            SET stock = stock - %s
            WHERE medicine_id = %s
        """, (
            quantity,
            medicine_id
        ))

        connection.commit()

        return redirect("/dispensing_history")

    return render_template(
        "dispense_medicine.html",
        medicines=medicines,
        patients=patients
    )

@app.route("/dispensing_history")
def dispensing_history():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    cursor.execute("""
        SELECT
            d.dispense_id,
            m.medicine_name,
            p.patient_name,
            d.quantity,
            d.dispensed_date
        FROM dispensed_medicines d
        JOIN medicines m
            ON d.medicine_id = m.medicine_id
        JOIN patients p
            ON d.patient_id = p.id
        ORDER BY d.dispense_id DESC
    """)

    records = cursor.fetchall()

    return render_template(
        "dispensing_history.html",
        records=records
    )

@app.route("/stock_update", methods=["GET", "POST"])
def stock_update():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    cursor.execute("""
        SELECT medicine_id, medicine_name
        FROM medicines
    """)
    medicines = cursor.fetchall()

    if request.method == "POST":

        medicine_id = request.form["medicine_id"]
        new_stock = int(request.form["new_stock"])

        cursor.execute("""
            UPDATE medicines
            SET stock = stock + %s
            WHERE medicine_id = %s
        """, (new_stock, medicine_id))

        connection.commit()

        return redirect("/view_medicines")

    return render_template(
        "stock_update.html",
        medicines=medicines
    )

@app.route("/search_medicine", methods=["GET", "POST"])
def search_medicine():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    medicines = []

    if request.method == "POST":

        keyword = request.form["keyword"]

        cursor.execute("""
            SELECT *
            FROM medicines
            WHERE medicine_name LIKE %s
        """, ("%" + keyword + "%",))

        medicines = cursor.fetchall()

    return render_template(
        "search_medicine.html",
        medicines=medicines
    )

@app.route("/low_stock")
def low_stock():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    cursor.execute("""
        SELECT *
        FROM medicines
        WHERE stock < 20
        ORDER BY stock ASC
    """)

    medicines = cursor.fetchall()

    return render_template(
        "low_stock.html",
        medicines=medicines
    )

@app.route("/expired_medicines")
def expired_medicines():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    today = date.today()

    cursor.execute("""
        SELECT *
        FROM medicines
        WHERE expiry_date < %s
        ORDER BY expiry_date
    """, (today,))

    medicines = cursor.fetchall()

    return render_template(
        "expired_medicines.html",
        medicines=medicines
    ) 

@app.route("/medicine_reports")
def pharmacy_report():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    # Total medicines
    cursor.execute("SELECT COUNT(*) FROM medicines")
    total_medicines = cursor.fetchone()[0]

    # Total stock
    cursor.execute("SELECT SUM(stock) FROM medicines")
    total_stock = cursor.fetchone()[0]

    # Low stock medicines
    cursor.execute("SELECT COUNT(*) FROM medicines WHERE stock < 20")
    low_stock = cursor.fetchone()[0]

    # Expired medicines
    cursor.execute("""
        SELECT COUNT(*)
        FROM medicines
        WHERE expiry_date < CURDATE()
    """)
    expired = cursor.fetchone()[0]

    # Total medicines dispensed
    cursor.execute("""
        SELECT IFNULL(SUM(quantity),0)
        FROM dispensed_medicines
    """)
    dispensed = cursor.fetchone()[0]

    return render_template(
        "pharmacy_report.html",
        total_medicines=total_medicines,
        total_stock=total_stock,
        low_stock=low_stock,
        expired=expired,
        dispensed=dispensed
    )

@app.route("/pharmacist_dashboard")
def pharmacist_dashboard():
    
    if "user" not in session:
        return redirect("/login")

    if session["role"] != "pharmacist":
        return "Access Denied"

    return render_template("pharmacist_dashboard.html")


@app.route("/search_patient", methods=["GET", "POST"])
def search_patient():

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    patients = []

    if request.method == "POST":

        search_by = request.form["search_by"]
        keyword = request.form["keyword"]

        if search_by == "id":

            cursor.execute("""
                SELECT *
                FROM patients
                WHERE id=%s
            """, (keyword,))

        elif search_by == "name":

            cursor.execute("""
                SELECT *
                FROM patients
                WHERE patient_name LIKE %s
            """, ("%" + keyword + "%",))

        elif search_by == "phone":

            cursor.execute("""
                SELECT *
                FROM patients
                WHERE phone LIKE %s
            """, ("%" + keyword + "%",))

        elif search_by == "aadhaar":

            cursor.execute("""
                SELECT *
                FROM patients
                WHERE aadhaar_number LIKE %s
            """, ("%" + keyword + "%",))

        patients = cursor.fetchall()

    return render_template(
        "search_patient.html",
        patients=patients
    )

@app.route("/billing_dashboard")
def billing_dashboard():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    return render_template("billing_dashboard.html")

@app.route("/generate_bill", methods=["GET","POST"])
def generate_bill():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)

    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        consultation_fee = float(request.form["consultation_fee"])

        laboratory_fee = float(request.form["laboratory_fee"])

        pharmacy_fee = float(request.form["pharmacy_fee"])

        total_amount = consultation_fee + laboratory_fee + pharmacy_fee

        cursor.execute("""
            INSERT INTO billing
            (
                patient_id,
                consultation_fee,
                laboratory_fee,
                pharmacy_fee,
                total_amount,
                bill_date
            )

            VALUES
            (%s,%s,%s,%s,%s,CURDATE())
        """,
        (
            patient_id,
            consultation_fee,
            laboratory_fee,
            pharmacy_fee,
            total_amount
        ))

        connection.commit()

        return redirect("/view_bills")

    return render_template(
        "generate_bill.html",
        patients=patients
    )


@app.route("/view_bills")
def view_bills():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            b.bill_id,
            p.patient_name,
            b.consultation_fee,
            b.laboratory_fee,
            b.pharmacy_fee,
            b.total_amount,
            b.payment_status,
            b.bill_date

        FROM billing b

        JOIN patients p
        ON b.patient_id = p.id

        ORDER BY b.bill_id DESC
    """)

    bills = cursor.fetchall()

    return render_template(
        "view_bills.html",
        bills=bills
    )

@app.route("/payment_status")
def payment_status():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            b.bill_id,
            p.patient_name,
            b.total_amount,
            b.payment_status

        FROM billing b

        JOIN patients p
        ON b.patient_id = p.id

        ORDER BY b.bill_id DESC
    """)

    bills = cursor.fetchall()

    return render_template(
        "payment_status.html",
        bills=bills
    )

@app.route("/mark_paid/<int:bill_id>")
def mark_paid(bill_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        UPDATE billing
        SET payment_status='Paid'
        WHERE bill_id=%s
    """, (bill_id,))

    connection.commit()

    return redirect("/payment_status")

@app.route("/generate_invoice/<int:bill_id>")
def generate_invoice(bill_id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            b.bill_id,
            p.patient_name,
            b.consultation_fee,
            b.laboratory_fee,
            b.pharmacy_fee,
            b.total_amount,
            b.payment_status,
            b.bill_date

        FROM billing b

        JOIN patients p
        ON b.patient_id = p.id

        WHERE b.bill_id=%s
    """, (bill_id,))

    bill = cursor.fetchone()

    buffer = BytesIO()

    doc = SimpleDocTemplate(buffer)

    styles = getSampleStyleSheet()

    story = []

    story.append(Paragraph("<b>Hospital Invoice</b>", styles["Title"]))
    story.append(Paragraph("<br/>", styles["Normal"]))

    story.append(Paragraph(f"Bill ID : {bill[0]}", styles["Normal"]))
    story.append(Paragraph(f"Patient : {bill[1]}", styles["Normal"]))
    story.append(Paragraph(f"Consultation Fee : ₹{bill[2]}", styles["Normal"]))
    story.append(Paragraph(f"Laboratory Fee : ₹{bill[3]}", styles["Normal"]))
    story.append(Paragraph(f"Pharmacy Fee : ₹{bill[4]}", styles["Normal"]))
    story.append(Paragraph(f"Total Amount : ₹{bill[5]}", styles["Normal"]))
    story.append(Paragraph(f"Payment Status : {bill[6]}", styles["Normal"]))
    story.append(Paragraph(f"Bill Date : {bill[7]}", styles["Normal"]))

    doc.build(story)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"Invoice_{bill_id}.pdf",
        mimetype="application/pdf"
    )

# =========================================================
# PATIENT API
# =========================================================


# =========================
# GET ALL PATIENTS
# =========================

@app.route("/api/patients", methods=["GET"])
def api_patients():

    cursor.execute("""
        SELECT
            id,
            patient_name,
            age,
            disease,
            phone,
            gender,
            blood_group,
            address,
            user_id,
            aadhaar_number
        FROM patients
    """)

    patients = cursor.fetchall()

    data = []

    for patient in patients:

        data.append({

            "id": patient[0],
            "patient_name": patient[1],
            "age": patient[2],
            "disease": patient[3],
            "phone": patient[4],
            "gender": patient[5],
            "blood_group": patient[6],
            "address": patient[7],
            "user_id": patient[8],
            "aadhaar_number": patient[9]

        })

    return jsonify(data)


# =========================
# ADD PATIENT
# =========================

@app.route("/api/patients", methods=["POST"])
def api_add_patient():

    data = request.json

    cursor.execute("""
        INSERT INTO patients
        (
            patient_name,
            age,
            disease,
            phone,
            gender,
            blood_group,
            address,
            user_id,
            aadhaar_number
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,%s,%s,%s)
    """, (

        data["patient_name"],
        data["age"],
        data["disease"],
        data["phone"],
        data["gender"],
        data["blood_group"],
        data["address"],
        data.get("user_id"),
        data["aadhaar_number"]

    ))

    connection.commit()

    return jsonify({
        "message": "Patient Added Successfully"
    }), 201


# =========================
# GET ONE PATIENT
# =========================

@app.route("/api/patients/<int:id>", methods=["GET"])
def api_get_patient(id):

    cursor.execute("""
        SELECT
            id,
            patient_name,
            age,
            disease,
            phone,
            gender,
            blood_group,
            address,
            user_id,
            aadhaar_number
        FROM patients
        WHERE id=%s
    """, (id,))

    patient = cursor.fetchone()

    if patient is None:

        return jsonify({
            "message": "Patient Not Found"
        }), 404

    return jsonify({

        "id": patient[0],
        "patient_name": patient[1],
        "age": patient[2],
        "disease": patient[3],
        "phone": patient[4],
        "gender": patient[5],
        "blood_group": patient[6],
        "address": patient[7],
        "user_id": patient[8],
        "aadhaar_number": patient[9]

    })


# =========================
# UPDATE PATIENT
# =========================

@app.route("/api/patients/<int:id>", methods=["PUT"])
def api_update_patient(id):

    data = request.json

    cursor.execute("""
        SELECT id
        FROM patients
        WHERE id=%s
    """, (id,))

    patient = cursor.fetchone()

    if patient is None:

        return jsonify({
            "message": "Patient Not Found"
        }), 404

    cursor.execute("""
        UPDATE patients
        SET
            patient_name=%s,
            age=%s,
            disease=%s,
            phone=%s,
            gender=%s,
            blood_group=%s,
            address=%s,
            user_id=%s,
            aadhaar_number=%s
        WHERE id=%s
    """, (

        data["patient_name"],
        data["age"],
        data["disease"],
        data["phone"],
        data["gender"],
        data["blood_group"],
        data["address"],
        data.get("user_id"),
        data["aadhaar_number"],
        id

    ))

    connection.commit()

    return jsonify({
        "message": "Patient Updated Successfully"
    })


# =========================
# DELETE PATIENT
# =========================

@app.route("/api/patients/<int:id>", methods=["DELETE"])
def api_delete_patient(id):

    cursor.execute("""
        SELECT id
        FROM patients
        WHERE id=%s
    """, (id,))

    patient = cursor.fetchone()

    if patient is None:

        return jsonify({
            "message": "Patient Not Found"
        }), 404

    cursor.execute("""
        DELETE FROM patients
        WHERE id=%s
    """, (id,))

    connection.commit()

    return jsonify({
        "message": "Patient Deleted Successfully"
    })

@app.route("/api/doctors", methods=["GET"])
def api_doctors():

    cursor.execute("""
        SELECT *
        FROM doctors
    """)

    doctors = cursor.fetchall()

    data = []

    for doctor in doctors:

        data.append({

            "doctor_id": doctor[0],
            "doctor_name": doctor[1],
            "specialization": doctor[2],
            "phone": doctor[3],
            "experience": doctor[4],
            "available_from": str(doctor[6]),
            "available_to": str(doctor[7])

        })

    return jsonify(data)

@app.route("/api/doctors", methods=["POST"])
def api_add_doctor():

    data = request.json

    cursor.execute("""
        INSERT INTO doctors
        (
            doctor_name,
            specialization,
            phone,
            experience,
            available_from,
            available_to
        )
        VALUES
        (%s,%s,%s,%s,%s,%s)
    """,(

        data["doctor_name"],
        data["specialization"],
        data["phone"],
        data["experience"],
        data["available_from"],
        data["available_to"]

    ))

    connection.commit()

    return jsonify({
        "message":"Doctor Added Successfully"
    }),201

@app.route("/api/doctors/<int:id>", methods=["GET"])
def api_get_doctor(id):

    cursor.execute("""
        SELECT *
        FROM doctors
        WHERE id=%s
    """,(id,))

    doctor = cursor.fetchone()

    if doctor is None:

        return jsonify({
            "message":"Doctor Not Found"
        }),404

    return jsonify({

        "doctor_id":doctor[0],
        "doctor_name":doctor[1],
        "specialization":doctor[2],
        "phone":doctor[3],
        "experience":doctor[4],
        "available_from":str(doctor[6]),
        "available_to":str(doctor[7])

    })

@app.route("/api/doctors/<int:id>", methods=["PUT"])
def api_update_doctor(id):

    data = request.json

    cursor.execute("""
        UPDATE doctors
        SET
            doctor_name=%s,
            specialization=%s,
            phone=%s,
            experience=%s,
            available_from=%s,
            available_to=%s
        WHERE id=%s
    """,(

        data["doctor_name"],
        data["specialization"],
        data["phone"],
        data["experience"],
        data["available_from"],
        data["available_to"],
        id

    ))

    connection.commit()

    return jsonify({
        "message":"Doctor Updated Successfully"
    })

@app.route("/api/doctors/<int:id>", methods=["DELETE"])
def api_delete_doctor(id):

    cursor.execute("""
        DELETE FROM doctors
        WHERE id=%s
    """,(id,))

    connection.commit()

    return jsonify({
        "message":"Doctor Deleted Successfully"
    })

@app.route("/api/nurses", methods=["GET"])
def api_nurses():

    cursor.execute("""
        SELECT *
        FROM nurses
    """)

    nurses = cursor.fetchall()

    data = []

    for nurse in nurses:

        data.append({

            "nurse_id": nurse[0],
            "nurse_name": nurse[1],
            "department": nurse[2],
            "phone": nurse[3]

        })

    return jsonify(data)

@app.route("/api/nurses", methods=["POST"])
def api_add_nurse():

    data = request.json

    cursor.execute("""
        INSERT INTO nurses
        (
            nurse_name,
            department,
            shift,
            phone,
            experience
        )
        VALUES
        (%s,%s,%s,%s,%s)
    """, (

        data["nurse_name"],
        data["department"],
        data["shift"],
        data["phone"],
        data["experience"]

    ))

    connection.commit()

    return jsonify({
        "message": "Nurse Added Successfully"
    }), 201

@app.route("/api/nurses/<int:id>", methods=["GET"])
def api_get_nurse(id):

    cursor.execute("""
        SELECT *
        FROM nurses
        WHERE id=%s
    """, (id,))

    nurse = cursor.fetchone()

    if nurse is None:

        return jsonify({
            "message": "Nurse Not Found"
        }), 404

    return jsonify({

        "nurse_id": nurse[0],
        "nurse_name": nurse[1],
        "department": nurse[2],
        "shift": nurse[3],
        "phone": nurse[4],
        "experience": nurse[5]

    })

@app.route("/api/nurses/<int:id>", methods=["PUT"])
def api_update_nurse(id):

    data = request.json

    cursor.execute("""
        UPDATE nurses
        SET
            nurse_name=%s,
            department=%s,
            shift=%s,
            phone=%s,
            experience=%s
        WHERE id=%s
    """, (

        data["nurse_name"],
        data["department"],
        data["shift"],
        data["phone"],
        data["experience"],
        id

    ))

    connection.commit()

    return jsonify({
        "message": "Nurse Updated Successfully"
    })

@app.route("/api/nurses/<int:id>", methods=["DELETE"])
def api_delete_nurse(id):

    cursor.execute("""
        DELETE FROM nurses
        WHERE id=%s
    """, (id,))

    connection.commit()

    return jsonify({
        "message": "Nurse Deleted Successfully"
    })



@app.route("/api/medicines", methods=["GET"])
def api_medicines():

    cursor.execute("""
        SELECT *
        FROM medicines
    """)

    medicines = cursor.fetchall()

    data = []

    for medicine in medicines:

        data.append({

            "medicine_id": medicine[0],
            "medicine_name": medicine[1],
            "category": medicine[2],
            "manufacturer": medicine[3],
            "batch_no": medicine[4],
            "stock": medicine[5],
            "unit_price": medicine[6],
            "expiry_date": str(medicine[7])

        })

    return jsonify(data)

@app.route("/api/bills", methods=["GET"])
def api_bills():

    cursor.execute("""
        SELECT *
        FROM billing
    """)

    bills = cursor.fetchall()

    data = []

    for bill in bills:

        data.append({

            "bill_id": bill[0],
            "patient_id": bill[1],
            "consultation_fee": bill[2],
            "laboratory_fee": bill[3],
            "pharmacy_fee": bill[4],
            "total_amount": bill[5],
            "payment_status": bill[6],
            "bill_date": str(bill[7])

        })

    return jsonify(data)

@app.route("/api/bills", methods=["POST"])
def api_add_bill():

    data = request.json

    cursor.execute("""
        INSERT INTO billing
        (
            patient_id,
            consultation_fee,
            laboratory_fee,
            pharmacy_fee,
            total_amount,
            payment_status,
            bill_date
        )
        VALUES
        (%s,%s,%s,%s,%s,%s,%s)
    """,(

        data["patient_id"],
        data["consultation_fee"],
        data["laboratory_fee"],
        data["pharmacy_fee"],
        data["total_amount"],
        data["payment_status"],
        data["bill_date"]

    ))

    connection.commit()

    return jsonify({
        "message":"Bill Added Successfully"
    }),201

@app.route("/api/bills/<int:id>", methods=["GET"])
def api_get_bill(id):

    cursor.execute("""
        SELECT *
        FROM billing
        WHERE bill_id=%s
    """,(id,))

    bill = cursor.fetchone()

    if bill is None:

        return jsonify({
            "message":"Bill Not Found"
        }),404

    return jsonify({

        "bill_id":bill[0],
        "patient_id":bill[1],
        "consultation_fee":bill[2],
        "laboratory_fee":bill[3],
        "pharmacy_fee":bill[4],
        "total_amount":bill[5],
        "payment_status":bill[6],
        "bill_date":str(bill[7])

    })

@app.route("/api/bills/<int:id>", methods=["PUT"])
def api_update_bill(id):

    data = request.json

    cursor.execute("""
        UPDATE billing
        SET
            consultation_fee=%s,
            laboratory_fee=%s,
            pharmacy_fee=%s,
            total_amount=%s,
            payment_status=%s,
            bill_date=%s
        WHERE bill_id=%s
    """,(

        data["consultation_fee"],
        data["laboratory_fee"],
        data["pharmacy_fee"],
        data["total_amount"],
        data["payment_status"],
        data["bill_date"],
        id

    ))

    connection.commit()

    return jsonify({
        "message":"Bill Updated Successfully"
    })

@app.route("/api/bills/<int:id>", methods=["DELETE"])
def api_delete_bill(id):

    cursor.execute("""
        DELETE FROM billing
        WHERE bill_id=%s
    """,(id,))

    connection.commit()

    return jsonify({
        "message":"Bill Deleted Successfully"
    })

@app.route("/api/appointments", methods=["GET"])
def api_appointments():

    cursor.execute("""
        SELECT *
        FROM appointments
    """)

    appointments = cursor.fetchall()

    data = []

    for appointment in appointments:

        data.append({

            "id": appointment[0],
            "patient_id": appointment[1],
            "doctor_id": appointment[2],
            "appointment_date": str(appointment[3]),
            "appointment_time": str(appointment[4]),
            "status": appointment[5]

        })

    return jsonify(data)

@app.route("/api/appointments", methods=["POST"])
def api_add_appointment():

    data = request.json

    cursor.execute("""
        INSERT INTO appointments
        (
            patient_id,
            doctor_id,
            appointment_date,
            appointment_time,
            status
        )
        VALUES
        (%s,%s,%s,%s,%s)
    """, (

        data["patient_id"],
        data["doctor_id"],
        data["appointment_date"],
        data["appointment_time"],
        data["status"]

    ))

    connection.commit()

    return jsonify({
        "message": "Appointment Added Successfully"
    }),201

@app.route("/api/appointments/<int:id>", methods=["GET"])
def api_get_appointment(id):

    cursor.execute("""
        SELECT *
        FROM appointments
        WHERE id=%s
    """,(id,))

    appointment = cursor.fetchone()

    if appointment is None:

        return jsonify({
            "message":"Appointment Not Found"
        }),404

    return jsonify({

        "id": appointment[0],
        "patient_id": appointment[1],
        "doctor_id": appointment[2],
        "appointment_date": str(appointment[3]),
        "appointment_time": str(appointment[4]),
        "status": appointment[5]

    })

@app.route("/api/appointments/<int:id>", methods=["PUT"])
def api_update_appointment(id):

    data = request.json

    cursor.execute("""
        UPDATE appointments
        SET
            patient_id=%s,
            doctor_id=%s,
            appointment_date=%s,
            appointment_time=%s,
            status=%s
        WHERE id=%s
    """, (

        data["patient_id"],
        data["doctor_id"],
        data["appointment_date"],
        data["appointment_time"],
        data["status"],
        id

    ))

    connection.commit()

    return jsonify({
        "message":"Appointment Updated Successfully"
    })

@app.route("/api/appointments/<int:id>", methods=["DELETE"])
def api_delete_appointment(id):

    cursor.execute("""
        DELETE FROM appointments
        WHERE id=%s
    """,(id,))

    connection.commit()

    return jsonify({
        "message":"Appointment Deleted Successfully"
    })

@app.route("/api_dashboard")
def api_dashboard():

    if "user" not in session:
        return redirect("/login")

    total = 5
    active = 5

    apis = [

        ("Patients", "/api/patients", "GET", "Active"),
        ("Doctors", "/api/doctors", "GET", "Active"),
        ("Nurses", "/api/nurses", "GET", "Active"),
        ("Medicines", "/api/medicines", "GET", "Active"),
        ("Bills", "/api/bills", "GET", "Active")

    ]

    return render_template(
        "api_dashboard.html",
        total=total,
        active=active,
        apis=apis
    )

@app.route("/notifications")
def notifications():

    if "user" not in session:
        return redirect("/login")

    return render_template("notifications.html")


@app.route("/appointment_notification", methods=["GET","POST"])
def appointment_notification():

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)

    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        message = request.form["message"]

        cursor.execute("""
            INSERT INTO notifications
            (
                patient_id,
                title,
                message,
                notification_type
            )

            VALUES
            (%s,%s,%s,%s)
        """, (

            patient_id,
            "Appointment Reminder",
            message,
            "Appointment"

        ))

        connection.commit()

        return redirect("/view_notifications")

    return render_template(
        "appointment_notification.html",
        patients=patients
    )

@app.route("/view_notifications")
def view_notifications():

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""

        SELECT

            n.notification_id,
            p.patient_name,
            n.title,
            n.message,
            n.notification_type,
            n.status,
            n.created_at

        FROM notifications n

        JOIN patients p

        ON n.patient_id = p.id

        ORDER BY n.notification_id DESC

    """)

    notifications = cursor.fetchall()

    return render_template(
        "view_notifications.html",
        notifications=notifications
    )

@app.route("/mark_notification_read/<int:id>")
def mark_notification_read(id):

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""
        UPDATE notifications
        SET status='Read'
        WHERE notification_id=%s
    """, (id,))

    connection.commit()

    return redirect("/view_notifications")

@app.route("/lab_notification", methods=["GET","POST"])
def lab_notification():

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)

    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        message = request.form["message"]

        cursor.execute("""
            INSERT INTO notifications
            (
                patient_id,
                title,
                message,
                notification_type
            )

            VALUES
            (%s,%s,%s,%s)
        """, (

            patient_id,
            "Lab Report Ready",
            message,
            "Lab"

        ))

        connection.commit()

        return redirect("/view_notifications")

    return render_template(
        "lab_notification.html",
        patients=patients
    )


@app.route("/prescription_notification", methods=["GET","POST"])
def prescription_notification():

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)

    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        message = request.form["message"]

        cursor.execute("""
            INSERT INTO notifications
            (
                patient_id,
                title,
                message,
                notification_type
            )

            VALUES
            (%s,%s,%s,%s)
        """, (

            patient_id,
            "Prescription Ready",
            message,
            "Prescription"

        ))

        connection.commit()

        return redirect("/view_notifications")

    return render_template(
        "prescription_notification.html",
        patients=patients
    )

@app.route("/billing_notification", methods=["GET","POST"])
def billing_notification():

    if "user" not in session:
        return redirect("/login")

    cursor.execute("""
        SELECT id, patient_name
        FROM patients
    """)

    patients = cursor.fetchall()

    if request.method == "POST":

        patient_id = request.form["patient_id"]

        message = request.form["message"]

        cursor.execute("""
            INSERT INTO notifications
            (
                patient_id,
                title,
                message,
                notification_type
            )

            VALUES
            (%s,%s,%s,%s)
        """, (

            patient_id,
            "Billing Reminder",
            message,
            "Billing"

        ))

        connection.commit()

        return redirect("/view_notifications")

    return render_template(
        "billing_notification.html",
        patients=patients
    )





@app.route("/patient_report")
def patient_report():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            id,
            patient_name,
            age,
            disease,
            phone,
            gender,
            blood_group
        FROM patients
    """)

    patients = cursor.fetchall()

    return render_template(
        "patient_report.html",
        patients=patients
    )

@app.route("/doctor_report")
def doctor_report():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            id,
            doctor_name,
            specialization,
            phone,
            experience,
            available_from,
            available_to
            
        FROM doctors
    """)

    doctors = cursor.fetchall()

    return render_template(
        "doctor_report.html",
        doctors=doctors
    )

@app.route("/appointment_report")
def appointment_report():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            a.id,
            p.patient_name,
            d.doctor_name,
            a.appointment_date,
            a.appointment_time,
            a.status

        FROM appointments a

        JOIN patients p
        ON a.patient_id = p.id

        JOIN doctors d
        ON a.doctor_id = d.id

        ORDER BY a.id DESC
    """)

    appointments = cursor.fetchall()

    return render_template(
        "appointment_report.html",
        appointments=appointments
    )



@app.route("/billing_report")
def billing_report():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            b.bill_id,
            p.patient_name,
            b.consultation_fee,
            b.laboratory_fee,
            b.pharmacy_fee,
            b.total_amount,
            b.payment_status,
            b.bill_date

        FROM billing b

        JOIN patients p
        ON b.patient_id = p.id

        ORDER BY b.bill_id DESC
    """)

    bills = cursor.fetchall()

    return render_template(
        "billing_report.html",
        bills=bills
    )

@app.route("/analytics_dashboard")
def analytics_dashboard():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("SELECT COUNT(*) FROM patients")
    total_patients = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM doctors")
    total_doctors = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM appointments")
    total_appointments = cursor.fetchone()[0]

    cursor.execute("""
        SELECT IFNULL(SUM(total_amount),0)
        FROM billing
    """)
    revenue = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            status,
            COUNT(*)
        FROM appointments
        GROUP BY status
    """)

    status_data = cursor.fetchall()

    return render_template(

        "analytics_dashboard.html",

        total_patients=total_patients,

        total_doctors=total_doctors,

        total_appointments=total_appointments,

        revenue=revenue,

        status_data=status_data

    )

# ==========================================================
# PATIENT FEEDBACK
# ==========================================================

@app.route("/feedback", methods=["GET", "POST"])
def feedback():

    # Check whether user is logged in
    if "user" not in session:
        return redirect("/login")


    # =========================================
    # GET LOGGED-IN PATIENT'S ID
    # =========================================

    cursor.execute("""
        SELECT id
        FROM patients
        WHERE patient_name = %s
    """, (session["user"],))

    patient = cursor.fetchone()


    if patient is None:

        return "Patient record not found"


    # This is now the INTEGER patient ID
    patient_id = patient[0]


    # =========================================
    # SUBMIT FEEDBACK
    # =========================================

    if request.method == "POST":

        doctor_id = request.form.get("doctor_id")

        department = request.form.get("department")

        doctor_rating = request.form.get("doctor_rating")
        hospital_rating = request.form.get("hospital_rating")
        laboratory_rating = request.form.get("laboratory_rating")
        pharmacy_rating = request.form.get("pharmacy_rating")

        comments = request.form.get("comments")
        suggestions = request.form.get("suggestions")


        # Convert empty doctor ID to NULL
        if doctor_id == "":
            doctor_id = None


        # Convert empty ratings to NULL
        if doctor_rating == "":
            doctor_rating = None

        if hospital_rating == "":
            hospital_rating = None

        if laboratory_rating == "":
            laboratory_rating = None

        if pharmacy_rating == "":
            pharmacy_rating = None


        # =========================================
        # INSERT FEEDBACK
        # =========================================

        cursor.execute("""
            INSERT INTO feedback
            (
                patient_id,
                doctor_id,
                department,
                doctor_rating,
                hospital_rating,
                laboratory_rating,
                pharmacy_rating,
                comments,
                suggestions
            )
            VALUES
            (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """, (
            patient_id,
            doctor_id,
            department,
            doctor_rating,
            hospital_rating,
            laboratory_rating,
            pharmacy_rating,
            comments,
            suggestions
        ))


        connection.commit()


        return redirect("/feedback?success=1")


    # =========================================
    # GET DOCTORS FOR DROPDOWN
    # =========================================

    cursor.execute("""
        SELECT id, doctor_name
        FROM doctors
    """)

    doctors = cursor.fetchall()


    # =========================================
    # GET PATIENT'S FEEDBACK HISTORY
    # =========================================

    cursor.execute("""
        SELECT
            f.id,
            d.doctor_name,
            f.department,
            f.doctor_rating,
            f.hospital_rating,
            f.laboratory_rating,
            f.pharmacy_rating,
            f.comments,
            f.suggestions,
            f.created_at

        FROM feedback f

        LEFT JOIN doctors d
        ON f.doctor_id = d.id

        WHERE f.patient_id = %s

        ORDER BY f.created_at DESC
    """, (patient_id,))


    feedback_history = cursor.fetchall()


    # =========================================
    # DISPLAY FEEDBACK PAGE
    # =========================================

    return render_template(
        "feedback.html",
        doctors=doctors,
        feedback_history=feedback_history
    )

# =========================================
# ADMIN FEEDBACK
# =========================================

@app.route("/admin_feedback")
def admin_feedback():

    if "user" not in session:
        return redirect("/login")

    if session["role"] != "admin":
        return "Access Denied"

    cursor.execute("""
        SELECT
            id,
            patient_id,
            doctor_id,
            department,
            doctor_rating,
            hospital_rating,
            laboratory_rating,
            pharmacy_rating,
            comments,
            suggestions,
            created_at
        FROM feedback
        ORDER BY id DESC
    """)

    feedback = cursor.fetchall()

    return render_template(
        "admin_feedback.html",
        feedback=feedback
    )


# =========================================================
# DOWNLOAD REPORTS
# =========================================================

@app.route("/download_report/<report_type>")
def download_report(report_type):

    if "user" not in session:
        return redirect("/login")

    if session.get("role") != "admin":
        return "Access Denied", 403

    buffer = BytesIO()

    styles = getSampleStyleSheet()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=(595, 842)
    )

    elements = []

    # =========================
    # PATIENT REPORT
    # =========================

    if report_type == "patients":

        cursor.execute("""
            SELECT
                id,
                patient_name,
                age,
                disease,
                phone,
                gender,
                blood_group
            FROM patients
        """)

        patients = cursor.fetchall()

        elements.append(
            Paragraph(
                "Patient Report",
                styles["Title"]
            )
        )

        elements.append(
            Paragraph(
                "Hospital Management System",
                styles["Normal"]
            )
        )

        for patient in patients:

            text = (
                f"ID: {patient[0]} | "
                f"Name: {patient[1]} | "
                f"Age: {patient[2]} | "
                f"Disease: {patient[3]} | "
                f"Phone: {patient[4]} | "
                f"Gender: {patient[5]} | "
                f"Blood Group: {patient[6]}"
            )

            elements.append(
                Paragraph(
                    text,
                    styles["Normal"]
                )
            )


    # =========================
    # DOCTOR REPORT
    # =========================

    elif report_type == "doctors":

        cursor.execute("""
            SELECT
                id,
                doctor_name,
                specialization,
                phone,
                gender
            FROM doctors
        """)

        doctors = cursor.fetchall()

        elements.append(
            Paragraph(
                "Doctor Report",
                styles["Title"]
            )
        )

        for doctor in doctors:

            text = (
                f"ID: {doctor[0]} | "
                f"Name: {doctor[1]} | "
                f"Specialization: {doctor[2]} | "
                f"Phone: {doctor[3]} | "
                f"Gender: {doctor[4]}"
            )

            elements.append(
                Paragraph(
                    text,
                    styles["Normal"]
                )
            )


    # =========================
    # APPOINTMENT REPORT
    # =========================

    elif report_type == "appointments":

        cursor.execute("""
            SELECT *
            FROM appointments
        """)

        appointments = cursor.fetchall()

        elements.append(
            Paragraph(
                "Appointment Report",
                styles["Title"]
            )
        )

        for appointment in appointments:

            text = " | ".join(
                str(value)
                for value in appointment
            )

            elements.append(
                Paragraph(
                    text,
                    styles["Normal"]
                )
            )


    # =========================
    # BILLING REPORT
    # =========================

    elif report_type == "billing":

        cursor.execute("""
            SELECT *
            FROM billing
        """)

        bills = cursor.fetchall()

        elements.append(
            Paragraph(
                "Billing Report",
                styles["Title"]
            )
        )

        for bill in bills:

            text = " | ".join(
                str(value)
                for value in bill
            )

            elements.append(
                Paragraph(
                    text,
                    styles["Normal"]
                )
            )


    else:

        return "Invalid Report Type", 400


    # =========================
    # GENERATE PDF
    # =========================

    doc.build(elements)

    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"{report_type}_report.pdf",
        mimetype="application/pdf"
    )


@app.route("/delete_patient/<int:id>")
def delete_patient(id):

    if "user" not in session:
        return redirect("/login")

    if session["role"] not in ["admin", "doctor", "nurse"]:
        return "Access Denied"

    cursor.execute("DELETE FROM patients WHERE id=%s", (id,))
    connection.commit()

    return redirect("/view_patients")
app.run(debug=True)

