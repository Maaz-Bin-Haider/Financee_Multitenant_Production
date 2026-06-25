<div align="center">

# 🏢 Accounting Plus Inventory Management System
### *A Full-Featured Django-Based ERP System*

![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-4.x-092E20?style=for-the-badge&logo=django&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791?style=for-the-badge&logo=postgresql&logoColor=white)
![AWS](https://img.shields.io/badge/AWS-EC2-FF9900?style=for-the-badge&logo=amazon-aws&logoColor=white)
![Nginx](https://img.shields.io/badge/Nginx-009639?style=for-the-badge&logo=nginx&logoColor=white)
![Gunicorn](https://img.shields.io/badge/Gunicorn-499848?style=for-the-badge&logo=gunicorn&logoColor=white)

> An enterprise-grade ERP system integrating **double-entry accounting**, **serial-number-based inventory tracking**, complete **purchase/sale cycles**, **returns management**, and **real-time financial reporting** — built with Django and powered by a PostgreSQL stored-procedure architecture.

</div>

---

## 📑 Table of Contents

- [Overview](#-overview)
- [System Architecture](#️-system-architecture)
- [Tech Stack](#-tech-stack)
- [Modules](#-modules)
- [Key Features](#-key-features)
- [Project Structure](#-project-structure)
- [Permission System](#-permission-system)
- [API Endpoints](#-api-endpoints)
- [Database Design](#-database-design)
- [Deployment](#-deployment)
- [Getting Started](#-getting-started)

---

## 🌟 Overview

This system is designed to serve small-to-medium businesses requiring a unified platform for:

- **Accounting** – Full double-entry bookkeeping with automated journal entries
- **Inventory Management** – Serial-number tracking with FIFO valuation
- **Trading Operations** – Purchase, Sales, and Returns workflows
- **Financial Reporting** – Profit & Loss, Balance Sheet, Stock Reports

All business logic is executed through **PostgreSQL stored functions**, making the backend thin, reliable, and extremely fast. Django handles routing, authentication, permission enforcement, and template rendering.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────┐
│                    CLIENT BROWSER                   │
└───────────────────────┬─────────────────────────────┘
                        │ HTTPS
                        ▼
┌─────────────────────────────────────────────────────┐
│              NGINX  (Reverse Proxy)                 │
│         Static files │ SSL Termination              │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│           GUNICORN  (WSGI Application Server)       │
└───────────────────────┬─────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────┐
│              DJANGO APPLICATION                     │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │   Auth   │ │  Views   │ │  Django Templates    │ │
│  │  Module  │ │ (Logic)  │ │  (Frontend / UI)     │ │
│  └──────────┘ └──────────┘ └──────────────────────┘ │
└───────────────────────┬─────────────────────────────┘
                        │ psycopg2
                        ▼
┌─────────────────────────────────────────────────────┐
│           POSTGRESQL DATABASE (AWS EC2)             │
│   Tables │ Stored Functions │ Triggers │ Views      │
└─────────────────────────────────────────────────────┘
```

---

## 🛠️ Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend Framework** | Django 4.x | Application logic, routing, auth |
| **Database** | PostgreSQL 14+ | Data storage, stored procedures, triggers |
| **DB Driver** | psycopg2-binary | Django–PostgreSQL connectivity |
| **Config Management** | django-environ | Environment variable management |
| **Frontend** | Django Templates + HTML/CSS/JS | Server-side rendered UI |
| **Web Server** | Nginx | Reverse proxy, static file serving |
| **App Server** | Gunicorn | WSGI production server |
| **Cloud** | AWS EC2 | Deployment infrastructure |

---

## 📦 Modules

The project is organized as a **multi-app Django project**, each app handling a dedicated business domain:

| App | Description |
|-----|-------------|
| `authentication` | Login, logout, session management, role-based permissions |
| `home` | Dashboard — cash balance, party balances, item lookups |
| `items` | Inventory item creation, updates, autocomplete search |
| `parties` | Customer/vendor management (add, update) |
| `sale` | Sales invoice creation, retrieval, summary reports |
| `purchase` | Purchase invoice management |
| `sale_return` | Sales return processing |
| `purchase_return` | Purchase return processing |
| `payments` | Outgoing payment recording and history |
| `receipts` | Incoming receipt recording and history |
| `display_reports` | Accounts Reports, Stock Reports, Profit Reports |

---

## ✨ Key Features

### 🔐 Authentication & Role-Based Access Control
- Session-based authentication using Django's built-in auth system
- **Granular module-level permissions** — each module (Sales, Purchase, Payments, etc.) has its own `view`, `add`, `change`, `delete` permissions
- Permissions assigned per user/group — unauthorized access redirects gracefully to the home dashboard
- JSON responses for AJAX-based login/logout flows

### 📊 Dashboard (Home)
- Real-time **cash balance** display
- **Party-wise balance** overview (receivables & payables)
- **Expense party balances** for expense tracking
- **Item & party autocomplete** APIs for fast data entry

### 🛒 Sales Module
- Full invoice creation with multiple line items
- Party name validation against the database
- Future-date restriction on invoice dates
- Sale summary and detailed invoice retrieval
- AJAX-based form submission with real-time error feedback

### 🏭 Purchase Module
- Complete purchase cycle: invoice creation → stock update → accounting entry
- Linked to inventory serial-number tracking

### 🔄 Returns Management
- **Sale Returns** — reversal of sales with automatic stock restoration
- **Purchase Returns** — reversal of purchases with full accounting reversal

### 💵 Payments & Receipts
- Date-wise payment/receipt history
- Old payment/receipt lookup
- Full party ledger support

### 📈 Reports
- **Profit Reports** — Gross profit, net profit analysis
- **Stock Reports** — Current inventory levels, valuation
- **Accounts Reports** — Party ledgers, balance sheet data

---

## 📁 Project Structure

```
Accounting-Plus-Inventory-System/
│
├── financee/                   # Main Django project settings
│   └── urls.py                 # Root URL configuration
│
├── authentication/             # User auth & permissions
│   ├── views.py                # login_view, logout_view, current_user
│   ├── urls.py
│   └── migrations/             # Permission seeders (11 migrations)
│
├── home/                       # Dashboard
│   └── views.py                # Cash balance, party APIs, item APIs
│
├── items/                      # Inventory items
│   └── views.py                # CRUD + autocomplete
│
├── parties/                    # Customer/Vendor management
│   └── views.py
│
├── sale/                       # Sales invoicing
│   └── views.py
│
├── purchase/                   # Purchase invoicing
│   └── views.py
│
├── sale_return/                # Sales return
├── purchase_return/            # Purchase return
├── payments/                   # Outgoing payments
├── receipts/                   # Incoming receipts
│
├── templates/                  # Django HTML templates
│   ├── base/base.html          # Base layout
│   ├── authentication_templates/
│   ├── home_templates/
│   ├── items_templates/
│   ├── parties_templates/
│   ├── sale_templates/
│   ├── purchase_templates/
│   ├── sale_return_templates/
│   ├── purchase_return_templates/
│   ├── payments_templates/
│   ├── receipts_templates/
│   └── display_report_templates/
│
├── requirements.txt
├── manage.py
└── .gitignore
```

---

## 🔑 Permission System

Permissions are seeded via Django migrations. Each module defines its own set of permissions:

```python
# Example – Sales Permissions Migration
permissions = [
    ("view_sale",   "Can View Sale Invoices"),
    ("add_sale",    "Can Create Sale Invoices"),
    ("change_sale", "Can Edit Sale Invoices"),
    ("delete_sale", "Can Delete Sale Invoices"),
]
```

Every view enforces permission checks:
```python
@login_required
def sales(request):
    if not request.user.has_perm("auth.view_sale"):
        messages.error(request, "You do not have permission to View Sale Invoices.")
        return redirect("home:home")
```

Modules with dedicated permissions: `Payments`, `Receipts`, `Purchase`, `Sale`, `Purchase Return`, `Sale Return`, `Items`, `Parties`, `Accounts Reports`, `Stock Reports`, `Profit Reports`.

---

## 🌐 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET/POST` | `/auth/login/` | User authentication |
| `POST` | `/auth/logout/` | Session logout |
| `GET` | `/auth/current/user/` | Logged-in user info |
| `GET` | `/api/cash/` | Current cash balance |
| `GET` | `/api/parties/` | Party list |
| `GET` | `/api/items/` | Item list |
| `GET` | `/api/party-balances/` | Receivables & payables |
| `GET` | `/items/autocomplete-item/` | Item search autocomplete |
| `GET/POST` | `/sale/sales/` | Sale invoice CRUD |
| `GET` | `/sale/get-sale/` | Fetch specific invoice |
| `GET` | `/sale/get-sale-summary/` | Sales summary |
| `GET/POST` | `/purchase/` | Purchase invoice CRUD |
| `GET/POST` | `/payments/payment/` | Record payment |
| `GET` | `/payments/get-old-payments/` | Payment history |
| `GET/POST` | `/receipts/receipt/` | Record receipt |
| `GET` | `/receipts/get-old-receipts/` | Receipt history |

---

## 🗄️ Database Design

All business logic lives in the **PostgreSQL layer** through stored functions and triggers. Django views simply call these functions via `connection.cursor()`:

```python
with connection.cursor() as cursor:
    cursor.execute("SELECT * FROM create_sale_invoice(%s, %s, %s)", [party, date, items])
    result = cursor.fetchone()
```

**Key Database Objects:**

| Type | Count | Examples |
|------|-------|---------|
| Tables | 18 | ChartOfAccounts, Parties, Items, Sale, Purchase... |
| Stored Functions | 40+ | `create_sale_invoice()`, `process_purchase_return()` |
| Triggers | 10+ | Auto journal entries, stock updates |
| Views | 5+ | Stock summary, party balances, profit views |

> 📖 See the **ERP-System (Database)** repository for complete schema documentation.

---

## ☁️ Deployment

```
AWS EC2 Instance
│
├── Ubuntu Server
│   ├── Nginx             → Port 80/443, static files, reverse proxy
│   ├── Gunicorn          → WSGI server, Unix socket
│   ├── Django App        → Application code
│   └── PostgreSQL        → Database server
│
└── Security Group        → Inbound: 22 (SSH), 80 (HTTP), 443 (HTTPS)
```

**Nginx → Gunicorn communication** is handled via Unix socket for optimal performance.

---

## 🚀 Getting Started

### Prerequisites
- Python 3.x
- PostgreSQL 14+
- pip

### Installation

```bash
# 1. Clone the repository
git clone <repo-url>
cd Accounting-Plus-Inventory-System

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate    # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your PostgreSQL credentials and Django secret key

# 5. Set up the database
# Run the SQL schema from the ERP-System (Database) repo first
# Then apply Django migrations
python manage.py migrate

# 6. Run the development server
python manage.py runserver
```

### Environment Variables (`.env`)

```env
SECRET_KEY=your_django secret key
DEBUG=True

# Database
DB_NAME=db_name
DB_USER=db_user
DB_PASSWORD=db_password
DB_HOST=localhost
DB_PORT=5432

```

---

## 🔗 Related Repository

> 📦 **[ERP-System (Database)](../ERP-System)** — Contains the complete PostgreSQL schema, stored functions, triggers, ER diagrams, execution flow diagrams, and database documentation.

---

<div align="center">

**Built with ❤️ using Django & PostgreSQL**

</div>
