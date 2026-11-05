# StudentLife Analytics

Responsive Flask website prototype for **StudentLife Analytics: A Student Grade Prediction and Academic Performance Monitoring System Using Linear Regression**.

## Features
- Admin and student login roles
- Admin dashboard and student record management
- Grade prediction and saved prediction history
- Student ranking, report table, and CSV export
- SQLite persistence
- Responsive desktop, tablet, and mobile layout

## Run locally
1. Install Python 3.10+.
2. Open a terminal in this project folder.
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Start the website:
   ```bash
   python app.py
   ```
5. Open `http://127.0.0.1:5000` in your browser.

## Demo admin
- Username: `admin`
- Password: `admin123`

Change the demo password and `app.secret_key` before deploying publicly.

## Student account
Use **Create an account** from the login page. Admin can add academic records from the Students page.

## Prediction note
The app fits an ordinary least-squares Linear Regression model using saved student records that have a current grade (at least three rows). Until sufficient training data exists, it uses the project's initial baseline formula. This is a learning/demo implementation, not a validated academic forecasting model.
