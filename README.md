# NagrikOne

A full-stack civic service and citizen grievance management portal built with Python (Flask) and MySQL, deployed on Microsoft Azure.

## Live Application
- **Production URL:** [https://nagrikone-f0e8ahc2dmb6d5gd.centralindia-01.azurewebsites.net](https://nagrikone-f0e8ahc2dmb6d5gd.centralindia-01.azurewebsites.net)

## Key Features
- **Role-Based Portals:** Dedicated dashboards and workflows for Applicants (Citizens), Officers, and Administrators.
- **Application Lifecycle Tracking:** Three-stage request tracking system with real-time status updates and downloadable PDF acknowledgement slips.
- **Document & Media Management:** Secure file uploads backed by Azure Blob Storage.
- **Audit Logging & Notifications:** Complete administrative audit trails and user status notifications.
- **Responsive UI:** Clean, accessible interface featuring consistent light and dark mode support and clutter-free print layouts.

## Tech Stack
- **Backend:** Python 3.11, Flask, Werkzeug, Jinja2, Gunicorn
- **Database:** Azure Database for MySQL (Flexible Server)
- **Cloud Storage:** Azure Blob Storage
- **Hosting & CI/CD:** Azure App Service (Linux) with automated deployments via GitHub Actions

## Project Structure
```text
NagrikOne/
├── .github/workflows/    # GitHub Actions CI/CD pipeline
├── static/               # CSS, JavaScript, and static assets
├── templates/            # Jinja2 HTML templates
├── app.py                # Main Flask application and routes
├── storage_provider.py   # Azure Blob Storage integration
├── schema.sql            # MySQL relational database schema
├── requirements.txt      # Python dependencies
└── Procfile              # Process startup configuration

## Azure Deployment Configuration

- **Hosting Platform:** Azure App Service (Linux, Python 3.11, Central India)
- **Service Plan:** Basic (B1 — 1 vCPU, 1.75 GB RAM)
- **WSGI Server:** Gunicorn bound to `0.0.0.0:8000` (`WEBSITES_PORT=8000`)
- **Database:** Azure Database for MySQL (Flexible Server) over SSL
- **Object Storage:** Azure Blob Storage for citizen document uploads
- **CI/CD Pipeline:** Automated build and deployment via GitHub Actions (`.github/workflows/main_nagrikone.yml`) using Azure OneDeploy
- **Build Automation:** `SCM_DO_BUILD_DURING_DEPLOYMENT=true` (Oryx builds `requirements.txt` on push)
