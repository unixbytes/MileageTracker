# Mileage Tracker

A lightweight, privacy-friendly Flask web application for logging, tracking, and reporting driving mileage. It supports live tracking, manual trip entry, CSV export, reporting, photo attachments, and admin management of users and trips.

Public instance: https://track.sultantech.ca

## Features

- Live trip tracking with automatic distance calculation
- Manual trip entry with date, type, vehicle, and distance
- Per-user trip isolation
- Reports with filtering by month and trip type
- CSV export from Reports
- Photo attachment support for trips
- Dark mode toggle with localStorage persistence
- Profile management: username and email updates
- Password change and secure reset via email
- Admin dashboard: user management, trip management across users, and SMTP configuration
- M365/Office 365 compatible SMTP email delivery
- Optional welcome email on registration
- Health check endpoint: `/healthz`
- Custom 404 and 500 error pages

## Requirements

- Python >= 3.11
- Flask >= 3.0
- Flask-SQLAlchemy >= 3.1
- Flask-WTF
- WTForms
- email-validator
- Flask-Migrate >= 4.0 (optional; used for schema migrations)

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/unixbytes/MileageTracker.git
   cd MileageTracker
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   .venv\\Scripts\\activate    # Windows
   ```

3. Install dependencies:
   ```bash
   pip install -r pyproject.toml
   ```

4. Set environment variables:
   ```bash
   export MILEAGE_SECRET_KEY="your-secret-key"
   export MILEAGE_INSTANCE_PATH="$(pwd)/instance"
   ```

5. Initialize the database:
   ```bash
   flask db init
   flask db migrate -m "baseline schema"
   flask db stamp head
   ```

6. Run the app:
   ```bash
   python run.py
   ```

7. Visit:
   ```text
   http://localhost:5000
   ```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MILEAGE_SECRET_KEY` | Flask secret key for sessions and CSRF | `dev-mileage-tracker-2026` |
| `MILEAGE_INSTANCE_PATH` | Path to instance folder for database and uploads | `./instance` |

### Units

- Default distance unit is kilometers (`km`).
- Users can switch between Miles and Kilometers in Settings.

### Email / SMTP

SMTP settings are managed from the Admin Dashboard:
- SMTP Host
- SMTP Port
- SMTP User
- SMTP Password
- Sender email (`smtp_from`)
- Enable Email checkbox

For M365/Office 365:
- Host: `smtp.office365.com`
- Port: `587`
- User: full mailbox email
- Password: app password or account password
- Sender: must match or be allowed by your tenant

## Usage

### Getting Started

1. Register an account at `/register`.
2. Log in at `/login`.
3. Start tracking from the `/track` page, or create a manual trip at `/trips`.

### Live Tracking

- Open `/track`.
- Tap **Start** to begin recording.
- The app records GPS points and computes distance automatically.
- Tap **Stop** to end tracking.
- Open the trip detail page to view the recorded route.

### Manual Trips

- Go to `/trips`.
- Fill in date, trip type, vehicle, and distance.
- Submit to create a trip.

### Reports

- Visit `/reports`.
- Filter by month and trip type.
- Use **Export CSV** to download filtered trip data.

### Photos

- When creating or editing a trip, attach a photo.
- Photos are stored in the instance uploads folder.

### Settings

- Change measurement units.
- Manage vehicles.
- Update profile username/email.
- Change password.

## Testing

Run the test suite:
```bash
pytest tests/test_mileage.py -q
```

## Deployment

This app is typically deployed as a systemd user service on a Linux server.

Example service unit:
```ini
[Unit]
Description=Mileage Tracker
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/unixbytes/mileage
ExecStart=/home/unixbytes/.local/bin/uv run python run.py
Restart=always
Environment=MILEAGE_SECRET_KEY=...
Environment=MILEAGE_INSTANCE_PATH=/home/unixbytes/mileage/instance

[Install]
WantedBy=default.target
```

Enable lingering and start the service:
```bash
loginctl enable-linger unixbytes
systemctl --user enable --now mileage.service
```

## Admin

- Admin login: `/admin/login`
- Admin dashboard: `/admin`
- Tabs:
  - SMTP Settings and Test Email
  - User Management
  - Trip Management

Admins can:
- Create, delete, and promote/demote users
- Edit or delete any user's trips
- Configure and test email delivery

## Troubleshooting

- **Email not sending**: verify SMTP settings in the admin dashboard. Use **Send Test Email** to debug.
- **Database errors**: ensure `MILEAGE_INSTANCE_PATH` points to a writable directory and `flask db stamp head` has been run.
- **Port already in use**: change the port in the systemd unit or run config.
- **Uploads failing**: confirm the `instance/uploads` directory exists and is writable.

## License

Proprietary. All rights reserved.
