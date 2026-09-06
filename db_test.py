import mysql.connector

connection = mysql.connector.connect(
    host="localhost",
    user="root",
    password="",
    database="patient_care_db"
)

cursor = connection.cursor()

if connection.is_connected():
    print("Connected to MySQL Successfully!")