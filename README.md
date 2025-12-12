# Library Management System

A comprehensive Library Management System built with Flask, SQLAlchemy, and Tailwind CSS.

> [!WARNING]
> **Important Note for Vercel Deployment:**
> This application uses SQLite. Vercel's filesystem is **read-only and ephemeral** (temporary).
> 1.  **Data Loss**: Any user you register or book you add on Vercel will be **deleted** when the server sleeps or restarts (usually every few minutes).
> 2.  **Login Failures**: If you register a student, the database might reset before you can log in, causing "User not found".
> 3.  **Recommendation**: For a permanent app, use **PythonAnywhere** or connect this app to a cloud database like PostgreSQL (Supabase/Neon).

## Features

- **User Roles**: Admin and Student dashboards.
- **Book Management**: Add, update, delete, and bulk import books.
- **Transactions**: Issue and return books with penalty calculation.
- **Interactive Inventory**: Track misplaced books and restore them.
- **Student Analytics**: Visualize reading history and fines.
- **Mobile Support**: Registration with country codes and responsive UI.
- **Security**: Password hashing and user blocking.

## Setup

1.  **Clone the repository**
2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```
3.  **Run the application**:
    ```bash
    python app.py
    ```
    Or for production:
    ```bash
    python serve.py
    ```
4.  **Access**: `http://localhost:8080`

## Tech Stack
-   **Backend**: Flask (Python)
-   **Database**: SQLite (SQLAlchemy)
-   **Frontend**: HTML, Tailwind CSS, JavaScript
-   **Deployment**: Waitress (WSGI), Docker
